# SPDX-License-Identifier: GPL-3.0-only
"""Explicit private corpus and memory bridge; never imports Hermes runtime.

Legacy knowledge is queried read-only, not automatically migrated. Unscoped
legacy facts/core memories are visible only to the configured private peer.
"""
from __future__ import annotations

import json
import hashlib
import sqlite3
import sys
import time
from contextlib import contextmanager
from pathlib import Path

if __package__:
    from . import native_cognition, native_goals
else:
    # Native Host invokes this file as a subprocess, not as a package module.
    import native_cognition
    import native_goals


@contextmanager
def connect(config):
    path = Path(config["corpus_db"])
    if not path.is_absolute():
        raise ValueError("explicit corpus path required")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    path.chmod(0o600)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS messages (
            seq INTEGER PRIMARY KEY, route TEXT NOT NULL, event TEXT NOT NULL,
            sender TEXT NOT NULL, body TEXT NOT NULL, UNIQUE(route,event));
        CREATE TABLE IF NOT EXISTS facts (
            scope TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
            source TEXT NOT NULL, PRIMARY KEY(scope,key));
        CREATE TABLE IF NOT EXISTS turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route TEXT NOT NULL, session_id TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL, sender TEXT NOT NULL DEFAULT '',
            event_id TEXT NOT NULL DEFAULT '', content TEXT NOT NULL,
            platform_message_id TEXT NOT NULL DEFAULT '',
            occurred_at REAL NOT NULL, created_at REAL NOT NULL,
            UNIQUE(route, role, event_id));
        CREATE INDEX IF NOT EXISTS idx_turns_route_time ON turns(route, occurred_at, id);
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT, route TEXT NOT NULL,
            source_seq INTEGER NOT NULL DEFAULT 0, summary TEXT NOT NULL,
            participants TEXT NOT NULL DEFAULT '[]', created_at REAL NOT NULL,
            source_seqs TEXT NOT NULL DEFAULT '[]', revision INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS self_state (
            key TEXT PRIMARY KEY, value TEXT NOT NULL, source TEXT NOT NULL,
            updated_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS commitments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, route TEXT NOT NULL,
            title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
            due_at REAL NOT NULL DEFAULT 0, source TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL, updated_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS action_reports (
            id TEXT PRIMARY KEY, route TEXT NOT NULL, kind TEXT NOT NULL,
            status TEXT NOT NULL, goal TEXT NOT NULL DEFAULT '',
            report TEXT NOT NULL DEFAULT '', evidence TEXT NOT NULL DEFAULT '[]',
            created_at REAL NOT NULL, updated_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT NOT NULL,
            kind TEXT NOT NULL, content TEXT NOT NULL, source TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS scene_state (
            route TEXT PRIMARY KEY, attentive INTEGER NOT NULL DEFAULT 0,
            silent_count INTEGER NOT NULL DEFAULT 0, episode_phase TEXT NOT NULL DEFAULT 'empty',
            turn_count INTEGER NOT NULL DEFAULT 0, decision_epoch INTEGER NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS fact_revisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT NOT NULL,
            key TEXT NOT NULL, value TEXT NOT NULL, source TEXT NOT NULL,
            source_event TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL, expires_at REAL NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS idx_fact_revisions_scope_key ON fact_revisions(scope,key,id);
        CREATE TABLE IF NOT EXISTS people (
            person_id TEXT PRIMARY KEY, scope TEXT NOT NULL, display_name TEXT NOT NULL DEFAULT '',
            understanding TEXT NOT NULL, trust REAL NOT NULL DEFAULT 0.5,
            source TEXT NOT NULL DEFAULT '', updated_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS emotions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT NOT NULL, mood TEXT NOT NULL,
            intensity REAL NOT NULL DEFAULT 0.5, reason TEXT NOT NULL DEFAULT '',
            lingering INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS platform_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL, route TEXT NOT NULL DEFAULT '',
            event_id TEXT NOT NULL DEFAULT '', event_type TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'observed',
            payload TEXT NOT NULL, created_at REAL NOT NULL, UNIQUE(account_id,event_id,event_type));
        CREATE TABLE IF NOT EXISTS message_flags (
            route TEXT NOT NULL, event_id TEXT NOT NULL, flag TEXT NOT NULL,
            value TEXT NOT NULL DEFAULT '1', created_at REAL NOT NULL,
            PRIMARY KEY(route,event_id,flag));
        CREATE TABLE IF NOT EXISTS outbound_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, route TEXT NOT NULL,
            publication_id TEXT NOT NULL, platform_message_id TEXT NOT NULL,
            sender TEXT NOT NULL DEFAULT '', content TEXT NOT NULL,
            occurred_at REAL NOT NULL, created_at REAL NOT NULL,
            UNIQUE(route, platform_message_id));
    """)
    if "scope" not in {row[1] for row in db.execute("PRAGMA table_info(self_state)")}:
        db.execute("ALTER TABLE self_state ADD COLUMN scope TEXT NOT NULL DEFAULT 'owner'")
        db.commit()
    if "platform_message_id" not in {row[1] for row in db.execute("PRAGMA table_info(turns)")}:
        db.execute("ALTER TABLE turns ADD COLUMN platform_message_id TEXT NOT NULL DEFAULT ''")
        db.commit()
    fields = {row[1] for row in db.execute("PRAGMA table_info(summaries)")}
    for field, declaration in {"source_seqs": "TEXT NOT NULL DEFAULT '[]'", "revision": "INTEGER NOT NULL DEFAULT 1"}.items():
        if field not in fields:
            db.execute(f"ALTER TABLE summaries ADD COLUMN {field} {declaration}")
            db.commit()
    native_cognition.initialize(db)
    native_goals.initialize(db)
    try:
        with db:
            yield db
    finally:
        db.close()


def record(config, envelope):
    with connect(config) as db:
        # QQ can reuse a message id. Keep legacy rows intact, but use the
        # original send time in all newly persisted identities.
        old = db.execute("SELECT body FROM messages WHERE route=? AND event=?",
                         (envelope["route_id"], envelope["event_id"])).fetchone()
        if old and int(json.loads(old[0]).get("occurred_at", 0)) == int(envelope["occurred_at"]):
            return
        identity = hashlib.sha256(json.dumps([envelope["route_id"], envelope["event_id"],
                                              int(envelope["occurred_at"])], separators=(",", ":")).encode()).hexdigest()
        db.execute("INSERT OR IGNORE INTO messages(route,event,sender,body) VALUES(?,?,?,?)",
                   (envelope["route_id"], identity, envelope["sender_id"],
                    json.dumps(envelope, ensure_ascii=False)))


def call(config, args):
    route, sender = args["route_id"], args["sender_id"]
    try:
        domain, domain_routes = native_cognition.resolve(config, route)
    except ValueError:
        # Deterministic maintenance/automation jobs use a session identity, not
        # a QQ scene.  Scene-bound actions still re-resolve and reject it.
        domain, domain_routes = route, [route]
    legacy_scopes = domain_routes if domain == native_cognition.OWNER else []
    # Peer grants are deployment-owned and private-only, not inferred from text.
    # The owner Web session is bound by the Host to an admitted owner session;
    # its route resolves into the same durable owner memory domain.
    privileged = (domain == native_cognition.OWNER or
                  (args.get("message_type") == "private"
                   and sender in config.get("memory_private_peers", [])))
    action = args.get("action", "recall")
    query = str(args.get("query", ""))[:200]
    if action in {"knowledge_search", "knowledge_read"}:
        from soyo.knowledge import call as knowledge_call
        return knowledge_call(config, args, authorized=privileged)
    with connect(config) as db:
        now = time.time()
        if action in native_cognition.ACTIONS:
            return native_cognition.call(db, config, args)
        if action in {"legacy_inspect", "legacy_stage", "legacy_apply"}:
            if not privileged:
                raise ValueError("legacy memory operator grant required")
            if __package__:
                from . import native_legacy
            else:
                import native_legacy
            return native_legacy.call(db, config, args)
        if action == 'note_source_guard':
            if __package__:
                from .note_source_guard import check
            else:
                from note_source_guard import check
            return check(db, config, args, now)
        if action == "automation_context":
            hours = max(1.0, min(24.0, float(args.get("hours", 6) or 6)))
            rows = []
            for row in db.execute(
                "SELECT route,body FROM messages WHERE route LIKE 'qq-group-%' AND CAST(json_extract(body,'$.occurred_at') AS REAL)>=? ORDER BY seq DESC LIMIT 120",
                (now - hours * 3600,),
            ):
                value = json.loads(row["body"])
                if value.get("historical"):
                    continue
                rows.append({"route_id": row["route"], "sender_id": value.get("sender_id"),
                             "text": str(value.get("text") or "")[:1200], "occurred_at": value.get("occurred_at")})
            return {"state": "observed", "job_id": str(args.get("job_id") or ""), "rows": list(reversed(rows))}
        if action == "memory_maintenance":
            if config.get('cognition_enabled'):
                return native_cognition.maintain(db, now, config)
            hours = max(1.0, min(168.0, float(args.get("hours", 24) or 24)))
            cutoff = now - hours * 3600
            routes = [row[0] for row in db.execute(
                "SELECT DISTINCT route FROM messages WHERE route LIKE 'qq-group-%' "
                "AND CAST(json_extract(body,'$.occurred_at') AS REAL)>=? ORDER BY route", (cutoff,))]
            created, examined = 0, 0
            for target_route in routes:
                rows = db.execute(
                    "SELECT seq,body FROM messages WHERE route=? AND CAST(json_extract(body,'$.occurred_at') AS REAL)>=? "
                    "ORDER BY seq ASC LIMIT 200", (target_route, cutoff)).fetchall()
                if not rows:
                    continue
                examined += len(rows)
                source_seq = int(rows[-1]["seq"])
                previous = db.execute(
                    "SELECT 1 FROM summaries WHERE route=? AND source_seq>=? LIMIT 1",
                    (target_route, source_seq),
                ).fetchone()
                if previous:
                    continue
                values = [json.loads(row["body"]) for row in rows]
                participants = sorted({str(value.get("sender_id") or "") for value in values if value.get("sender_id")})[:32]
                snippets = [str(value.get("text") or "").strip().replace("\n", " ")[:180] for value in values[-12:]]
                snippets = [item for item in snippets if item]
                summary = f"公开群聊整理：{len(rows)} 条消息；最近内容：" + " / ".join(snippets)
                db.execute(
                    "INSERT INTO summaries(route,source_seq,summary,participants,created_at) VALUES(?,?,?,?,?)",
                    (target_route, source_seq, summary[:12000], json.dumps(participants, ensure_ascii=False), now),
                )
                created += 1
            return {"state": "completed", "kind": "memory_maintenance", "hours": hours,
                    "routes_examined": len(routes), "messages_examined": examined,
                    "summaries_created": created, "semantic_promotion": False,
                    "note": "确定性公开场景整理；未读取旧 Hermes memory，未进行模型语义晋升或外部发布。"}
        if action == "platform_event":
            raw = args.get("event") if isinstance(args.get("event"), dict) else {}
            clean = {key: value for key, value in raw.items() if key not in {"access_token", "token", "cookies", "secret"}}
            event_type = str(raw.get("request_type") or raw.get("notice_type") or raw.get("post_type") or "unknown")[:80]
            event_id = str(raw.get("request_id") or raw.get("message_id") or raw.get("time") or "")[:160]
            target = str(raw.get("group_id") or raw.get("user_id") or "")
            db.execute("INSERT OR IGNORE INTO platform_events(account_id,route,event_id,event_type,status,payload,created_at) VALUES(?,?,?,?,?,?,?)",
                       (str(config.get("account_id") or ""), "qq-" + event_type + "-" + target if target else "", event_id, event_type, "observed", json.dumps(clean, ensure_ascii=False)[:30000], now))
            if raw.get("notice_type") == "group_recall" and raw.get("group_id") and raw.get("message_id"):
                db.execute("INSERT OR REPLACE INTO message_flags(route,event_id,flag,value,created_at) VALUES(?,?,?,?,?)",
                           ("qq-group-" + str(raw["group_id"]), str(raw["message_id"]), "recalled", "1", now))
            return {"state": "platform_event_recorded", "event_type": event_type}
        if action == "attach_forward":
            event_id = str(args.get("event_id") or "")[:160]
            value = args.get("forward_context") if isinstance(args.get("forward_context"), dict) else {}
            row = db.execute(
                "SELECT seq,body FROM messages WHERE route=? AND json_extract(body,'$.event_id')=? ORDER BY seq DESC LIMIT 1",
                (route, event_id),
            ).fetchone()
            if not row:
                return {"state": "forward_not_attached", "reason": "message_not_found", "event_id": event_id}
            body = json.loads(row["body"]); body["forward_context"] = value
            db.execute("UPDATE messages SET body=? WHERE seq=?", (json.dumps(body, ensure_ascii=False), row["seq"]))
            return {"state": "forward_attached", "event_id": event_id}
        if action == "automation_watchdog":
            try:
                from native_tools import call as native_action
                login = native_action(config, {"action": "get_status", "params": {}, "sender_id": sender, "route_id": route})
            except Exception as error:
                login = {"success": False, "error": type(error).__name__}
            status_file = Path(str(config.get("status_file") or ""))
            status = json.loads(status_file.read_text(encoding='utf-8')) if status_file.is_file() else {}
            socket_ok = Path(str(config.get("host_socket") or "")).exists() and status.get("state") == "connected" and now - float(status.get("updated_at") or 0) < 30
            alert = ""
            if not login.get("success") or not socket_ok or (login.get("data") or {}).get("online") is False:
                alert = "⚠️ Bot transport watchdog: OneBot/native host health is not fully ready。"
            old = db.execute("SELECT value FROM self_state WHERE key='transport-watchdog'").fetchone()
            state = json.loads(old[0]) if old else {}
            unhealthy = bool(alert)
            unhealthy_count = int(state.get("unhealthy_count") or 0) + 1 if unhealthy else 0
            # A schedule can run during the short DSH/OneBot reconnect window.
            # Do not publish a private alarm for one transient observation;
            # require two consecutive unhealthy checks before notifying owner.
            if alert and unhealthy_count < 2:
                alert = ""
            if alert and now - float(state.get("last_alert") or 0) < 300:
                alert = ""
            db.execute("INSERT INTO self_state(key,value,source,updated_at) VALUES(?,?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                       ("transport-watchdog", json.dumps({"last_alert": now if alert else state.get("last_alert", 0),
                           "healthy": not unhealthy, "unhealthy_count": unhealthy_count}), "native-watchdog", now))
            return {"state": "observed", "login": login, "native_socket": socket_ok, "alert": alert}
        if action == "social_event":
            row = db.execute("SELECT * FROM scene_state WHERE route=?", (route,)).fetchone()
            values = dict(row) if row else {"route": route, "attentive": 0, "silent_count": 0,
                                             "episode_phase": "empty", "turn_count": 0, "decision_epoch": 0}
            if bool(args.get("mentioned")) and not bool(args.get("historical")):
                values.update(attentive=1, silent_count=0,
                              episode_phase="starting" if values.get("episode_phase") in {"empty", "exiting", "winding_down"} else "mid")
            db.execute("INSERT INTO scene_state(route,attentive,silent_count,episode_phase,turn_count,decision_epoch,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(route) DO UPDATE SET attentive=excluded.attentive,silent_count=excluded.silent_count,episode_phase=excluded.episode_phase,updated_at=excluded.updated_at",
                       (route, int(values.get("attentive", 0)), int(values.get("silent_count", 0)), values.get("episode_phase", "empty"),
                        int(values.get("turn_count", 0)), int(values.get("decision_epoch", 0)), now))
            return {"state": "social_event_recorded", "route_id": route}
        if action == "social_reply":
            db.execute("INSERT INTO scene_state(route,attentive,silent_count,episode_phase,turn_count,decision_epoch,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(route) DO UPDATE SET attentive=1,silent_count=0,episode_phase='mid',turn_count=scene_state.turn_count+1,updated_at=excluded.updated_at",
                       (route, 1, 0, "mid", 1, 0, now))
            return {"state": "social_reply_recorded", "route_id": route}
        if action == "attach_receipt":
            publication_id = str(args.get("publication_id") or "")[:200]
            platform_message_id = str(args.get("platform_message_id") or "")[:160]
            if not publication_id or not platform_message_id:
                raise ValueError("receipt identity required")
            updated = db.execute(
                "UPDATE turns SET platform_message_id=? WHERE route=? AND role='assistant' AND event_id=?",
                (platform_message_id, route, publication_id),
            ).rowcount
            turn = db.execute(
                "SELECT content,occurred_at,sender FROM turns WHERE route=? AND role='assistant' AND event_id=? LIMIT 1",
                (route, publication_id),
            ).fetchone()
            if turn:
                db.execute(
                    "INSERT OR REPLACE INTO outbound_messages(route,publication_id,platform_message_id,sender,content,occurred_at,created_at) VALUES(?,?,?,?,?,?,?)",
                    (route, publication_id, platform_message_id, turn["sender"], turn["content"], turn["occurred_at"], now),
                )
            return {"state": "receipt_attached", "route_id": route,
                    "publication_id": publication_id, "platform_message_id": platform_message_id,
                    "updated": bool(updated)}
        if action == "record_outbound":
            publication_id = str(args.get("publication_id") or "")[:200]
            platform_message_id = str(args.get("platform_message_id") or "")[:160]
            content = str(args.get("content") or "")[:16000]
            if not publication_id or not platform_message_id or not content:
                raise ValueError("outbound receipt identity/content required")
            db.execute(
                "INSERT OR REPLACE INTO outbound_messages(route,publication_id,platform_message_id,sender,content,occurred_at,created_at) VALUES(?,?,?,?,?,?,?)",
                (route, publication_id, platform_message_id, str(args.get("sender_id") or config.get("account_id") or "")[:80],
                 content, float(args.get("occurred_at") or now), now),
            )
            return {"state": "outbound_recorded", "route_id": route,
                    "publication_id": publication_id, "platform_message_id": platform_message_id}
        if action == "remember":
            key, value = str(args.get("key", ""))[:160], str(args.get("value", ""))[:2000]
            if not key.strip() or not value.strip():
                raise ValueError("key and value required")
            scope = "global" if privileged and args.get("shared") is True else domain
            db.execute("INSERT INTO fact_revisions(scope,key,value,source,source_event,reason,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?)",
                       (scope, key, value, sender, str(args.get("event_id") or "")[:200],
                        str(args.get("reason") or "")[:500], now,
                        now + min(365 * 86400, max(0, float(args.get("ttl_seconds") or 0))) if args.get("ttl_seconds") else 0))
            db.execute("INSERT INTO facts VALUES(?,?,?,?) ON CONFLICT(scope,key) DO UPDATE SET value=excluded.value,source=excluded.source",
                       (scope, key, value, sender))
            return {"state": "stored", "scope": "shared" if scope == "global" else ("owner" if domain == native_cognition.OWNER else "scene")}
        if action == "person":
            if args.get("message_type") != "private" or not privileged:
                raise ValueError("person understanding requires an authorized private owner scene")
            person_id = str(args.get("person_id") or sender)[:80]
            understanding = str(args.get("understanding") or "")[:4000]
            if not understanding.strip(): raise ValueError("person understanding required")
            db.execute("INSERT INTO people(person_id,scope,display_name,understanding,trust,source,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(person_id) DO UPDATE SET display_name=excluded.display_name,understanding=excluded.understanding,trust=excluded.trust,source=excluded.source,updated_at=excluded.updated_at",
                       (person_id, domain, str(args.get("display_name") or person_id)[:160], understanding,
                        max(0.0, min(1.0, float(args.get("trust", 0.5)))), sender, now))
            return {"state": "person_recorded", "person_id": person_id}
        if action == "feel":
            if not privileged:
                raise ValueError("private feeling update requires owner grant")
            mood = str(args.get("mood") or "").strip()[:80]; reason = str(args.get("reason") or "")[:1000]
            intensity = max(0.0, min(1.0, float(args.get("intensity", 0.5))))
            if not mood: raise ValueError("mood required")
            db.execute("INSERT INTO emotions(scope,mood,intensity,reason,lingering,source,created_at) VALUES(?,?,?,?,?,?,?)",
                       ("global" if args.get("shared") is True else domain, mood, intensity, reason,
                        int(bool(args.get("lingering"))), sender, now))
            return {"state": "emotion_recorded", "mood": mood, "intensity": intensity}
        if action == "record_owner_message":
            if domain != native_cognition.OWNER or not route.startswith("dsh-owner:"):
                raise ValueError("owner Web memory route required")
            text = str(args.get("text") or "")[:16000]
            event_id = str(args.get("event_id") or "")[:200]
            occurred_at = float(args.get("occurred_at") or now)
            if not text.strip() or not event_id:
                raise ValueError("owner Web message identity/content required")
            identity = hashlib.sha256(json.dumps([route, event_id, int(occurred_at)], separators=(",", ":")).encode()).hexdigest()
            envelope = {"route_id": route, "event_id": event_id, "sender_id": sender or "owner",
                        "message_type": "private", "target_id": sender or "owner", "text": text,
                        "occurred_at": occurred_at, "source": "owner-web", "historical": False}
            db.execute("INSERT OR IGNORE INTO messages(route,event,sender,body) VALUES(?,?,?,?)",
                       (route, identity, sender or "owner", json.dumps(envelope, ensure_ascii=False)))
            return {"state": "owner_message_recorded", "route_id": route, "domain": domain,
                    "duplicate": db.execute("SELECT changes()").fetchone()[0] == 0}
        if action in {"record_turn", "record_assistant"}:
            role = str(args.get("role") or ("assistant" if action == "record_assistant" else "user"))[:32]
            content = str(args.get("content") or "")[:16000]
            event_id = str(args.get("event_id") or "")[:200]
            if not content.strip():
                raise ValueError("turn content required")
            db.execute("INSERT OR IGNORE INTO turns(route,session_id,role,sender,event_id,content,platform_message_id,occurred_at,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                       (route, str(args.get("session_id") or "")[:160], role, sender,
                         event_id, content, str(args.get("platform_message_id") or "")[:160],
                         float(args.get("occurred_at") or now), now))
            return {"state": "turn_recorded", "route_id": route, "role": role}
        if action == "record_summary":
            summary = str(args.get("summary") or "")[:12000]
            if not summary.strip():
                raise ValueError("summary required")
            source_seq = int(args.get("source_seq") or 0)
            source_seqs = args.get("source_seqs")
            if source_seqs is None:
                source_seqs = [source_seq] if source_seq else []
            if not isinstance(source_seqs, list) or len(source_seqs) > 48 or any(type(seq) is not int or seq < 1 for seq in source_seqs):
                raise ValueError("bounded summary sources required")
            if source_seqs:
                native_cognition.source_rows(db, domain_routes, sorted(set(source_seqs)))
                source_seq = max(source_seqs) if source_seqs else 0
            db.execute("INSERT INTO summaries(route,source_seq,summary,participants,created_at,source_seqs) VALUES(?,?,?,?,?,?)",
                       (domain, source_seq, summary,
                        json.dumps(args.get("participants") or [], ensure_ascii=False), now,
                        json.dumps(sorted(set(source_seqs)))))
            return {"state": "summary_recorded", "route_id": domain, "source_bound": bool(source_seqs)}
        if action == "self_state":
            if not privileged:
                raise ValueError("self state changes require an owner-private grant")
            key = str(args.get("key") or "").strip()[:120]
            value = str(args.get("value") or "")[:4000]
            if not key or not value:
                raise ValueError("self state key/value required")
            db.execute("INSERT INTO self_state(key,value,source,updated_at,scope) VALUES(?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,source=excluded.source,updated_at=excluded.updated_at,scope=excluded.scope",
                       (key, value, sender or "native", now, "public" if args.get("shared") is True else ("owner" if domain == native_cognition.OWNER else domain)))
            return {"state": "self_state_recorded", "key": key}
        if action == "commitment":
            return native_goals.call(db, config, args, privileged)
        if action == "note":
            kind = str(args.get("kind") or "reflection").strip()[:40]
            content = str(args.get("content") or "")[:6000]
            scope = "global" if privileged and args.get("shared") is True else domain
            if not content.strip():
                raise ValueError("note content required")
            db.execute("INSERT INTO notes(scope,kind,content,source,created_at) VALUES(?,?,?,?,?)",
                       (scope, kind, content, sender, now))
            return {"state": "note_recorded", "scope": scope, "kind": kind}
        if action == "action_report":
            action_id = str(args.get("id") or "").strip()[:160]
            status = str(args.get("status") or "").strip()[:32]
            if not action_id or status not in {"queued", "running", "completed", "failed", "unknown", "cancelled"}:
                raise ValueError("bounded action report required")
            db.execute("INSERT INTO action_reports(id,route,kind,status,goal,report,evidence,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,report=excluded.report,evidence=excluded.evidence,updated_at=excluded.updated_at",
                       (action_id, route, str(args.get("kind") or "action")[:40], status,
                        str(args.get("goal") or "")[:2000], str(args.get("report") or "")[:12000],
                        json.dumps(args.get("evidence") or [], ensure_ascii=False), now, now))
            return {"state": "action_recorded", "id": action_id, "status": status}
        fact_scopes = list(dict.fromkeys([domain, "global", *legacy_scopes]))
        fact_marks = ",".join("?" for _ in fact_scopes)
        fact_rows = db.execute(
            "SELECT f.scope,f.key,f.value,f.source FROM facts f WHERE scope IN (" + fact_marks + ") AND (f.key LIKE ? OR f.value LIKE ?) "
            "AND NOT EXISTS (SELECT 1 FROM fact_revisions r WHERE r.scope=f.scope AND r.key=f.key "
            "AND r.id=(SELECT MAX(v.id) FROM fact_revisions v WHERE v.scope=f.scope AND v.key=f.key) "
            "AND r.expires_at>0 AND r.expires_at<=?) ORDER BY (scope=?) DESC,f.key LIMIT 64",
            (*fact_scopes, "%" + query + "%", "%" + query + "%", now, domain))
        facts, seen_facts = [], set()
        for row in fact_rows:
            if row["key"] in seen_facts:
                continue
            seen_facts.add(row["key"])
            facts.append(dict(row))
            if len(facts) >= 12:
                break
        # Legacy Hermes is an explicit recall source, never ambient QQ
        # context. The old implementation treated an empty context query as
        # LIKE '%%' and injected unrelated private/group history into every
        # owner DM turn.
        legacy = []
        old = Path(config.get("legacy_memory_db", ""))
        if action == "recall" and not query.strip():
            raise ValueError("legacy recall requires an explicit query")
        if action == "recall" and privileged and old.is_file():
            with sqlite3.connect(old.resolve().as_uri() + "?mode=ro", uri=True) as source:
                source.execute("PRAGMA query_only=ON")
                legacy = [{"key": row[0], "value": row[1], "origin": "legacy_read_only"}
                          for row in source.execute(
                              "SELECT key,value FROM long_term_entries WHERE active=1 AND (key LIKE ? OR value LIKE ?) ORDER BY updated_at DESC LIMIT 12",
                              ("%" + query + "%", "%" + query + "%"))]
        turn_scopes = list(dict.fromkeys([domain, *legacy_scopes]))
        turns = []
        if action in {"context", "recall"}:
            turns = [dict(row) for row in db.execute(
                "SELECT role,sender,event_id,content,occurred_at FROM turns WHERE route IN (" +
                ",".join("?" for _ in turn_scopes) + ") AND (content LIKE ? OR ?='') "
                "ORDER BY occurred_at DESC,id DESC LIMIT 20",
                (*turn_scopes, "%" + query + "%", query if action == "recall" else ""))]
            turns.reverse()
            for item in turns:
                if db.execute("SELECT 1 FROM message_flags WHERE route IN (" +
                              ",".join("?" for _ in domain_routes) + ") AND event_id=? AND flag='recalled'",
                              (*domain_routes, item["event_id"])).fetchone():
                    item["content"] = "[该来源已撤回]"; item["recalled"] = True
        result = {"state": "observed", "domain": domain, "facts": facts, "legacy": legacy, "turns": turns}
        if action in {"context", "recall"}:
            result["cognition"] = native_cognition.context(db, route, query if action == "recall" else "", now, config=config)
        if action == "context":
            result['speak_from_program'] = {'one_self': '你保持私有人格文件中的同一身份，同时在不同会话生活；你在这里说过的话就是你自己说的。这里不带其他场景的聊天或权限。'}
            # Only enum/intensity from public native Soyo expressions may linger
            # across scenes. All source text/person records stay in their scene.
            for scope in [row[0] for row in db.execute("SELECT DISTINCT scope FROM cognition WHERE kind='emotion' AND status='promoted' AND scope LIKE 'qq-group-%'")]:
                native_cognition.invalidate_recalled(db, scope, now, [scope])
            result['lingering_self_affect'] = native_cognition.native_reflection.shared_affect(db, now)
            # Only the admitted @/DM asks for a context build. Ambient events just INSERT.
            boundary = db.execute("SELECT seq FROM messages WHERE route IN (" +
                                   ",".join("?" for _ in domain_routes) + ") AND json_extract(body,'$.event_id')=? "
                                   "AND CAST(json_extract(body,'$.occurred_at') AS INTEGER)=? ORDER BY seq DESC LIMIT 1",
                                   (*domain_routes, args["event_id"], int(args["occurred_at"]))).fetchone()
            rows = db.execute("SELECT route,body FROM messages WHERE route IN (" +
                              ",".join("?" for _ in domain_routes) + ") AND seq<=? ORDER BY seq DESC LIMIT 30",
                              (*domain_routes, boundary[0] if boundary else 0)).fetchall()
            result["recent"] = [{key: value for key, value in json.loads(row["body"]).items()
                                 if key in {"route_id", "event_id", "sender_id", "text", "occurred_at", "media", "reply_to", "forward_context"}}
                                 for row in reversed(rows)]
            for item in result["recent"]:
                if db.execute("SELECT 1 FROM message_flags WHERE route=? AND event_id=? AND flag='recalled'",
                              (item.get("route_id") or route, item["event_id"])).fetchone():
                    item["text"] = "[该来源已撤回]"; item["media"] = []; item.pop("forward_context", None); item["recalled"] = True
                else:
                    item["text"] = item["text"][:800]
            for item in result["facts"] + result["legacy"]:
                item["value"] = str(item["value"])[:800]
            summaries = []
            for row in db.execute(
                    "SELECT summary,participants,created_at,source_seq,source_seqs FROM summaries "
                    "WHERE route=? AND source_seq>0 ORDER BY id DESC LIMIT 8", (domain,)):
                refs = json.loads(row["source_seqs"]) if row["source_seqs"] else [row["source_seq"]]
                try:
                    native_cognition.source_rows(db, domain_routes, refs)
                except ValueError:
                    continue
                summaries.append({"summary": row["summary"], "participants": json.loads(row["participants"]),
                                  "created_at": row["created_at"], "source_seqs": refs})
                if len(summaries) >= 4:
                    break
            result["summaries"] = summaries
            state_scopes = list(dict.fromkeys(["public", domain, *legacy_scopes]))
            state_rows = db.execute(
                "SELECT scope,key,value,updated_at FROM self_state WHERE scope IN (" +
                ",".join("?" for _ in state_scopes) + ") ORDER BY updated_at DESC LIMIT 24", state_scopes).fetchall()
            self_state, seen_state = [], set()
            for row in state_rows:
                if row["key"] in seen_state:
                    continue
                seen_state.add(row["key"]); self_state.append({"key": row["key"], "value": row["value"], "updated_at": row["updated_at"]})
                if len(self_state) >= 12: break
            result["self_state"] = self_state
            goal_scopes = list(dict.fromkeys([domain, *legacy_scopes]))
            result["commitments"] = [dict(row) for row in db.execute(
                "SELECT id,title,status,due_at,revision FROM commitments WHERE route IN (" +
                ",".join("?" for _ in goal_scopes) + ") AND status IN ('open','blocked','snoozed') ORDER BY id DESC LIMIT 12", goal_scopes)]
            person_scopes = list(dict.fromkeys([domain, "global", *legacy_scopes]))
            people_rows = db.execute(
                "SELECT person_id,display_name,understanding,trust,updated_at FROM people WHERE scope IN (" +
                ",".join("?" for _ in person_scopes) + ") ORDER BY updated_at DESC LIMIT 24", person_scopes).fetchall()
            people, seen_people = [], set()
            for row in people_rows:
                if row["person_id"] in seen_people: continue
                seen_people.add(row["person_id"]); people.append(dict(row))
                if len(people) >= 12: break
            result["people"] = people
            result["emotions"] = [dict(row) for row in db.execute(
                "SELECT mood,intensity,reason,lingering,created_at FROM emotions WHERE scope IN (" +
                ",".join("?" for _ in person_scopes) + ") ORDER BY id DESC LIMIT 8", person_scopes)]
            # Outbound native replies are kept in turns, not in the inbound
            # message table.  Surface them explicitly so the role brain can
            # see what it previously generated in this scene instead of
            # claiming that its own messages are invisible.  This is bounded
            # context only; delivery still requires a separate platform
            # receipt and is never inferred here.
            assistant_rows = db.execute(
                "SELECT sender,event_id,content,occurred_at FROM turns "
                "WHERE route IN (" + ",".join("?" for _ in turn_scopes) + ") AND role='assistant' "
                "ORDER BY occurred_at DESC,id DESC LIMIT 12",
                turn_scopes,
            ).fetchall()
            result["assistant_recent"] = [
                {"role": "assistant", "sender": row["sender"], "event_id": row["event_id"],
                 "content": str(row["content"])[:4000], "occurred_at": row["occurred_at"]}
                for row in reversed(assistant_rows)
            ]
            reply_id = str(args.get("reply_to") or "")[:160]
            if reply_id:
                message = db.execute(
                    "SELECT route,body FROM messages WHERE route IN (" +
                    ",".join("?" for _ in domain_routes) + ") AND json_extract(body,'$.event_id')=? "
                    "ORDER BY seq DESC LIMIT 1", (*domain_routes, reply_id)).fetchone()
                if message:
                    value = json.loads(message["body"])
                    result["reply_context"] = {"state": "resolved", "kind": "inbound",
                        "message_id": reply_id, "sender_id": value.get("sender_id"),
                        "text": str(value.get("text") or "")[:8000],
                        "occurred_at": value.get("occurred_at"), "media": value.get("media") or []}
                    if db.execute("SELECT 1 FROM message_flags WHERE route=? AND event_id=? AND flag='recalled'", (message["route"], reply_id)).fetchone():
                        result["reply_context"] = {"state": "recalled", "message_id": reply_id}
                else:
                    turn = db.execute(
                        "SELECT role,sender,event_id,platform_message_id,content,occurred_at FROM turns "
                        "WHERE route IN (" + ",".join("?" for _ in turn_scopes) + ") AND (platform_message_id=? OR event_id=?) "
                        "ORDER BY id DESC LIMIT 1", (*turn_scopes, reply_id, reply_id)).fetchone()
                    if turn:
                        result["reply_context"] = {"state": "resolved", "kind": turn["role"],
                            "message_id": reply_id, "sender_id": turn["sender"],
                            "publication_id": turn["event_id"],
                            "text": str(turn["content"] or "")[:8000],
                            "occurred_at": turn["occurred_at"]}
                    else:
                        outbound = db.execute(
                            "SELECT publication_id,platform_message_id,sender,content,occurred_at FROM outbound_messages "
                            "WHERE route IN (" + ",".join("?" for _ in domain_routes) +
                            ") AND platform_message_id=? ORDER BY id DESC LIMIT 1", (*domain_routes, reply_id)).fetchone()
                        if outbound:
                            result["reply_context"] = {"state": "resolved", "kind": "assistant",
                                "message_id": reply_id, "sender_id": outbound["sender"],
                                "publication_id": outbound["publication_id"],
                                "text": str(outbound["content"] or "")[:8000],
                                "occurred_at": outbound["occurred_at"]}
                        else:
                            result["reply_context"] = {"state": "unavailable", "message_id": reply_id}
            else:
                result["reply_context"] = {"state": "not_requested"}
            result["scene_state"] = dict(db.execute("SELECT attentive,silent_count,episode_phase,turn_count,decision_epoch,updated_at FROM scene_state WHERE route=?", (route,)).fetchone() or {})
            # Legacy remains an explicit operator source in recall; it is never
            # silently injected into the resident scene context.
            result["legacy"] = []
        return result


if __name__ == "__main__":
    from soyo.platform import load_private_json
    config = load_private_json(Path(sys.argv[1]))
    arguments = json.loads(sys.stdin.buffer.read(64 * 1024))
    print(json.dumps(call(config, arguments), ensure_ascii=False))
