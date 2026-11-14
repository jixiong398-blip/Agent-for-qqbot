import json
import sqlite3
import pytest
from soyo.qq import native_memory, native_recall


def test_old_text_and_media_are_recalled_without_widening_the_recent_window(tmp_path):
    config={'corpus_db':str(tmp_path/'corpus.db'),'admin_ids':['100001'],'memory_private_peers':['100001']}
    route='qq-group-200001'
    with native_memory.connect(config) as db:
        for index in range(350):
            envelope={'route_id':route,'event_id':str(index),'sender_id':'100002','target_id':'200001',
                'message_type':'group','occurred_at':1000+index,'text':('x'*1500+' rareportrait original drawing') if index==0 else 'unrelated chatter'}
            if index==0:envelope['media']=[{'kind':'image','ref':'private-signed-reference'}]
            native_memory.record_in(db,envelope,config)
            db.execute("INSERT INTO turns(route,role,sender,event_id,content,occurred_at,created_at) VALUES(?,'user',?,?,?,?,?)",
                (route,'100002',str(index),envelope['text'],1000+index,1000+index))
        for fn in (native_recall._readable_turns,native_recall._readable_corpus):
            rows=fn(db,[route],['rareportrait'],2000,set())
            assert any('0' in row['source_events'] for row in rows)
            assert any('rareportrait' in row['text'] for row in rows)
        recall=native_recall.collect(db,config,route,'rareportrait',2000)
        surface=native_recall.build_surface(recall)
        item=next(v for v in surface['candidates'] if v['source']=='corpus')
        assert item['media_sources']==[{'message_id':'0','media_index':0,'kind':'image'}]
        assert 'private-signed-reference' not in json.dumps(surface)
        assert native_recall.media_sources(db,[route],message_id='0')[0]['media']
        assert native_recall.media_sources(db,['qq-group-200002'],message_id='0')==[]
        db.execute("INSERT INTO message_flags VALUES(?,?,'recalled','1',?)",(route,'0',2000))
        assert native_recall.media_sources(db,[route],message_id='0')==[]
        assert native_recall._readable_corpus(db,[route],['rareportrait'],2000,set())==[]


def test_image_lookup_requires_explicit_source_and_stays_scene_bound(tmp_path):
    config={'corpus_db':str(tmp_path/'corpus.db'),'admin_ids':['100001']}
    with pytest.raises(ValueError,match='explicit'):
        native_memory.call(config,{'action':'image_sources','route_id':'qq-group-200001','sender_id':'100002','message_type':'group'})
    assert native_memory.call(config,{'action':'image_sources','route_id':'qq-group-200001',
        'sender_id':'100002','message_type':'group','message_id':'not-present'})['sources']==[]
