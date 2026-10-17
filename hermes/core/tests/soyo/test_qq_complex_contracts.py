"""Local hardening after the real loopback HTTP/SQLite/planner/receipt design probe."""
from __future__ import annotations

import pytest

from soyo.qq import ChannelRoute, OutboundIntent, build_outbound_plans, split_reply_text
from soyo.qq.forward_context import resolve
from soyo.qq.outbound import OutboundPlanError, encode_group_text


def envelope(ref='root'):
    return {'route_id': 'qq-group-123456', 'message_type': 'group', 'target_id': '123456',
            'sender_id': '100002', 'event_id': 'current', 'forward_refs': [ref]}


def reader_for(trees, calls):
    def read(config, args):
        ref = args['params']['message_id']
        assert args['forward_refs'] == [ref] and args['route_id'] == 'qq-group-123456'
        assert 0 < config['onebot_action_timeout_seconds'] <= 5
        calls.append(ref)
        return {'success': True, 'data': {'messages': trees.get(ref, [])}}
    return read


def text(value): return {'type': 'text', 'data': {'text': value}}
def forward(ref): return {'type': 'forward', 'data': {'id': ref}}


def test_nested_ref_can_only_come_from_an_admitted_parent():
    calls = []
    trees = {'root': [{'content': [text('outer'), forward('inner')]}], 'inner': [{'content': [text('inner')]}]}
    found = resolve({}, envelope(), reader_for(trees, calls))
    assert found['state'] == 'resolved' and calls == ['root', 'inner']
    assert [row['depth'] for row in found['nodes']] == [0, 1]
    assert found['nodes'][1]['ref'] == 'inner'


def test_cycle_marks_partial_without_recursive_requests():
    calls = []
    found = resolve({}, envelope(), reader_for({'root': [{'content': [text('visible'), forward('root')]}]}, calls))
    assert calls == ['root'] and found['state'] == 'partial'
    assert found['errors'][0]['reason'] == 'cyclic_forward'


def test_depth_bound_stops_new_reads_and_clearly_marks_partial():
    calls = []
    trees = {str(i): [{'content': [text('level ' + str(i)), forward(str(i + 1))]}] for i in range(10)}
    found = resolve({}, envelope('0'), reader_for(trees, calls))
    assert calls == ['0', '1', '2', '3']
    assert found['state'] == 'partial' and 'depth_budget' in found['limits']


def test_repeated_reference_reuses_receipt_but_keeps_each_occurrence():
    calls = []
    trees = {'root': [{'content': [forward('child'), forward('child')]}], 'child': [{'content': [text('quoted twice')]}]}
    found = resolve({}, envelope(), reader_for(trees, calls))
    assert calls == ['root', 'child'] and len(found['nodes']) == 2
    assert found['state'] == 'resolved'


def test_shared_text_budget_never_silently_claims_full_expansion():
    calls = []
    trees = {'root': [{'nickname': str(i), 'content': [text('x' * 8000)]} for i in range(20)]}
    found = resolve({}, envelope(), reader_for(trees, calls))
    assert found['state'] == 'partial' and found['truncated']
    assert len(found['text']) <= 12000 and sum(len(row['text']) for row in found['nodes']) <= 12000


def test_request_budget_is_shared_across_the_entire_tree():
    calls = []
    trees = {'root': [{'content': [text('start'), *[forward(str(i)) for i in range(20)]]}],
             **{str(i): [{'content': [text('child ' + str(i))]}] for i in range(20)}}
    found = resolve({}, envelope(), reader_for(trees, calls))
    assert len(calls) == 8 and 'request_or_time_budget' in found['limits']


def test_failed_child_is_partial_not_all_or_nothing_success():
    def read(_config, args):
        return {'success': True, 'data': {'messages': [{'content': [text('real parent'), forward('broken')]}]}} if args['params']['message_id'] == 'root' else {'success': False, 'error': 'permission_rejected'}
    found = resolve({}, envelope(), read)
    assert found['state'] == 'partial' and 'real parent' in found['text']
    assert found['errors'][0]['reason'] == 'permission_rejected'


def test_inline_nested_nodes_keep_sender_and_whitespace():
    calls = []
    nested = {'type': 'node', 'data': {'nickname': 'inner', 'content': [text('    indented\n\nend')]}}
    found = resolve({}, envelope(), reader_for({'root': [{'nickname': 'outer', 'content': [nested]}]}, calls))
    assert found['nodes'][0]['sender'] == 'inner' and found['nodes'][0]['text'] == '    indented\n\nend'


def test_code_fences_stay_one_part_with_indentation_and_blank_lines():
    block = '```python\nif True:\n    value = 1\n\n    value += 1\n```'
    assert split_reply_text('before\n' + block + '\nafter') == ['before', block, 'after']
    with pytest.raises(OutboundPlanError, match='code_block_too_long'):
        split_reply_text('before\n```\n' + 'x' * 2000 + '\n```', max_chars=1800)


def test_fence_with_suffix_inside_code_is_not_a_closing_fence():
    block = '```text\n```not-a-close\n    @qq:100002\n```'
    assert split_reply_text(block) == [block]
    assert encode_group_text(block) == [{'type': 'text', 'data': {'text': block}}]


def test_code_literal_at_does_not_tag_real_people_but_prose_marker_does():
    encoded = encode_group_text('@qq:100001\n```\n@qq:100002\n```')
    assert [row['data']['qq'] for row in encoded if row['type'] == 'at'] == ['100001']
    assert '@qq:100002' in ''.join(row['data'].get('text', '') for row in encoded)


def test_private_quote_only_on_the_first_frozen_part():
    route = ChannelRoute('qq-private-100001', 'private', '100001', '900001')
    intent = OutboundIntent('pub', 'attempt', route.route_id, 'private', '100001', 'first\nsecond', reply_to='42', account_id='900001')
    plans = build_outbound_plans(intent, route)
    assert plans[0].params['message'][0] == {'type': 'reply', 'data': {'id': '42'}}
    assert all(row['type'] != 'reply' for row in plans[1].params['message'])
