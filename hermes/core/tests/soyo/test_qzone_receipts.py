"""Local Qzone receipt and persistence contracts after actual subprocess/HTTP/SQLite probe."""
import json
import sqlite3

import pytest

from soyo.qq.qzone_publisher import _db, _publication_receipt, _approved_image, _endpoint, context
from soyo.qq.native_memory import connect, record, call


@pytest.mark.parametrize('payload', [{'code': 0, 'tid': ''}, {'code': 0, 'tid': True}, {'code': 0, 'tid': 0}, {'code': 0}, ['not-json-object']])
def test_code_zero_is_not_a_post_identity(payload):
    assert _publication_receipt(payload)['state'] == 'unknown'


def test_real_top_level_or_nested_tid_is_retained_without_inventing_a_message():
    assert _publication_receipt({'code': 0, 'tid': 'opaque-qzone-tid'})['qzone_message_id'] == 'opaque-qzone-tid'
    assert _publication_receipt({'code': 0, 'data': {'tid': 'nested-tid'}})['state'] == 'platform_accepted'
    assert _publication_receipt({'code': 17, 'tid': 'still-not-accepted'})['state'] == 'failed'
    assert _publication_receipt({'tid': 'id-but-no-result-code'})['state'] == 'unknown'


def test_schema_upgrade_preserves_the_old_response_without_fabricating_a_tid(tmp_path):
    root = tmp_path/'qzone'; root.mkdir()
    db = sqlite3.connect(root/'ledger.db')
    db.execute("CREATE TABLE posts(occurrence_id TEXT PRIMARY KEY,content TEXT,normalized TEXT,image_path TEXT,state TEXT,qzone_code TEXT,response TEXT,created_at REAL,updated_at REAL)")
    response = json.dumps({'code': 0})
    db.execute('INSERT INTO posts VALUES(?,?,?,?,?,?,?,?,?)', ('old', 'old text', 'oldtext', '', 'platform_accepted', '0', response, 1, 1)); db.commit(); db.close()
    migrated = _db({'native_root': str(tmp_path)})
    try:
        row = migrated.execute("SELECT * FROM posts WHERE occurrence_id='old'").fetchone()
        assert row['content'] == 'old text' and row['response'] == response and row['qzone_message_id'] == ''
    finally: migrated.close()


def test_publication_image_cannot_borrow_working_directory_or_symlink(tmp_path):
    media = tmp_path/'media'; media.mkdir(); image = media/'real.png'; image.write_bytes(b'fixture-image')
    config = {'media_root': str(media)}
    assert _approved_image(config, str(image)) == image
    link = media/'link.png'; link.symlink_to(image)
    with pytest.raises(ValueError): _approved_image(config, str(link))
    with pytest.raises(ValueError): _approved_image({}, str(image))


def test_fixture_url_cannot_redirect_credentials_to_an_arbitrary_host():
    actual = 'https://user.qzone.qq.com/proxy/domain/example-path'
    assert _endpoint({}, actual) == actual
    with pytest.raises(ValueError): _endpoint({'qzone_fixture_allow_loopback': True, 'qzone_fixture_api_base': 'https://attacker.invalid'}, actual)


def test_qzone_context_excludes_private_and_recalled_sources(tmp_path):
    import time
    config = {'native_root': str(tmp_path), 'corpus_db': str(tmp_path/'corpus.db')}
    with connect(config): pass
    for route, event, text in [('qq-group-123456', 'live', 'public live'), ('qq-group-123456', 'recalled', 'must-not-leak'), ('qq-private-100001', 'private', 'must-not-leak-private')]:
        record(config, {'route_id': route, 'sender_id': '100002', 'event_id': event, 'occurred_at': time.time(), 'text': text})
    call(config, {'action': 'platform_event', 'route_id': 'qq-group-123456', 'sender_id': '100002', 'event': {'notice_type': 'group_recall', 'group_id': '123456', 'message_id': 'recalled'}})
    assert [row['text'] for row in context(config)['public_group_messages']] == ['public live']
