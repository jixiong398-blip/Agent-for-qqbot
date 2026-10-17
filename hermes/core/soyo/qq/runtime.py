# SPDX-License-Identifier: GPL-3.0-only
"""OneBot transport -> durable Soyo channel -> real native DSH host.

The model/agent loop lives in DSH, not in this process. No Hermes import,
ambient judgment, catch-up, token streaming, or implicit send retry.
"""
from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import logging
import os
import signal
import stat
import subprocess
import time
import hashlib
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
import websockets
from soyo.platform import assert_private, is_root, uid
from soyo.transport import private_client

from . import CatchupPolicy, CatchupRunner, ChannelConfig, ChannelRoute, HistoryPage, PortResult, SoyoQQChannel
from .contracts import InboundEnvelope, qq_id
from .inbound import parse_message
from .journal import SoyoQQJournal
from .native_memory import call as memory_call, record
from .native_tools import call as native_tool_call


log = logging.getLogger("soyo.qq.native")


def private_config(path):
    path = Path(path)
    assert_private(path, max_bytes=2 * 1024 * 1024)
    config = json.loads(path.read_text(encoding="utf-8"))
    if not qq_id(config["account_id"]):
        raise ValueError("account missing")
    for field, scheme in [("http_url", "http"), ("ws_url", "ws")]:
        url = urlsplit(config[field])
        if (url.scheme != scheme or url.hostname != "127.0.0.1" or not url.port
                or url.username or url.password or url.query or url.fragment):
            raise ValueError("OneBot endpoints must be explicit clean loopback URLs")
    for field in ("media_root", "tool_script", "media_script", "publication_root"):
        if field in config and config[field] and not Path(config[field]).is_absolute():
            raise ValueError("explicit absolute deployment paths required")
    return config


class NapCat:
    def __init__(self, config):
        self.config = config
        self.client = httpx.Client(base_url=config["http_url"], trust_env=False,
            timeout=15, headers={"Authorization": "Bearer " + config["onebot_token"]})

    def action(self, action, params=None):
        response = self.client.post("/" + action, json=params or {})
        response.raise_for_status()
        if len(response.content) > 8 * 1024 * 1024:
            raise ValueError("OneBot response too large")
        return response.json()

    def read(self, action, params=None):
        if action not in {"get_login_info", "get_group_list", "get_group_member_list", "get_friend_list", "get_group_msg_history"}:
            raise ValueError("unsupported read action")
        body = self.action(action, params)
        if body.get("retcode") != 0:
            raise ValueError("OneBot read rejected")
        return body["data"]

    def send(self, plan):
        if plan.action not in {"send_group_msg", "send_private_msg"}:
            raise ValueError("unsupported send")
        # Exactly one attempt; the caller has already fsynced its fence.
        return self.action(plan.action, dict(plan.params))

    def routes(self):
        if qq_id(self.read("get_login_info").get("user_id")) != self.config["account_id"]:
            raise ValueError("NapCat login identity mismatch")
        routes = []
        self.names = {}
        allow = set(self.config.get("allowed_users", []))
        block = set(self.config.get("blocked_users", []))
        for group in self.read("get_group_list"):
            gid = qq_id(group.get("group_id"))
            if not gid:
                continue
            try:
                members = {qq_id(row.get("user_id")) for row in self.read("get_group_member_list", {"group_id": int(gid)})}
            except Exception:
                log.warning("Group membership unavailable; route not admitted")
                continue
            members.discard("")
            members -= block
            if allow:
                members &= allow
            routes.append(ChannelRoute("qq-group-" + gid, "group", gid, self.config["account_id"], frozenset(members)))
            self.names["qq-group-" + gid] = str(group.get("group_name") or gid)[:80]
        friend_rows = self.read("get_friend_list")
        friends = {qq_id(item.get("user_id")) for item in friend_rows}
        friend_names = {qq_id(item.get("user_id")): str(item.get("remark") or item.get("nickname") or item.get("user_id"))[:80] for item in friend_rows}
        friends.update(self.config.get("memory_private_peers", []))
        for peer in friends - block - {"", self.config["account_id"]}:
            if not allow or peer in allow:
                routes.append(ChannelRoute("qq-private-" + peer, "private", peer, self.config["account_id"]))
                self.names["qq-private-" + peer] = friend_names.get(peer, peer)
        return routes


