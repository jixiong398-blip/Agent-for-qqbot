"""Local contracts hardened after the native DSH boundary probes."""

from __future__ import annotations

import sqlite3
from pathlib import Path
import pytest

from soyo.qq import ChannelRoute, OutboundIntent, build_outbound_plans, split_reply_text
from soyo.qq.native_memory import call, record
from soyo.qq import ChannelConfig, OutboxClaim, PortResult, SoyoQQChannel, OutboundPlanError


def _config(tmp_path: Path) -> dict:
    return {
        "corpus_db": str(tmp_path / "corpus.db"),
        "legacy_memory_db": str(tmp_path / "legacy.db"),
        "memory_private_peers": ["100001"],
    }


def test_native_reply_split_is_bounded_and_keeps_each_nonempty_line():
    parts = split_reply_text("第一段\n\n第二段\n" + "长" * 2000, max_chars=180, max_parts=64)
    assert parts[:2] == ["第一段", "第二段"]
    assert len(parts) <= 64
    assert all(0 < len(part) <= 180 for part in parts)


def test_native_context_never_ambiently_reads_legacy(tmp_path: Path):
    config = _config(tmp_path)
    envelope = {"route_id": "qq-private-100001", "event_id": "e1", "sender_id": "100001",
                "text": "scene fact", "occurred_at": 100.0, "mentioned_account_ids": []}
    record(config, envelope)
    with sqlite3.connect(config["legacy_memory_db"]) as db:
        db.executescript("CREATE TABLE long_term_entries (key TEXT, value TEXT, active INTEGER, updated_at REAL)")
        db.execute("INSERT INTO long_term_entries VALUES ('private-secret','must not be ambient',1,100)")
    ambient = call({**config, "memory_private_peers": ["100001"]},
                   {**envelope, "action": "context", "message_type": "private"})
    assert ambient["legacy"] == []
    explicit = call({**config, "memory_private_peers": ["100001"]},
                    {**envelope, "action": "recall", "message_type": "private", "query": "private-secret"})
    assert explicit["legacy"][0]["origin"] == "legacy_read_only"


def test_native_context_exposes_recent_generated_replies_without_marking_them_delivered(tmp_path: Path):
    config = _config(tmp_path)
    envelope = {"route_id": "qq-private-100001", "event_id": "current", "sender_id": "100001",
                "text": "能看到你上一条吗", "occurred_at": 200.0, "mentioned_account_ids": []}
    record(config, envelope)
    call(config, {**envelope, "action": "record_turn", "role": "assistant", "sender_id": "900001",
                  "event_id": "qq-final-1", "content": "上一条已经生成的回复", "occurred_at": 199.0,
                  "message_type": "private"})

    context = call(config, {**envelope, "action": "context", "message_type": "private"})

    assert context["assistant_recent"] == [{
        "role": "assistant", "sender": "900001", "event_id": "qq-final-1",
        "content": "上一条已经生成的回复", "occurred_at": 199.0,
    }]
    assert "receipt" not in context["assistant_recent"][0]


def test_qq_read_history_combines_inbound_and_generated_replies(tmp_path: Path):
    from soyo.qq.native_tools import call as tool_call

    config = _config(tmp_path)
    envelope = {"route_id": "qq-private-100001", "event_id": "inbound-1", "sender_id": "100001",
                "text": "上一条消息", "occurred_at": 100.0, "mentioned_account_ids": []}
    record(config, envelope)
    call(config, {**envelope, "action": "record_turn", "role": "assistant", "sender_id": "900001",
                  "event_id": "qq-final-1", "content": "这是我刚才发的回复", "occurred_at": 101.0,
                  "message_type": "private"})

    result = tool_call(config, {"operation": "read_history", "route_id": envelope["route_id"],
                                "source_route_id": envelope["route_id"], "sender_id": "100001",
                                "query": "", "limit": 10})

    assert result["success"]
    assert [(item["role"], item["text"]) for item in result["items"]] == [
        ("user", "上一条消息"), ("assistant", "这是我刚才发的回复")]


def test_native_context_resolves_platform_reply_to_generated_or_external_message(tmp_path: Path):
    config = _config(tmp_path)
    current = {"route_id": "qq-private-100001", "event_id": "current", "sender_id": "100001",
               "text": "这个哦", "occurred_at": 200.0, "reply_to": "platform-42",
               "mentioned_account_ids": [], "message_type": "private"}
    record(config, current)
    call(config, {**current, "action": "record_turn", "role": "assistant", "sender_id": "900001",
                  "event_id": "qq-final-42", "content": "被引用的正文", "occurred_at": 199.0})
    call(config, {"action": "attach_receipt", "route_id": current["route_id"],
                  "sender_id": "900001", "message_type": "private", "publication_id": "qq-final-42",
                  "platform_message_id": "platform-42"})

    context = call(config, {**current, "action": "context"})

    assert context["reply_context"]["state"] == "resolved"
    assert context["reply_context"]["text"] == "被引用的正文"


