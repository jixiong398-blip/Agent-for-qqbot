# SPDX-License-Identifier: GPL-3.0-only
"""Fixed authenticated Host operator worker, never registered as a model tool."""
import json
import os
import sys
from pathlib import Path
from soyo.platform import assert_private, is_root
if __package__:
    from .native_memory import connect
    from .native_goals import call as mutate
else:
    from native_memory import connect
    from native_goals import call as mutate


def call(config,args):
    if not (is_root() and config.get('direct_root') is True) and not config.get('operator_ui_enabled') and config.get('fixture_operator_ui') is not True:
        raise ValueError('authenticated direct-root goal operator backend required')
    if len(json.dumps(args))>6000:raise ValueError('bounded goal operator request required')
    with connect(config) as db:
        return mutate(db,config,{**args,'sender_id':'native-owner-ui'},True)


if __name__ == '__main__':
    path=Path(sys.argv[1]);assert_private(path, max_bytes=2 * 1024 * 1024)
    config=json.loads(path.read_text(encoding='utf-8'));args=json.loads(sys.stdin.buffer.read(8*1024))
    try:value=call(config,args)
    except ValueError as error:
        message=str(error);value={'error':{'code':message.split(':',1)[0] if message.startswith('GOAL_') else 'GOAL_REQUEST_REJECTED','message':message[:240]}}
    print(json.dumps(value,ensure_ascii=False))
