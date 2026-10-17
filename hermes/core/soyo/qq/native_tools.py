# SPDX-License-Identifier: GPL-3.0-only
"""Explicit NapCat capability bridge for the native DSH QQ worker.

This file intentionally does not import Hermes' registry or adapter singleton.
The host supplies the deployment-owned config and the current trusted actor;
the action allowlist and owner check are enforced here before any HTTP side
effect.  Model text can request an action, but cannot change the account,
route, or authorization source.
"""
from __future__ import annotations

import json
import math
import os
import stat
import time
import sqlite3
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

import httpx
from soyo.platform import assert_private, is_root, uid


READ_ACTIONS = frozenset({
    "get_status", "get_login_info", "get_group_list", "get_group_info",
    "get_group_member_list", "get_group_member_info", "get_friend_list",
    "get_stranger_info", "get_msg", "get_group_msg_history",
    "get_group_system_msg", "get_group_notice", "get_group_at_all_remain",
    "get_version_info", "get_group_list", "get_online_clients", "get_forward_msg", "_get_group_notice",
})
NORMAL_ACTIONS = frozenset({
    "send_like", "send_poke", "send_group_sign", "send_group_poke",
    "set_msg_emoji_like", "get_file", "get_image", "get_record",
})
ADMIN_ACTIONS = frozenset({
    "set_group_ban", "set_group_kick", "set_group_admin", "set_group_card",
    "set_group_name", "set_group_leave", "_del_group_notice", "_send_group_notice",
    "_set_group_notice", "set_group_portrait", "set_profile",
    "set_online_status", "set_self_longnick", "set_qq_avatar", "delete_msg", "upload_group_file",
    "set_essence_msg", "delete_essence_msg", "send_group_forward_msg",
    "send_private_forward_msg", "forward_group_single_msg",
    "forward_friend_single_msg", "set_group_add_request",
})
ALL_ACTIONS = READ_ACTIONS | NORMAL_ACTIONS | ADMIN_ACTIONS


def _id(value: Any) -> str:
    text = str(value or "").strip()
    return text if text.isascii() and text.isdigit() and 1 <= len(text) <= 20 else ""


def _private_file(path: str) -> Path:
    value = Path(path)
    if not value.is_absolute() or value.is_symlink():
        raise ValueError("private path required")
    assert_private(value)
    return value


def _config(config: Mapping[str, Any]) -> tuple[str, str, str]:
    account = _id(config.get("account_id"))
    base = str(config.get("http_url") or "").rstrip("/")
    token = str(config.get("onebot_token") or "")
    parsed = urlsplit(base)
    if not account or parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port:
        raise ValueError("OneBot endpoint is not an explicit loopback URL")
    if not token or len(token) > 256:
        raise ValueError("OneBot credential unavailable")
    return account, base, token


