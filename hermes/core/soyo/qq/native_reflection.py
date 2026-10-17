# SPDX-License-Identifier: GPL-3.0-only
"""Host-recorded role expressions; never a model memory-write action.

The only cross-scene projection contains an enum tone and decayed intensity,
not other scenes' text, people, permission, private expressions or pending work.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import time
from pathlib import Path


TONES = {'calm', 'curious', 'happy', 'sad', 'concerned', 'tired', 'frustrated', 'hopeful'}


def initialize(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS role_reflections (
            id TEXT PRIMARY KEY, route TEXT NOT NULL, source_seq INTEGER NOT NULL,
            body TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_role_reflections_route_seq ON role_reflections(route,source_seq);
        CREATE TABLE IF NOT EXISTS cognition_role_sources (
            memory_id TEXT NOT NULL, revision INTEGER NOT NULL, refs TEXT NOT NULL,
            PRIMARY KEY(memory_id,revision));
    """)


def record(db, config, args):
    envelope = args.get('envelope') or {}; route = envelope.get('route_id')
    if not isinstance(route, str) or not (
            re.fullmatch(r'qq-(group|private)-[1-9][0-9]{0,19}', route) or
            (route.startswith('dsh-owner:') and route.removeprefix('dsh-owner:') in
             ({'soyo-owner'} | set(config.get('owner_sessions') or []) |
              set((config.get('collaborator') or {}).get('owner_sessions') or [])))):
        raise ValueError('native reflection scene required')
    if args.get('completed') is not True or not re.fullmatch(r'[a-f0-9]{64}', args.get('job_key') or ''):
        raise ValueError('completed native role binding required')
    for field in ('session_id', 'call_id', 'thought'):
        if not isinstance(args.get(field), str) or not args[field].strip() or len(args[field]) > (360 if field == 'thought' else 200):
            raise ValueError('bounded native role expression required')
    if any(type(args.get(field)) is not int or args[field] < 1 for field in ('turn', 'call_seq')):
        raise ValueError('actual native role coordinates required')
    tone = args.get('feeling'); intensity = args.get('intensity', 0)
    if tone is not None and tone not in TONES or type(intensity) not in (int, float) or not math.isfinite(intensity) or not 0 <= intensity <= 1:
        raise ValueError('bounded role affect required')
    row = db.execute("SELECT seq FROM messages WHERE route=? AND json_extract(body,'$.event_id')=? "
                     "AND CAST(json_extract(body,'$.occurred_at') AS INTEGER)=? ORDER BY seq DESC LIMIT 1",
                     (route, str(envelope.get('event_id') or ''), int(envelope['occurred_at']))).fetchone()
    if not row or row['seq'] <= int(config.get('cognition_start_seq', 0)):
        return {'state': 'not_recorded', 'reason': 'no-current-post-deployment-corpus-source'}
    if __package__:
        from .native_cognition import source_rows
    else:
        from native_cognition import source_rows
    source_rows(db, route, [row['seq']])
    identity = hashlib.sha256(json.dumps([args['session_id'], args['turn'], args['call_id']], separators=(',', ':')).encode()).hexdigest()
    value = {key: args[key] for key in ('session_id', 'turn', 'call_id', 'call_seq', 'thought')}
    value.update(id=identity, source_seq=row['seq'], feeling=tone, intensity=float(intensity), kind='native-role-expression-not-model-summary')
    previous = db.execute('SELECT body FROM role_reflections WHERE id=?', (identity,)).fetchone()
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if previous and previous['body'] != encoded:
        raise ValueError('immutable role expression conflict')
    db.execute('INSERT OR IGNORE INTO role_reflections(id,route,source_seq,body,created_at) VALUES(?,?,?,?,?)',
               (identity, route, row['seq'], encoded, time.time()))
    return {'state': 'recorded', 'id': identity, 'duplicate': bool(previous), 'source_seq': row['seq'], 'platform_sends': 0}


def sources(db, route, seqs, before=None):
    if not seqs:
        return []
    routes = list(route) if isinstance(route, (list, tuple, set)) else [route]
    before = time.time() if before is None else before
    rows = db.execute('SELECT body,created_at FROM role_reflections WHERE route IN (' +
                      ','.join('?' for _ in routes) + ') AND source_seq IN (' +
                      ','.join('?' for _ in seqs) + ') AND created_at BETWEEN ? AND ? ORDER BY created_at DESC,id LIMIT 24',
                      (*routes, *seqs, before - 7200, before)).fetchall()
    return [{**json.loads(row['body']), 'created_at': row['created_at']} for row in rows]


def admit(db, route, batch, entry, routes=None):
    refs = entry.get('role_sources', [])
    if not isinstance(refs, list):
        raise ValueError('role sources must be an exact id list')
    if not refs:
        return []
    if entry['kind'] not in {'emotion', 'self'} or not 1 <= len(refs) <= 8 or any(
            not isinstance(ref, str) or not re.fullmatch(r'[a-f0-9]{64}', ref) for ref in refs):
        raise ValueError('bounded role source ids are only for Bot own state')
    routes = routes or json.loads(batch['routes'] or '[]') or [route]
    permitted = {row['id']: row for row in sources(db, routes, json.loads(batch['sources']), batch['created_at'])}
    if any(ref not in permitted or permitted[ref]['source_seq'] not in entry['sources'] for ref in refs):
        raise ValueError('role expression is not in the admitted scene/batch sources')
    return sorted(set(refs))


def attribution(db, memory):
    record = db.execute('SELECT refs FROM cognition_role_sources WHERE memory_id=? AND revision=?', (memory['id'], memory['revision'])).fetchone()
    refs = json.loads(record['refs']) if record else []
    return {'subject': 'soyo' if refs else 'scene-observation', 'basis': 'native-role-expression' if refs else 'qq-source-interpretation', 'role_sources': refs}


def shared_affect(db, now):
    rows = db.execute("SELECT r.body,r.created_at,c.id FROM cognition c JOIN cognition_role_sources e "
                      "ON e.memory_id=c.id AND e.revision=c.revision JOIN role_reflections r "
                      "ON EXISTS(SELECT 1 FROM json_each(e.refs) WHERE value=r.id) "
                      "WHERE c.kind='emotion' AND c.status='promoted' AND c.scope LIKE 'qq-group-%' "
                      "AND (c.expires_at=0 OR c.expires_at>?) AND r.route=c.scope AND r.created_at BETWEEN ? AND ? "
                      "ORDER BY r.created_at DESC,r.id LIMIT 24", (now, now-7200, now)).fetchall()
    for row in rows:
        value = json.loads(row['body'])
        if value.get('feeling') not in TONES:
            continue
        intensity = value['intensity'] * math.pow(.5, max(0, now-row['created_at']) / 1800)
        if intensity < .02:
            continue
        return {'tone': value['feeling'], 'intensity': round(intensity, 4), 'age_minutes': round(max(0, now-row['created_at'])/60, 1),
                'evidence_id': row['id'], 'subject': 'soyo', 'basis': 'public-role-expression-with-applied-cognition',
                'other_scene_text_exported': False, 'authority_granted': False}
    return None


if __name__ == '__main__':
    # Dedicated Host subprocess, deliberately absent from soyo_memory enum/call.
    from native_memory import connect
    from soyo.platform import load_private_json
    config = load_private_json(Path(sys.argv[1]))
    args = json.loads(sys.stdin.buffer.read(16 * 1024))
    with connect(config) as database:
        result = record(database, config, args)
    print(json.dumps(result, ensure_ascii=False))
