"""Rolling settlement, owner domain and explicit legacy import contracts."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from soyo.qq import native_cognition, native_memory


def setup(tmp_path):
    return {
        "corpus_db": str(tmp_path / "corpus.db"),
        "native_root": str(tmp_path),
        "legacy_memory_db": str(tmp_path / "old.db"),
        "memory_private_peers": ["100001"],
        "admin_ids": ["100001"],
        "owner_sessions": ["soyo-owner"],
        "cognition_enabled": True,
        "cognition_min_sources": 2,
        "cognition_roll_seconds": 3600,
        "cognition_idle_seconds": 7200,
    }


def message(config, route, event, text, stamp=100, sender="100002", message_type="group"):
    envelope = {"route_id": route, "event_id": event, "sender_id": sender,
                "message_type": message_type, "target_id": route.rsplit("-", 1)[-1],
                "text": text, "occurred_at": stamp}
    native_memory.record(config, envelope)
    with sqlite3.connect(config["corpus_db"]) as db:
        return db.execute("SELECT seq FROM messages WHERE route=? AND json_extract(body,'$.event_id')=? ORDER BY seq DESC LIMIT 1",
                          (route, event)).fetchone()[0]


def call(config, route, action, **extra):
    message_type = "private" if route.startswith("qq-private-") else "group"
    sender = route.rsplit("-", 1)[-1] if message_type == "private" else "100002"
    return native_memory.call(config, {"action": action, "route_id": route, "sender_id": sender,
                                       "message_type": message_type, **extra})


def test_owner_private_and_web_share_domain_while_groups_stay_isolated(tmp_path):
    config = setup(tmp_path)
    owner = "qq-private-100001"
    web = "dsh-owner:soyo-owner"
    first = message(config, owner, "owner-1", "主人喜欢安静的晚上", stamp=100, sender="100001", message_type="private")
    second = message(config, web, "web-1", "主人今天在 Web 里说想听爵士", stamp=101, sender="100001", message_type="private")
    prepared = call(config, owner, "cognition_prepare", force=True)
    assert prepared["state"] == "prepared"
    assert {row["route"] for row in prepared["sources"]} == {owner, web}
    assert {row["seq"] for row in prepared["sources"]} == {first, second}
    result = call(config, owner, "cognition_apply", batch_id=prepared["batch_id"],
                  source_model="fixture",
                  payload=json.dumps({"entries": [{"kind": "fact", "key": "music",
                      "body": "主人喜欢安静的晚上和爵士", "sources": [first, second],
                      "confidence": .9, "salience": .8}]}, ensure_ascii=False))
    assert result["state"] == "applied"
    assert call(config, web, "cognition_read")["memories"][0]["key"] == "music"
    assert call(config, "qq-group-999999", "cognition_read")["memories"] == []
    # A fact written through the owner Web route is visible in the owner DM.
    call(config, web, "remember", key="late", value="主人喜欢深夜工作")
    assert any(row["key"] == "late" for row in call(config, owner, "recall", query="深夜")["facts"])


def test_failed_batch_retries_the_same_sources_and_does_not_skip_watermark(tmp_path):
    config = setup(tmp_path)
    route = "qq-group-123456"
    first = message(config, route, "a", "第一句话", stamp=100)
    second = message(config, route, "b", "第二句话", stamp=101)
    prepared = call(config, route, "cognition_prepare", force=True)
    assert prepared["state"] == "prepared"
    batch_id = prepared["batch_id"]
    call(config, route, "cognition_failed", batch_id=batch_id, reason="fixture-failure")
    retry = call(config, route, "cognition_prepare", force=True)
    assert retry["state"] == "prepared" and retry["batch_id"] == batch_id
    assert {row["seq"] for row in retry["sources"]} == {first, second}
    call(config, route, "cognition_apply", batch_id=batch_id, source_model="fixture",
         payload=json.dumps({"entries": []}))
    third = message(config, route, "c", "第三句话", stamp=102)
    next_batch = call(config, route, "cognition_prepare", force=True)
    assert next_batch["state"] == "prepared"
    assert {row["seq"] for row in next_batch["sources"]} == {third}


def test_due_window_consolidates_low_traffic_without_a_bot_reply(tmp_path):
    config = setup(tmp_path)
    route = "qq-group-123456"
    message(config, route, "old-1", "很久以前的一句话", stamp=int(time.time()) - 7200)
    due = call(config, route, "cognition_due")
    assert due["state"] == "due" and due["reason"] == "idle"
    prepared = call(config, route, "cognition_prepare", force=True)
    assert prepared["state"] == "prepared"
    call(config, route, "cognition_apply", batch_id=prepared["batch_id"], source_model="fixture",
         payload=json.dumps({"entries": []}))
    assert call(config, route, "cognition_due")["state"] == "not_due"


def test_source_bound_summary_is_kept_and_withdrawn_with_its_sources(tmp_path):
    config = setup(tmp_path)
    route = "qq-group-123456"
    seq = message(config, route, "summary-1", "今天聊了音乐", stamp=100)
    call(config, route, "record_summary", summary="今天的音乐话题", source_seq=seq, source_seqs=[seq])
    call(config, route, "record_summary", summary="旧的无来源摘要")
    latest = message(config, route, "summary-2", "现在呢", stamp=101)
    context = call(config, route, "context", **{"event_id": "summary-2", "occurred_at": 101})
    assert [row["summary"] for row in context["summaries"]] == ["今天的音乐话题"]
    native_memory.call(config, {"action": "platform_event", "route_id": route, "sender_id": "100002",
        "event": {"notice_type": "group_recall", "group_id": "123456", "message_id": "summary-1"}})
    context = call(config, route, "context", **{"event_id": "summary-2", "occurred_at": 101})
    assert context["summaries"] == []


def legacy_db(path):
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE long_term_entries (
            id INTEGER PRIMARY KEY, category TEXT, key TEXT, value TEXT, confidence REAL,
            retrieval_count INTEGER, last_retrieved REAL, ttl_days INTEGER, created_at REAL,
            updated_at REAL, memory_type TEXT, salience REAL, active INTEGER, deleted_at TEXT);
        CREATE TABLE core_memories (
            id INTEGER PRIMARY KEY, category TEXT, content TEXT, source TEXT, occurred_at REAL,
            created_at REAL, updated_at REAL, active INTEGER, deleted_at REAL);
        CREATE TABLE wiki_entries (
            id INTEGER PRIMARY KEY, source_url TEXT, title TEXT, section TEXT, content TEXT,
            created_at REAL, updated_at REAL);
        CREATE TABLE memory_edges (
            id INTEGER PRIMARY KEY, src_id INTEGER, dst_id INTEGER, relation TEXT, weight REAL, created_at TEXT);
    """)
    db.execute("INSERT INTO long_term_entries VALUES(1,'user_preferences','night','主人喜欢深夜工作',.9,3,100,0,100,100,'semantic',.8,1,NULL)")
    db.execute("INSERT INTO long_term_entries VALUES(2,'qzone','outing','一次公开动态经历',.8,0,0,0,100,100,'episodic',.6,1,NULL)")
    db.execute("INSERT INTO core_memories VALUES(1,'人物','主人是信任的人','legacy',100,100,100,1,NULL)")
    db.execute("INSERT INTO wiki_entries VALUES(1,'https://example.invalid','音乐笔记','notes','和弦与节奏',100,100)")
    db.execute("INSERT INTO memory_edges VALUES(1,1,2,'related',.5,'100')")
    db.commit(); db.close()