class NapCatHistory:
    """Bounded reconnect history adapter; historical rows never wake a turn."""

    def __init__(self, napcat):
        self.napcat = napcat

    def get_history_page(self, route, *, since, cursor, limit):
        if route.message_type != "group":
            return HistoryPage(events=(), next_cursor=None, complete=True)
        params = {"group_id": int(route.target_id), "count": min(100, int(limit))}
        if cursor:
            try:
                params["message_seq"] = int(cursor)
            except (TypeError, ValueError):
                return HistoryPage(events=(), next_cursor=None, complete=False)
        try:
            data = self.napcat.read("get_group_msg_history", params)
        except Exception:
            return HistoryPage(events=(), next_cursor=None, complete=False)
        messages = data.get("messages", data) if isinstance(data, dict) else data
        if not isinstance(messages, list):
            return HistoryPage(events=(), next_cursor=None, complete=False)
        # OneBot history implementations differ in cursor fields.  The
        # runner treats a missing cursor as a complete bounded page.
        next_cursor = None
        if len(messages) >= params["count"] and messages:
            last = messages[0] if isinstance(messages[0], dict) else {}
            value = last.get("message_id") or last.get("message_seq")
            next_cursor = str(value) if value else None
        return HistoryPage(events=messages, next_cursor=next_cursor, complete=next_cursor is None)


def _forward_segment_text(segment: dict) -> str:
    if not isinstance(segment, dict):
        return ""
    kind = str(segment.get("type") or "")
    data = segment.get("data") if isinstance(segment.get("data"), dict) else {}
    if kind == "text":
        return str(data.get("text") or "")
    if kind == "at":
        return "@" + str(data.get("qq") or data.get("user_id") or "")
    if kind:
        return "[" + kind + "]"
    return ""


def resolve_forward_context(config, envelope: dict) -> dict:
    from .forward_context import resolve
    return resolve(config, envelope, native_tool_call)


def resolve_reply_context(config, envelope: dict) -> dict:
    reply_id = str(envelope.get("reply_to") or "")
    if not reply_id:
        return {"state": "not_requested"}
    try:
        result = native_tool_call(config, {"action": "get_msg", "params": {"message_id": reply_id},
            "reply_lookup": True, "route_id": envelope["route_id"], "sender_id": envelope["sender_id"],
            "scene_target_id": envelope["target_id"], "scene_event_id": envelope["event_id"],
            "message_type": envelope.get("message_type")})
        if not result.get("success"):
            return {"state": "unavailable", "message_id": reply_id, "reason": str(result.get("error") or "read_rejected")[:160]}
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        parsed = parse_message(data.get("message") or data.get("raw_message") or "")
        text = parsed.text_with_media.strip()[:8000]
        if not text:
            return {"state": "unavailable", "message_id": reply_id, "reason": "quoted_message_has_no_text"}
        sender = data.get("sender") if isinstance(data.get("sender"), dict) else {}
        return {"state": "resolved", "kind": "platform", "message_id": reply_id,
            "sender_id": str(sender.get("user_id") or data.get("user_id") or ""),
            "sender_name": str(sender.get("card") or sender.get("nickname") or "")[:120],
            "text": text, "media": [item.as_dict() for item in parsed.media[:8]]}
    except Exception as error:
        return {"state": "unavailable", "message_id": reply_id, "reason": type(error).__name__}


