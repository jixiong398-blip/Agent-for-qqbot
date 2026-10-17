# SPDX-License-Identifier: MIT
"""Actual HTTP access contract; no external models or QQ connections."""
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest

from soyo.app.config import initialize, update
from soyo.platform import worker_environment


@pytest.mark.parametrize('require_key', [False, True])
def test_direct_entry_or_opt_in_key_keep_host_origin_and_csrf_guards(tmp_path, require_key):
    home = tmp_path / 'instance'; config = initialize(home)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
    update(home, {'management_port': port, 'management_require_key': require_key}, config['revision'])
    origin = f'http://127.0.0.1:{port}'
    child = subprocess.Popen([sys.executable, '-B', '-m', 'soyo.app', '--home', str(home), 'start', '--no-browser', '--no-autostart'],
                             env=worker_environment(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with httpx.Client(base_url=origin, trust_env=False, timeout=3) as client:
            deadline = time.monotonic() + 15
            while True:
                try:
                    if client.get('/').status_code == 200: break
                except httpx.HTTPError: pass
                if child.poll() is not None or time.monotonic() > deadline: raise AssertionError('private test supervisor not ready')
                time.sleep(.1)
            assert client.get('/api/config').status_code == (401 if require_key else 200)
            key = (home / 'private/control-key').read_text().strip()
            client.headers['Authorization'] = 'Bearer ' + key
            csrf = client.get('/api/csrf').json()['csrf']
            body = {'revision': 2, 'changes': {'character_name': 'private fixture'}}
            assert client.post('/api/config', json=body, headers={'Origin': 'http://attacker.invalid', 'X-Agent-CSRF': csrf}).status_code == 403
            assert client.post('/api/config', json=body, headers={'Origin': origin}).status_code == 403
            assert client.get('/api/config', headers={'Host': 'attacker.invalid', 'X-Forwarded-For': '127.0.0.1'}).status_code == 403
            saved = client.post('/api/config', json=body, headers={'Origin': origin, 'X-Agent-CSRF': csrf})
            assert saved.status_code == 200 and saved.json()['character_name'] == 'private fixture'
            assert key not in saved.text
            assert client.post('/api/shutdown', json={}, headers={'Origin': origin, 'X-Agent-CSRF': csrf}).status_code == 200
        assert child.wait(timeout=15) == 0
    finally:
        if child.poll() is None: child.terminate(); child.wait(timeout=10)
