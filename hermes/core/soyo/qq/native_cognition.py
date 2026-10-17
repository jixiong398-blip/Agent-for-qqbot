# SPDX-License-Identifier: GPL-3.0-only
"""Source-bound native cognition records; no model calls or Hermes runtime imports.

The executor supplies semantic interpretations.  This module checks real corpus
sources, revision/scope/retraction rules and persists candidates/promotions.  It
does not claim deterministic snippets are semantic summaries.

Two deployment-level concepts are added here without weakening the source rules:

* A **memory domain** is the durable identity of a conversation owner.  The
  trusted owner's QQ private scene and the owner Web session share one domain
  (``owner``); groups and other private scenes remain isolated.
* A **batch watermark** only advances for applied or explicitly discarded
  batches.  Failed/stale batches are retried with the same sources instead of
  being silently skipped.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time

if __package__:
    from . import native_reflection
else:
    import native_reflection


OWNER = "owner"
KINDS = {"fact", "episode", "workflow", "person", "emotion", "self", "knowledge"}
READ_ACTIONS = {"cognition_prepare", "cognition_read", "cognition_status", "cognition_due"}
ACTIONS = READ_ACTIONS | {"cognition_apply", "cognition_dispatched", "cognition_failed",
                          "correct_memory", "forget_memory", "workflow_used"}
SECRET = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}|(?:access_token|api_key|app_secret)\s*[:=]", re.I)
QQ_ROUTE = re.compile(r"qq-(group|private)-[1-9][0-9]{0,19}")
WEB_ROUTE = re.compile(r"dsh-owner:([A-Za-z0-9_.:-]{1,160})")


def initialize(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS cognition (
            id TEXT PRIMARY KEY, scope TEXT NOT NULL, kind TEXT NOT NULL, key TEXT NOT NULL,
            body TEXT NOT NULL, status TEXT NOT NULL, confidence REAL NOT NULL, salience REAL NOT NULL,
            sources TEXT NOT NULL, revision INTEGER NOT NULL, model TEXT NOT NULL,
            created_at REAL NOT NULL, updated_at REAL NOT NULL, expires_at REAL NOT NULL DEFAULT 0,
            last_used REAL NOT NULL DEFAULT 0, uses INTEGER NOT NULL DEFAULT 0, successes INTEGER NOT NULL DEFAULT 0,
            UNIQUE(scope,kind,key));
        CREATE INDEX IF NOT EXISTS idx_cognition_scope_status ON cognition(scope,status,updated_at);
        CREATE TABLE IF NOT EXISTS cognition_revisions (
            id INTEGER PRIMARY KEY, memory_id TEXT NOT NULL, revision INTEGER NOT NULL,
            body TEXT NOT NULL, status TEXT NOT NULL, sources TEXT NOT NULL, reason TEXT NOT NULL,
            created_at REAL NOT NULL, UNIQUE(memory_id,revision));
        CREATE TABLE IF NOT EXISTS cognition_batches (
            id TEXT PRIMARY KEY, route TEXT NOT NULL, after_seq INTEGER NOT NULL, through_seq INTEGER NOT NULL,
            sources TEXT NOT NULL, state TEXT NOT NULL, task_id TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL, settled_at REAL NOT NULL DEFAULT 0, UNIQUE(route,through_seq));
        CREATE TABLE IF NOT EXISTS cognition_admin_operations (
            request_id TEXT PRIMARY KEY, scope TEXT NOT NULL, fingerprint TEXT NOT NULL,
            memory_id TEXT NOT NULL, revision INTEGER NOT NULL, operation TEXT NOT NULL,
            reason TEXT NOT NULL, result TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS cognition_imports (
            id INTEGER PRIMARY KEY, target_table TEXT NOT NULL, target_id TEXT NOT NULL,
            legacy_table TEXT NOT NULL, legacy_key TEXT NOT NULL, legacy_hash TEXT NOT NULL,
            mapped_kind TEXT NOT NULL DEFAULT '', imported_at REAL NOT NULL,
            UNIQUE(legacy_table,legacy_key,legacy_hash));
        CREATE TABLE IF NOT EXISTS memory_edges (
            id INTEGER PRIMARY KEY, src_id TEXT NOT NULL, dst_id TEXT NOT NULL,
            relation TEXT NOT NULL, weight REAL NOT NULL DEFAULT 1,
            created_at REAL NOT NULL, UNIQUE(src_id,dst_id,relation));
    """)
    with db:
        fields = {row[1] for row in db.execute("PRAGMA table_info(cognition_batches)")}
        for field, declaration in {
            "attempts": "INTEGER NOT NULL DEFAULT 0",
            "last_error": "TEXT NOT NULL DEFAULT ''",
            "routes": "TEXT NOT NULL DEFAULT '[]'",
        }.items():
            if field not in fields:
                db.execute(f"ALTER TABLE cognition_batches ADD COLUMN {field} {declaration}")
    native_reflection.initialize(db)


