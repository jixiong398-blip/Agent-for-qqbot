# SPDX-License-Identifier: GPL-3.0-only
"""Check public notes against the scene's actual two-hour corpus, not a context sample.

No source text leaves this checker. Retractions do not authorize republication;
an incomplete/budgeted scan fails closed instead of claiming the window was checked.
"""
from __future__ import annotations

import json
import re


def check(db, config, args, now):
    route = args.get('route_id')
    text = args.get('text')
    if not isinstance(route, str) or not re.fullmatch(r'qq-(group|private)-[1-9][0-9]{0,19}', route):
        raise ValueError('Current native source scene required')
    if not isinstance(text, str) or not text.strip() or len(text) > 300:
        raise ValueError('Bounded public note required')
    windows = {text[index:index + 20] for index in range(max(0, len(text) - 19))}
    checked, characters = 0, 0
    for row in db.execute(
        "SELECT seq,sender,body FROM messages WHERE route=? "
        "AND CAST(json_extract(body,'$.occurred_at') AS REAL)>=? "
        "AND CAST(json_extract(body,'$.occurred_at') AS REAL)<=? ORDER BY seq DESC LIMIT 10001",
        (route, now - 7200, now),
    ):
        checked += 1
        if checked > 10000:
            return {'state': 'refused', 'reason': 'NOTE_SOURCE_WINDOW_INCOMPLETE', 'checked_sources': checked - 1}
        value = json.loads(row['body'])
        # Include recalled/historical rows if they fall within this real time window.
        # A copied forward body is also someone else's wording, not our own speech.
        lines = [] if str(row['sender']) == str(config['account_id']) else [str(value.get('text') or '')]
        pending = [(value.get('forward_context'), 0)]
        while pending:
            item, depth = pending.pop()
            if depth > 12:
                return {'state': 'refused', 'reason': 'NOTE_SOURCE_WINDOW_INCOMPLETE', 'checked_sources': checked}
            if isinstance(item, dict):
                if isinstance(item.get('text'), str) and str(item.get('sender_id') or '') != str(config['account_id']):
                    lines.append(item['text'])
                pending.extend((child, depth + 1) for key, child in item.items() if key != 'text' and isinstance(child, (dict, list)))
            elif isinstance(item, list):
                pending.extend((child, depth + 1) for child in item)
        for line in lines:
            characters += len(line)
            if characters > 8 * 1024 * 1024:
                return {'state': 'refused', 'reason': 'NOTE_SOURCE_WINDOW_INCOMPLETE', 'checked_sources': checked}
            if any(line[index:index + 20] in windows for index in range(max(0, len(line) - 19))):
                return {'state': 'refused', 'reason': 'NOTE_NOT_OWN_WORDS', 'source_seq': row['seq'], 'checked_sources': checked}
    return {'state': 'checked', 'window_seconds': 7200, 'checked_sources': checked, 'raw_source_text_exported': False}