class NativeHost:
    def __init__(self, config):
        self.config = config
        self.client = private_client(config, timeout=httpx.Timeout(180.0, connect=10.0, write=10.0, pool=10.0))

    def request(self, path, body=None):
        response = self.client.post(path, json=body or {})
        response.raise_for_status()
        value = response.json()
        return value

    def post_event(self, envelope):
        record(self.config, envelope)
        try:
            memory_call(self.config, {**envelope, "action": "record_turn", "role": "user",
                "content": envelope.get("text", ""), "session_id": envelope.get("route_id", ""),
                "route_id": envelope["route_id"], "sender_id": envelope["sender_id"],
                "message_type": envelope.get("message_type")})
        except Exception:
            log.warning("Native user turn memory record deferred")
        try:
            memory_call(self.config, {**envelope, "action": "social_event",
                                      "mentioned": bool(envelope.get("mentioned_account_ids")),
                                      "route_id": envelope["route_id"], "sender_id": envelope["sender_id"],
                                      "message_type": envelope.get("message_type")})
        except Exception:
            pass
        args = dict(envelope, action="context")
        context = memory_call(self.config, args)
        if context.get("reply_context", {}).get("state") not in {"resolved", "recalled"}:
            context["reply_context"] = resolve_reply_context(self.config, envelope)
        context["forward_context"] = resolve_forward_context(self.config, envelope)
        if context["forward_context"].get("state") != "not_requested":
            try:
                memory_call(self.config, {"action": "attach_forward", "route_id": envelope["route_id"],
                    "sender_id": envelope["sender_id"], "message_type": envelope.get("message_type"),
                    "event_id": envelope["event_id"], "forward_context": context["forward_context"]})
            except Exception:
                log.warning("Native forward context persistence deferred")
        # The QQ adapter speaks the same normalized channel API as the
        # character runtime.  The private legacy aliases remain available for
        # recovery, but new input goes through the canonical event resource.
        result = self.request("/v1/channels/qq/events", {"envelope": envelope, "context": context})
        return PortResult(result["kind"], payload={key: value for key, value in result.items() if key != "kind"})

    def register_routes(self, routes, names):
        return self.request("/routes", {"routes": [{"route_id": row.route_id, "message_type": row.message_type,
            "target_id": row.target_id, "name": names.get(row.route_id, row.target_id),
            "members": sorted(row.allowed_sender_ids)} for row in routes]})

    def observe(self, envelope):
        record(self.config, envelope)
        return self.request("/observe", {"envelope": envelope})

    def claim_outbox(self, *, wait_seconds=0):
        result = self.request("/v1/channels/qq/outbox")
        return PortResult("items", payload={"items": result["items"]})

    def post_receipt(self, publication_id, receipt):
        result = self.request("/v1/channels/qq/outbox/" + quote(str(publication_id), safe="") + "/receipt",
                             {"publication_id": publication_id, "receipt": dict(receipt)})
        return PortResult(result["kind"])


def queue_owner_notification(config, *, event_id: str, text: str) -> None:
    """Queue a deterministic private publication; the QQ worker is the only sender."""
    owner = next((str(value) for value in config.get("admin_ids", config.get("memory_private_peers", [])) if qq_id(value)), "")
    if not owner or not text.strip():
        return
    publication_id = "platform-event-" + hashlib.sha256(str(event_id).encode()).hexdigest()[:40]
    root = Path(config["publication_root"]); root.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = root / (hashlib.sha256(publication_id.encode()).hexdigest() + ".json")
    if path.exists():
        return
    SoyoQQJournal.write_json(path, {"state": "pending", "publication_id": publication_id,
        "attempt_id": publication_id + "-attempt", "kind": "message", "account_id": config["account_id"],
        "route_id": "qq-private-" + owner, "target": {"type": "private", "id": owner},
        "text": text[:5000], "source": "native-platform-event", "event_id": str(event_id)})


def handle_platform_event(config, event: dict) -> None:
    """Persist notices/requests and perform only deployment-owned invite policy."""
    ptype = str(event.get("post_type") or "")
    event_id = str(event.get("request_id") or event.get("message_id") or event.get("time") or hashlib.sha256(json.dumps(event, sort_keys=True).encode()).hexdigest()[:40])
    route = "qq-platform-events"
    memory_call(config, {"action": "platform_event", "route_id": route, "sender_id": str(event.get("user_id") or config["account_id"]), "event": event})
    if ptype == "request":
        request_type, sub_type = str(event.get("request_type") or ""), str(event.get("sub_type") or "")
        flag, inviter, group_id = str(event.get("flag") or ""), qq_id(event.get("user_id")), qq_id(event.get("group_id"))
        if request_type == "group" and sub_type == "invite" and flag and group_id:
            admins = {str(value) for value in config.get("admin_ids", config.get("memory_private_peers", []))}
            if inviter in admins and config.get("auto_approve_admin_invites", False):
                native_tool_call(config, {"action": "set_group_add_request", "params": {"flag": flag, "sub_type": "invite", "approve": True}, "sender_id": inviter, "route_id": route})
            else:
                queue_owner_notification(config, event_id=event_id, text=f"[加群邀请] QQ {inviter or '未知'} 邀请我加入群 {group_id}。请在 owner 会话确认同意或拒绝；不会因普通正文自动获得权限。")
        elif request_type == "friend":
            queue_owner_notification(config, event_id=event_id, text=f"[好友请求] 收到 QQ {inviter or '未知'} 的好友请求。请在 owner 会话确认；不会自动同意。")
    elif ptype == "notice":
        notice = str(event.get("notice_type") or "")
        if notice == "group_increase":
            # Membership churn is an observed platform fact, not an owner
            # notification. Invites/friend requests are actionable; joins are
            # visible in the native events pane and remain silent by default.
            return
        elif notice == "group_recall":
            # The event is retained/flagged in the native corpus; no model wake.
            return