def bounded(value, limit, field):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or SECRET.search(value):
        raise ValueError(f"bounded credential-free {field} required")
    return value.strip()


def number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError("bounded finite cognition weight required")
    return float(value)


def owner_ids(config):
    values = set()
    for key in ("admin_ids", "memory_private_peers"):
        values.update(str(value) for value in (config or {}).get(key, []) if str(value).isdigit())
    return values


def owner_sessions(config):
    values = {"soyo-owner"}
    values.update(str(value) for value in ((config or {}).get("owner_sessions") or []))
    values.update(str(value) for value in (((config or {}).get("collaborator") or {}).get("owner_sessions") or []))
    return values


def domain_of(config, route):
    """Return the durable memory domain for a real scene/route."""
    if route == OWNER:
        return OWNER
    if isinstance(route, str) and route.startswith("qq-private-"):
        return OWNER if route.removeprefix("qq-private-") in owner_ids(config) else route
    match = WEB_ROUTE.fullmatch(route) if isinstance(route, str) else None
    if match and match.group(1) in owner_sessions(config):
        return OWNER
    return route


def domain_routes(config, domain):
    """Every corpus route that contributes sources to a domain."""
    if domain != OWNER:
        return [domain]
    routes = ["qq-private-" + peer for peer in sorted(owner_ids(config))]
    routes += ["dsh-owner:" + session for session in sorted(owner_sessions(config))]
    return routes


def resolve(config, route):
    if not isinstance(route, str) or not route:
        raise ValueError("native memory route required")
    domain = domain_of(config, route)
    if domain == OWNER:
        return OWNER, domain_routes(config, OWNER)
    if QQ_ROUTE.fullmatch(route):
        return route, [route]
    if WEB_ROUTE.fullmatch(route):
        # An unknown Web session is not a silent owner alias.
        raise ValueError("unadmitted owner Web memory route")
    raise ValueError("native memory route required")


def source_rows(db, route, seqs):
    """Verify exact corpus sources.  ``route`` may be a domain route list."""
    routes = list(route) if isinstance(route, (list, tuple, set)) else [route]
    if not isinstance(seqs, list) or not 1 <= len(seqs) <= 64 or any(type(seq) is not int or seq < 1 for seq in seqs):
        raise ValueError("exact corpus source ids required")
    seqs = sorted(set(seqs))
    rows = []
    for seq in seqs:
        row = db.execute("SELECT seq,route,body FROM messages WHERE seq=?", (seq,)).fetchone()
        if not row or row["route"] not in routes:
            raise ValueError("cognition source belongs to a different scene or is absent")
        value = json.loads(row["body"])
        if db.execute("SELECT 1 FROM message_flags WHERE route=? AND event_id=? AND flag='recalled'",
                      (row["route"], value["event_id"])).fetchone():
            raise ValueError("recalled source cannot support cognition")
        rows.append({"seq": seq, "route": row["route"], "event_id": value["event_id"],
                     "sender_id": value["sender_id"], "occurred_at": value.get("occurred_at"),
                     "text": str(value.get("text") or "")[:1200]})
    return rows


