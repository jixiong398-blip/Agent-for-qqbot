"""Real HTTP/SQLite channel paths against an isolated OneBot-shaped loopback, never live QQ."""
from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

from soyo.qq import ChannelRoute, OutboundIntent, build_outbound_plans
from soyo.qq.native_memory import call, record
from soyo.qq.native_data import call as data_call
from soyo.qq.outbound import classify_send_response
from soyo.qq.runtime import NapCat, NativeHost, resolve_forward_context


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--root', type=Path, required=True)
    root = parser.parse_args().root
    assert root.is_absolute() and not root.exists()
    root.mkdir(mode=0o700)
    calls, inputs = [], []
    tree = {
        'outer': [{'sender': {'nickname': 'A'}, 'content': [
            {'type': 'text', 'data': {'text': '外层原话'}}, {'type': 'forward', 'data': {'id': 'inner'}}]}],
        'inner': [{'nickname': 'B', 'content': [{'type': 'text', 'data': {'text': '嵌套正文\n    code_indent'}}]}],
        'cycle': [{'nickname': 'C', 'content': [{'type': 'text', 'data': {'text': '可读部分'}}, {'type': 'forward', 'data': {'id': 'cycle'}}]}],
        'large': [{'nickname': 'L', 'content': [{'type': 'text', 'data': {'text': '长' * 20000}}]}],
    }
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            value = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append({'action': self.path, 'params': value})
            if self.path == '/get_forward_msg':
                body = {'status': 'ok', 'retcode': 0, 'data': {'messages': tree.get(value['message_id'], [])}}
            elif self.path == '/v1/channels/qq/events':
                inputs.append(value); body = {'kind': 'accepted', 'episode_id': 'loopback-episode'}
            elif self.path == '/send_private_msg':
                body = {'status': 'ok', 'retcode': 0, 'data': {'message_id': 'loopback-' + str(len(calls))}}
            else:
                body = {'status': 'failed', 'retcode': 100, 'message': 'unexpected loopback action'}
            raw = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(raw)))
            self.end_headers(); self.wfile.write(raw)
        def log_message(self, *args): pass
    proof = {'status': 'unverified', 'live_qq_sends': 0, 'external_model_calls': 0, 'onebot': 'loopback-only'}
    try:
        with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            url = f'http://127.0.0.1:{server.server_port}'
            config = {'account_id': '900001', 'http_url': url, 'onebot_token': 'fixture-loopback-only', 'host_key': 'fixture-only',
                      'corpus_db': str(root / 'corpus.db'), 'legacy_memory_db': str(root / 'legacy.db'), 'memory_private_peers': ['100001']}
            config['host_socket'] = str(root / 'host-not-started.sock')
            envelope = {'account_id': '900001', 'route_id': 'qq-group-123456', 'message_type': 'group', 'target_id': '123456',
                        'sender_id': '100002', 'event_id': 'current', 'occurred_at': 100.0, 'text': '@900001 看转发', 'forward_refs': ['outer']}
            try:
                resolved = resolve_forward_context(config, envelope)
                proof['first_resolution'] = resolved
                assert resolved['state'] == 'resolved' and resolved['expanded_refs'] == ['outer', 'inner']
                assert '嵌套正文\n    code_indent' in resolved['text']
                record(config, envelope)
                call(config, {**envelope, 'action': 'attach_forward', 'forward_context': resolved})
                projected = data_call(config, {'route': envelope['route_id'], 'category': 'messages'})['rows'][0]
                assert projected['forward_context']['expanded_refs'] == ['outer', 'inner']
                cycle = resolve_forward_context(config, {**envelope, 'forward_refs': ['cycle']})
                assert cycle['state'] == 'partial' and cycle['errors'][0]['reason'] == 'cyclic_forward'
                large = resolve_forward_context(config, {**envelope, 'forward_refs': ['large']})
                assert large['state'] == 'partial' and large['truncated'] and len(large['text']) <= 12000
                withdrawn = {**envelope, 'event_id': 'withdrawn', 'text': '不得再次透出'}
                record(config, withdrawn)
                call(config, {**envelope, 'action': 'platform_event', 'event': {'notice_type': 'group_recall', 'group_id': '123456', 'message_id': 'withdrawn'}})
                current = {**envelope, 'event_id': 'reply-new', 'forward_refs': [], 'reply_to': 'withdrawn'}
                record(config, current)
                port = NativeHost(config); port.client.close()
                port.client = httpx.Client(base_url=url, trust_env=False, headers={'Authorization': 'Bearer ' + config['host_key']})
                try:
                    accepted = port.post_event(current)
                    assert accepted.kind == 'accepted' and inputs[-1]['context']['reply_context']['state'] == 'recalled'
                    assert not any(row['action'] == '/get_msg' for row in calls)
                finally: port.client.close()
                private = ChannelRoute('qq-private-100001', 'private', '100001', '900001')
                block = '```python\nif True:\n    print("@qq:100002")\n\n    print("ok")\n```'
                intent = OutboundIntent('probe-publication', 'probe-attempt', private.route_id, 'private', private.target_id,
                                        '前段\n' + block + '\n后段', reply_to='quote-source', account_id=private.account_id)
                plans = build_outbound_plans(intent, private)
                assert len(plans) == 3 and plans[1].params['message'][0]['data']['text'] == block
                assert plans[0].params['message'][0]['type'] == 'reply'
                assert all(segment['type'] != 'reply' for plan in plans[1:] for segment in plan.params['message'])
                boundary = NapCat(config)
                try:
                    receipts = [classify_send_response(boundary.send(plan), publication_id=intent.publication_id, attempt_id=intent.attempt_id) for plan in plans]
                    assert all(receipt.status == 'platform_accepted' for receipt in receipts)
                finally: boundary.client.close()
                group = ChannelRoute('qq-group-123456', 'group', '123456', '900001', frozenset({'100002'}))
                group_intent = OutboundIntent('group-plan-only', 'group-plan-attempt', group.route_id, 'group', group.target_id,
                                             block, account_id=group.account_id)
                assert all(segment['type'] == 'text' for segment in build_outbound_plans(group_intent, group)[0].params['message'])
                proof.update(status='verified_loopback_complex_qq_path', nested_forward=True, cyclic_forward_partial=True,
                             clipping_explicit=True, real_forward_sqlite_projection=True, recalled_reply_not_refetched=True,
                             code_indentation_preserved=True, private_quote_first_part_only=True, literal_code_at_not_promoted=True,
                             loopback_private_sends=len(plans), actual_onebot_compatibility='not-proven-by-loopback')
            finally: server.shutdown(); thread.join(timeout=10)
    except BaseException as error:
        proof['error'] = type(error).__name__ + ': ' + str(error); raise
    finally:
        (root / 'probe.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(proof, ensure_ascii=False))


if __name__ == '__main__': main()
