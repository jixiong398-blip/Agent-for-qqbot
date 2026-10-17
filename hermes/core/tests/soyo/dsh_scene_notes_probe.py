# SPDX-License-Identifier: MIT
"""Real native pass_note/leave_note -> persistence -> next turn/read/reply.

The first part uses isolated native probe turns (zero QQ sends). Optional
owner-authorized wake sends one synthetic owner input and expects a real QQ
receipt plus a completed local-home turn. Never cancels/repeats stalled work.
"""
import argparse
import json
import os
import time
import uuid
from pathlib import Path

import httpx

from dsh_direct_root_probe import events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--with-owner-wake', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    home, root = args.config.parent, Path(config['native_root'])
    owner = str((config.get('admin_ids') or config['memory_private_peers'])[0])
    owner_route = 'qq-private-' + owner
    scenes = json.loads((root / 'scenes.json').read_text())
    group = next(scene for scene in scenes if scene['enabled'] and scene['message_type'] == 'group' and
                 any(member != config['account_id'] for member in scene.get('members', [])))
    member = next(value for value in group['members'] if value != config['account_id'])
    nonce = uuid.uuid4().hex
    marker, reply = 'NOTE_' + nonce, 'NOTE_REPLY_' + nonce
    proof = {'status': 'unverified', 'synthetic_host_input': True, 'qq_receipts': []}
    try:
        with httpx.Client(transport=httpx.HTTPTransport(uds=config['host_socket']), base_url='http://soyo.local',
                          trust_env=False, headers={'Authorization': 'Bearer ' + config['host_key']}, timeout=30) as client:
            def notes():
                return [json.loads(path.read_text()) for path in (root / 'scene-notes').glob('note-*.json')]

            def settled_note(note_id):
                until = time.monotonic() + 30
                while True:
                    row = next(row for row in notes() if row['id'] == note_id)
                    if row.get('read_at'):
                        return row
                    if time.monotonic() > until:
                        raise AssertionError('completed turn note receipt not persisted: ' + note_id)
                    time.sleep(.1)

            def turn(route, sender, text, probe=True):
                kind, target = route.split('-')[1:]
                envelope = {'account_id': config['account_id'], 'route_id': route, 'message_type': kind,
                            'target_id': target, 'sender_id': sender, 'event_id': 'notes-probe-' + uuid.uuid4().hex,
                            'occurred_at': time.time(), 'text': text}
                if kind == 'group':
                    envelope['mentioned_account_ids'] = [config['account_id']]
                accepted = client.post('/probe' if probe else '/inbound', json={'envelope': envelope, 'context': {'recent': []}}).raise_for_status().json()
                assert accepted['kind'] == 'accepted', accepted
                key = accepted['key']
                until = time.monotonic() + 240
                while True:
                    job = json.loads((root / 'jobs' / (key + '.json')).read_text())
                    if job['state'] in ['failed', 'suppressed']:
                        raise AssertionError({'key': key, 'state': job['state'], 'reason': job.get('reason')})
                    if job['state'] == 'complete' and (probe or job.get('receipt')):
                        break
                    if time.monotonic() > until:
                        raise AssertionError('observer ended; no turn cancelled or resent: ' + key)
                    time.sleep(1)
                return job

            def tool(job, name):
                rows = events(home, job['session_id'])
                calls = [row['data'] for row in rows if row.get('type') == 'tool/call' and row['data'].get('name') == name]
                result_ids = {call['callId'] for call in calls}
                successful = [row for row in rows if row.get('type') == 'tool/result' and
                              row['data']['message'].get('toolCallId') in result_ids and not row['data']['message'].get('isError')]
                assert calls and successful, {'missing_successful_native_tool': name, 'job': job['key']}
                return rows

            first = turn(owner_route, owner, f'本轮只验证内部便签，不问 GPT、不改其他文件。先 soyo_think，再实际 pass_note，to={group["route_id"]}，mode=next_time，text 写：我留了一句便签测试 {marker}。最后简短告诉我已保存。')
            tool(first, 'pass_note')
            original = next(row for row in notes() if marker in row['text'] and row['from'] == owner_route)
            assert original['state'] == 'waiting' and original['mode'] == 'next_time' and original['probe']
            proof['next_time_no_wake'] = True
            second = turn(group['route_id'], member, f'本轮是只读背景+内部便签测试，不发平台消息。先 soyo_think，读 notes_from_program 那张含 {marker} 的便签。实际 leave_note 回到 {owner_route}，mode=next_time，reply_to={original["id"]}，用自己的话说收到了 {reply}。最后只回复你看到的原便签随机标记。不要问 GPT、不要调用其他工具。')
            tool(second, 'leave_note')
            assert marker in second['publication']['text']
            original = settled_note(original['id'])
            assert original['state'] == 'replied' and original['read_at'] and original['reply_note_id']
            answer = next(row for row in notes() if row['id'] == original['reply_note_id'])
            assert answer['from_class'] == 'public' and answer['trust'] == 'outside' and answer['hop'] == 2
            third = turn(owner_route, owner, '本轮只查看 notes_from_program 中外面 Soyo 的回信。先 soyo_think，最终复述回信里的随机标记，不写便签、不问 GPT、不执行其他工具。')
            assert reply in third['publication']['text'], third['publication']['text']
            answer = settled_note(answer['id'])
            assert answer['state'] == 'read' and answer['seen_in']
            proof.update(native_pass_note=True, native_leave_note=True, source_marked=True,
                         completed_turn_read=True, reply_link_verified=True, isolated_group_qq_sends=0,
                         notes=[original['id'], answer['id']])
            if args.with_owner_wake:
                wake_marker = 'WAKE_' + nonce
                instruction = f'这是家里两条线的便签验证：我想确认你看到了 {wake_marker}。请给来源 {owner_route} 用 pass_note 回一张 next_time 便签，reply_to 用你收到的便签 id，内容写收到 {wake_marker}。除此之外不问 GPT、不执行主机/QQ工具。'
                live = turn(owner_route, owner, f'给本机的自己写张便签，不问 GPT，不做其他事。先 soyo_think，再 pass_note，to=dsh-owner:soyo-owner，mode=wake，text={instruction}。交出后简短告诉我开始了，不等待结果。', probe=False)
                tool(live, 'pass_note')
                assert live['receipt']['status'] == 'platform_accepted'
                proof['qq_receipts'].append({'status': live['receipt']['status'], 'platform_message_id': live['receipt']['platform_message_id']})
                until = time.monotonic() + 240
                while True:
                    local_note = next((row for row in notes() if row['from'] == owner_route and row['to'] == 'dsh-owner:soyo-owner' and wake_marker in row['text']), None)
                    if local_note and local_note.get('reply_note_id') and local_note.get('read_at'):
                        break
                    if time.monotonic() > until:
                        raise AssertionError('local wake observer ended; no note cancelled/repeated')
                    time.sleep(1)
                assert local_note['mode'] == 'wake' and local_note['state'] == 'replied'
                local_events = events(home, 'soyo-owner')
                calls = [row['data'] for row in local_events if row.get('type') == 'tool/call' and row['data'].get('name') == 'pass_note' and
                         wake_marker in row['data']['arguments']]
                assert calls, 'local Soyo must actually write its reply'
                reply_ids = {call['callId'] for call in calls}
                assert any(row.get('type') == 'tool/result' and row['data']['message'].get('toolCallId') in reply_ids and not row['data']['message'].get('isError') for row in local_events)
                proof.update(local_native_wake=True, local_native_reply=True, live_note=local_note['id'])
            proof['status'] = 'verified'
    except BaseException as error:
        proof['error'] = str(error)[:1600]
        raise
    finally:
        args.evidence.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(args.evidence, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as file:
            json.dump(proof, file, ensure_ascii=False, indent=2)
        print(json.dumps(proof, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