def test_forward_segment_keeps_bounded_reference_for_native_expansion():
    from soyo.qq.inbound import parse_message

    parsed = parse_message([
        {"type": "text", "data": {"text": "外层"}},
        {"type": "forward", "data": {"id": "forward-42", "summary": "合并转发"}},
    ])

    assert parsed.forward_refs == ("forward-42",)
    assert parsed.media[0].kind == "forward"
    assert parsed.media[0].ref == "forward-42"


def test_native_capabilities_do_not_grant_group_or_external_side_effects(tmp_path: Path):
    from soyo.qq.native_tools import call as tool_call

    config = _config(tmp_path)
    owner = tool_call(config, {"operation": "capabilities", "route_id": "qq-private-100001",
                               "sender_id": "100001", "message_type": "private"})
    group = tool_call(config, {"operation": "capabilities", "route_id": "qq-group-123456",
                               "sender_id": "100002", "message_type": "group"})

    assert owner["owner"] is True
    assert owner["qq"]["ordinary_text_send"] is False
    assert owner["external"]["arbitrary_shell"] is False
    assert group["dsh"]["gpt_consult"] is False
    assert group["dsh"]["schedule"] is False


def test_native_group_owner_requires_explicit_group_binding(tmp_path: Path):
    from soyo.qq.native_tools import call as tool_call

    config = {**_config(tmp_path), "admin_ids": ["100001"], "owner_group_ids": ["123456"]}
    owner_group = tool_call(config, {"operation": "capabilities", "route_id": "qq-group-123456",
                                     "scene_target_id": "123456", "sender_id": "100001",
                                     "message_type": "group"})
    other_member = tool_call(config, {"operation": "capabilities", "route_id": "qq-group-123456",
                                      "scene_target_id": "123456", "sender_id": "100002",
                                      "message_type": "group"})
    owner_unbound = tool_call(config, {"operation": "capabilities", "route_id": "qq-group-999999",
                                       "scene_target_id": "999999", "sender_id": "100001",
                                       "message_type": "group"})

    assert owner_group["owner"] is True
    assert owner_group["group_admin"] is True
    assert owner_group["dsh"]["action_brain"] is True
    assert owner_group["host"]["root"] is True
    assert other_member["owner"] is False
    assert other_member["host"]["root"] is False
    assert owner_unbound["owner"] is False
    assert owner_unbound["host"]["root"] is False


def test_non_owner_cannot_write_global_feeling(tmp_path: Path):
    from soyo.qq.native_memory import call

    config = _config(tmp_path)
    with pytest.raises(ValueError, match="owner grant"):
        call(config, {"action": "feel", "route_id": "qq-group-123456", "sender_id": "100002",
                      "message_type": "group", "mood": "happy", "shared": True})


def test_forward_context_is_kept_in_read_only_projection(tmp_path: Path):
    import json
    from soyo.qq.native_memory import record, call
    from soyo.qq.native_data import call as data_call

    config = _config(tmp_path)
    envelope = {"route_id": "qq-group-123456", "event_id": "forward-event", "sender_id": "100001",
                "text": "[合并转发（未解析）]", "occurred_at": 100.0, "mentioned_account_ids": []}
    record(config, envelope)
    call(config, {**envelope, "action": "attach_forward", "forward_context": {
        "state": "resolved", "refs": ["forward-1"],
        "nodes": [{"sender": "A", "text": "节点正文"}], "text": "A: 节点正文"}})

    result = data_call({**config, "native_root": str(tmp_path)}, {"action": "page", "route": envelope["route_id"], "category": "messages", "offset": 0, "search": ""})

    assert result["rows"][0]["forward_context"]["state"] == "resolved"
    assert result["rows"][0]["forward_text"] == "A: 节点正文"


def test_multiline_publication_keeps_reply_only_on_first_part():
    route = ChannelRoute("qq-group-123456", "group", "123456", "900001", frozenset({"100001"}))
    plans = build_outbound_plans(
        OutboundIntent("pub", "attempt", route.route_id, "group", route.target_id,
                       "one\ntwo", reply_to="42", account_id=route.account_id), route)
    assert len(plans) == 2
    assert plans[0].params["message"][0]["type"] == "reply"
    assert all(segment["type"] != "reply" for segment in plans[1].params["message"])


