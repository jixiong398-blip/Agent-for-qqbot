# SPDX-License-Identifier: GPL-3.0-only
"""Bounded expansion of only the forward references admitted in a QQ message."""
from __future__ import annotations

import math
import time

from .contracts import bounded_id


def segment_text(segment):
    kind = str(segment.get('type') or '')
    data = segment.get('data') if isinstance(segment.get('data'), dict) else {}
    if kind == 'text': return str(data.get('text') or '')
    if kind == 'at': return '@' + str(data.get('qq') or data.get('user_id') or '')
    return '[' + kind + ']' if kind else ''


def resolve(config, envelope, reader):
    raw = envelope.get('forward_refs') or []
    if not isinstance(raw, (tuple, list)):
        return {'state': 'unavailable', 'errors': [{'reason': 'forward_refs_shape'}]}
    refs = list(dict.fromkeys(ref for value in raw if (ref := bounded_id(value, limit=240))))
    if not refs: return {'state': 'not_requested'}
    budget = float(config.get('forward_budget_seconds', 8))
    if not math.isfinite(budget) or budget <= 0: raise ValueError('finite forward budget required')
    deadline = time.monotonic() + min(20, budget)
    resolved, errors, expanded, visiting, cache, limits = [], [], [], set(), {}, set()
    total = 0

    def append(ref, sender, value, depth, path):
        nonlocal total
        if not value.strip(): return
        if len(resolved) >= 64 or total >= 12000:
            limits.add('node_or_text_budget'); return
        allowance = min(4000, 12000 - total)
        if len(value) > allowance: limits.add('text_budget')
        value = value[:allowance]; total += len(value)
        resolved.append({'ref': ref, 'sender': str(sender)[:120], 'text': value, 'depth': depth, 'path': path[:120]})

    def content(ref, value, sender, depth, path):
        if isinstance(value, str): append(ref, sender, value, depth, path); return
        if isinstance(value, dict): value = [value]
        if not isinstance(value, list):
            errors.append({'ref': ref, 'reason': 'node_content_unrecognized'}); return
        pieces = []
        def flush(): append(ref, sender, ''.join(pieces), depth, path); pieces.clear()
        for segment in value[:256]:
            if not isinstance(segment, dict): continue
            data = segment.get('data') if isinstance(segment.get('data'), dict) else {}
            if segment.get('type') == 'forward':
                flush(); child = bounded_id(data.get('id'), limit=240)
                if child: expand(child, depth + 1, path + '/forward')
                else: errors.append({'ref': ref, 'reason': 'invalid_nested_ref'})
            elif segment.get('type') == 'node':
                flush()
                if depth >= 3: limits.add('depth_budget'); continue
                content(ref, data.get('content', data.get('message', [])), data.get('nickname', data.get('user_id', sender)), depth + 1, path + '/node')
            else: pieces.append(segment_text(segment))
            if len(resolved) >= 64 or total >= 12000:
                limits.add('node_or_text_budget'); break
        if len(value) > 256: limits.add('segment_budget')
        flush()

    def expand(ref, depth, path):
        if depth > 3: limits.add('depth_budget'); return
        if ref in visiting: errors.append({'ref': ref, 'reason': 'cyclic_forward'}); return
        if len(resolved) >= 64 or total >= 12000: limits.add('node_or_text_budget'); return
        remaining = deadline - time.monotonic()
        if remaining <= 0 or ref not in cache and len(expanded) >= 8:
            limits.add('request_or_time_budget'); return
        visiting.add(ref)
        try:
            if ref not in cache:
                cache[ref] = reader({**config, 'onebot_action_timeout_seconds': min(5, remaining)}, {
                    'action': 'get_forward_msg', 'params': {'message_id': ref}, 'route_id': envelope['route_id'],
                    'sender_id': envelope['sender_id'], 'scene_target_id': envelope['target_id'], 'scene_event_id': envelope['event_id'],
                    'message_type': envelope.get('message_type'), 'forward_refs': [ref]})
                expanded.append(ref)
            result = cache[ref]
            if not result.get('success'):
                errors.append({'ref': ref, 'reason': str(result.get('error') or 'read_rejected')[:160]}); return
            data = result.get('data') or {}
            nodes = (data.get('messages') or data.get('message') or data.get('nodes') or []) if isinstance(data, dict) else data
            if isinstance(nodes, dict): nodes = [nodes]
            if not isinstance(nodes, list):
                errors.append({'ref': ref, 'reason': 'forward_shape_unrecognized'}); return
            for index, node in enumerate(nodes[:64]):
                if not isinstance(node, dict): continue
                value = node.get('data') if isinstance(node.get('data'), dict) else node
                sender = value.get('sender') if isinstance(value.get('sender'), dict) else {}
                who = value.get('nickname') or sender.get('nickname') or value.get('user_id') or sender.get('user_id') or node.get('sender_id') or ''
                content(ref, value.get('content', value.get('message', node.get('message', []))), who, depth, path + '/' + str(index))
                if len(resolved) >= 64 or total >= 12000:
                    if index + 1 < len(nodes): limits.add('node_or_text_budget')
                    break
            if len(nodes) > 64: limits.add('node_budget')
        except Exception as error: errors.append({'ref': ref, 'reason': type(error).__name__})
        finally: visiting.discard(ref)

    for ref in refs[:4]: expand(ref, 0, ref)
    if len(refs) > 4: limits.add('top_ref_budget')
    formatted = '\n'.join((row['sender'] + ': ' if row['sender'] else '') + row['text'] for row in resolved)
    if len(formatted) > 12000: limits.add('formatted_text_budget')
    return {'state': 'partial' if resolved and (errors or limits) else 'resolved' if resolved else 'unavailable',
            'refs': refs[:4], 'expanded_refs': expanded, 'nodes': resolved, 'text': formatted[:12000],
            'truncated': bool(limits), 'limits': sorted(limits),
            **({'errors': errors[:8]} if errors else {} if resolved else {'errors': [{'reason': 'empty_forward'}]})}
