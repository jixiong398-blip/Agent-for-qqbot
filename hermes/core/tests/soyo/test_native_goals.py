"""Persistent goal contracts after real native role/action/write/read/CAS viability."""
from concurrent.futures import ThreadPoolExecutor
import json
import pytest
from soyo.qq import native_memory, native_data, native_goals_admin


def setup(tmp_path):
    config={'native_root':str(tmp_path),'corpus_db':str(tmp_path/'corpus.db'),'memory_private_peers':['100001'],'fixture_operator_ui':True}
    args={'action':'commitment','route_id':'qq-private-100001','sender_id':'100001','message_type':'private',
          'title':'Persistent fixture goal','status':'open','goal_request_id':'goal-create-1234567890123456'}
    return config,args,native_memory.call(config,args)


def test_same_operation_is_idempotent_and_changed_intent_is_refused(tmp_path):
    cfg,args,value=setup(tmp_path)
    assert native_memory.call(cfg,args)['id']==value['id'] and native_memory.call(cfg,args)['duplicate']
    with pytest.raises(ValueError,match='OPERATION_CONFLICT'):native_memory.call(cfg,{**args,'title':'different'})
    with native_memory.connect(cfg) as db:assert db.execute('SELECT COUNT(*) FROM commitments').fetchone()[0]==1


def test_same_title_done_is_not_a_close_and_model_only_evidence_cannot_complete(tmp_path):
    cfg,args,value=setup(tmp_path)
    with pytest.raises(ValueError,match='ID_REQUIRED'):native_memory.call(cfg,{**args,'goal_request_id':'goal-done-1234567890123456','status':'done'})
    action='action-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';path=tmp_path/'actions';path.mkdir()
    (path/(action+'.json')).write_text(json.dumps({'id':action,'state':'completed','actor':{'route_id':args['route_id']},'native_receipts':[]}))
    from soyo.platform import protect
    protect(path/(action+'.json'))
    with pytest.raises(ValueError,match='EFFECT_REQUIRED'):native_memory.call(cfg,{**args,'commitment_id':value['id'],'expected_revision':1,'status':'done',
        'reason':'model claimed done','evidence_id':action,'goal_request_id':'goal-close-1234567890123456'})
    with native_memory.connect(cfg) as db:assert db.execute('SELECT status FROM commitments').fetchone()[0]=='open'


def test_stale_revision_and_wrong_scene_do_not_change_a_goal(tmp_path):
    cfg,args,value=setup(tmp_path)
    for changed in ({'expected_revision':0},{'route_id':'qq-private-100009','sender_id':'100009'}):
        with pytest.raises(ValueError):native_memory.call(cfg,{**args,'commitment_id':value['id'],'expected_revision':1,'status':'cancelled','reason':'stop',
            'goal_request_id':'goal-cancel-1234567890123456',**changed})
    with native_memory.connect(cfg) as db:assert db.execute('SELECT revision FROM commitments').fetchone()[0]==1


def test_concurrent_operators_serialize_cas_and_retain_the_losing_intent(tmp_path):
    cfg,args,value=setup(tmp_path)
    def mutate(index):
        try:return native_goals_admin.call(cfg,{'route_id':args['route_id'],'commitment_id':value['id'],'expected_revision':1,'status':'blocked' if index==0 else 'cancelled',
            'reason':'independent operator intent','goal_request_id':'goal-concurrent-123456789012345'+str(index)})
        except ValueError as error:return {'error':str(error)}
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(mutate,[0,1]))
    assert sum('error' not in row for row in results)==1 and any('GOAL_CONFLICT' in row.get('error','') for row in results)
    with native_memory.connect(cfg) as db:
        assert db.execute('SELECT revision FROM commitments').fetchone()[0]==2
        assert db.execute('SELECT COUNT(*) FROM commitment_revisions').fetchone()[0]==2
        assert db.execute('SELECT COUNT(*) FROM commitment_operations').fetchone()[0]==2


def test_private_goal_read_face_keeps_versions_and_blocks_other_scene(tmp_path):
    cfg,args,value=setup(tmp_path)
    native_memory.call(cfg,{**args,'commitment_id':value['id'],'expected_revision':1,'status':'cancelled','reason':'explicit cancel','goal_request_id':'goal-cancel-1234567890123456'})
    detail=native_data.call(cfg,{'action':'detail','route':args['route_id'],'category':'goals','id':str(value['id'])})
    assert detail['row']['revision']==2 and len(detail['row']['revisions'])==2
    assert native_data.call(cfg,{'action':'detail','route':'qq-group-123456','category':'goals','id':str(value['id'])})['row'] is None


def test_goal_operator_requires_real_backend_and_never_starts_work(tmp_path):
    cfg,args,value=setup(tmp_path)
    with pytest.raises(ValueError,match='direct-root'):native_goals_admin.call({**cfg,'fixture_operator_ui':False},{})
    result=native_goals_admin.call(cfg,{'route_id':args['route_id'],'commitment_id':value['id'],'expected_revision':1,'status':'blocked',
        'reason':'operator decision only','goal_request_id':'goal-operator-1234567890123456'})
    assert result['scheduled'] is False and result['platform_sends']==0 and result['revision']==2
