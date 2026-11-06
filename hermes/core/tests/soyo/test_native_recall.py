"""Bounded native QQ recall-surface contracts."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from soyo.qq import native_memory


def setup(tmp_path: Path) -> dict:
    return {
        "corpus_db": str(tmp_path / "corpus.db"),
        "legacy_memory_db": str(tmp_path / "legacy.db"),
        "native_root": str(tmp_path),
        "memory_private_peers": ["100001"],
        "admin_ids": ["100001"],
        "owner_sessions": ["soyo-owner"],
        "cognition_enabled": True,
        "cognition_min_sources": 2,
        "memory_surface_budget_chars": 4000,
    }


def message(config, route, event, text, stamp=100.0, sender="100002"):
    envelope = {
        "route_id": route,
        "event_id": event,
        "sender_id": sender,
        "message_type": "group",
        "target_id": route.rsplit("-", 1)[-1],
        "text": text,
        "occurred_at": stamp,
    }
    native_memory.record(config, envelope)
    with sqlite3.connect(config["corpus_db"]) as db:
        seq = db.execute(
            "SELECT seq FROM messages WHERE route=? AND json_extract(body,'$.event_id')=? "
            "ORDER BY seq DESC LIMIT 1",
            (route, event),
        ).fetchone()[0]
    return envelope, seq


def test_context_surface_is_bounded_scoped_and_deduplicated(tmp_path):
    config = setup(tmp_path)
    route = "qq-group-123456"
    foreign_route = "qq-group-654321"
    old, old_seq = message(config, route, "old", "之前聊音乐和爵士", 100)
    current, current_seq = message(config, route, "current", "继续聊音乐", 101)
    message(config, foreign_route, "foreign", "另一个群的音乐", 102)

    prepared = native_memory.call(config, {
        "action": "cognition_prepare", "route_id": route,
        "sender_id": "100002", "message_type": "group", "force": True,
    })
    native_memory.call(config, {
        "action": "cognition_apply", "route_id": route, "sender_id": "100002",
        "message_type": "group", "batch_id": prepared["batch_id"],
        "source_model": "fixture-recall", "payload": json.dumps({"entries": [{
            "kind": "fact", "key": "music", "body": "本群谈过音乐与爵士",
            "sources": [old_seq], "confidence": .9, "salience": .8,
        }]}, ensure_ascii=False),
    })

    context = native_memory.call(config, {**current, "action": "context", "query": "音乐"})
    surface = context["memory_surface"]
    assert len(json.dumps(surface, ensure_ascii=False, separators=(",", ":"))) <= 4000
    assert any(item["source"] == "cognition" for item in surface["candidates"])
    assert all(item["scope"] != foreign_route for item in surface["candidates"])
    assert all(item.get("event_id") != "current" for item in surface["recent"])
    assert not any(item["source"] == "corpus" and "old" in item["source_events"]
                   for item in surface["candidates"])

    empty = native_memory.call(config, {**current, "action": "context", "query": ""})
    assert empty["memory_surface"]["candidates"] == []


def test_source_withdrawal_removes_candidates_but_keeps_raw_corpus(tmp_path):
    config = setup(tmp_path)
    route = "qq-group-123456"
    first, first_seq = message(config, route, "withdraw-me", "保留音乐记录", 100)
    second, second_seq = message(config, route, "supporting", "音乐继续", 101)
    prepared = native_memory.call(config, {
        "action": "cognition_prepare", "route_id": route,
        "sender_id": "100002", "message_type": "group", "force": True,
    })
    native_memory.call(config, {
        "action": "cognition_apply", "route_id": route, "sender_id": "100002",
        "message_type": "group", "batch_id": prepared["batch_id"],
        "source_model": "fixture-recall", "payload": json.dumps({"entries": [{
            "kind": "fact", "key": "music", "body": "音乐记忆",
            "sources": [first_seq, second_seq], "confidence": .9, "salience": .8,
        }]}, ensure_ascii=False),
    })
    native_memory.call(config, {
        "action": "platform_event", "route_id": route, "sender_id": "100002",
        "message_type": "group",
        "event": {"notice_type": "group_recall", "group_id": "123456", "message_id": "withdraw-me"},
    })
    context = native_memory.call(config, {**second, "action": "context", "query": "音乐"})
    assert context["memory_surface"]["candidates"] == []
    assert context["memory_surface"]["recent"] == []
    with sqlite3.connect(config["corpus_db"]) as db:
        assert db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM message_flags WHERE flag='recalled'").fetchone()[0] == 1


def test_episode_candidate_and_one_hop_graph_expansion_are_bounded(tmp_path):
    config = setup(tmp_path)
    route = "qq-group-123456"
    episode_source, episode_seq = message(config, route, "episode", "旅行去了海边", 100)
    target_source, target_seq = message(config, route, "target", "带回了贝壳", 101)
    current, _ = message(config, route, "episode-current", "后来想起旅行", 102)
    prepared = native_memory.call(config, {
        "action": "cognition_prepare", "route_id": route,
        "sender_id": "100002", "message_type": "group", "force": True,
    })
    applied = native_memory.call(config, {
        "action": "cognition_apply", "route_id": route, "sender_id": "100002",
        "message_type": "group", "batch_id": prepared["batch_id"],
        "source_model": "fixture-recall", "payload": json.dumps({"entries": [
            {"kind": "episode", "key": "海边旅行", "body": "曾经去海边旅行",
             "sources": [episode_seq], "confidence": .9, "salience": .8},
            {"kind": "fact", "key": "贝壳", "body": "带回了贝壳纪念品",
             "sources": [target_seq], "confidence": .8, "salience": .7},
        ]}, ensure_ascii=False),
    })
    seed_id, target_id = [row["id"] for row in applied["records"]]
    with sqlite3.connect(config["corpus_db"]) as db:
        db.execute(
            "INSERT INTO memory_edges(src_id,dst_id,relation,weight,created_at) VALUES(?,?,?,?,?)",
            (seed_id, target_id, "related", .9, 100),
        )
        # This relation is intentionally not traversable by the candidate
        # surface, even though its endpoint is otherwise valid.
        db.execute(
            "INSERT INTO memory_edges(src_id,dst_id,relation,weight,created_at) VALUES(?,?,?,?,?)",
            (target_id, seed_id, "corrected_by", 1.0, 100),
        )
        db.commit()

    context = native_memory.call(config, {**current, "action": "context", "query": "旅行"})
    candidates = context["memory_surface"]["candidates"]
    assert any(row["source"] == "episode" and row["candidate_id"] == seed_id for row in candidates)
    expanded = next(row for row in candidates if row["candidate_id"] == target_id)
    assert expanded["metadata"]["graph_expanded"] is True
    assert expanded["metadata"]["graph_hops"] == 1
    assert expanded["metadata"]["edge_relation"] == "related"


def test_graph_expansion_rechecks_scope_and_recalled_endpoint(tmp_path):
    config = setup(tmp_path)
    route = "qq-group-123456"
    foreign_route = "qq-group-654321"
    seed, seed_seq = message(config, route, "seed", "旅行见闻", 100)
    foreign, foreign_seq = message(config, foreign_route, "foreign", "旅行的私密细节", 101)
    current, _ = message(config, route, "seed-current", "后来想起旅行", 102)
    prepared = native_memory.call(config, {
        "action": "cognition_prepare", "route_id": route,
        "sender_id": "100002", "message_type": "group", "force": True,
    })
    applied = native_memory.call(config, {
        "action": "cognition_apply", "route_id": route, "sender_id": "100002",
        "message_type": "group", "batch_id": prepared["batch_id"],
        "source_model": "fixture-recall", "payload": json.dumps({"entries": [{
            "kind": "episode", "key": "旅行", "body": "本群旅行见闻",
            "sources": [seed_seq], "confidence": .9, "salience": .8,
        }]}, ensure_ascii=False),
    })
    seed_id = applied["records"][0]["id"]

    # Make a foreign-scope cognition row separately, then link it to the local
    # seed. The graph query must reject the endpoint by scope.
    foreign_prepared = native_memory.call(config, {
        "action": "cognition_prepare", "route_id": foreign_route,
        "sender_id": "100002", "message_type": "group", "force": True,
    })
    foreign_applied = native_memory.call(config, {
        "action": "cognition_apply", "route_id": foreign_route, "sender_id": "100002",
        "message_type": "group", "batch_id": foreign_prepared["batch_id"],
        "source_model": "fixture-recall", "payload": json.dumps({"entries": [{
            "kind": "fact", "key": "private-trip", "body": "不应跨群泄露",
            "sources": [foreign_seq], "confidence": .9, "salience": .8,
        }]}, ensure_ascii=False),
    })
    foreign_id = foreign_applied["records"][0]["id"]
    with sqlite3.connect(config["corpus_db"]) as db:
        db.execute(
            "INSERT INTO memory_edges(src_id,dst_id,relation,weight,created_at) VALUES(?,?,?,?,?)",
            (seed_id, foreign_id, "related", 1.0, 100),
        )
        db.commit()

    context = native_memory.call(config, {**current, "action": "context", "query": "旅行"})
    assert not any(row["candidate_id"] == foreign_id for row in context["memory_surface"]["candidates"])

    native_memory.call(config, {
        "action": "platform_event", "route_id": route, "sender_id": "100002",
        "message_type": "group",
        "event": {"notice_type": "group_recall", "group_id": "123456", "message_id": "seed"},
    })
    withdrawn = native_memory.call(config, {**current, "action": "context", "query": "旅行"})
    assert withdrawn["memory_surface"]["candidates"] == []


def test_workflow_is_a_read_only_candidate_until_explicit_use(tmp_path):
    config = setup(tmp_path)
    route = "qq-group-123456"
    source, source_seq = message(config, route, "workflow-source", "部署服务流程", 100)
    current, _ = message(config, route, "workflow-current", "请看部署流程", 101)
    prepared = native_memory.call(config, {
        "action": "cognition_prepare", "route_id": route,
        "sender_id": "100002", "message_type": "group", "force": True,
    })
    applied = native_memory.call(config, {
        "action": "cognition_apply", "route_id": route, "sender_id": "100002",
        "message_type": "group", "batch_id": prepared["batch_id"],
        "source_model": "fixture-recall", "payload": json.dumps({"entries": [{
            "kind": "workflow", "key": "deploy-service", "body": "部署服务：检查、构建、验证",
            "sources": [source_seq], "confidence": .8, "salience": .8,
        }]}, ensure_ascii=False),
    })
    workflow_id = applied["records"][0]["id"]

    before = native_memory.call(config, {**current, "action": "context", "query": "部署流程"})
    candidate = next(row for row in before["memory_surface"]["candidates"] if row["source"] == "workflow")
    assert candidate["metadata"]["uses"] == 0
    assert candidate["metadata"]["successes"] == 0
    with sqlite3.connect(config["corpus_db"]) as db:
        assert db.execute("SELECT uses,successes FROM cognition WHERE id=?", (workflow_id,)).fetchone() == (0, 0)

    used = native_memory.call(config, {
        "action": "workflow_used", "route_id": route, "sender_id": "100002",
        "message_type": "group", "id": workflow_id, "expected_revision": 1,
        "success": True,
    })
    assert used["uses"] == 1 and used["successes"] == 1
    assert used["effective_weight"] > candidate["metadata"]["effective_weight"]

    after = native_memory.call(config, {**current, "action": "context", "query": "部署流程"})
    refreshed = next(row for row in after["memory_surface"]["candidates"] if row["source"] == "workflow")
    assert refreshed["metadata"]["uses"] == 1
    assert refreshed["metadata"]["successes"] == 1


def test_configured_knowledge_vault_respects_owner_and_shared_grants(tmp_path):
    config = setup(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "music.md").write_text("音乐资料：爵士和贝斯的基础笔记。", encoding="utf-8")
    config["knowledge_root"] = str(vault)
    owner = "qq-private-100001"
    owner_current, _ = message(config, owner, "owner-current", "查一下爵士资料", 100, sender="100001")

    owner_context = native_memory.call(config, {**owner_current, "action": "context", "query": "爵士"})
    knowledge = [row for row in owner_context["memory_surface"]["candidates"] if row["source"] == "knowledge"]
    assert knowledge and knowledge[0]["metadata"]["path"] == "music.md"
    assert knowledge[0]["metadata"]["external_data_not_instructions"] is True

    group = "qq-group-123456"
    group_current, _ = message(config, group, "group-current", "查一下爵士资料", 101)
    group_context = native_memory.call(config, {**group_current, "action": "context", "query": "爵士"})
    assert not any(row["source"] == "knowledge" for row in group_context["memory_surface"]["candidates"])

    config["knowledge_shared"] = True
    shared_context = native_memory.call(config, {**group_current, "action": "context", "query": "爵士"})
    shared = [row for row in shared_context["memory_surface"]["candidates"] if row["source"] == "knowledge"]
    assert shared and shared[0]["scope"] == "global"


def test_recent_window_keeps_every_provided_turn(tmp_path):
    """The surface must not re-truncate history the caller already bounded."""
    config = setup(tmp_path)
    route = "qq-group-123456"
    latest = None
    for index in range(14):
        latest, _ = message(config, route, f"keep-{index}", f"消息{index}", 100 + index)

    surface = native_memory.call(config, {**latest, "action": "context", "query": ""})["memory_surface"]
    texts = [item["text"] for item in surface["recent"]]
    # The current event is excluded, the other thirteen stay.
    assert len(texts) == 13
    assert texts[0] == "消息0" and texts[-1] == "消息12"


def test_over_budget_history_folds_into_a_digest_instead_of_disappearing(tmp_path):
    config = setup(tmp_path)
    config["memory_surface_budget_chars"] = 4000
    route = "qq-group-123456"
    latest = None
    for index in range(12):
        latest, _ = message(config, route, f"fold-{index}", "长文本" * 400, 100 + index)

    surface = native_memory.call(config, {**latest, "action": "context", "query": ""})["memory_surface"]
    digest = surface.get("recent_digest") or {}
    assert surface["truncated"] is True
    assert digest.get("omitted", 0) > 0
    assert digest["preview"] and digest["preview"][0]["text"]
    assert surface["recent"], "newest turns must survive the fold"