def _scopes(domain, routes):
    values = [domain]
    if domain == OWNER:
        values += [route for route in routes if route != domain]
    return sorted(set(values))


def invalidate_recalled(db, route, now, routes=None):
    routes = list(routes) if routes is not None else (list(route) if isinstance(route, (list, tuple, set)) else [route])
    domain = route if isinstance(route, str) else OWNER
    scopes = _scopes(domain, routes)
    rows = db.execute("SELECT id,scope,sources,revision,body,status FROM cognition WHERE scope IN (" +
                      ",".join("?" for _ in scopes) + ") AND status NOT IN ('withdrawn','forgotten')", scopes).fetchall()
    count = 0
    for row in rows:
        try:
            refs = json.loads(row["sources"])
        except (TypeError, ValueError):
            refs = []
        # Imported legacy rows have no corpus source list; they are corrected or
        # forgotten explicitly, never silently withdrawn by a route scan.
        if not refs:
            continue
        try:
            source_rows(db, routes, refs)
        except ValueError:
            revision = row["revision"] + 1
            db.execute("UPDATE cognition SET status='withdrawn',revision=?,updated_at=? WHERE id=?", (revision, now, row["id"]))
            db.execute("INSERT INTO cognition_revisions(memory_id,revision,body,status,sources,reason,created_at) VALUES(?,?,?,?,?,?,?)",
                       (row["id"], revision, row["body"], "withdrawn", row["sources"], "source-recalled-or-unavailable", now))
            count += 1
    return count


def find_existing(db, domain, routes, kind, key):
    scopes = _scopes(domain, routes)
    return db.execute("SELECT * FROM cognition WHERE kind=? AND key=? AND scope IN (" +
                      ",".join("?" for _ in scopes) + ") ORDER BY (scope=?) DESC LIMIT 1",
                      (kind, key, *scopes, domain)).fetchone()


def _due_rows(db, routes, after):
    rows = db.execute("SELECT seq,route,body FROM messages WHERE route IN (" +
                      ",".join("?" for _ in routes) + ") AND seq>? "
                      "AND COALESCE(json_extract(body,'$.historical'),0)=0 "
                      "AND trim(COALESCE(json_extract(body,'$.text'),''))<>'' "
                      "AND NOT EXISTS (SELECT 1 FROM message_flags WHERE message_flags.route=messages.route AND "
                      "message_flags.event_id=json_extract(messages.body,'$.event_id') AND flag='recalled') "
                      "ORDER BY seq LIMIT 48", (*routes, after)).fetchall()
    return rows


def _minimum(config, route):
    base = 24 if route.startswith("qq-private-") or route == OWNER else 10
    return max(2, min(48, int(config.get("cognition_min_sources", base) or base)))


def _after_seq(db, config, domain):
    return max(int(config.get("cognition_start_seq", 0)), db.execute(
        "SELECT COALESCE(MAX(through_seq),0) FROM cognition_batches WHERE route=? "
        "AND state IN ('applied','discarded')", (domain,)).fetchone()[0])


def _batch_view(db, route, batch, config, routes):
    seqs = json.loads(batch["sources"])
    return {"state": "prepared", "batch_id": batch["id"], "scene": route, "routes": routes,
            "sources": source_rows(db, routes, seqs),
            "role_sources": native_reflection.sources(db, routes, seqs, batch["created_at"]),
            "current": context(db, route, "", time.time(), config),
            "inactive": [dict(row) for row in db.execute(
                "SELECT id,kind,key,status,revision FROM cognition WHERE scope=? AND "
                "status IN ('expired','withdrawn','forgotten') ORDER BY updated_at DESC LIMIT 24", (route,))],
            "attempts": batch["attempts"] if "attempts" in batch.keys() else 0,
            "kind": "semantic-input-not-a-derived-summary"}