def other_gateway_idle(config):
    # A new distribution has no production systemd unit binding. Refuse a live
    # legacy writer instead of inventing one or stopping another user's process.
    unit = config.get("competing_unit")
    if not unit or os.name == "nt":
        import psutil
        for process in psutil.process_iter(["pid", "name"]):
            if process.pid == os.getpid() or "python" not in (process.info["name"] or "").lower():
                continue
            try:
                command = process.cmdline()
                if "hermes_cli.main" in command and "gateway" in command:
                    raise RuntimeError("Legacy Hermes writer is active; stop it explicitly before starting native QQ")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return
    env = os.environ.copy()
    deployment_uid = int(config.get("competing_user_uid", uid()))
    # Direct-root system service still checks the deployment user's old
    # Hermes writer, not root's unrelated user manager.
    env["XDG_RUNTIME_DIR"] = f"/run/user/{deployment_uid}"
    env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{deployment_uid}/bus"
    command = ["systemctl", "--user", "show", unit, "-p", "ActiveState"]
    if is_root() and deployment_uid != 0:
        import pwd
        account = pwd.getpwuid(deployment_uid)
        env["HOME"] = account.pw_dir
        # Recent systemd rejects cross-user --user transport even with the
        # correct socket address. Query as that user; this never starts it.
        command = ["/usr/sbin/runuser", "-u", account.pw_name, "--", *command]
    result = subprocess.run(command,
                            capture_output=True, text=True, timeout=5, check=True, env=env)
    if result.stdout.strip() not in {"ActiveState=inactive", "ActiveState=failed"}:
        raise RuntimeError("Competing Gateway is active or unknown; refusing OneBot writer")


