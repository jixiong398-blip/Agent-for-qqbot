# SPDX-License-Identifier: GPL-3.0-only
"""Bounded operator projections; all database connections are read-only.

The native Host derives the route from its own session binding. This process
does not accept filesystem paths from a browser and never initializes a DB.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3
import sys
import time


def text(value, limit=16000):
    return re.sub(r"\bsk-[A-Za-z0-9_-]{16,}", "<credential-redacted>", str(value or ""))[:limit]


@contextmanager
def reading(path):
    path = Path(path)
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise ValueError("read-only data source unavailable")
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    try:
        yield db
    finally:
        db.close()


def source(row):
    envelope = json.loads(row["body"])
    result = {"id": str(row["seq"]), "event_id": envelope["event_id"],
            "sender_id": envelope["sender_id"], "occurred_at": envelope.get("occurred_at"),
            "text": text(envelope.get("text")), "historical": bool(envelope.get("historical")),
            "media_count": len(envelope.get("media") or []),
            "mentioned_account_ids": envelope.get("mentioned_account_ids", [])}
    forward = envelope.get("forward_context")
    if isinstance(forward, dict):
        result["forward_context"] = {"state": forward.get("state"), "refs": forward.get("refs", []),
                                      "nodes": forward.get("nodes", [])[:64],
                                      "errors": forward.get("errors", [])[:8], "truncated": bool(forward.get("truncated")),
                                      "limits": forward.get("limits", []), "expanded_refs": forward.get("expanded_refs", [])[:8]}
        if forward.get("state") in {"resolved", "partial"} and forward.get("text"):
            result["forward_text"] = text(forward["text"], 12000)
    return result


def scopes(config, route):
    allowed = ["global", route]
    owners = {str(value) for value in
              dict.fromkeys([*config.get("admin_ids", []), *config.get("memory_private_peers", [])])}
    if route.startswith("qq-private-") and route.removeprefix("qq-private-") in owners:
        allowed.append("owner")
    return allowed


def cognition_available(db):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cognition'").fetchone())


def goal_row(found):
    return {'id':str(found['id']),'kind':'goal','title':text(found['title'],300),
            'text':text(found['title'],300),'status':found['status'],'revision':found['revision'] if 'revision' in found.keys() else 1,
            'due_at':found['due_at'],'source':found['source'],'scope':found['route'],
            'occurred_at':found['created_at'],'updated_at':found['updated_at']}


def source_routes(config, route):
    owners = {str(value) for value in
              dict.fromkeys([*config.get("admin_ids", []), *config.get("memory_private_peers", [])])}
    if route.startswith("qq-private-") and route.removeprefix("qq-private-") in owners:
        return ["qq-private-" + str(peer) for peer in
                dict.fromkeys([*config.get("admin_ids", []), *config.get("memory_private_peers", [])])] + \
               ["dsh-owner:" + str(session) for session in
                dict.fromkeys(["soyo-owner", *config.get("owner_sessions", []),
                               *((config.get("collaborator") or {}).get("owner_sessions") or [])])]
    return [route]


def cognition_row(db, config, route, found):
    status = found["status"]
    refs = json.loads(found["sources"])
    routes = source_routes(config, route) if found["scope"] == "owner" else [found["scope"]]
    recalled = db.execute("SELECT 1 FROM messages m JOIN message_flags f ON f.route=m.route "
                          "AND f.event_id=json_extract(m.body,'$.event_id') AND f.flag='recalled' "
                          "WHERE m.route IN (" + ','.join('?' for _ in routes) + ") AND m.seq IN (" +
                          ','.join('?' for _ in refs) + ') LIMIT 1', (*routes, *refs)).fetchone() if refs else None
    if recalled and status != "forgotten":
        status = "withdrawn"
    elif found["expires_at"] and found["expires_at"] <= time.time() and status not in {"forgotten", "withdrawn"}:
        status = "expired"
    attribution = {'subject': 'scene-observation', 'basis': 'qq-source-interpretation', 'role_sources': []}
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='cognition_role_sources'").fetchone():
        role = db.execute('SELECT refs FROM cognition_role_sources WHERE memory_id=? AND revision=?', (found['id'], found['revision'])).fetchone()
        if role:
            attribution = {'subject': 'soyo', 'basis': 'native-role-expression', 'role_sources': json.loads(role['refs'])}
    return {"id": found["id"], "kind": "cognition", "title": text(found["key"], 160), "text": text(found["body"], 4000),
            "status": status, "memory_kind": found["kind"], "revision": found["revision"],
            "source_seqs": refs, "scope": found["scope"], "model": found["model"],
            "confidence": found["confidence"], "occurred_at": found["created_at"], "updated_at": found["updated_at"], 'attribution': attribution}


def detail(config, route, kind, record_id):
    """Exact scoped record reads for the author Memory disclosure, no page scans."""
    if not isinstance(record_id, str) or len(record_id) > 2048:
        raise ValueError("bounded record identity required")
    with reading(config["corpus_db"]) as db:
        row, sources = None, []
        allowed = scopes(config, route)
        scope_sql = ",".join("?" for _ in allowed)
        if kind == "messages":
            found = db.execute("SELECT seq,body FROM messages WHERE route=? AND seq=?", (route, record_id)).fetchone()
            if found:
                row = {**source(found), "kind": "source", "title": "QQ · " + source(found)["sender_id"]}
                if db.execute("SELECT 1 FROM message_flags WHERE route=? AND event_id=? AND flag='recalled'", (route, row["event_id"])).fetchone():
                    row["recalled"] = True
                    row["text"] = "[已撤回] " + row["text"]
        elif kind == "facts":
            scope, _, key = record_id.partition(":")
            if scope not in allowed:
                raise ValueError("record belongs to a different scene")
            found = db.execute("SELECT scope,key,value,source FROM facts WHERE scope=? AND key=?", (scope, key)).fetchone()
            if found:
                row = {"id": record_id, "kind": "fact", "title": text(found["key"], 160), "text": text(found["value"], 2000),
                       "scope": "shared" if scope == "global" else "scene", "sender_id": found["source"]}
        elif kind == "cognition":
            found = db.execute("SELECT * FROM cognition WHERE id=? AND scope IN (" + scope_sql + ") ORDER BY (scope=?) DESC LIMIT 1",
                               (record_id, *allowed, route)).fetchone() if cognition_available(db) else None
            if found:
                row = cognition_row(db, config, route, found)
                routes = source_routes(config, route) if found["scope"] == "owner" else [found["scope"]]
                route_sql = ",".join("?" for _ in routes)
                row['role_sources'] = []
                for identifier in row['attribution']['role_sources']:
                    expression = db.execute('SELECT body,created_at FROM role_reflections WHERE route IN (' +
                                            route_sql + ') AND id=?', (*routes, identifier)).fetchone()
                    if expression:
                        value = json.loads(expression['body'])
                        row['role_sources'].append({**value, 'thought': text(value['thought'], 360), 'occurred_at': expression['created_at']})
                for seq in row["source_seqs"]:
                    original = db.execute("SELECT seq,route,body FROM messages WHERE route IN (" +
                                          route_sql + ") AND seq=?", (*routes, seq)).fetchone()
                    if original:
                        item = source(original)
                        if db.execute("SELECT 1 FROM message_flags WHERE route=? AND event_id=? AND flag='recalled'",
                                      (original["route"], item["event_id"])).fetchone():
                            item["recalled"] = True; item["text"] = "[已撤回] " + item["text"]
                        sources.append(item)
                row["revisions"] = [dict(revision) for revision in db.execute(
                    "SELECT revision,status,reason,created_at FROM cognition_revisions WHERE memory_id=? ORDER BY revision DESC LIMIT 8", (row["id"],))]
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cognition_admin_operations'").fetchone():
                    row['operator_corrections'] = [dict(value) for value in db.execute(
                        'SELECT request_id,revision,operation,reason,created_at FROM cognition_admin_operations WHERE memory_id=? AND scope IN (' +
                        scope_sql + ') ORDER BY revision DESC LIMIT 8', (row['id'], *allowed))]
        elif kind == 'goals':
            found=db.execute('SELECT * FROM commitments WHERE id=? AND route=?',(record_id,route)).fetchone()
            if found:
                row=goal_row(found);row['revisions']=[];row['operations']=[]
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='commitment_revisions'").fetchone():
                    row['revisions']=[{**dict(value),'body':json.loads(value['body']),'evidence':json.loads(value['evidence'])} for value in db.execute(
                        'SELECT revision,body,evidence,created_at FROM commitment_revisions WHERE goal_id=? ORDER BY revision DESC LIMIT 12',(found['id'],))]
                    row['operations']=[dict(value) for value in db.execute('SELECT request_id,created_at FROM commitment_operations WHERE goal_id=? AND route=? ORDER BY created_at DESC LIMIT 12',(found['id'],route))]
                row['text']+='\n\n【目标状态与原生效果链接；不等于自动判断任意目标已验收】\n'+text(json.dumps(
                    {'id':found['id'],'revision':row['revision'],'status':found['status'],'due_at':found['due_at'],
                     'revisions':row['revisions'],'operations':row['operations']},ensure_ascii=False,indent=2),14000)
        elif kind == "turns":
            found = db.execute("SELECT * FROM turns WHERE route=? AND id=?", (route, record_id)).fetchone()
            if found:
                row = {"id": str(found["id"]), "kind": "turn", "title": found["role"], "text": text(found["content"], 12000),
                       "sender_id": found["sender"], "event_id": found["event_id"], "occurred_at": found["occurred_at"]}
        elif kind == "state":
            found = db.execute(f"SELECT * FROM self_state WHERE key=? AND scope IN ({scope_sql})", (record_id, *allowed)).fetchone()
            if found:
                row = {"id": found["key"], "kind": "self_state", "title": found["key"], "text": text(found["value"], 4000),
                       "source": found["source"], "updated_at": found["updated_at"], "scope": found["scope"]}
        elif kind == "people":
            found = db.execute(f"SELECT * FROM people WHERE person_id=? AND scope IN ({scope_sql})", (record_id, *allowed)).fetchone()
            if found:
                row = {"id": found["person_id"], "kind": "person", "title": found["display_name"], "text": text(found["understanding"], 6000),
                       "trust": found["trust"], "updated_at": found["updated_at"], "scope": found["scope"]}
        elif kind == "emotions":
            found = db.execute(f"SELECT * FROM emotions WHERE id=? AND scope IN ({scope_sql})", (record_id, *allowed)).fetchone()
            if found:
                row = {"id": str(found["id"]), "kind": "emotion", "title": found["mood"], "text": text(found["reason"], 2000),
                       "intensity": found["intensity"], "lingering": bool(found["lingering"]), "occurred_at": found["created_at"], "scope": found["scope"]}
        elif kind == "events":
            # The operator view already exposes the retained platform-event ledger.
            found = db.execute("SELECT * FROM platform_events WHERE id=?", (record_id,)).fetchone()
            if found:
                row = {"id": str(found["id"]), "kind": "platform_event", "title": found["event_type"] + ' · ' + found["status"],
                       "text": text(found["payload"], 5000), "occurred_at": found["created_at"]}
        elif kind == "legacy":
            peer = route.removeprefix("qq-private-") if route.startswith("qq-private-") else ""
            if peer not in config.get("memory_private_peers", []):
                raise ValueError("legacy private memory is not admitted here")
            with reading(config["legacy_memory_db"]) as old:
                found = old.execute("SELECT key,value,updated_at FROM long_term_entries WHERE active=1 AND key=?", (record_id,)).fetchone()
                if found:
                    row = {"id": found["key"], "kind": "legacy_read_only", "title": text(found["key"], 160),
                           "text": text(found["value"], 12000), "updated_at": found["updated_at"]}
        elif kind == "qzone":
            path = Path(str(config.get("qzone_db") or Path(config["native_root"]) / "qzone/ledger.db"))
            if path.is_file():
                with reading(path) as qzone:
                    found = qzone.execute("SELECT * FROM posts WHERE occurrence_id=?", (record_id,)).fetchone()
                    if found:
                        receipt = {"qzone_code": found['qzone_code'], "qzone_message_id": found['qzone_message_id'] if 'qzone_message_id' in found.keys() else ''}
                        row = {"id": found["occurrence_id"], "kind": "qzone", "title": found["state"], "text": text(found["content"], 3000),
                                "status": found["state"], "occurred_at": found["created_at"], "updated_at": found["updated_at"],
                                "receipt": receipt}
        else:
            raise ValueError("unsupported detail category")
        if row and row.get("event_id") and kind != "messages":
            found = db.execute("SELECT seq,body FROM messages WHERE route=? AND json_extract(body,'$.event_id')=? LIMIT 1", (route, row["event_id"])).fetchone()
            if found:
                item = source(found)
                if db.execute("SELECT 1 FROM message_flags WHERE route=? AND event_id=? AND flag='recalled'", (route, item["event_id"])).fetchone():
                    item["recalled"] = True
                    item["text"] = "[已撤回] " + item["text"]
                sources.append(item)
        return {"row": row, "sources": sources}


def all_page(config, route, offset, query, summary_only=False):
    """A stable merged native-record page; no derived-memory or legacy import."""
    # Filter each branch by its real scope before ordering/pagination. Do not
    # page N categories separately and silently skip their undisplayed rows.
    owner_allowed = "owner" in scopes(config, route)
    sql = """
      SELECT category,id,stamp FROM (
        SELECT 'messages' category, CAST(seq AS TEXT) id, COALESCE(json_extract(body,'$.occurred_at'),0) stamp
          FROM messages WHERE route=:route AND instr(body,:query)>0
        UNION ALL SELECT 'facts', scope || ':' || key, 0 FROM facts
          WHERE scope IN (:route,'global') AND (instr(key,:query)>0 OR instr(value,:query)>0)
        UNION ALL SELECT 'turns', CAST(id AS TEXT), occurred_at FROM turns WHERE route=:route AND instr(content,:query)>0
        UNION ALL SELECT 'goals', CAST(id AS TEXT), updated_at FROM commitments WHERE route=:route AND instr(title,:query)>0
        UNION ALL SELECT 'state', key, updated_at FROM self_state WHERE instr(key || value,:query)>0
          AND (scope IN (:route,'global') OR (:owner_allowed AND scope='owner'))
        UNION ALL SELECT 'people', person_id, updated_at FROM people WHERE instr(person_id || display_name || understanding,:query)>0
          AND (scope IN (:route,'global') OR (:owner_allowed AND scope='owner'))
        UNION ALL SELECT 'emotions', CAST(id AS TEXT), created_at FROM emotions WHERE instr(mood || reason,:query)>0
          AND (scope IN (:route,'global') OR (:owner_allowed AND scope='owner'))
      ) ORDER BY stamp DESC,category,id LIMIT 25 OFFSET :offset
    """
    with reading(config["corpus_db"]) as db:
        if cognition_available(db):
            sql = sql.replace(") ORDER BY stamp", "UNION ALL SELECT 'cognition',id,updated_at FROM cognition "
                              "WHERE scope IN (:route" + (",'owner'" if owner_allowed else "") +
                              ") AND instr(key || body,:query)>0\n) ORDER BY stamp")
        keys = db.execute(sql, {"route": route, "query": query, "offset": offset, "owner_allowed": owner_allowed}).fetchall()
    rows = []
    for key in keys[:24]:
        found = detail(config, route, key["category"], key["id"])["row"]
        if found:
            if summary_only:
                found["text"] = text(found["text"], 240)
            rows.append({**found, "data_category": key["category"]})
    return {"rows": rows, "next_offset": offset + 24 if len(keys) > 24 else None}


def call(config, args):
    action = args.get("action", "page")
    route = args.get("route")
    if not isinstance(route, str) or not re.fullmatch(r"qq-(group|private)-[1-9][0-9]{0,19}", route):
        raise ValueError("native scene required")
    kind, offset = args.get("category", "messages"), args.get("offset", 0)
    query = args.get("search", "")
    if type(offset) is not int or not 0 <= offset <= 100000 or not isinstance(query, str) or len(query) > 160:
        raise ValueError("bounded page required")
    if action == "detail":
        return detail(config, route, kind, args.get("id"))
    if kind == "all":
        return all_page(config, route, offset, query, args.get("summary_only") is True)
    with reading(config["corpus_db"]) as db:
        allowed = scopes(config, route)
        scope_sql = ",".join("?" for _ in allowed)
        if action == "projection":
            after = args.get("after", 0)
            if type(after) is not int or after < 0:
                raise ValueError("invalid cursor")
            rows = db.execute("SELECT seq,body FROM messages WHERE route=? AND seq>? ORDER BY seq LIMIT 50", (route, after))
            return {"rows": [source(row) for row in rows]}
        if action == "recent":
            rows = list(db.execute("SELECT seq,body FROM messages WHERE route=? ORDER BY seq DESC LIMIT 30", (route,)))
            return {"rows": [source(row) for row in reversed(rows)]}
        if kind == "messages":
            rows = list(db.execute("SELECT seq,body FROM messages WHERE route=? AND instr(body,?)>0 ORDER BY seq DESC LIMIT 25 OFFSET ?",
                                   (route, query, offset)))
            result = []
            for row in rows:
                item = {**source(row), "kind": "source", "title": "QQ · " + source(row)["sender_id"]}
                flag = db.execute("SELECT flag FROM message_flags WHERE route=? AND event_id=? AND flag='recalled'", (route, item["event_id"])).fetchone()
                if flag: item["recalled"] = True; item["text"] = "[已撤回] " + item["text"]
                result.append(item)
        elif kind == "facts":
            rows = list(db.execute("SELECT scope,key,value,source FROM facts WHERE scope IN (" + scope_sql + ") AND (instr(key,?)>0 OR instr(value,?)>0) ORDER BY scope,key LIMIT 25 OFFSET ?",
                                   (*allowed, query, query, offset)))
            result = [{"id": row["scope"] + ":" + row["key"], "kind": "fact", "title": text(row["key"], 160),
                       "text": text(row["value"], 2000), "scope": "shared" if row["scope"] == "global" else "scene",
                        "sender_id": row["source"]} for row in rows]
        elif kind == "cognition":
            rows = db.execute("SELECT * FROM cognition WHERE scope IN (" + scope_sql + ") AND instr(key || body,?)>0 ORDER BY updated_at DESC,id LIMIT 25 OFFSET ?",
                              (*allowed, query, offset)).fetchall() if cognition_available(db) else []
            result = [cognition_row(db, config, route, row) for row in rows]
        elif kind == 'goals':
            rows=db.execute('SELECT * FROM commitments WHERE route=? AND instr(title,?)>0 ORDER BY updated_at DESC,id LIMIT 25 OFFSET ?',(route,query,offset)).fetchall()
            result=[goal_row(row) for row in rows]
        elif kind == "legacy":
            peer = route.removeprefix("qq-private-") if route.startswith("qq-private-") else ""
            if not peer or peer not in config.get("memory_private_peers", []):
                return {"rows": [], "next_offset": None, "note": "旧私有记忆只在部署授权的私聊场景可查看。"}
            with reading(config["legacy_memory_db"]) as old:
                rows = list(old.execute("SELECT key,value,updated_at FROM long_term_entries WHERE active=1 AND (instr(key,?)>0 OR instr(value,?)>0) ORDER BY updated_at DESC LIMIT 25 OFFSET ?",
                                        (query, query, offset)))
                result = [{"id": row["key"], "kind": "legacy_read_only", "title": text(row["key"], 160),
                           "text": text(row["value"], 12000), "updated_at": row["updated_at"]} for index, row in enumerate(rows)]
        elif kind == "turns":
            rows = list(db.execute(
                "SELECT id,role,sender,event_id,content,occurred_at FROM turns WHERE route=? AND instr(content,?)>0 ORDER BY occurred_at DESC,id DESC LIMIT 25 OFFSET ?",
                (route, query, offset)))
            result = [{"id": str(row["id"]), "kind": "turn", "title": row["role"],
                       "text": text(row["content"], 12000), "sender_id": row["sender"],
                       "event_id": row["event_id"], "occurred_at": row["occurred_at"]} for row in rows]
        elif kind == "actions":
            rows = list(db.execute(
                "SELECT id,kind,status,goal,report,evidence,updated_at FROM action_reports WHERE route=? AND instr(goal || report,?)>0 ORDER BY updated_at DESC LIMIT 25 OFFSET ?",
                (route, query, offset)))
            result = [{"id": row["id"], "kind": "action", "title": row["kind"] + " · " + row["status"],
                       "text": text(row["report"] or row["goal"], 12000),
                       "status": row["status"], "evidence": row["evidence"], "updated_at": row["updated_at"]} for row in rows]
        elif kind == "state":
            rows = list(db.execute(
                f"SELECT key,value,source,scope,updated_at FROM self_state WHERE instr(key || value,?)>0 AND scope IN ({scope_sql}) ORDER BY updated_at DESC LIMIT 25 OFFSET ?",
                (query, *allowed, offset)))
            result = [{"id": row["key"], "kind": "self_state", "title": row["key"],
                       "text": text(row["value"], 4000), "source": row["source"], "scope": row["scope"],
                       "updated_at": row["updated_at"]} for row in rows]
        elif kind == "people":
            rows = list(db.execute(f"SELECT person_id,display_name,understanding,trust,scope,updated_at FROM people WHERE instr(person_id || display_name || understanding,?)>0 AND scope IN ({scope_sql}) ORDER BY updated_at DESC LIMIT 25 OFFSET ?", (query, *allowed, offset)))
            result = [{"id": row["person_id"], "kind": "person", "title": row["display_name"], "text": text(row["understanding"], 6000), "trust": row["trust"], "scope": row["scope"], "updated_at": row["updated_at"]} for row in rows]
        elif kind == "emotions":
            rows = list(db.execute(f"SELECT id,mood,intensity,reason,lingering,scope,created_at FROM emotions WHERE instr(mood || reason,?)>0 AND scope IN ({scope_sql}) ORDER BY id DESC LIMIT 25 OFFSET ?", (query, *allowed, offset)))
            result = [{"id": str(row["id"]), "kind": "emotion", "title": row["mood"], "text": text(row["reason"], 2000), "intensity": row["intensity"], "lingering": bool(row["lingering"]), "scope": row["scope"], "occurred_at": row["created_at"]} for row in rows]
        elif kind == "qzone":
            qzone_path = Path(str(config.get("qzone_db") or Path(config["native_root"]) / "qzone/ledger.db"))
            if not qzone_path.is_file() or qzone_path.is_symlink():
                result = []
            else:
                with sqlite3.connect(qzone_path.as_uri() + "?mode=ro", uri=True) as qzone:
                    qzone.row_factory = sqlite3.Row
                    rows = qzone.execute("SELECT occurrence_id,content,state,qzone_code,created_at,updated_at FROM posts WHERE instr(content,?)>0 ORDER BY created_at DESC LIMIT 25 OFFSET ?", (query, offset)).fetchall()
                result = [{"id": row["occurrence_id"], "kind": "qzone", "title": row["state"], "text": text(row["content"], 3000), "status": row["state"], "qzone_code": row["qzone_code"], "occurred_at": row["created_at"], "updated_at": row["updated_at"]} for row in rows]
        elif kind == "events":
            rows = list(db.execute("SELECT id,event_type,status,payload,created_at FROM platform_events WHERE instr(event_type || payload,?)>0 ORDER BY id DESC LIMIT 25 OFFSET ?", (query, offset)))
            result = [{"id": str(row["id"]), "kind": "platform_event", "title": row["event_type"] + ' · ' + row["status"], "text": text(row["payload"], 5000), "occurred_at": row["created_at"]} for row in rows]
        else:
            raise ValueError("invalid data category")
    if args.get("summary_only") is True:
        for row in result:
            row["text"] = text(row["text"], 240)
    return {"rows": result[:24], "next_offset": offset + 24 if len(result) > 24 else None,
            "note": "只读查看；不会调用模型、导入旧库或修改记忆。"}


if __name__ == "__main__":
    from soyo.platform import load_private_json
    config = load_private_json(Path(sys.argv[1]))
    args = json.loads(sys.stdin.buffer.read(64 * 1024))
    print(json.dumps(call(config, args), ensure_ascii=False))