def _revive(db, routes, batch, now, *, retry=False):
    """Drop recalled sources from a retry and keep the usable remainder."""
    seqs = json.loads(batch["sources"])
    usable = []
    for seq in seqs:
        try:
            source_rows(db, routes, [seq])
        except ValueError:
            continue
        usable.append(seq)
    if not usable:
        db.execute("UPDATE cognition_batches SET state='discarded',settled_at=?,last_error=?,sources='[]' WHERE id=?",
                   (now, "all-sources-withdrawn", batch["id"]))
        return None
    if usable != seqs:
        db.execute("UPDATE cognition_batches SET sources=? WHERE id=?", (json.dumps(usable), batch["id"]))
    if retry:
        db.execute("UPDATE cognition_batches SET state='prepared',attempts=attempts+1,task_id='',last_error='' WHERE id=?",
                   (batch["id"],))
    return db.execute("SELECT * FROM cognition_batches WHERE id=?", (batch["id"],)).fetchone()


def prepare(db, route, args, config):
    domain, routes = resolve(config, route)
    now = time.time()
    invalidate_recalled(db, domain, now, routes)
    pending = db.execute("SELECT * FROM cognition_batches WHERE route=? AND state IN ('prepared','dispatched') "
                         "ORDER BY created_at LIMIT 1", (domain,)).fetchone()
    if pending:
        if pending["state"] == "prepared":
            revived = _revive(db, routes, pending, now)
            if not revived:
                pending = None
            else:
                return _batch_view(db, domain, revived, config, routes)
        else:
            stale = now - float(pending["created_at"])
            limit = max(60, min(86400, int(config.get("cognition_batch_stale_seconds", 900) or 900)))
            if not (args.get("reclaim_stale") is True and stale >= limit):
                return {"state": "in_flight", "batch_id": pending["id"], "task_id": pending["task_id"],
                        "stale_seconds": round(stale, 1)}
            db.execute("UPDATE cognition_batches SET state='failed',last_error='stale-dispatch',settled_at=? WHERE id=?",
                       (now, pending["id"]))
    if not pending:
        after = _after_seq(db, config, domain)
        failed = db.execute("SELECT * FROM cognition_batches WHERE route=? AND state='failed' AND through_seq>? "
                            "ORDER BY created_at LIMIT 1", (domain, after)).fetchone()
        if failed:
            revived = _revive(db, routes, failed, now, retry=True)
            if revived:
                return _batch_view(db, domain, revived, config, routes)
    after = _after_seq(db, config, domain)
    rows = _due_rows(db, routes, after)
    seqs = []
    for row in rows:
        value = json.loads(row["body"])
        if value.get("historical") or not str(value.get("text") or "").strip():
            continue
        seqs.append(row["seq"])
    minimum = _minimum(config, domain)
    if not seqs or len(seqs) < minimum and args.get("force") is not True:
        return {"state": "not_due", "new_sources": len(seqs), "minimum": minimum,
                "oldest_pending_at": _oldest_pending(db, routes, after)}
    through = rows[-1]["seq"]
    batch_id = hashlib.sha256(json.dumps([domain, after, through], separators=(",", ":")).encode()).hexdigest()
    prior = db.execute("SELECT * FROM cognition_batches WHERE route=? AND through_seq=?", (domain, through)).fetchone()
    if prior:
        if prior["state"] in {"applied", "discarded"}:
            return {"state": "not_due", "new_sources": 0, "minimum": minimum}
        batch_id = prior["id"]
        db.execute("UPDATE cognition_batches SET routes=? WHERE id=?", (json.dumps(routes), batch_id))
    else:
        db.execute("INSERT OR IGNORE INTO cognition_batches(id,route,after_seq,through_seq,sources,state,created_at,routes) "
                   "VALUES(?,?,?,?,?,'prepared',?,?)",
                   (batch_id, domain, after, through, json.dumps(seqs), now, json.dumps(routes)))
    batch = db.execute("SELECT * FROM cognition_batches WHERE id=?", (batch_id,)).fetchone()
    if batch["state"] == "failed":
        batch = _revive(db, routes, batch, now, retry=True)
        if not batch:
            return {"state": "not_due", "new_sources": 0, "minimum": minimum}
    return _batch_view(db, domain, batch, config, routes)


