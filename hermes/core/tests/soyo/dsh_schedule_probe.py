# SPDX-License-Identifier: MIT
"""Real native one-shot Schedule -> grant -> tool -> persisted result; no platforms."""
import argparse
import json
import os
import time
import uuid
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    result = {'status': 'unverified', 'platform_effects': 0}
    try:
        with httpx.Client(transport=httpx.HTTPTransport(uds=config['automation_socket']),
                          base_url='http://soyo.automation', trust_env=False,
                          headers={'Authorization': 'Bearer ' + config['host_key']}, timeout=20) as client:
            marker = 'NATIVE_OCCURRENCE_' + uuid.uuid4().hex
            accepted = client.post('/automation-probe', json={'marker': marker}).raise_for_status().json()
            assert accepted['state'] == 'accepted', accepted
            result['schedule_id'] = accepted['schedule_id']
            until = time.monotonic() + 240
            while True:
                work = client.post('/automation-probe-status', json={'occurrence_at': accepted['scheduled_at']}).raise_for_status().json()
                if work['state'] in ['completed', 'failed', 'cancelled', 'skipped']:
                    break
                if time.monotonic() > until:
                    raise AssertionError('observer ended; no catch-up or repeated Schedule creation')
                time.sleep(2)
            assert work['state'] == 'completed' and work.get('probe_checked') and marker in work.get('final_text', ''), work
            assert not work.get('publication') and not work.get('feishu'), 'probe must never publish'
            result.update(status='verified', occurrence_id=work['id'], tool_grant_survived=True,
                          final_marker=marker, platform_effects=0)
    except BaseException as error:
        result['error'] = str(error)[:1600]
        raise
    finally:
        fd = os.open(args.evidence, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as file:
            json.dump(result, file, ensure_ascii=False, indent=2)
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
