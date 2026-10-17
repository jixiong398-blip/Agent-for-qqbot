"""Read-only Memory contracts after the real native Host/browser probes."""
from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from soyo.qq.native_data import call
from soyo.qq.native_memory import connect


PRIVATE = "qq-private-100001"
GROUP = "qq-group-123456"
OTHER = "qq-group-654321"


def database(tmp_path):
    config = {"corpus_db": str(tmp_path / "corpus.db"), "native_root": str(tmp_path),
              "legacy_memory_db": str(tmp_path / "legacy.db"), "memory_private_peers": ["100001"]}
    with connect(config):
        pass
    return config


def message(db, route, event, content="fixture source", stamp=100):
    body = {"event_id": event, "sender_id": "100001", "text": content, "occurred_at": stamp}
    return str(db.execute("INSERT INTO messages(route,event,sender,body) VALUES(?,?,?,?)",
                          (route, event, "100001", json.dumps(body))).lastrowid)


def page(config, route, kind, **extra):
    return call(config, {"action": "page", "route": route, "category": kind, **extra})


def detail(config, route, kind, identity):
    return call(config, {"action": "detail", "route": route, "category": kind, "id": identity})


def test_exact_source_and_turn_identity_cannot_cross_scenes(tmp_path):
    config = database(tmp_path)
    with connect(config) as db:
        identity = message(db, PRIVATE, "private-event")
        turn_id = str(db.execute("INSERT INTO turns(route,role,event_id,content,occurred_at,created_at) VALUES(?,?,?,?,?,?)",
                                 (PRIVATE, "user", "private-event", "fixture turn", 100, 100)).lastrowid)
    assert detail(config, PRIVATE, "messages", identity)["row"]["text"] == "fixture source"
    assert detail(config, GROUP, "messages", identity)["row"] is None
    assert detail(config, GROUP, "turns", turn_id)["row"] is None
    assert len(detail(config, PRIVATE, "turns", turn_id)["sources"]) == 1


@pytest.mark.parametrize("kind,table,key", [("state", "self_state", "key"),
                                          ("people", "people", "person_id"),
                                          ("emotions", "emotions", "id")])
def test_owner_and_other_scene_records_are_hidden_in_list_and_detail(tmp_path, kind, table, key):
    config = database(tmp_path)
    with connect(config) as db:
        identities = {}
        for scope in ("owner", "global", GROUP, OTHER):
            if table == "self_state":
                identity = scope + "-state"
                db.execute("INSERT INTO self_state(key,value,source,updated_at,scope) VALUES(?,?,?,?,?)",
                           (identity, "fixture " + scope, "test", 100, scope))
            elif table == "people":
                identity = scope + "-person"
                db.execute("INSERT INTO people(person_id,scope,display_name,understanding,updated_at) VALUES(?,?,?,?,?)",
                           (identity, scope, "fixture", "fixture " + scope, 100))
            else:
                identity = str(db.execute("INSERT INTO emotions(scope,mood,reason,created_at) VALUES(?,?,?,?)",
                                          (scope, "fixture", "fixture " + scope, 100)).lastrowid)
            identities[scope] = identity
    rows = page(config, GROUP, kind)["rows"]
    assert {row["id"] for row in rows} == {identities["global"], identities[GROUP]}
    for hidden in ("owner", OTHER):
        assert detail(config, GROUP, kind, identities[hidden])["row"] is None
    assert detail(config, PRIVATE, kind, identities["owner"])["row"] is not None
    overview = page(config, GROUP, "all")["rows"]
    assert all(row["scope"] in ("global", GROUP) for row in overview)


