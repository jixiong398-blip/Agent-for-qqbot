"""Local writer-fence contracts after real process/WebSocket/SQLite probing."""
import subprocess
import os
from types import SimpleNamespace

import pytest

from soyo.qq import runtime

pytestmark = pytest.mark.skipif(os.name == 'nt', reason='Explicit POSIX systemd adapter; Windows process fences are tested separately')


@pytest.mark.parametrize('state', ['inactive', 'failed'])
def test_quiescent_competitor_is_accepted(monkeypatch, state):
    monkeypatch.setattr(runtime.os, 'getuid', lambda: 1000)
    calls = []
    def query(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout='ActiveState=' + state + '\n')
    monkeypatch.setattr(runtime.subprocess, 'run', query)
    runtime.other_gateway_idle({'competing_unit': 'fixture.service', 'competing_user_uid': 1000})
    assert calls[0][0] == ['systemctl', '--user', 'show', 'fixture.service', '-p', 'ActiveState']
    assert calls[0][1]['check'] and calls[0][1]['timeout'] == 5


@pytest.mark.parametrize('output', ['ActiveState=active', 'ActiveState=activating', 'ActiveState=deactivating',
                                   'ActiveState=reloading', 'ActiveState=unknown', '', 'inactive'])
def test_active_or_ambiguous_competitor_is_refused(monkeypatch, output):
    monkeypatch.setattr(runtime.os, 'getuid', lambda: 1000)
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout=output))
    with pytest.raises(RuntimeError, match='refusing OneBot writer'):
        runtime.other_gateway_idle({'competing_unit': 'fixture.service'})


@pytest.mark.parametrize('error', [subprocess.TimeoutExpired(['systemctl'], 5),
                                  subprocess.CalledProcessError(1, ['systemctl']), OSError('fixture query unavailable')])
def test_failed_query_is_not_converted_to_inactive(monkeypatch, error):
    monkeypatch.setattr(runtime.os, 'getuid', lambda: 1000)
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(runtime.subprocess, 'run', fail)
    with pytest.raises(type(error)):
        runtime.other_gateway_idle({'competing_unit': 'fixture.service'})


def test_direct_root_queries_the_deployment_users_manager(monkeypatch):
    import pwd
    monkeypatch.setattr(runtime.os, 'getuid', lambda: 0)
    monkeypatch.setattr(pwd, 'getpwuid', lambda uid: SimpleNamespace(pw_name='fixture-user', pw_dir='/fixture/home'))
    calls = []
    def query(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout='ActiveState=inactive\n')
    monkeypatch.setattr(runtime.subprocess, 'run', query)
    runtime.other_gateway_idle({'competing_unit': 'fixture.service', 'competing_user_uid': 1000})
    command, options = calls[0]
    assert command[:4] == ['/usr/sbin/runuser', '-u', 'fixture-user', '--']
    assert options['env']['XDG_RUNTIME_DIR'] == '/run/user/1000'
    assert options['env']['HOME'] == '/fixture/home'
