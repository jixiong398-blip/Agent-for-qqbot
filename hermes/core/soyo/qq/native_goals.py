# SPDX-License-Identifier: GPL-3.0-only
"""Scene-bound persistent goals with CAS, atomic operation audit and real work links.

Marking a goal done is a source actor's decision with native effect evidence,
not an automatic semantic judgement that arbitrary work met its objective.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import time
import uuid
from pathlib import Path
from soyo.platform import open_private, assert_private


def initialize(db):
    # Serialize migration on an old corpus across the first two real workers.
    # executescript would implicitly commit and release the lock mid-migration.
    with db:
        db.execute('BEGIN IMMEDIATE')
        fields = {row[1] for row in db.execute('PRAGMA table_info(commitments)')}
        for field, declaration in {'revision': 'INTEGER NOT NULL DEFAULT 1', 'origin_job_key': "TEXT NOT NULL DEFAULT ''"}.items():
            if field not in fields:
                db.execute(f'ALTER TABLE commitments ADD COLUMN {field} {declaration}')
        db.execute("""CREATE TABLE IF NOT EXISTS commitment_revisions (
            goal_id INTEGER NOT NULL, revision INTEGER NOT NULL, body TEXT NOT NULL,
            evidence TEXT NOT NULL, created_at REAL NOT NULL, PRIMARY KEY(goal_id,revision))""")
        db.execute("""CREATE TABLE IF NOT EXISTS commitment_operations (
            request_id TEXT PRIMARY KEY, route TEXT NOT NULL, fingerprint TEXT NOT NULL,
            goal_id INTEGER NOT NULL, result TEXT NOT NULL, created_at REAL NOT NULL)""")


def completion_evidence(config, row, identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r'action-[a-f0-9-]{36}', identifier):
        raise ValueError('GOAL_EFFECT_REQUIRED: settled native action id required')
    path = Path(config.get('action_root') or Path(config['native_root'])/'actions')/(identifier+'.json')
    try:
        fd = open_private(path)
    except OSError as error:
        raise ValueError('GOAL_EFFECT_REQUIRED: retained native action evidence unavailable') from error
    with os.fdopen(fd, 'rb') as file:
        info = os.fstat(file.fileno())
        if info.st_size > 256*1024:
            raise ValueError('GOAL_EFFECT_REQUIRED: private native evidence file required')
        raw = file.read(); task = json.loads(raw)
    if task.get('id') != identifier or task.get('state') != 'completed' or task.get('actor', {}).get('route_id') != row['route'] or (
            row['origin_job_key'] and task['actor'].get('origin_job_key') != row['origin_job_key']):
        raise ValueError('GOAL_EFFECT_REQUIRED: completed work must belong to the original goal scene/task')
    effects = [receipt for receipt in task.get('native_receipts', []) if receipt.get('is_error') is False and
               isinstance(receipt.get('effect_observation'), dict) and receipt['effect_observation'].get('verified') is True and
               receipt.get('tool') not in {'ask_character','report_progress','soyo_memory'} and
               type(receipt.get('call_seq')) is int and type(receipt.get('result_seq')) is int and
               receipt['result_seq'] > receipt['call_seq'] and receipt.get('session_id') == task.get('child_session_id')]
    if not effects:
        raise ValueError('GOAL_EFFECT_REQUIRED: model completion alone is not an effect receipt')
    return {'action_id': identifier, 'ledger_sha256': hashlib.sha256(raw).hexdigest(), 'native_receipts': effects[:64],
            'basis': 'source-actor-decision-with-native-effect-evidence-not-automatic-goal-acceptance'}


def call(db, config, args, privileged):
    if not privileged:
        raise ValueError('GOAL_PERMISSION: owner-private scene grant required')
    route = args['route_id']; request = args.get('goal_request_id') or 'goal-op-' + uuid.uuid4().hex
    if not isinstance(route,str) or not re.fullmatch(r'qq-(group|private)-[1-9][0-9]{0,19}',route):
        raise ValueError('native goal scene required')
    if not isinstance(request, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,96}', request):
        raise ValueError('bounded goal operation identity required')
    fingerprint = hashlib.sha256(json.dumps({key: args.get(key) for key in
        ('commitment_id','expected_revision','title','status','due_at','evidence_id','reason')},sort_keys=True,allow_nan=False).encode()).hexdigest()
    db.execute('BEGIN IMMEDIATE')
    previous = db.execute('SELECT * FROM commitment_operations WHERE request_id=?', (request,)).fetchone()
    if previous:
        if previous['route'] != route or previous['fingerprint'] != fingerprint:
            raise ValueError('GOAL_OPERATION_CONFLICT: operation cannot change its goal or intent')
        return {**json.loads(previous['result']), 'duplicate': True}
    identifier = args.get('commitment_id'); row = None
    if identifier is not None:
        if type(identifier) is not int or identifier < 1:
            raise ValueError('bounded persistent goal id required')
        row = db.execute('SELECT * FROM commitments WHERE id=? AND route=?', (identifier,route)).fetchone()
        if not row or type(args.get('expected_revision')) is not int or args['expected_revision'] != row['revision']:
            raise ValueError('GOAL_CONFLICT: exact scene/id/revision required')
    title = args.get('title', row['title'] if row else '')
    status = args.get('status', row['status'] if row else 'open')
    due = args.get('due_at', row['due_at'] if row else 0)
    if not isinstance(title,str) or not title.strip() or len(title)>300 or re.search(r'\bsk-[A-Za-z0-9_-]{16,}|(?:access_token|api_key)\s*[:=]',title,re.I):
        raise ValueError('bounded credential-free goal title required')
    if status not in {'open','done','cancelled','snoozed','blocked'} or type(due) not in (int,float) or not math.isfinite(due) or due<0:
        raise ValueError('bounded goal state/deadline required')
    if status == 'done' and not row:
        raise ValueError('GOAL_ID_REQUIRED: a new done row does not close an existing goal')
    reason = args.get('reason','')
    if not isinstance(reason,str) or len(reason)>500 or row and not reason.strip():
        raise ValueError('bounded goal decision reason required')
    evidence = completion_evidence(config,row,args.get('evidence_id')) if status=='done' else {}
    now = time.time()
    if row:
        revision=row['revision']+1
        db.execute('INSERT OR IGNORE INTO commitment_revisions(goal_id,revision,body,evidence,created_at) VALUES(?,?,?,?,?)',
                   (row['id'],row['revision'],json.dumps(dict(row)), '{}',now))
        db.execute('UPDATE commitments SET title=?,status=?,due_at=?,revision=?,updated_at=? WHERE id=?',
                   (title.strip(),status,due,revision,now,row['id']))
    else:
        origin = args.get('origin_job_key') or ''
        if origin and not re.fullmatch(r'[a-f0-9]{64}',origin):raise ValueError('Host-bound goal origin required')
        identifier=db.execute('INSERT INTO commitments(route,title,status,due_at,source,created_at,updated_at,revision,origin_job_key) VALUES(?,?,?,?,?,?,?,1,?)',
            (route,title.strip(),status,due,str(args['sender_id']),now,now,origin)).lastrowid;revision=1
    updated=dict(db.execute('SELECT * FROM commitments WHERE id=?',(identifier,)).fetchone())
    db.execute('INSERT INTO commitment_revisions(goal_id,revision,body,evidence,created_at) VALUES(?,?,?,?,?)',
               (identifier,revision,json.dumps({**updated,'decision_reason':reason}),json.dumps(evidence),now))
    result={'state':'commitment_recorded','id':identifier,'revision':revision,'status':status,'duplicate':False,
            'effect_evidence':evidence,'scheduled':False,'platform_sends':0,'old_revisions_retained':True}
    db.execute('INSERT INTO commitment_operations(request_id,route,fingerprint,goal_id,result,created_at) VALUES(?,?,?,?,?,?)',
               (request,route,fingerprint,identifier,json.dumps(result),now))
    return result