def test_recalled_message_remains_marked_in_details_and_turn_sources(tmp_path):
    config = database(tmp_path)
    with connect(config) as db:
        identity = message(db, GROUP, "recalled-event")
        db.execute("INSERT INTO message_flags(route,event_id,flag,created_at) VALUES(?,?,?,?)",
                   (GROUP, "recalled-event", "recalled", 101))
        turn_id = str(db.execute("INSERT INTO turns(route,role,event_id,content,occurred_at,created_at) VALUES(?,?,?,?,?,?)",
                                 (GROUP, "user", "recalled-event", "fixture turn", 100, 100)).lastrowid)
    for row in (page(config, GROUP, "messages")["rows"][0], detail(config, GROUP, "messages", identity)["row"],
                detail(config, GROUP, "turns", turn_id)["sources"][0]):
        assert row["recalled"] and row["text"].startswith("[已撤回]")


def test_fact_detail_uses_exact_scoped_key_including_colons(tmp_path):
    config = database(tmp_path)
    with connect(config) as db:
        db.execute("INSERT INTO facts(scope,key,value,source) VALUES(?,?,?,?)", (GROUP, "topic:detail", "fixture fact", "test"))
    row = page(config, GROUP, "facts")["rows"][0]
    assert detail(config, GROUP, "facts", row["id"])["row"]["text"] == "fixture fact"
    with pytest.raises(ValueError, match="different scene"):
        detail(config, OTHER, "facts", row["id"])


def test_legacy_keys_survive_paging_and_search_without_import_or_write(tmp_path):
    config = database(tmp_path)
    with sqlite3.connect(config["legacy_memory_db"]) as db:
        db.execute("CREATE TABLE long_term_entries (key TEXT PRIMARY KEY,value TEXT,active INTEGER,updated_at TEXT)")
        for n in range(30):
            db.execute("INSERT INTO long_term_entries VALUES(?,?,1,?)",
                       (f"legacy-{n:02}", f"fixture legacy {n}", f"2026-10-13T00:00:{n:02}Z"))
    digest = lambda: hashlib.sha256((tmp_path / "legacy.db").read_bytes()).hexdigest()
    before = digest()
    first = page(config, PRIVATE, "legacy")
    second = page(config, PRIVATE, "legacy", offset=first["next_offset"])
    assert {row["id"] for row in first["rows"]}.isdisjoint(row["id"] for row in second["rows"])
    selected = second["rows"][0]
    filtered = page(config, PRIVATE, "legacy", search=selected["id"])
    assert filtered["rows"][0]["id"] == selected["id"]
    assert detail(config, PRIVATE, "legacy", selected["id"])["row"]["updated_at"].endswith("Z")
    assert not page(config, GROUP, "legacy")["rows"]
    with pytest.raises(ValueError, match="not admitted"):
        detail(config, GROUP, "legacy", selected["id"])
    assert not page(config, PRIVATE, "all")["rows"]
    assert digest() == before


def test_overview_pagination_does_not_skip_or_duplicate_native_records(tmp_path):
    config = database(tmp_path)
    with connect(config) as db:
        for n in range(40):
            message(db, GROUP, f"event-{n}", "fixture " + "长" * 2000, 100 + n)
        for n in range(15):
            db.execute("INSERT INTO facts(scope,key,value,source) VALUES(?,?,?,?)", (GROUP, str(n), "fixture fact", "test"))
        message(db, OTHER, "other-event", "must not appear", 10000)
    seen = set()
    offset = 0
    while True:
        result = page(config, GROUP, "all", offset=offset, summary_only=True)
        keys = {(row["data_category"], row["id"]) for row in result["rows"]}
        assert seen.isdisjoint(keys)
        assert all(len(row["text"]) <= 240 for row in result["rows"])
        seen.update(keys)
        if result["next_offset"] is None:
            break
        offset = result["next_offset"]
    assert len(seen) == 55


@pytest.mark.parametrize("extra", [{"offset": -1}, {"offset": True}, {"search": "x" * 161}])
def test_invalid_pages_are_rejected_before_reading(tmp_path, extra):
    config = {"corpus_db": str(tmp_path / "not-created.db")}
    with pytest.raises(ValueError, match="bounded page"):
        page(config, GROUP, "messages", **extra)
    assert not (tmp_path / "not-created.db").exists()
