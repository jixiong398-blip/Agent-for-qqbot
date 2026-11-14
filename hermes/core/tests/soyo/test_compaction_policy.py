import pytest
from soyo.app.compaction import model_policy, configure_plugins


@pytest.mark.parametrize('window,output', [(400000,131072),(32768,4096),(8192,1024),(32768,25000)])
def test_compaction_budgets_fit_routed_window(window, output):
    policy = model_policy('fixture', {'name':'fixture','context_window':window,'max_tokens':output})
    threshold = min(window // 2, window-output-policy['headroomTokens'])
    assert 0 < policy['maxTokens'] <= min(output,policy['headroomTokens'])
    assert 0 <= policy['retainTokens'] < threshold
    if window == 400000:
        assert policy['maxTokens'] == 65536
        assert threshold == 200000
        assert policy['retainTokens'] == 67232


def test_impossible_output_reservation_is_rejected_instead_of_silently_disabling_compaction():
    with pytest.raises(ValueError, match='too little room'):
        model_policy('fixture', {'name':'fixture','context_window':8192,'max_tokens':8000})


def test_existing_standard_group_and_qq_group_are_both_configured():
    plugin = {'name':'cordis:group','config':[{'name':'@deepseek-ai/dsh-compaction-basic','config':{}}]}
    policy = model_policy('fixture', {'name':'fixture','context_window':400000,'max_tokens':131072})
    configure_plugins([plugin],[policy])
    assert plugin['config'][0]['config']['modelPolicies'] == [policy]
