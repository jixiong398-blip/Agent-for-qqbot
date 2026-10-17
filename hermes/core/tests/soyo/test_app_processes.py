# SPDX-License-Identifier: MIT
"""Real owned child lifecycle, including the Windows Job Object API."""
import subprocess
import sys

import pytest

from soyo.app.config import initialize, update
from soyo.app.manager import Manager
from soyo.platform import worker_environment


def instance(tmp_path):
    home = tmp_path / 'instance'; config = initialize(home)
    update(home, {'stop_timeout': 1}, config['revision'])
    return Manager(home)


def test_owned_child_is_recorded_then_stopped_without_port_or_name_kills(tmp_path):
    manager = instance(tmp_path)
    child = manager.spawn('web', [sys.executable, '-B', '-c', 'import time;time.sleep(20)'],
                          cwd=manager.home / 'workspace', env=worker_environment())
    try:
        assert manager.retained['web']['pid'] == child.pid
        assert manager.status()['services']['web']['running']
    finally:
        manager.stop('web')
    assert child.wait(timeout=5) is not None
    assert 'web' not in manager.retained and 'web' not in manager.jobs


def test_failed_process_record_does_not_leave_an_unowned_child(tmp_path, monkeypatch):
    manager = instance(tmp_path)
    children, real = [], subprocess.Popen
    def capture(*args, **kwargs):
        child = real(*args, **kwargs); children.append(child); return child
    monkeypatch.setattr(subprocess, 'Popen', capture)
    def fail(): raise OSError('fixture record unavailable')
    monkeypatch.setattr(manager, '_persist', fail)
    with pytest.raises(OSError, match='record unavailable'):
        manager.spawn('web', [sys.executable, '-B', '-c', 'import time;time.sleep(20)'],
                      cwd=manager.home / 'workspace', env=worker_environment())
    assert len(children) == 1 and children[0].poll() is not None
    assert not manager.retained and not manager.jobs
