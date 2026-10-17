"""Own-state boundaries hardened after the actual native role/worker/next-scene probe."""
import json
import pytest
from soyo.qq import native_cognition, native_memory, native_reflection


def setup(tmp_path, monkeypatch, route='qq-group-123456'):
    clock=[10000.0];monkeypatch.setattr(native_memory.time,'time',lambda:clock[0])
    config={'native_root':str(tmp_path),'corpus_db':str(tmp_path/'corpus.db'),'account_id':'900001',
            'cognition_start_seq':0,'cognition_min_sources':2,'memory_private_peers':['100001']}
    env={'route_id':route,'event_id':'affect-source','sender_id':'100002','occurred_at':clock[0],
         'message_type':'group' if route.startswith('qq-group-') else 'private','text':'自己的反应不是我的心情'}
    native_memory.record(config,env)
    args={'envelope':env,'session_id':'soyo-qq-fixture','job_key':'a'*64,'turn':1,'call_seq':10,'call_id':'native-think-1',
          'thought':'我对音乐感到好奇，这是自身反应。','feeling':'curious','intensity':.8,'completed':True}
    return config,env,args,clock


def apply(config, env, args):
    with native_memory.connect(config) as db: role=native_reflection.record(db,config,args)
    batch=native_memory.call(config,{**env,'action':'cognition_prepare','force':True})
    entry={'kind':'emotion','key':'own-curiosity','body':'Soyo自身对音乐好奇。','sources':[role['source_seq']],
           'role_sources':[role['id']], 'ttl_seconds':7200}
    value=native_memory.call(config,{**env,'action':'cognition_apply','batch_id':batch['batch_id'],'payload':{'entries':[entry]}})
    return role,batch,entry,value['records'][0]


def test_a_role_source_is_immutable_and_native_coordinates_are_required(tmp_path,monkeypatch):
    config,env,args,clock=setup(tmp_path,monkeypatch)
    with native_memory.connect(config) as db:
        first=native_reflection.record(db,config,args)
        assert native_reflection.record(db,config,args)['duplicate']
        with pytest.raises(ValueError,match='immutable'):native_reflection.record(db,config,{**args,'thought':'different meaning'})
        with pytest.raises(ValueError,match='coordinates'):native_reflection.record(db,config,{**args,'call_seq':True})


def test_only_applied_public_own_state_can_cross_scenes_and_it_decays(tmp_path,monkeypatch):
    config,env,args,clock=setup(tmp_path,monkeypatch);apply(config,env,args)
    with native_memory.connect(config) as db:
        value=native_reflection.shared_affect(db,clock[0]+1800)
        assert value['tone']=='curious' and value['intensity']==.4
        assert not any(key in value for key in ('body','thought','route','sender','source_text','session_id'))
        assert native_reflection.shared_affect(db,clock[0]+7201) is None


def test_private_role_affect_never_enters_public_shared_projection(tmp_path,monkeypatch):
    config,env,args,clock=setup(tmp_path,monkeypatch,'qq-private-100001');apply(config,env,args)
    with native_memory.connect(config) as db:assert native_reflection.shared_affect(db,clock[0]) is None


def test_a_new_expression_cannot_sneak_into_an_already_prepared_batch(tmp_path,monkeypatch):
    config,env,args,clock=setup(tmp_path,monkeypatch)
    batch=native_memory.call(config,{**env,'action':'cognition_prepare','force':True});clock[0]+=1
    with native_memory.connect(config) as db:role=native_reflection.record(db,config,args)
    repeated=native_memory.call(config,{**env,'action':'cognition_prepare','force':True})
    assert repeated['batch_id']==batch['batch_id'] and repeated['role_sources']==[]
    with pytest.raises(ValueError,match='admitted'):
        native_memory.call(config,{**env,'action':'cognition_apply','batch_id':batch['batch_id'],'payload':{'entries':[
            {'kind':'emotion','key':'forgery','body':'not originally admitted','sources':[role['source_seq']],'role_sources':[role['id']]}]}})


def test_operator_correction_does_not_borrow_old_native_emotion_attribution(tmp_path,monkeypatch):
    config,env,args,clock=setup(tmp_path,monkeypatch);role,batch,entry,stored=apply(config,env,args)
    with native_memory.connect(config) as db:
        native_cognition.mutate_operator(db,env['route_id'],{'action':'correct_memory','id':stored['id'],'expected_revision':1,
            'reason':'exact owner correction','body':'A different corrected description','sources':entry['sources'],'request_id':'operator-1234567890123456'})
        assert native_reflection.shared_affect(db,clock[0]) is None
        assert db.execute('SELECT COUNT(*) FROM cognition_role_sources').fetchone()[0]==1


def test_memory_tool_action_cannot_create_host_role_evidence(tmp_path,monkeypatch):
    config,env,args,clock=setup(tmp_path,monkeypatch)
    native_memory.call(config,{**env,'action':'record_role_reflection',**args})
    with native_memory.connect(config) as db:assert db.execute('SELECT COUNT(*) FROM role_reflections').fetchone()[0]==0


def test_deployment_watermark_does_not_retroactively_project_old_thoughts(tmp_path,monkeypatch):
    config,env,args,clock=setup(tmp_path,monkeypatch);config['cognition_start_seq']=1
    with native_memory.connect(config) as db:
        assert native_reflection.record(db,config,args)['state']=='not_recorded'
        assert db.execute('SELECT COUNT(*) FROM role_reflections').fetchone()[0]==0