def _oldest_pending(db, routes, after):
    row = db.execute("SELECT MIN(CAST(json_extract(body,'$.occurred_at') AS REAL)) FROM messages WHERE route IN (" +
                     ",".join("?" for _ in routes) + ") AND seq>? "
                     "AND trim(COALESCE(json_extract(body,'$.text'),''))<>''", (*routes, after)).fetchone()
    return row[0] if row and row[0] else None


def due(db, route, args, config):
    domain, routes = resolve(config, route)
    now = time.time()
    after = _after_seq(db, config, domain)
    rows = _due_rows(db, routes, after)
    pending = db.execute("SELECT id,state,created_at,attempts,through_seq FROM cognition_batches WHERE route=? "
                         "AND (state IN ('prepared','dispatched') OR (state='failed' AND through_seq>?)) "
                         "ORDER BY created_at LIMIT 1", (domain, after)).fetchone()
    oldest = _oldest_pending(db, routes, after)
    age = max(0.0, now - float(oldest)) if oldest else 0.0
    window = max(300, min(7 * 86400, int(config.get("cognition_roll_seconds", 3600) or 3600)))
    idle = max(window, min(30 * 86400, int(config.get("cognition_idle_seconds", 6 * 3600) or 6 * 3600)))
    minimum = _minimum(config, domain)
    state, reason = "not_due", "waiting"
    if pending:
        if pending["state"] == "prepared":
            state, reason = "due", "prepared-retry"
        elif pending["state"] == "failed":
            state, reason = "due", "failed-retry"
        else:
            state, reason = "in_flight", "dispatched"
    elif len(rows) >= minimum:
        state, reason = "due", "threshold"
    elif len(rows) >= 2 and age >= window:
        state, reason = "due", "window"
    elif len(rows) >= 1 and age >= idle:
        state, reason = "due", "idle"
    return {"state": state, "reason": reason, "domain": domain, "new_sources": len(rows),
            "minimum": minimum, "oldest_pending_at": oldest, "oldest_pending_age_seconds": round(age, 1),
            "window_seconds": window, "idle_seconds": idle,
            "batch_id": pending["id"] if pending else None,
            "batch_state": pending["state"] if pending else None,
            "attempts": pending["attempts"] if pending else 0}