def test_too_many_parts_rejects_instead_of_truncating_the_final():
    with pytest.raises(OutboundPlanError, match="too_many_reply_parts"):
        split_reply_text("\n".join(["paragraph"] * 65))


def test_unknown_part_stops_remaining_sends_and_survives_restart(tmp_path):
    route = ChannelRoute("qq-group-123456", "group", "123456", "900001", frozenset({"100001"}))
    claim = OutboxClaim("multipart", "multipart-attempt", {"account_id": route.account_id, "route_id": route.route_id,
        "target": {"type": "group", "id": route.target_id}, "text": "first\nsecond\nthird"})
    class Boundary:
        sends = 0
        def send(self, plan):
            self.sends += 1
            return {"retcode": 0, "data": {"message_id": 42}} if self.sends == 1 else {"retcode": 1200}
        def post_receipt(self, publication_id, receipt):
            return PortResult("accepted")
    boundary = Boundary()
    config = ChannelConfig(route.account_id, chunk_delay_seconds=0)
    with SoyoQQChannel(config=config, routes=[route], data_root=tmp_path) as channel:
        receipt = channel.process_outbox_claim(claim, boundary, boundary)
    assert receipt.status == "unknown"
    assert boundary.sends == 2
    assert receipt.response["cancelled_parts"] == 1
    assert receipt.response["parts"][0]["platform_message_id"] == "42"
    with SoyoQQChannel(config=config, routes=[route], data_root=tmp_path) as channel:
        assert channel.process_outbox_claim(claim, boundary, boundary).as_dict() == receipt.as_dict()
    assert boundary.sends == 2


def test_private_self_state_requires_explicit_public_scope(tmp_path):
    config = _config(tmp_path)
    owner = {"route_id": "qq-private-100001", "sender_id": "100001", "message_type": "private"}
    group = {"route_id": "qq-group-123456", "sender_id": "100002", "message_type": "group",
             "event_id": "g1", "occurred_at": 100}
    call(config, {**owner, "action": "self_state", "key": "private", "value": "owner-only"})
    with pytest.raises(ValueError, match="owner-private"):
        call(config, {**group, "action": "self_state", "key": "private", "value": "other"})
    assert call(config, {**group, "action": "context"})["self_state"] == []
    call(config, {**owner, "action": "self_state", "key": "public", "value": "public-state", "shared": True})
    assert [row["key"] for row in call(config, {**group, "action": "context"})["self_state"]] == ["public"]


def test_latest_fact_revision_ttl_hides_expired_without_deleting(tmp_path, monkeypatch):
    import soyo.qq.native_memory as memory
    config = _config(tmp_path)
    args = {"route_id": "qq-group-123456", "sender_id": "100001", "message_type": "group"}
    monkeypatch.setattr(memory.time, "time", lambda: 100)
    call(config, {**args, "action": "remember", "key": "timed", "value": "temporary", "ttl_seconds": 10})
    monkeypatch.setattr(memory.time, "time", lambda: 111)
    assert call(config, {**args, "action": "recall", "query": "timed"})["facts"] == []
    with sqlite3.connect(config["corpus_db"]) as db:
        assert db.execute("SELECT COUNT(*) FROM fact_revisions").fetchone()[0] == 1


def test_cdn_http_get_never_receives_the_onebot_bearer(tmp_path):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from soyo.qq.native_tools import read_media
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append(("POST", self.headers.get("Authorization")))
            body = json.dumps({"retcode": 0, "data": {"url": f"http://127.0.0.1:{self.server.server_port}/image"}}).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        def do_GET(self):
            seen.append(("GET", self.headers.get("Authorization")))
            body = b"fixture-image-bytes"
            self.send_response(200); self.send_header("Content-Type", "image/png"); self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)
        def log_message(self, *args):
            pass
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            result = read_media({"account_id": "900001", "http_url": f"http://127.0.0.1:{server.server_port}",
                                 "onebot_token": "fixture-only-token", "media_root": str(tmp_path / "media"), "media_url_domains": ["127.0.0.1"]},
                                {"kind": "image", "ref": "fixture-file-id"})
            assert result["ok"]
            assert seen == [("POST", "Bearer fixture-only-token"), ("GET", None)]
        finally:
            server.shutdown(); thread.join(timeout=5)
