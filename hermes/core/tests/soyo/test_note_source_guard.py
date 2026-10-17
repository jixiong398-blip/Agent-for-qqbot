"""Local own-words boundaries after actual subprocess and native note pipeline viability."""
import pytest
from soyo.qq.native_memory import record, call


def setup(tmp_path, monkeypatch):
    monkeypatch.setattr('soyo.qq.native_memory.time.time', lambda: 10000)
    return {'native_root':str(tmp_path),'corpus_db':str(tmp_path/'corpus.db'),'account_id':'900001'}


def source(config, **extra):
    record(config, {'route_id':'qq-group-123456','sender_id':'100002','event_id':'source','occurred_at':9000,
                    'text':'他人的二十个连续字符🙂🙂🙂🙂🙂🙂🙂🙂🙂🙂🙂🙂🙂🙂🙂🙂🙂🙂🙂🙂', **extra})


def check(config, text, **extra):
    return call(config, {'action':'note_source_guard','route_id':'qq-group-123456','sender_id':'100002','text':text,**extra})


def test_non_bmp_run_uses_codepoints_not_utf16_units(tmp_path, monkeypatch):
    config=setup(tmp_path,monkeypatch); source(config)
    assert check(config,'🙂'*20)['reason']=='NOTE_NOT_OWN_WORDS'
    assert check(config,'🙂'*19)['state']=='checked'


def test_own_lines_and_other_scenes_are_not_foreign_sources(tmp_path, monkeypatch):
    config=setup(tmp_path,monkeypatch); source(config,sender_id='900001')
    source(config,event_id='other',route_id='qq-group-654321')
    assert check(config,'🙂'*20)['state']=='checked'


def test_recall_does_not_authorize_republishing_a_foreign_line(tmp_path, monkeypatch):
    config=setup(tmp_path,monkeypatch); source(config)
    call(config,{'action':'platform_event','route_id':'qq-group-123456','sender_id':'100002',
         'event':{'notice_type':'group_recall','group_id':'123456','message_id':'source'}})
    assert check(config,'🙂'*20)['reason']=='NOTE_NOT_OWN_WORDS'


def test_window_is_two_hours_and_does_not_include_future_timestamps(tmp_path, monkeypatch):
    config=setup(tmp_path,monkeypatch); source(config,occurred_at=2799)
    source(config,event_id='future',occurred_at=10001)
    assert check(config,'🙂'*20)['state']=='checked'
    source(config,event_id='boundary',occurred_at=2800)
    assert check(config,'🙂'*20)['reason']=='NOTE_NOT_OWN_WORDS'


def test_foreign_forward_words_are_not_reclassified_as_our_own(tmp_path, monkeypatch):
    config=setup(tmp_path,monkeypatch); source(config,sender_id='900001',text='my own short intro',
        forward_context={'nodes':[{'sender_id':'100003','text':'转发正文😄😄😄😄😄😄😄😄😄😄😄😄😄😄😄😄😄😄😄😄'}]})
    assert check(config,'😄'*20)['reason']=='NOTE_NOT_OWN_WORDS'


def test_invalid_scene_or_note_cannot_claim_a_window_was_checked(tmp_path, monkeypatch):
    config=setup(tmp_path,monkeypatch)
    with pytest.raises(ValueError): check(config,'short',route_id='dsh-owner')
    with pytest.raises(ValueError): check(config,'x'*301)