def apply_batch(db, route, sender, args, config):
    domain, routes = resolve(config, route)
    batch_id = bounded(args.get("batch_id"), 64, "batch id")
    batch = db.execute("SELECT * FROM cognition_batches WHERE id=? AND route=?", (batch_id, domain)).fetchone()
    if not batch:
        raise ValueError("native cognition batch is not bound to this scene")
    if batch["state"] == "applied":
        return {"state": "duplicate", "batch_id": batch_id}
    if batch["state"] == "discarded":
        raise ValueError("native cognition batch was discarded after source withdrawal")
    payload = args.get("payload")
    if isinstance(payload, str):
        if len(payload) > 24000:
            raise ValueError("bounded semantic payload required")
        payload = json.loads(payload)
    entries = payload.get("entries") if isinstance(payload, dict) else None
    if not isinstance(entries, list) or len(entries) > 24:
        raise ValueError("bounded native semantic entries required")
    admitted = set(json.loads(batch["sources"]))
    source_rows(db, routes, sorted(admitted))  # Recheck recalls after the model worked.
    now = time.time()
    created = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("kind") not in KINDS:
            raise ValueError("supported cognition kind required")
        kind = entry["kind"]
        key = bounded(entry.get("key"), 160, "memory key")
        body = bounded(entry.get("body"), 4000, "memory body")
        refs = entry.get("sources")
        actual = source_rows(db, routes, refs)
        if not {row["seq"] for row in actual}.issubset(admitted):
            raise ValueError("semantic sources were not in the admitted batch")
        role_refs = native_reflection.admit(db, domain, batch, entry, routes)
        confidence = number(entry.get("confidence", .5), 0, 1)
        salience = number(entry.get("salience", .5), 0, 1)
        identity = hashlib.sha256(json.dumps([domain, kind, key], separators=(",", ":")).encode()).hexdigest()
        previous = find_existing(db, domain, routes, kind, key)
        if previous and previous["status"] in {"forgotten", "withdrawn"}:
            raise ValueError("COGNITION_TOMBSTONE: only an explicit source-bound correction can restore this memory")
        if previous and (type(entry.get('expected_revision')) is not int or entry.get("expected_revision") != previous["revision"]):
            raise ValueError("COGNITION_CONFLICT: reload the memory revision")
        revision = previous["revision"] + 1 if previous else 1
        if previous:
            identity = previous["id"]
        support = {row["event_id"] for row in actual}
        status = "promoted" if kind in {"episode", "emotion", "self", "knowledge"} or len(support) >= 2 and confidence >= .7 else "candidate"
        expires = number(entry.get("ttl_seconds", 0), 0, 365 * 86400)
        model = bounded(str(args.get("source_model") or "native-executor"), 100, "source model")
        refs_json = json.dumps(sorted({row["seq"] for row in actual}))
        db.execute("INSERT INTO cognition(id,scope,kind,key,body,status,confidence,salience,sources,revision,model,created_at,updated_at,expires_at) "
                   "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET scope=excluded.scope,body=excluded.body,status=excluded.status,"
                   "confidence=excluded.confidence,salience=excluded.salience,sources=excluded.sources,revision=excluded.revision,"
                   "model=excluded.model,updated_at=excluded.updated_at,expires_at=excluded.expires_at",
                   (identity, domain, kind, key, body, status, confidence, salience, refs_json, revision, model,
                    previous["created_at"] if previous else now, now, now + expires if expires else 0))
        db.execute("INSERT INTO cognition_revisions(memory_id,revision,body,status,sources,reason,created_at) VALUES(?,?,?,?,?,?,?)",
                   (identity, revision, body, status, refs_json, "executor-semantic-settlement", now))
        if role_refs:
            db.execute('INSERT INTO cognition_role_sources(memory_id,revision,refs) VALUES(?,?,?)',
                       (identity, revision, json.dumps(role_refs)))
        created.append({"id": identity, "kind": kind, "status": status, "revision": revision,
                        "source_count": len(actual)})
    db.execute("UPDATE cognition_batches SET state='applied',settled_at=?,last_error='' WHERE id=?", (now, batch_id))
    return {"state": "applied", "batch_id": batch_id, "records": created, "legacy_imported": False,
            "platform_sends": 0, "domain": domain}


def mutate(db, route, args, config=None, *, operator=False):
    domain, routes = resolve(config or {}, route)
    scopes = _scopes(domain, routes)
    row = db.execute("SELECT * FROM cognition WHERE id=? AND scope IN (" + ",".join("?" for _ in scopes) +
                     ") ORDER BY (scope=?) DESC LIMIT 1", (args.get("id"), *scopes, domain)).fetchone()
    if not row or type(args.get('expected_revision')) is not int or args.get("expected_revision") != row["revision"]:
        raise ValueError("COGNITION_CONFLICT: exact scene/revision required")
    if not operator and domain != OWNER:
        sender = str(args.get('sender_id') or '')
        owners = owner_ids(config)
        refs = json.loads(row['sources'])
        authors = db.execute('SELECT seq,sender FROM messages WHERE route IN (' +
                             ','.join('?' for _ in routes) + ') AND seq IN (' +
                             ','.join('?' for _ in refs) + ')',
                             (*routes, *refs)).fetchall() if refs else []
        if sender not in owners and (not authors or len(authors) != len(set(refs)) or
                                     any(source['sender'] != sender for source in authors)):
            raise ValueError('COGNITION_PERMISSION: only the source author or deployment owner may correct/forget this memory')
    action = args["action"]
    now = time.time()
    if action == "workflow_used":
        if row["kind"] != "workflow":
            raise ValueError("workflow identity required")
        if row["status"] in {"forgotten", "withdrawn"} or row["expires_at"] and row["expires_at"] <= now:
            raise ValueError("inactive workflow cannot be reinforced")
        succeeded = args.get("success") is True
        db.execute("UPDATE cognition SET uses=uses+1,successes=successes+?,last_used=? WHERE id=?",
                   (int(succeeded), now, row["id"]))
        return {"state": "workflow_usage_recorded", "success": succeeded}
    reason = bounded(args.get("reason"), 500, "correction reason")
    status = "forgotten" if action == "forget_memory" else "promoted"
    body = row["body"] if action == "forget_memory" else bounded(args.get("body"), 4000, "corrected body")
    refs = row["sources"]
    if action != "forget_memory":
        actual = source_rows(db, routes, args.get("sources"))
        refs = json.dumps([source["seq"] for source in actual])
    revision = row["revision"] + 1
    db.execute("UPDATE cognition SET scope=?,body=?,status=?,sources=?,revision=?,updated_at=? WHERE id=?",
               (domain, body, status, refs, revision, now, row["id"]))
    db.execute("INSERT INTO cognition_revisions(memory_id,revision,body,status,sources,reason,created_at) VALUES(?,?,?,?,?,?,?)",
               (row["id"], revision, body, status, refs, reason, now))
    return {"state": status, "id": row["id"], "revision": revision, "old_revision_retained": True,
            "domain": domain}


