# SPDX-License-Identifier: GPL-3.0-only
"""Fixed SQLite operator entry; no model, platform, credential or Hermes imports.

This is not registered as a model tool. The authenticated native owner UI derives
the scene and invokes it in the existing direct-root Host, never a privilege helper.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from soyo.platform import assert_private, is_root

if __package__:
    from .native_memory import connect
    from .native_cognition import mutate_operator
else:
    from native_memory import connect
    from native_cognition import mutate_operator


def call(config, args):
    if not (is_root() and config.get('direct_root') is True) and not config.get('operator_ui_enabled') and config.get('fixture_operator_ui') is not True:
        raise ValueError('authenticated direct-root operator backend required')
    if len(json.dumps(args)) > 24000:
        raise ValueError('bounded native mutation required')
    with connect(config) as db:
        # Serialize both the idempotency lookup and the revision check across subprocesses.
        db.execute('BEGIN IMMEDIATE')
        return mutate_operator(db, args['route_id'], args, config)


if __name__ == '__main__':
    path = Path(sys.argv[1])
    assert_private(path, max_bytes=2 * 1024 * 1024)
    config = json.loads(path.read_text(encoding='utf-8')); args = json.loads(sys.stdin.buffer.read(32*1024))
    try:
        result = call(config, args)
    except ValueError as error:
        message = str(error)
        code = message.split(':', 1)[0] if message.startswith('COGNITION_') else 'MEMORY_REQUEST_REJECTED'
        result = {'error': {'code': code, 'message': message[:240]}}
    print(json.dumps(result, ensure_ascii=False))
