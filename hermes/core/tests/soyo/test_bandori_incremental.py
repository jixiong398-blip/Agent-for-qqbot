"""Local safety/quality contracts after actual subprocess/HTTP and public-site probes."""
import json
import pytest
from soyo.qq.automation_worker import article_text, bandori_sync


def test_watermarks_cannot_inflate_article_content_or_hide_direction_controls():
    assert article_text('音乐活动\u200c\u200e\n \u200c\u200e \n日期\u202e\n2026-10-11')=='音乐活动\n日期\n2026-10-11'


@pytest.mark.parametrize('limit',[0,11,True,'10'])
def test_bounded_batch_limit_is_not_coerced(tmp_path,limit):
    with pytest.raises(ValueError,match='bounded_page_limit'):
        bandori_sync({'bandori_knowledge_root':str(tmp_path)}, {'limit':limit})


def test_old_malformed_state_is_retained_not_overwritten(tmp_path):
    state=tmp_path/'native-sync-state.json';raw=json.dumps({'lastmod':[], 'user_owned_unknown_field':'retained'});state.write_text(raw)
    with pytest.raises(ValueError,match='state_shape'):bandori_sync({'bandori_knowledge_root':str(tmp_path)}, {})
    assert state.read_text()==raw


def test_fixture_override_cannot_redirect_to_an_arbitrary_host(tmp_path):
    with pytest.raises(ValueError,match='fixture_loopback'):
        bandori_sync({'bandori_knowledge_root':str(tmp_path),'bandori_source_url':'https://source.invalid','bandori_fixture_allow_loopback':True,
                      'bandori_fixture_api_base':'https://attacker.invalid'}, {})