def _safe_params(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or len(value) > 32:
        raise ValueError("bounded action parameters required")
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if len(encoded) > 32 * 1024:
        raise ValueError("action parameters too large")
    return dict(value)


def _owner_ids(config: Mapping[str, Any]) -> set[str]:
    values = config.get("admin_ids") or config.get("memory_private_peers") or []
    if isinstance(values, str):
        values = values.split(",")
    return {_id(value) for value in values if _id(value)}


def _owner_group_ids(config: Mapping[str, Any]) -> set[str]:
    values = config.get("owner_group_ids") or []
    if isinstance(values, str):
        values = values.split(",")
    return {_id(value) for value in values if _id(value)}


def _owner_actor(config: Mapping[str, Any], args: Mapping[str, Any]) -> bool:
    sender = _id(args.get("sender_id"))
    if sender not in _owner_ids(config):
        return False
    message_type = str(args.get("message_type") or "")
    if message_type == "private":
        return True
    if message_type != "group":
        return False
    target = _id(args.get("scene_target_id"))
    route = str(args.get("route_id") or "")
    return bool(target and target in _owner_group_ids(config) and route == "qq-group-" + target)


def _message_in_scene(config: Mapping[str, Any], route: str, message_id: str) -> bool:
    """Check the bounded native corpus/outbound index before a read-back."""
    path = Path(str(config.get("corpus_db") or ""))
    if not path.is_absolute() or not path.is_file():
        return False
    try:
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            inbound = db.execute(
                "SELECT 1 FROM messages WHERE route=? AND json_extract(body,'$.event_id')=? LIMIT 1",
                (route, message_id),
            ).fetchone()
            outbound = db.execute(
                "SELECT 1 FROM outbound_messages WHERE route=? AND platform_message_id=? LIMIT 1",
                (route, message_id),
            ).fetchone()
        return bool(inbound or outbound)
    except sqlite3.Error:
        return False


def _call(config: Mapping[str, Any], action: str, params: Mapping[str, Any]) -> dict[str, Any]:
    account, base, token = _config(config)
    if action not in ALL_ACTIONS:
        return {"success": False, "error": "action_not_allowlisted", "action": action}
    body = _safe_params(params)
    timeout = float(config.get('onebot_action_timeout_seconds', 20))
    if not math.isfinite(timeout) or timeout <= 0: raise ValueError('finite OneBot request budget required')
    with httpx.Client(base_url=base, trust_env=False, timeout=min(20, timeout),
                      headers={"Authorization": "Bearer " + token}) as client:
        response = client.post("/" + action, json=body)
        response.raise_for_status()
        if len(response.content) > 8 * 1024 * 1024:
            raise ValueError("OneBot response too large")
        result = response.json()
    if not isinstance(result, Mapping) or result.get("retcode") != 0:
        return {"success": False, "action": action,
                "error": str((result or {}).get("message", (result or {}).get("msg", "onebot_rejected")))[:240]}
    return {"success": True, "action": action, "account_id": account,
            "data": result.get("data", {})}


def call(config: Mapping[str, Any], args: Mapping[str, Any]) -> dict[str, Any]:
    action = str(args.get("action") or "").strip()
    params = _safe_params(args.get("params") or {})
    sender = _id(args.get("sender_id"))
    route = str(args.get("route_id") or "")
    owner = _owner_actor(config, args)
    privileged = owner and args.get("message_type") == "private"
    group_owner = owner and args.get("message_type") == "group"
    if args.get("operation") == "capabilities":
        if not privileged:
            return {"success": True, "state": "observed", "route_id": route,
                    "owner": owner, "owner_private": False,
                    "group_admin": group_owner,
                    "note": "详细 DSH 私聊权限矩阵仅在 owner 私聊中可查看；群内 owner 只显示当前受限群/root边界",
                    "qq": {"current_scene_read": True, "group_management": group_owner, "ordinary_text_send": False},
                    "dsh": {"gpt_consult": False, "schedule": False, "action_brain": group_owner, "peer": False},
                    "host": {"root": group_owner, "arbitrary_shell": group_owner},
                    "external": {"arbitrary_shell": group_owner}}
        return {"success": True, "state": "observed", "route_id": route,
                "actor": sender, "owner": owner, "owner_private": privileged,
                "group_admin": owner and args.get("message_type") == "group",
                "qq": {"read_current_scene": True, "read_forward_refs": True,
                       "read_other_scenes": owner, "low_impact_interaction": True,
                       "management": owner, "upload_media": owner,
                       "ordinary_text_send": False, "final_publication_only": True},
                "dsh": {"memory_scene": True, "legacy_recall": privileged,
                        "gpt_consult": privileged and args.get("message_type") == "private",
                        "schedule": owner and args.get("message_type") == "private",
                        "action_brain": owner and args.get("message_type") == "private",
                        "peer": owner and args.get("message_type") == "private",
                        "agent_line": False},
                "host": {"mode": "direct-root" if config.get("direct_root") and is_root() else "user",
                         "effective_uid": uid(), "native_tools": ["bash", "read", "write", "edit", "glob", "grep"]},
                "external": {"qzone": False, "feishu": False,
                             "host_restart": bool(config.get("direct_root") and is_root()),
                             "arbitrary_shell": bool(config.get("direct_root") and is_root())}}
    if args.get("operation") == "profile":
        if not owner: return {"success": False, "error": "owner_grant_required"}
        field, value = str(args.get("field") or ""), str(args.get("value") or "")
        mapping = {"longnick": ("set_self_longnick", {"longNick": value[:80]}),
                   "online_status": ("set_online_status", {"status": value, "ext_status": 0, "battery_status": 0})}
        if field == "avatar":
            mapping[field] = ("set_qq_avatar", {"file": value})
        if field not in mapping: return {"success": False, "error": "unsupported_profile_field"}
        action, params = mapping[field]
        return _call(config, action, params)
    if args.get("operation") == "invite_approve":
        if not owner: return {"success": False, "error": "owner_grant_required"}
        group_id = _id(args.get("group_id")); approve = bool(args.get("approve"))
        if not group_id: return {"success": False, "error": "invalid_group_id"}
        db_path = Path(str(config.get("corpus_db") or ""))
        if not db_path.is_file(): return {"success": False, "error": "event_ledger_unavailable"}
        with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as db:
            rows = db.execute("SELECT payload FROM platform_events WHERE route=? AND event_type='group' ORDER BY id DESC LIMIT 50", ("qq-group-" + group_id,)).fetchall()
        for row in rows:
            event = json.loads(row[0])
            if event.get("request_type") == "group" and event.get("sub_type") == "invite" and event.get("flag"):
                return _call(config, "set_group_add_request", {"flag": str(event["flag"]), "sub_type": "invite", "approve": approve,
                    **({"reason": str(args.get("reason"))[:240]} if not approve and args.get("reason") else {})})
        return {"success": False, "error": "pending_invite_not_found"}
    if args.get("operation") == "read_history":
        if not owner and str(args.get("route_id") or "") != str(args.get("source_route_id") or args.get("route_id") or ""):
            return {"success": False, "error": "history_outside_current_scene"}
        route_id = str(args.get("source_route_id") or args.get("route_id") or "")
        query = str(args.get("query") or "")[:160]; limit = max(1, min(100, int(args.get("limit") or 20)))
        path = Path(str(config.get("corpus_db") or ""))
        if not path.is_file() or not path.is_absolute(): return {"success": False, "error": "corpus_unavailable"}
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            inbound = db.execute(
                "SELECT sender,body,seq AS ordering FROM messages "
                "WHERE route=? AND instr(body,?)>0 ORDER BY seq DESC LIMIT ?",
                (route_id, query, limit),
            ).fetchall()
            outbound = db.execute(
                "SELECT sender,event_id,content,occurred_at,id AS ordering FROM turns "
                "WHERE route=? AND role='assistant' AND (instr(content,?)>0 OR ?='') "
                "ORDER BY occurred_at DESC,id DESC LIMIT ?",
                (route_id, query, query, limit),
            ).fetchall()
        items = []
        for sender_id, raw, ordering in inbound:
            value = json.loads(raw)
            items.append({"role": "user", "sender_id": sender_id,
                          **{key: value for key, value in value.items()
                             if key in {"event_id", "text", "occurred_at", "media"}},
                          "_ordering": float(value.get("occurred_at") or ordering)})
        for sender_id, event_id, content, occurred_at, ordering in outbound:
            items.append({"role": "assistant", "sender_id": sender_id,
                          "event_id": event_id, "text": str(content)[:16000],
                          "occurred_at": occurred_at, "_ordering": float(occurred_at or ordering)})
        items.sort(key=lambda item: (item["_ordering"], item.get("event_id", "")))
        for item in items:
            item.pop("_ordering", None)
        return {"success": True, "operation": "read_history", "route_id": route_id,
                "items": items[-limit:]}
    if args.get("operation") == "forward":
        source_route = str(args.get("source_route_id") or args.get("route_id") or "")
        target_type = str(args.get("target_type") or "group"); target_id = _id(args.get("target_id"))
        if not owner or target_type not in {"group", "private"} or not target_id:
            return {"success": False, "error": "forward_requires_owner_and_bounded_target"}
        limit = max(1, min(100, int(args.get("limit") or 20))); path = Path(str(config.get("corpus_db") or ""))
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            rows = db.execute("SELECT sender,body FROM messages WHERE route=? ORDER BY seq DESC LIMIT ?", (source_route, limit)).fetchall()
        nodes = []
        for sender_id, raw in reversed(rows):
            value = json.loads(raw); text = str(value.get("text") or "")[:5000]
            if not text: continue
            nodes.append({"type": "node", "data": {"nickname": str(sender_id), "content": [{"type": "text", "data": {"text": text}}]}})
        if not nodes: return {"success": False, "error": "no_forwardable_native_messages"}
        action = "send_group_forward_msg" if target_type == "group" else "send_private_forward_msg"
        return _call(config, action, {"group_id" if target_type == "group" else "user_id": int(target_id), "messages": nodes})
    if args.get("operation") == "forward_single":
        if not owner: return {"success": False, "error": "forward_requires_owner_grant"}
        message_id = str(args.get("message_id") or "").strip(); target_type = str(args.get("target_type") or "group"); target_id = _id(args.get("target_id"))
        if not message_id or target_type not in {"group", "private"} or not target_id: return {"success": False, "error": "bounded_forward_target_required"}
        action = "forward_group_single_msg" if target_type == "group" else "forward_friend_single_msg"
        return _call(config, action, {"group_id" if target_type == "group" else "user_id": int(target_id), "message_id": message_id})
    if action in {"send_group_forward_msg", "send_private_forward_msg", "forward_group_single_msg", "forward_friend_single_msg"}:
        return {"success": False, "error": "final_only_forward_publication_not_migrated", "action": action}
    scene_target = _id(args.get("scene_target_id"))
    scene_event = str(args.get("scene_event_id") or "")
    for key in ("group_id", "user_id"):
        target = _id(params.get(key)) if key in params else ""
        if key in params and not target:
            return {"success": False, "error": "invalid_target_id", "action": action}
        if target and not owner and scene_target and target != scene_target:
            return {"success": False, "error": "target_outside_current_scene", "action": action}
    if action in {"get_group_list", "get_friend_list", "get_online_clients", "get_version_info"} and not owner:
        return {"success": False, "error": "owner_read_grant_required", "action": action}
    reply_lookup = bool(args.get("reply_lookup"))
    if action == "get_msg" and not owner:
        message_id = str(params.get("message_id") or "")
        # The current message is always in scope. A quoted target may be read
        # only when the native ledger already proves it belongs to this scene;
        # callers cannot turn this into an arbitrary QQ history reader.
        if message_id != scene_event and not _message_in_scene(config, route, message_id) and not reply_lookup:
            return {"success": False, "error": "message_outside_current_scene", "action": action}
    if action == "get_forward_msg" and not owner:
        allowed_refs = {str(value) for value in (args.get("forward_refs") or [])}
        if str(params.get("message_id") or "") not in allowed_refs:
            return {"success": False, "error": "forward_outside_current_scene", "action": action}
    if action in {"set_msg_emoji_like", "set_essence_msg", "delete_essence_msg"} and not owner:
        message_id = str(params.get("message_id") or "")
        if message_id != scene_event and not _message_in_scene(config, route, message_id):
            return {"success": False, "error": "message_outside_current_scene", "action": action}
    if action in ADMIN_ACTIONS and not owner:
        return {"success": False, "error": "admin_grant_required", "action": action,
                "route_id": route, "sender_id": sender}
    if action in {"set_group_leave", "set_profile", "set_online_status"} and sender not in _owner_ids(config):
        return {"success": False, "error": "owner_grant_required", "action": action}
    if action == "upload_group_file":
        root = Path(str(config.get("media_root") or "")).resolve()
        raw_path = Path(str(params.get("file") or ""))
        if not raw_path.is_absolute() or raw_path.is_symlink() or not raw_path.is_file():
            return {"success": False, "error": "artifact_required", "action": action}
        try:
            raw_path.resolve().relative_to(root)
        except ValueError:
            return {"success": False, "error": "artifact_outside_media_root", "action": action}
    if "file" in params and action in {"set_group_portrait", "set_profile", "upload_group_file"}:
        path_value = Path(str(params.get("file") or "")).resolve(); root = Path(str(config.get("media_root") or "")).resolve()
        try: path_value.relative_to(root)
        except ValueError: return {"success": False, "error": "artifact_outside_media_root", "action": action}
        if not path_value.is_file() or path_value.is_symlink(): return {"success": False, "error": "artifact_required", "action": action}
    if action in {"get_file", "get_image", "get_record"} and not owner:
        return {"success": False, "error": "use_admitted_media_only", "action": action}
    result = _call(config, action, params)
    if action == "get_msg" and reply_lookup and not owner and result.get("success"):
        data = result.get("data") if isinstance(result.get("data"), Mapping) else {}
        same_group = args.get("message_type") == "group" and _id(data.get("group_id")) == scene_target
        same_private = args.get("message_type") == "private" and _id(data.get("user_id")) in {sender, scene_target, _id(config.get("account_id"))}
        if not (same_group or same_private):
            return {"success": False, "error": "message_outside_current_scene", "action": action}
    result["route_id"] = route
    result["actor"] = sender
    return result


def read_media(config: Mapping[str, Any], args: Mapping[str, Any]) -> dict[str, Any]:
    """Fetch a bounded image/record reference through NapCat for the host.

    The function only writes beneath the deployment-owned media root and
    returns metadata; it never exposes OneBot credentials or arbitrary paths.
    """
    _, base, token = _config(config)
    ref = str(args.get("ref") or "").strip()
    kind = str(args.get("kind") or "image").strip().lower()
    if not ref or len(ref) > 2048 or kind not in {"image", "record", "video"}:
        raise ValueError("bounded media reference required")
    max_bytes = int(config.get("max_media_bytes", 20 * 1024 * 1024))
    action = {"image": "get_image", "record": "get_record", "video": "get_file"}[kind]
    url = ref
    if urlsplit(ref).scheme not in {"http", "https"}:
        with httpx.Client(base_url=base, trust_env=False, timeout=15,
                          headers={"Authorization": "Bearer " + token}) as client:
            response = client.post("/" + action, json={"file": ref})
            response.raise_for_status()
            result = response.json()
            if result.get("retcode") != 0:
                return {"ok": False, "error": "media_reference_rejected"}
            data = result.get("data") or {}
            url = str(data.get("url") or data.get("file") or "")
    parsed = urlsplit(url)
    allowed_domains = tuple(config.get("media_url_domains") or ["qpic.cn", "qq.com", "gtimg.cn", "gtimg.com", "multimedia.nt.qq.com.cn"])
    host = (parsed.hostname or "").lower()
    if (parsed.scheme not in {"http", "https"} or parsed.username or parsed.password
            or not any(host == domain or host.endswith("." + domain) for domain in allowed_domains)):
        return {"ok": False, "error": "media_url_not_authorized"}
    # An external image server must never receive the OneBot Bearer token.
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=20) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            if int(response.headers.get("content-length") or 0) > max_bytes:
                raise ValueError("media exceeds bounded size")
            content_type = str(response.headers.get("content-type") or "").split(";", 1)[0].lower()
            chunks, size = [], 0
            for chunk in response.iter_bytes(64 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError("media exceeds bounded size")
                chunks.append(chunk)
            content = b"".join(chunks)
    root = Path(str(config.get("media_root") or ""))
    if not root.is_absolute() or root.is_symlink():
        raise ValueError("media root unavailable")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    import hashlib
    digest = hashlib.sha256(content).hexdigest()
    suffix = ".bin"
    suffixes = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif",
                "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "video/mp4": ".mp4"}
    suffix = suffixes.get(content_type, suffix)
    path = root / (digest + suffix)
    if not path.exists():
        path.write_bytes(content)
        path.chmod(0o600)
    return {"ok": True, "kind": kind, "path": str(path), "bytes": len(content),
            "media_type": content_type or "application/octet-stream", "sha256": digest,
            "name": Path(urlsplit(url).path).name[:120]}


if __name__ == "__main__":
    from soyo.platform import load_private_json
    config = load_private_json(Path(os.environ["SOYO_CONFIG_FILE"]))
    request = json.loads(os.sys.stdin.buffer.read(128 * 1024))
    if request.get("op") == "media":
        result = read_media(config, request)
    else:
        result = call(config, request)
    print(json.dumps(result, ensure_ascii=False))