async def serve(config):
    await asyncio.to_thread(other_gateway_idle, config)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT, *((signal.SIGBREAK,) if hasattr(signal, 'SIGBREAK') else ())):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))
    napcat, host = NapCat(config), NativeHost(config)
    transport_connected = False
    routes = await asyncio.to_thread(napcat.routes)
    await asyncio.to_thread(host.request, "/v1/channels/qq/status")
    await asyncio.to_thread(host.register_routes, routes, napcat.names)
    log.info("DSH QQ admission: mention-only; final-only; authorized routes=%d", len(routes))
    with SoyoQQChannel(config=ChannelConfig(
                           config["account_id"],
                           chunk_delay_seconds=config.get("chunk_delay_seconds", 0.6),
                           reply_part_chars=config.get("reply_part_chars", 1800),
                           max_reply_parts=config.get("max_reply_parts", 64),
                           attachment_root=config.get("media_root", "")),
                       routes=routes,
                       data_root=config["channel_root"]) as channel:
        # Preserve old unsent input as context only, never restart old reply obligations.
        for path in channel.journal.spool_list("inbound"):
            blob = channel.journal.read_json(path)
            envelope = InboundEnvelope.from_dict(blob["envelope"])
            channel.journal.append("inbound_restart_context", {"item": blob})
            channel.journal.finish_inbound(path, envelope, "restart_context_only")

        async def tick():
            refresh = time.monotonic() + 300
            sync = 0
            while not stop.is_set():
                try:
                    # Keep the uncached writer check before every publication
                    # cycle, but never block WebSocket admission on systemd I/O.
                    await asyncio.to_thread(other_gateway_idle, config)
                    for path in channel.journal.spool_list("inbound"):
                        blob = channel.journal.read_json(path)
                        record(config, InboundEnvelope.from_dict(blob["envelope"]).as_dict())
                    await asyncio.to_thread(channel.submit_pending_inbound, host)
                    receipts = await asyncio.to_thread(channel.poll_outbox, host, napcat)
                    for receipt in receipts:
                        log.info("DSH QQ publication outcome=%s", receipt.status)
                    if time.monotonic() >= refresh:
                        current_routes = await asyncio.to_thread(napcat.routes)
                        channel.replace_routes(current_routes)
                        await asyncio.to_thread(host.register_routes, current_routes, napcat.names)
                        refresh = time.monotonic() + 300
                    if time.monotonic() >= sync:
                        await asyncio.to_thread(host.request, "/sync")
                        sync = time.monotonic() + 10
                    health = channel.health_snapshot()
                    SoyoQQJournal.write_json(Path(config["status_file"]), {
                        "backend": "dsh", "state": "connected" if transport_connected else "connecting", "updated_at": time.time(),
                        "mention_only": True, "final_only": True, "routes": len(channel.routes),
                        "counters": {k: v for k, v in health.items() if k.startswith(("inbound_", "outbox_"))}})
                except RuntimeError:
                    stop.set()
                    raise
                except Exception as error:
                    log.warning("DSH boundary not ready (%s); no unfenced retry", type(error).__name__)
                try:
                    await asyncio.wait_for(stop.wait(), 0.4)
                except TimeoutError:
                    pass

        ticker = asyncio.create_task(tick())
        catchup_done = False
        try:
            while not stop.is_set():
                await asyncio.to_thread(other_gateway_idle, config)
                kwargs = {"open_timeout": 15, "ping_interval": 20, "max_size": 4 * 1024 * 1024}
                signature = inspect.signature(websockets.connect).parameters
                kwargs["additional_headers" if "additional_headers" in signature else "extra_headers"] = {
                    "Authorization": "Bearer " + config["onebot_token"]}
                if "proxy" in signature:
                    kwargs["proxy"] = None
                try:
                    async with websockets.connect(config["ws_url"], **kwargs) as socket:
                        transport_connected = True
                        log.info("DSH OneBot transport connected; no Hermes agent loop")
                        if config.get("catchup_enabled") and not catchup_done:
                            try:
                                policy = CatchupPolicy(
                                    route_ids=tuple(route.route_id for route in routes if route.message_type == "group"),
                                    lookback_hours=float(config.get("catchup_hours", 1.0)),
                                )
                                totals = await asyncio.to_thread(CatchupRunner(channel, policy).run, NapCatHistory(napcat))
                                catchup_done = True
                                log.info("DSH QQ bounded historical context catch-up: %s", totals)
                                await asyncio.to_thread(host.request, "/sync")
                            except Exception as error:
                                log.warning("QQ historical context catch-up deferred (%s)", type(error).__name__)
                        while not stop.is_set():
                            try:
                                raw = await asyncio.wait_for(socket.recv(), 1)
                            except TimeoutError:
                                continue
                            event = json.loads(raw)
                            if event.get("post_type") != "message":
                                try:
                                    await asyncio.to_thread(handle_platform_event, config, event)
                                except Exception:
                                    log.warning("Platform event was not persisted")
                                continue
                            decision = await asyncio.to_thread(channel.ingest_onebot_event, event)
                            if decision.accepted:
                                # Corpus durability is independent of the UI projection; no recall here.
                                await asyncio.to_thread(record, config, decision.envelope.as_dict())
                                try:
                                    await asyncio.to_thread(host.request, "/observe", {"envelope": decision.envelope.as_dict()})
                                except httpx.HTTPError:
                                    log.warning("Native source projection deferred; durable corpus retained")
                except Exception as error:
                    transport_connected = False
                    log.warning("OneBot disconnected (%s); reconnect without history replay", type(error).__name__)
                    try:
                        await asyncio.wait_for(stop.wait(), 3)
                    except TimeoutError:
                        pass
        finally:
            stop.set()
            await ticker
            napcat.client.close()
            host.client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    config = private_config(args.config)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.preflight:
        napcat, host = NapCat(config), NativeHost(config)
        try:
            routes = napcat.routes()
            native = host.request("/health")
            print(json.dumps({"napcat_identity_verified": True, "authorized_routes": len(routes),
                              "native": native, "ws_opened": False, "qq_sends": 0}))
        finally:
            napcat.client.close()
            host.client.close()
    else:
        from soyo.platform import file_lock, protect
        cache = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".cache"))) / "Agent-for-qqbot" / "writer-locks"
        cache.mkdir(parents=True, mode=0o700, exist_ok=True); protect(cache, directory=True)
        lock = cache / (hashlib.sha256(config["account_id"].encode("ascii")).hexdigest() + ".lock")
        with file_lock(lock, blocking=False):
            asyncio.run(serve(config))


if __name__ == "__main__":
    main()
