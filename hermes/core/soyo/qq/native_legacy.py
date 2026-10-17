# SPDX-License-Identifier: GPL-3.0-only
"""Explicit, append-only import of the old Hermes memory layers.

The legacy database is never modified.  Staging first copies the native corpus
through SQLite's backup API, imports into that copy, and reports what would
change.  Production import requires an explicit confirmation string and is
idempotent by ``(legacy_table, legacy_key, legacy_hash)``.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

try:
    from . import native_cognition
except ImportError:  # pragma: no cover - native Host subprocess import
    import native_cognition


OWNER = native_cognition.OWNER
STAGE_NAME = "legacy-import-stage.db"


def _hash(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _legacy(path):
    path = Path(str(path or ""))
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise ValueError("explicit legacy memory database required")
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def _tables(db):
    return {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def inspect(config):
    path = config.get("legacy_memory_db")
    with closing(_legacy(path)) as old:
        tables = _tables(old)
        result = {"state": "observed", "tables": {}, "legacy_read_only": True}
        for name in sorted(tables):
            if "_fts" in name or name.startswith("sqlite_") or name in {"lte_fts", "we_fts", "wfe_fts"}:
                continue
            try:
                count = old.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]
            except sqlite3.DatabaseError:
                continue
            result["tables"][name] = count
        for name, column in (("long_term_entries", "active"), ("core_memories", "active")):
            if name in tables:
                result["tables"][name + "_active"] = old.execute(
                    'SELECT COUNT(*) FROM "' + name + '" WHERE active=1').fetchone()[0]
        return result


def _kind(memory_type, category):
    category = str(category or "")
    if memory_type == "episodic" or category in {"qzone", "qzone_post", "qzone_posts", "qzone_log", "sticker", "事件"}:
        return "episode"
    if category in {"agent_identity"}:
        return "self"
    if category in {"relationships", "人物"}:
        return "person"
    if category in {"knowledge", "wiki"}:
        return "knowledge"
    return "fact"


def _bounded(value, limit):
    text = str(value or "").strip()
    return text[:limit]


def _record_import(db, target_table, target_id, legacy_table, legacy_key, legacy_hash, kind, now):
    db.execute("INSERT OR IGNORE INTO cognition_imports(target_table,target_id,legacy_table,legacy_key,legacy_hash,mapped_kind,imported_at) "
               "VALUES(?,?,?,?,?,?,?)",
               (target_table, target_id, legacy_table, legacy_key, legacy_hash, kind, now))


def _already(db, legacy_table, legacy_key, legacy_hash):
    return db.execute("SELECT 1 FROM cognition_imports WHERE legacy_table=? AND legacy_key=? AND legacy_hash=?",
                      (legacy_table, legacy_key, legacy_hash)).fetchone() is not None


def _existing_memory(db, kind, key):
    return db.execute("SELECT id FROM cognition WHERE scope=? AND kind=? AND key=?", (OWNER, kind, key[:160])).fetchone()


def _import_ltm(db, old, now):
    stats = {"examined": 0, "facts_created": 0, "memories_created": 0, "duplicates": 0,
             "conflicts": 0, "expired": 0}
    rows = old.execute(
        "SELECT id,category,key,value,confidence,retrieval_count,last_retrieved,ttl_days,created_at,updated_at,"
        "memory_type,salience FROM long_term_entries WHERE active=1 AND COALESCE(deleted_at,'')=''").fetchall()
    for row in rows:
        stats["examined"] += 1
        key = _bounded(row["key"], 160)
        body = _bounded(row["value"], 12000)
        if not key or not body:
            continue
        kind = _kind(row["memory_type"], row["category"])
        digest = _hash("long_term_entries", row["id"], row["category"], key, body, row["updated_at"])
        legacy_key = str(row["id"])
        if _already(db, "long_term_entries", legacy_key, digest):
            stats["duplicates"] += 1
            continue
        expires = float(row["updated_at"] or now) + float(row["ttl_days"] or 0) * 86400 if row["ttl_days"] else 0
        if expires and expires <= now:
            stats["expired"] += 1
            continue
        created = float(row["created_at"] or row["updated_at"] or now)
        updated = float(row["updated_at"] or created)
        confidence = max(0.0, min(1.0, float(row["confidence"] if row["confidence"] is not None else .8)))
        salience = max(0.0, min(1.0, float(row["salience"] if row["salience"] is not None else .6)))
        # Long-term facts keep their old key when it is free.  A native fact
        # already using that key wins; the old row stays in the legacy DB and
        # is still available through explicit legacy recall.
        fact_key = key if len(key) <= 160 else key[:160]
        changed = db.execute("INSERT OR IGNORE INTO facts(scope,key,value,source) VALUES(?,?,?,?)",
                             (OWNER, fact_key, body[:12000], "legacy:long_term_entries:" + legacy_key)).rowcount
        if changed:
            stats["facts_created"] += 1
            db.execute("INSERT INTO fact_revisions(scope,key,value,source,source_event,reason,created_at,expires_at) "
                       "VALUES(?,?,?,?,?,?,?,?)",
                       (OWNER, fact_key, body[:12000], "legacy:long_term_entries:" + legacy_key, legacy_key,
                        "legacy-import", now, expires))
        else:
            stats["conflicts"] += 1
        identity = hashlib.sha256(json.dumps(["legacy", "long_term_entries", legacy_key], separators=(",", ":")).encode()).hexdigest()
        if db.execute("SELECT 1 FROM cognition WHERE id=?", (identity,)).fetchone():
            stats["duplicates"] += 1
            _record_import(db, "cognition", identity, "long_term_entries", legacy_key, digest, kind, now)
            continue
        existing = _existing_memory(db, kind, key)
        if existing:
            stats["conflicts"] += 1
            _record_import(db, "cognition", existing["id"], "long_term_entries", legacy_key, digest, kind, now)
            continue
        db.execute("INSERT INTO cognition(id,scope,kind,key,body,status,confidence,salience,sources,revision,model,"
                   "created_at,updated_at,expires_at,last_used,uses,successes) VALUES(?,?,?,?,?,'promoted',?,?,'[]',1,?,?,?,?,?,?,0)",
                   (identity, OWNER, kind, key[:160], body[:4000], confidence, salience,
                    "legacy-import:long_term_entries:" + legacy_key, created, now, expires,
                    now, int(row["retrieval_count"] or 0)))
        db.execute("INSERT INTO cognition_revisions(memory_id,revision,body,status,sources,reason,created_at) "
                   "VALUES(?,1,?,'promoted','[]','legacy-import',?)", (identity, body[:4000], now))
        _record_import(db, "cognition", identity, "long_term_entries", legacy_key, digest, kind, now)
        stats["memories_created"] += 1
    return stats


def _import_core(db, old, now):
    stats = {"examined": 0, "memories_created": 0, "duplicates": 0}
    if "core_memories" not in _tables(old):
        return stats
    for row in old.execute("SELECT id,category,content,source,occurred_at,created_at,updated_at FROM core_memories WHERE active=1"):
        stats["examined"] += 1
        body = _bounded(row["content"], 12000)
        if not body:
            continue
        kind = _kind("", row["category"])
        legacy_key = str(row["id"])
        digest = _hash("core_memories", row["id"], row["category"], body, row["updated_at"])
        if _already(db, "core_memories", legacy_key, digest):
            stats["duplicates"] += 1
            continue
        key = "core:" + _bounded(row["category"], 60) + ":" + legacy_key
        identity = hashlib.sha256(json.dumps(["legacy", "core_memories", legacy_key], separators=(",", ":")).encode()).hexdigest()
        if db.execute("SELECT 1 FROM cognition WHERE id=?", (identity,)).fetchone():
            stats["duplicates"] += 1
            _record_import(db, "cognition", identity, "core_memories", legacy_key, digest, kind, now)
            continue
        existing = _existing_memory(db, kind, key)
        if existing:
            _record_import(db, "cognition", existing["id"], "core_memories", legacy_key, digest, kind, now)
            stats["duplicates"] += 1
            continue
        created = float(row["created_at"] or row["occurred_at"] or now)
        db.execute("INSERT INTO cognition(id,scope,kind,key,body,status,confidence,salience,sources,revision,model,"
                   "created_at,updated_at,expires_at) VALUES(?,?,?,?,?,'promoted',.9,.8,'[]',1,?,?,?,0)",
                   (identity, OWNER, kind, key[:160], body[:4000], "legacy-import:core_memories:" + legacy_key,
                    created, now))
        db.execute("INSERT INTO cognition_revisions(memory_id,revision,body,status,sources,reason,created_at) "
                   "VALUES(?,1,?,'promoted','[]','legacy-import',?)", (identity, body[:4000], now))
        _record_import(db, "cognition", identity, "core_memories", legacy_key, digest, kind, now)
        stats["memories_created"] += 1
    return stats


def _import_wiki(db, old, now):
    stats = {"examined": 0, "memories_created": 0, "duplicates": 0}
    if "wiki_entries" not in _tables(old):
        return stats
    for row in old.execute("SELECT id,title,section,content,source_url,created_at,updated_at FROM wiki_entries"):
        stats["examined"] += 1
        body = _bounded(row["content"], 12000)
        title = _bounded(row["title"], 160)
        if not body or not title:
            continue
        legacy_key = str(row["id"])
        digest = _hash("wiki_entries", row["id"], title, row["section"], body, row["source_url"], row["updated_at"])
        if _already(db, "wiki_entries", legacy_key, digest):
            stats["duplicates"] += 1
            continue
        key = "wiki:" + legacy_key + ":" + title
        identity = hashlib.sha256(json.dumps(["legacy", "wiki_entries", legacy_key], separators=(",", ":")).encode()).hexdigest()
        if db.execute("SELECT 1 FROM cognition WHERE id=?", (identity,)).fetchone():
            stats["duplicates"] += 1
            _record_import(db, "cognition", identity, "wiki_entries", legacy_key, digest, "knowledge", now)
            continue
        existing = _existing_memory(db, "knowledge", key)
        if existing:
            _record_import(db, "cognition", existing["id"], "wiki_entries", legacy_key, digest, "knowledge", now)
            stats["duplicates"] += 1
            continue
        created = float(row["created_at"] or row["updated_at"] or now)
        db.execute("INSERT INTO cognition(id,scope,kind,key,body,status,confidence,salience,sources,revision,model,"
                   "created_at,updated_at,expires_at) VALUES(?,?,?,?,?,'promoted',.8,.7,'[]',1,?,?,?,0)",
                   (identity, OWNER, "knowledge", key[:160], (body + ("\n\n来源: " + str(row["source_url"]) if row["source_url"] else ""))[:4000],
                    "legacy-import:wiki_entries:" + legacy_key, created, now))
        db.execute("INSERT INTO cognition_revisions(memory_id,revision,body,status,sources,reason,created_at) "
                   "VALUES(?,1,?,'promoted','[]','legacy-import',?)", (identity, body[:4000], now))
        _record_import(db, "cognition", identity, "wiki_entries", legacy_key, digest, "knowledge", now)
        stats["memories_created"] += 1
    return stats


def _import_workflows(db, old, now):
    stats = {"examined": 0, "memories_created": 0, "duplicates": 0}
    if "workflow_entries" not in _tables(old):
        return stats
    for row in old.execute("SELECT * FROM workflow_entries"):
        stats["examined"] += 1
        name = _bounded(row["name"], 160)
        if not name:
            continue
        body = json.dumps({"description": row["description"], "trigger_patterns": row["trigger_patterns"],
                           "steps": row["steps"], "preconditions": row["preconditions"],
                           "expected_outcome": row["expected_outcome"]}, ensure_ascii=False)
        legacy_key = str(row["id"])
        digest = _hash("workflow_entries", row["id"], name, body, row["updated_at"])
        if _already(db, "workflow_entries", legacy_key, digest):
            stats["duplicates"] += 1
            continue
        identity = hashlib.sha256(json.dumps(["legacy", "workflow_entries", legacy_key], separators=(",", ":")).encode()).hexdigest()
        if db.execute("SELECT 1 FROM cognition WHERE id=?", (identity,)).fetchone():
            stats["duplicates"] += 1
            _record_import(db, "cognition", identity, "workflow_entries", legacy_key, digest, "workflow", now)
            continue
        existing = _existing_memory(db, "workflow", name)
        if existing:
            _record_import(db, "cognition", existing["id"], "workflow_entries", legacy_key, digest, "workflow", now)
            stats["duplicates"] += 1
            continue
        created = float(row["created_at"] or row["updated_at"] or now)
        db.execute("INSERT INTO cognition(id,scope,kind,key,body,status,confidence,salience,sources,revision,model,"
                   "created_at,updated_at,expires_at,last_used,uses,successes) VALUES(?,?,?,?,?,'promoted',.8,.7,'[]',1,?,?,?,0,?,?,?)",
                   (identity, OWNER, "workflow", name, body[:4000], "legacy-import:workflow_entries:" + legacy_key,
                    created, now, float(row["last_used"] or 0), int(row["usage_count"] or 0), int(row["success_count"] or 0)))
        db.execute("INSERT INTO cognition_revisions(memory_id,revision,body,status,sources,reason,created_at) "
                   "VALUES(?,1,?,'promoted','[]','legacy-import',?)", (identity, body[:4000], now))
        _record_import(db, "cognition", identity, "workflow_entries", legacy_key, digest, "workflow", now)
        stats["memories_created"] += 1
    return stats


def _import_episodes(db, old, now):
    stats = {"examined": 0, "memories_created": 0, "duplicates": 0}
    if "episode_fragments" not in _tables(old):
        return stats
    for row in old.execute("SELECT * FROM episode_fragments"):
        stats["examined"] += 1
        body = _bounded(row["text"], 12000)
        if not body:
            continue
        legacy_key = str(row["id"])
        digest = _hash("episode_fragments", row["id"], body, row["end_ts"])
        if _already(db, "episode_fragments", legacy_key, digest):
            stats["duplicates"] += 1
            continue
        key = "episode:" + legacy_key
        identity = hashlib.sha256(json.dumps(["legacy", "episode_fragments", legacy_key], separators=(",", ":")).encode()).hexdigest()
        if db.execute("SELECT 1 FROM cognition WHERE id=?", (identity,)).fetchone():
            stats["duplicates"] += 1
            _record_import(db, "cognition", identity, "episode_fragments", legacy_key, digest, "episode", now)
            continue
        existing = _existing_memory(db, "episode", key)
        if existing:
            _record_import(db, "cognition", existing["id"], "episode_fragments", legacy_key, digest, "episode", now)
            stats["duplicates"] += 1
            continue
        created = float(row["start_ts"] or row["created_at"] or now)
        db.execute("INSERT INTO cognition(id,scope,kind,key,body,status,confidence,salience,sources,revision,model,"
                   "created_at,updated_at,expires_at) VALUES(?,?,?,?,?,'promoted',.8,.7,'[]',1,?,?,?,0)",
                   (identity, OWNER, "episode", key[:160], body[:4000],
                    "legacy-import:episode_fragments:" + legacy_key, created, now))
        db.execute("INSERT INTO cognition_revisions(memory_id,revision,body,status,sources,reason,created_at) "
                   "VALUES(?,1,?,'promoted','[]','legacy-import',?)", (identity, body[:4000], now))
        _record_import(db, "cognition", identity, "episode_fragments", legacy_key, digest, "episode", now)
        stats["memories_created"] += 1
    return stats


def _import_edges(db, old, now):
    stats = {"examined": 0, "created": 0, "unmapped": 0, "duplicates": 0}
    if "memory_edges" not in _tables(old):
        return stats
    def target(identifier):
        row = db.execute("SELECT target_id FROM cognition_imports WHERE legacy_table='long_term_entries' AND legacy_key=? "
                         "ORDER BY id DESC LIMIT 1", (str(identifier),)).fetchone()
        return row["target_id"] if row else None
    for row in old.execute("SELECT src_id,dst_id,relation,weight FROM memory_edges"):
        stats["examined"] += 1
        src, dst = target(row["src_id"]), target(row["dst_id"])
        if not src or not dst:
            stats["unmapped"] += 1
            continue
        changed = db.execute("INSERT OR IGNORE INTO memory_edges(src_id,dst_id,relation,weight,created_at) VALUES(?,?,?,?,?)",
                             (src, dst, _bounded(row["relation"], 80) or "related", float(row["weight"] or 1), now)).rowcount
        stats["created"] += changed
        stats["duplicates"] += 0 if changed else 1
    return stats


def import_all(db, config, now=None):
    now = time.time() if now is None else now
    path = config.get("legacy_memory_db")
    with closing(_legacy(path)) as old:
        result = {"state": "completed", "legacy_read_only": True, "platform_sends": 0,
                  "model_calls": 0, "legacy_imported": True,
                  "long_term": _import_ltm(db, old, now),
                  "core": _import_core(db, old, now),
                  "wiki": _import_wiki(db, old, now),
                  "workflow": _import_workflows(db, old, now),
                  "episode": _import_episodes(db, old, now),
                  "edges": _import_edges(db, old, now)}
    return result


def _stage_path(config, args):
    target = Path(str(args.get("target_path") or ""))
    if not str(args.get("target_path") or ""):
        target = Path(config["corpus_db"]).with_name(STAGE_NAME)
    if not target.is_absolute() or target == Path(config["corpus_db"]):
        raise ValueError("staging must be a separate absolute corpus copy")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    return target


def stage(config, args):
    target = _stage_path(config, args)
    if target.exists() and args.get("replace") is not True:
        raise ValueError("staging copy already exists; inspect it or pass replace=true")
    temporary = target.with_name(target.name + ".tmp")
    if temporary.exists():
        temporary.unlink()
    source = sqlite3.connect(config["corpus_db"], timeout=10)
    try:
        destination = sqlite3.connect(temporary)
        try:
            source.backup(destination)
            destination.row_factory = sqlite3.Row
            result = import_all(destination, config)
            destination.commit()
        finally:
            destination.close()
    finally:
        source.close()
    os.replace(temporary, target)
    target.chmod(0o600)
    verify = sqlite3.connect(target.as_uri() + "?mode=ro", uri=True)
    try:
        verify.row_factory = sqlite3.Row
        counts = {name: verify.execute("SELECT COUNT(*) FROM " + name).fetchone()[0]
                  for name in ("facts", "cognition", "cognition_imports", "memory_edges")}
        result["stage"] = str(target)
        result["stage_counts"] = counts
        result["production_unchanged"] = True
    finally:
        verify.close()
    return result


def apply(config, args, db):
    if args.get("confirm") != "append-only":
        raise ValueError("legacy import requires confirm=append-only")
    return import_all(db, config)


def call(db, config, args):
    action = args.get("action")
    if action == "legacy_inspect":
        return inspect(config)
    if action == "legacy_stage":
        return stage(config, args)
    if action == "legacy_apply":
        # The caller's connection is the production corpus; the same function
        # is reused for staging with a separate connection.
        return apply(config, args, db)
    raise ValueError("unsupported legacy memory action")
