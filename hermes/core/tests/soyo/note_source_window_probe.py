# SPDX-License-Identifier: GPL-3.0-only
"""Actual SQLite/subprocess two-hour own-words guard; no inference or platform."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

from soyo.qq import native_memory


def main():
    root = Path(sys.argv[1]); assert root.is_absolute() and not root.exists(); root.mkdir(mode=0o700)
    config = {'native_root': str(root), 'corpus_db': str(root/'corpus.db'), 'account_id': '900001'}
    path = root/'config.json'; path.write_text(json.dumps(config)); path.chmod(0o600)
    route = 'qq-group-123456'; text = '这是一段足够长而且已不在当前窗口前四十八条内的旧原话，用来核对完整来源'
    now = time.time()
    native_memory.record(config, {'route_id': route, 'sender_id': '100002', 'event_id': 'guard-old-within-window', 'occurred_at': now-7100, 'text': text})
    for index in range(60):
        native_memory.record(config, {'route_id': route, 'sender_id': '100003', 'event_id': f'guard-new-{index}', 'occurred_at': now-100+index, 'text': f'new message {index}'})
    native_memory.record(config, {'route_id': route, 'sender_id': '900001', 'event_id': 'guard-own', 'occurred_at': now-40,
                                 'text': '这是Soyo自己的已经送达的话，复用自己的句子并不属于搬运外人原话'} )
    native_memory.record(config, {'route_id': route, 'sender_id': '100002', 'event_id': 'guard-expired', 'occurred_at': now-7300,
                                 'text': '这是早于两小时的来源边界句子，专门核对不能错误算入最近两小时'} )
    proof = {'status': 'unverified', 'model_calls': 0, 'platform_sends': 0}
    try:
        def run(text):
            value = subprocess.run([sys.executable, '-B', native_memory.__file__, str(path)], input=json.dumps({
                'action': 'note_source_guard', 'route_id': route, 'sender_id': '100002', 'text': text}), text=True, capture_output=True, timeout=20)
            assert value.returncode == 0, value.stderr
            return json.loads(value.stdout)
        refused = run(text); assert refused['state']=='refused' and refused['reason']=='NOTE_NOT_OWN_WORDS' and refused['checked_sources'] > 48
        assert run('我注意到之前那段讨论有点长，打算只把自己的理解留给另一处自己。')['state']=='checked'
        assert run('这是Soyo自己的已经送达的话，复用自己的句子并不属于搬运外人原话')['state']=='checked'
        assert run('这是早于两小时的来源边界句子，专门核对不能错误算入最近两小时')['state']=='checked'
        proof.update(status='verified_subprocess_note_source_window', beyond_recent_48_refused=True, two_hour_scope_enforced=True,
                     own_words_allowed=True, whole_foreign_source_not_exported='text' not in refused)
    except BaseException as error: proof['error']=type(error).__name__+': '+str(error); raise
    finally:
        (root/'probe.json').write_text(json.dumps(proof,indent=2)); print(json.dumps(proof))


if __name__ == '__main__': main()