def test_legacy_stage_apply_is_append_only_and_idempotent(tmp_path):
    config = setup(tmp_path)
    legacy_db(config["legacy_memory_db"])
    route = "qq-private-100001"
    before = Path(config["corpus_db"])
    assert not before.exists() or before.stat().st_size >= 0
    staged = call(config, route, "legacy_stage", target_path=str(tmp_path / "stage.db"))
    assert staged["state"] == "completed" and staged["legacy_read_only"] is True
    assert staged["long_term"]["facts_created"] == 2
    assert staged["long_term"]["memories_created"] == 2
    assert staged["core"]["memories_created"] == 1
    assert staged["wiki"]["memories_created"] == 1
    assert staged["edges"]["created"] == 1
    # Staging must not touch the production corpus.
    with sqlite3.connect(config["corpus_db"]) as db:
        assert db.execute("SELECT COUNT(*) FROM cognition").fetchone()[0] == 0
    applied = call(config, route, "legacy_apply", confirm="append-only")
    assert applied["state"] == "completed"
    with sqlite3.connect(config["corpus_db"]) as db:
        assert db.execute("SELECT COUNT(*) FROM facts WHERE scope='owner'").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM cognition WHERE model LIKE 'legacy-import:%'").fetchone()[0] == 4
        assert db.execute("SELECT COUNT(*) FROM memory_edges").fetchone()[0] == 1
    duplicate = call(config, route, "legacy_apply", confirm="append-only")
    assert duplicate["long_term"]["duplicates"] >= 2
    with sqlite3.connect(config["corpus_db"]) as db:
        assert db.execute("SELECT COUNT(*) FROM facts WHERE scope='owner'").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM cognition WHERE model LIKE 'legacy-import:%'").fetchone()[0] == 4


def test_legacy_apply_requires_explicit_confirmation(tmp_path):
    config = setup(tmp_path)
    legacy_db(config["legacy_memory_db"])
    try:
        call(config, "qq-private-100001", "legacy_apply")
    except ValueError as error:
        assert "confirm=append-only" in str(error)
    else:
        raise AssertionError("legacy apply accepted without confirmation")
