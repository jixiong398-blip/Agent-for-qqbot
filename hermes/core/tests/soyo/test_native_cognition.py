"""Source/transaction contracts hardened after real native Agent/subprocess/SQLite probes."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from soyo.qq import native_cognition, native_memory
from soyo.qq.native_data import call as data_call


GROUP = 'qq-group-123456'
OTHER = 'qq-private-100001'


def setup(tmp_path):
    config = {'corpus_db': str(tmp_path / 'corpus.db'), 'native_root': str(tmp_path), 'legacy_memory_db': str(tmp_path / 'old.db'),
              'memory_private_peers': ['100001'], 'cognition_enabled': True, 'cognition_min_sources': 2}
    return config


def source(config, event, text='喜欢音乐', route=GROUP, stamp=100):
    envelope = {'route_id': route, 'event_id': event, 'sender_id': '100002', 'message_type': 'group', 'text': text, 'occurred_at': stamp}
    native_memory.record(config, envelope)
    with sqlite3.connect(config['corpus_db']) as db:
        seq = db.execute('SELECT seq FROM messages WHERE route=? AND json_extract(body,\'$.event_id\')=? ORDER BY seq DESC LIMIT 1', (route, event)).fetchone()[0]
    return seq, envelope


def call(config, action, **extra):
    return native_memory.call(config, {'action': action, 'route_id': GROUP, 'sender_id': '100002', 'message_type': 'group', **extra})


def batch(config):
    value = call(config, 'cognition_prepare')
    assert value['state'] == 'prepared'
    return value


def entry(prepared, key='music', kind='fact', **extra):
    return {'kind': kind, 'key': key, 'body': '喜欢讨论音乐', 'sources': [row['seq'] for row in prepared['sources']],
            'confidence': .8, 'salience': .9, **extra}


def settle(config, prepared, entries=None):
    return call(config, 'cognition_apply', batch_id=prepared['batch_id'], source_model='fixture-inference',
                payload=json.dumps({'entries': [entry(prepared)] if entries is None else entries}, ensure_ascii=False))


def paired(config, prefix='event'):
    source(config, prefix + '-1'); source(config, prefix + '-2')
    return batch(config)


def test_promoted_memory_has_real_scene_sources_and_apply_is_idempotent(tmp_path):
    config = setup(tmp_path); prepared = paired(config)
    result = settle(config, prepared)
    assert result['records'][0]['status'] == 'promoted'
    assert settle(config, prepared)['state'] == 'duplicate'
    assert call(config, 'cognition_read', route_id=OTHER)['memories'] == []
    record = call(config, 'cognition_read')['memories'][0]
    assert record['source_seqs'] == [row['seq'] for row in prepared['sources']]
    assert record['revision'] == 1
    with sqlite3.connect(config['corpus_db']) as db:
        assert db.execute('SELECT COUNT(*) FROM cognition').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM cognition_revisions').fetchone()[0] == 1


def test_old_corpus_before_cutover_is_not_automatically_imported(tmp_path):
    config = setup(tmp_path); source(config, 'old-1'); last, _ = source(config, 'old-2')
    config['cognition_start_seq'] = last
    assert call(config, 'cognition_prepare')['state'] == 'not_due'
    prepared = paired(config, 'new')
    assert all(row['seq'] > last for row in prepared['sources'])
    settle(config, prepared)
    assert not Path(config['legacy_memory_db']).exists()


def test_foreign_or_recalled_sources_cannot_support_a_semantic_entry(tmp_path):
    config = setup(tmp_path); prepared = paired(config)
    foreign, _ = source(config, 'foreign', route=OTHER)
    with pytest.raises(ValueError, match='different scene'):
        settle(config, prepared, [entry(prepared, sources=[foreign])])
    call(config, 'platform_event', event={'notice_type': 'group_recall', 'group_id': '123456', 'message_id': 'event-1'})
    with pytest.raises(ValueError, match='recalled'):
        settle(config, prepared)
    assert call(config, 'cognition_read')['memories'] == []


def test_revision_conflict_rolls_back_the_entire_batch(tmp_path):
    config = setup(tmp_path); first = paired(config); settle(config, first)
    second = paired(config, 'next')
    with pytest.raises(ValueError, match='COGNITION_CONFLICT'):
        settle(config, second, [entry(second, key='must-not-partially-save'), entry(second, expected_revision=0)])
    records = call(config, 'cognition_read')['memories']
    assert [row['key'] for row in records] == ['music'] and records[0]['revision'] == 1
    assert call(config, 'cognition_status', batch_id=second['batch_id'])['state'] == 'prepared'


def test_single_source_fact_remains_a_candidate(tmp_path):
    config = setup(tmp_path); seq, _ = source(config, 'one')
    prepared = call(config, 'cognition_prepare', force=True)
    result = settle(config, prepared, [entry(prepared, sources=[seq, seq])])
    assert result['records'][0]['status'] == 'candidate' and result['records'][0]['source_count'] == 1


def test_forgetting_cannot_be_undone_by_automatic_extraction(tmp_path):
    config = setup(tmp_path); prepared = paired(config); identity = settle(config, prepared)['records'][0]['id']
    call(config, 'forget_memory', id=identity, expected_revision=1, reason='user requested forgetting')
    assert call(config, 'cognition_read')['memories'] == []
    next_batch = paired(config, 'again')
    with pytest.raises(ValueError, match='COGNITION_TOMBSTONE'):
        settle(config, next_batch, [entry(next_batch, expected_revision=2)])
    call(config, 'correct_memory', id=identity, expected_revision=2, reason='explicit current-source correction',
         sources=[row['seq'] for row in next_batch['sources']], body='喜欢分享音乐而非每天讨论')
    assert call(config, 'cognition_read')['memories'][0]['revision'] == 3


def test_ttl_hides_without_deleting_history(tmp_path, monkeypatch):
    monkeypatch.setattr(native_cognition.time, 'time', lambda: 100)
    config = setup(tmp_path); prepared = paired(config); settle(config, prepared, [entry(prepared, ttl_seconds=10)])
    monkeypatch.setattr(native_cognition.time, 'time', lambda: 111)
    assert call(config, 'cognition_read')['memories'] == []
    face = data_call(config, {'route': GROUP, 'category': 'cognition'})
    assert face['rows'][0]['status'] == 'expired'
    with sqlite3.connect(config['corpus_db']) as db:
        assert db.execute('SELECT COUNT(*) FROM cognition_revisions').fetchone()[0] == 1


def test_recall_removes_raw_context_and_derived_memory_but_retains_inspector_evidence(tmp_path):
    config = setup(tmp_path); prepared = paired(config); identity = settle(config, prepared)['records'][0]['id']
    call(config, 'record_summary', summary='old unbound summary must not bypass withdrawals')
    call(config, 'platform_event', event={'notice_type': 'group_recall', 'group_id': '123456', 'message_id': 'event-1'})
    _, latest = source(config, 'now', text='当前问题', stamp=200)
    context = native_memory.call(config, {**latest, 'action': 'context', 'reply_to': 'event-1'})
    assert context['cognition'] == [] and context['summaries'] == []
    assert context['recent'][0]['text'] == '[该来源已撤回]'
    assert context['reply_context']['state'] == 'recalled'
    detail = data_call(config, {'action': 'detail', 'route': GROUP, 'category': 'cognition', 'id': identity})
    assert detail['row']['status'] == 'withdrawn'
    assert detail['sources'][0]['recalled'] and detail['row']['revision'] == 2


def test_read_face_does_not_mutate_or_expose_other_scenes(tmp_path):
    config = setup(tmp_path); prepared = paired(config); settle(config, prepared)
    path = Path(config['corpus_db']); before = hashlib.sha256(path.read_bytes()).hexdigest()
    assert data_call(config, {'route': OTHER, 'category': 'cognition'})['rows'] == []
    rows = data_call(config, {'route': GROUP, 'category': 'all'})['rows']
    assert any(row['kind'] == 'cognition' for row in rows)
    identity = next(row['id'] for row in rows if row['kind'] == 'cognition')
    assert data_call(config, {'action': 'detail', 'route': OTHER, 'category': 'cognition', 'id': identity})['row'] is None
    assert before == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize('extra', [{'confidence': float('nan')}, {'salience': -1}, {'body': 'api_key=must-not-be-memory'}])
def test_invalid_or_credential_shaped_interpretations_are_atomic(tmp_path, extra):
    config = setup(tmp_path); prepared = paired(config)
    with pytest.raises(ValueError):
        settle(config, prepared, [entry(prepared, **extra)])
    assert call(config, 'cognition_read')['memories'] == []


def test_native_file_invocation_works_without_package_import_context(tmp_path):
    config = setup(tmp_path); prepared = paired(config); settle(config, prepared)
    path = tmp_path / 'config.json'; path.write_text(json.dumps(config))
    from soyo.platform import protect, worker_environment
    protect(path)
    result = subprocess.run([sys.executable, '-B', native_memory.__file__, str(path)],
        input=json.dumps({'action': 'cognition_read', 'route_id': GROUP, 'sender_id': '100002'}), text=True, capture_output=True,
        timeout=15, env=worker_environment())
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['memories'][0]['key'] == 'music'


def test_housekeeping_is_versioned_and_never_synthesizes_summaries(tmp_path, monkeypatch):
    monkeypatch.setattr(native_cognition.time, 'time', lambda: 100)
    config = setup(tmp_path); prepared = paired(config); identity = settle(config, prepared, [entry(prepared, ttl_seconds=10)])['records'][0]['id']
    monkeypatch.setattr(native_cognition.time, 'time', lambda: 111)
    result = call(config, 'memory_maintenance', route_id='soyo-automation')
    assert result['expired'] == 1 and result['model_calls'] == 0 and result['summaries_created'] == 0
    assert call(config, 'memory_maintenance')['expired'] == 0
    with sqlite3.connect(config['corpus_db']) as db:
        assert db.execute('SELECT status,revision FROM cognition WHERE id=?', (identity,)).fetchone() == ('expired', 2)
        assert db.execute('SELECT COUNT(*) FROM summaries').fetchone()[0] == 0


def test_expired_body_is_not_ambient_but_new_sources_can_renew_the_exact_revision(tmp_path, monkeypatch):
    monkeypatch.setattr(native_cognition.time, 'time', lambda: 100)
    config = setup(tmp_path); prepared = paired(config); settle(config, prepared, [entry(prepared, ttl_seconds=10)])
    monkeypatch.setattr(native_cognition.time, 'time', lambda: 111)
    call(config, 'memory_maintenance')
    new = paired(config, 'fresh')
    assert new['current'] == []
    assert new['inactive'][0]['status'] == 'expired' and new['inactive'][0]['revision'] == 2
    assert 'body' not in new['inactive'][0]
    result = settle(config, new, [entry(new, expected_revision=2, body='来自当前新来源的理解')])
    assert result['records'][0]['revision'] == 3
    assert call(config, 'cognition_read')['memories'][0]['body'] == '来自当前新来源的理解'


def test_a_member_cannot_forget_another_authors_memory_or_forge_operator_flags(tmp_path):
    config = setup(tmp_path); prepared = paired(config); identity = settle(config, prepared)['records'][0]['id']
    with pytest.raises(ValueError, match='COGNITION_PERMISSION'):
        call(config, 'forget_memory', sender_id='100003', id=identity, expected_revision=1, reason='not my source', operator=True)
    assert call(config, 'cognition_read')['memories'][0]['revision'] == 1


def test_bool_is_not_an_exact_revision(tmp_path):
    config = setup(tmp_path); prepared = paired(config); identity = settle(config, prepared)['records'][0]['id']
    with pytest.raises(ValueError, match='COGNITION_CONFLICT'):
        call(config, 'forget_memory', id=identity, expected_revision=True, reason='not a valid revision')


def operator_request(config):
    prepared = paired(config); identity = settle(config, prepared)['records'][0]['id']
    config['fixture_operator_ui'] = True
    return {'action':'correct_memory','route_id':GROUP,'id':identity,'expected_revision':1,'request_id':'fixture-operation-0001',
            'body':'人工纠错正文','sources':[row['seq'] for row in prepared['sources']],'reason':'explicit fixture operator correction'}


def test_operator_mutation_keeps_old_versions_and_distinguishes_manual_provenance(tmp_path):
    from soyo.qq.native_cognition_admin import call as mutate
    config = setup(tmp_path); request = operator_request(config)
    assert mutate(config, request)['revision'] == 2
    assert mutate(config, request)['duplicate'] is True
    with sqlite3.connect(config['corpus_db']) as db:
        assert db.execute('SELECT COUNT(*) FROM cognition_admin_operations').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM cognition_revisions').fetchone()[0] == 2
        assert db.execute('SELECT model FROM cognition').fetchone()[0] == 'owner-ui-verbatim-correction'


def test_operator_id_cannot_silently_change_intent_or_scope(tmp_path):
    from soyo.qq.native_cognition_admin import call as mutate
    config = setup(tmp_path); request = operator_request(config); mutate(config, request)
    for change in ({'body':'other intent'},{'route_id':OTHER}):
        with pytest.raises(ValueError, match='COGNITION_OPERATION_CONFLICT'):
            mutate(config, {**request,**change})


def test_invalid_operator_source_rolls_back_revision_and_audit_together(tmp_path):
    from soyo.qq.native_cognition_admin import call as mutate
    config = setup(tmp_path); request = operator_request(config)
    foreign,_ = source(config,'foreign-operator-source',route=OTHER)
    with pytest.raises(ValueError): mutate(config,{**request,'sources':[foreign]})
    with sqlite3.connect(config['corpus_db']) as db:
        assert db.execute('SELECT revision FROM cognition').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM cognition_admin_operations').fetchone()[0] == 0


def test_concurrent_same_intent_creates_one_operator_revision(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from soyo.qq.native_cognition_admin import call as mutate
    config = setup(tmp_path); request = operator_request(config)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _:mutate(config,request),range(2)))
    assert sorted(result['duplicate'] for result in results) == [False,True]
    with sqlite3.connect(config['corpus_db']) as db:
        assert db.execute('SELECT COUNT(*) FROM cognition_revisions').fetchone()[0] == 2