def mutate_operator(db, route, args, config=None):
    """Only the dedicated authenticated Host admin subprocess calls this entry."""
    config = config or {}
    domain, routes = resolve(config, route)
    request = args.get('request_id')
    if not isinstance(request, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,80}', request):
        raise ValueError('bounded native operation identity required')
    if args.get('action') not in {'correct_memory', 'forget_memory'}:
        raise ValueError('bounded operator memory action required')
    fingerprint = hashlib.sha256(json.dumps({key: args.get(key) for key in ('action', 'id', 'expected_revision', 'reason', 'body', 'sources')},
                                           sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    prior = db.execute('SELECT * FROM cognition_admin_operations WHERE request_id=?', (request,)).fetchone()
    if prior:
        if prior['scope'] != domain or prior['fingerprint'] != fingerprint:
            raise ValueError('COGNITION_OPERATION_CONFLICT: an operation id cannot change its intent')
        return {**json.loads(prior['result']), 'duplicate': True}
    result = mutate(db, route, args, config, operator=True)
    if args['action'] == 'correct_memory':
        db.execute("UPDATE cognition SET model='owner-ui-verbatim-correction' WHERE id=? AND scope=?",
                   (result['id'], domain))
    db.execute('INSERT INTO cognition_admin_operations(request_id,scope,fingerprint,memory_id,revision,operation,reason,result,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
               (request, domain, fingerprint, result['id'], result['revision'], args['action'],
                args['reason'], json.dumps(result), time.time()))
    return {**result, 'duplicate': False, 'model_calls': 0, 'platform_sends': 0}


def context(db, route, query="", now=None, config=None):
    now = time.time() if now is None else now
    if config is not None:
        domain, routes = resolve(config, route)
    else:
        domain, routes = route, [route]
    invalidate_recalled(db, domain, now, routes)
    scopes = _scopes(domain, routes)
    rows = db.execute("SELECT * FROM cognition WHERE scope IN (" + ",".join("?" for _ in scopes) + ") "
                      "AND status IN ('candidate','promoted') AND (expires_at=0 OR expires_at>?) "
                      "AND (instr(key,?)>0 OR instr(body,?)>0) "
                      "ORDER BY (scope=?) DESC,salience DESC,updated_at DESC LIMIT 48",
                      (*scopes, now, query, query, domain)).fetchall()
    values, seen = [], set()
    for row in rows:
        identity = (row["kind"], row["key"])
        if identity in seen:
            continue
        seen.add(identity)
        half_life = 1 if row["kind"] == "workflow" else 30
        age = max(0, (now - max(row["last_used"], row["updated_at"])) / 86400)
        weight = row["salience"] * math.pow(.5, age / half_life) + min(.35, math.log1p(row["uses"]) / math.log(51) * .35)
        if weight < .02 and row["kind"] not in {"self", "person"}:
            continue
        values.append({"id": row["id"], "kind": row["kind"], "key": row["key"], "body": row["body"][:1200],
                       "status": row["status"], "confidence": row["confidence"], "revision": row["revision"],
                       "source_seqs": json.loads(row["sources"]), "effective_weight": round(weight, 4),
                       "attribution": native_reflection.attribution(db, row)})
        if len(values) >= 24:
            break
    return values


def maintain(db, now, config=None):
    """Source/TTL housekeeping only, never generate a pseudo-semantic summary."""
    scopes = [row[0] for row in db.execute("SELECT DISTINCT scope FROM cognition")]
    withdrawn = 0
    for scope in scopes:
        routes = domain_routes(config, scope) if config and scope == OWNER else ([scope] if scope != OWNER else None)
        if not routes:
            continue
        withdrawn += invalidate_recalled(db, scope, now, routes)
    expired = db.execute("SELECT * FROM cognition WHERE status IN ('candidate','promoted') AND expires_at>0 AND expires_at<=?", (now,)).fetchall()
    for row in expired:
        revision = row['revision'] + 1
        db.execute("UPDATE cognition SET status='expired',revision=?,updated_at=? WHERE id=?", (revision, now, row['id']))
        db.execute("INSERT INTO cognition_revisions(memory_id,revision,body,status,sources,reason,created_at) VALUES(?,?,?,?,?,?,?)",
                   (row['id'], revision, row['body'], 'expired', row['sources'], 'ttl-expired', now))
    return {'state': 'completed', 'kind': 'source_bound_memory_maintenance', 'scopes_examined': len(scopes),
            'withdrawn': withdrawn, 'expired': len(expired), 'summaries_created': 0,
            'semantic_promotion': False, 'model_calls': 0, 'platform_sends': 0, 'legacy_imported': False}


def call(db, config, args):
    route = args["route_id"]
    domain, routes = resolve(config, route)
    action = args["action"]
    if action == "cognition_prepare":
        return prepare(db, route, args, config)
    if action == "cognition_due":
        return due(db, route, args, config)
    if action in {"cognition_dispatched", "cognition_failed", "cognition_status"}:
        batch = db.execute("SELECT * FROM cognition_batches WHERE route=? AND id=?",
                           (domain, args.get("batch_id"))).fetchone()
        if not batch:
            raise ValueError("native cognition batch is not bound to this scene")
        if action == "cognition_dispatched":
            task = bounded(args.get("task_id"), 80, "task identity")
            if not re.fullmatch(r"action-[0-9a-f-]{36}", task):
                raise ValueError("native action task identity required")
            if batch["state"] in {"prepared", "failed", "dispatched"}:
                db.execute("UPDATE cognition_batches SET state='dispatched',task_id=?,attempts=attempts+1,last_error='' WHERE id=?",
                           (task, batch["id"]))
        if action == "cognition_failed" and batch["state"] != "applied":
            db.execute("UPDATE cognition_batches SET state='failed',settled_at=?,last_error=? WHERE id=?",
                       (time.time(), str(args.get("reason") or "executor-failed")[:240], batch["id"]))
        row = db.execute("SELECT id,state,task_id,through_seq,attempts,last_error FROM cognition_batches WHERE id=?",
                         (batch["id"],)).fetchone()
        return {"batch_id": row["id"], "state": row["state"], "task_id": row["task_id"],
                "through_seq": row["through_seq"], "attempts": row["attempts"],
                "last_error": row["last_error"], "domain": domain}
    if action == "cognition_apply":
        return apply_batch(db, route, args["sender_id"], args, config)
    if action in {"correct_memory", "forget_memory", "workflow_used"}:
        return mutate(db, route, args, config)
    if action == "cognition_read":
        return {"state": "observed", "domain": domain, "memories": context(db, route, str(args.get("query") or "")[:160], config=config)}
    raise ValueError("unsupported native cognition action")
