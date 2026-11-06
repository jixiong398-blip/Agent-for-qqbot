"""Explicit cross-platform sandbox selection; never inherit a root/systemd backend."""
import os
import uuid
from types import SimpleNamespace

import pytest

from soyo.qq import development_worker
from soyo import sandbox


def test_broker_defaults_to_disabled_without_starting_any_process(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('Unisolated candidate process started')
    monkeypatch.setattr(sandbox.subprocess, 'run', forbidden)
    result = development_worker.call({'development_home': str(tmp_path / 'development')},
                                     {'operation': 'test', 'work_id': 'action-' + str(uuid.uuid4())})
    assert result['state'] == 'blocked' and result['reason'] == 'isolated_execution_backend_required'


@pytest.mark.skipif(os.name == 'nt', reason='bubblewrap is Linux only; Windows uses an explicitly pinned Docker backend')
def test_broker_uses_only_explicit_bubblewrap_without_systemd_or_sudo(tmp_path, monkeypatch):
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        kwargs['stderr'].write(b'Ran 1 test in 0.001s\n\nOK\n')
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(sandbox.shutil, 'which', lambda value: '/fixture/bwrap')
    monkeypatch.setattr(sandbox.subprocess, 'run', run)
    result = development_worker.call({'development_home': str(tmp_path / 'development'), 'development': {'backend': 'bubblewrap'}},
                                     {'operation': 'test', 'work_id': 'action-' + str(uuid.uuid4())})
    assert commands[0][0] == '/fixture/bwrap'
    assert '--unshare-all' in commands[0]
    assert '--cap-drop' in commands[0]
    assert result['exit_code'] == 0
    assert result['sandbox'] == 'bubblewrap'


@pytest.mark.parametrize('image', ['', 'python:latest', 'python@sha256:bad'])
def test_docker_requires_an_immutable_digest(monkeypatch, image):
    monkeypatch.setattr(sandbox.shutil, 'which', lambda value: '/fixture/docker')
    assert not sandbox.sandbox_available({'development': {'backend': 'docker', 'image': image}})


def _capture_docker_argv(monkeypatch):
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        # `docker inspect` runs without captured streams; only the run itself
        # carries a TemporaryFile for stderr.
        if kwargs.get('stderr') is not None and hasattr(kwargs['stderr'], 'write'):
            kwargs['stderr'].write(b'Ran 1 test in 0.001s\n\nOK\n')
        return SimpleNamespace(returncode=0, stdout='')

    monkeypatch.setattr(sandbox.shutil, 'which', lambda value: '/fixture/docker')
    monkeypatch.setattr(sandbox.subprocess, 'run', run)
    return commands


DIGEST = 'docker.io/library/python@sha256:' + 'a' * 64


def test_sandbox_network_is_denied_when_the_config_omits_the_key(tmp_path, monkeypatch):
    """Outbound access is an explicit deployment choice, never an implicit one."""
    commands = _capture_docker_argv(monkeypatch)
    result = sandbox.run_sandbox({'development': {'backend': 'docker', 'image': DIGEST}},
                                 tmp_path, ['python', '-m', 'pytest'])
    assert result['exit_code'] == 0
    assert '--network=none' in commands[0]
    assert not any(item.startswith('--network=bridge') for item in commands[0])


def test_sandbox_network_requires_an_explicit_true(tmp_path, monkeypatch):
    commands = _capture_docker_argv(monkeypatch)
    sandbox.run_sandbox({'development': {'backend': 'docker', 'image': DIGEST, 'network': True}},
                        tmp_path, ['python', '-m', 'pytest'])
    assert '--network=bridge' in commands[0]


def test_sandbox_network_rejects_a_non_boolean_setting(tmp_path):
    from soyo.app import config
    home = tmp_path / 'instance'
    value = config.initialize(home)
    config.update(home, {'character_name': 'Fixture',
        'models': {'character': {'name': 'fixture', 'base_url': 'http://127.0.0.1:12345/v1', 'auth_mode': 'none',
            'api_key': '', 'api': 'openai-completions', 'context_window': 8192, 'max_tokens': 1024, 'vision': False}},
        'action_uses_character': True}, value['revision'])
    current = config.read_json(home / 'deployment.json')
    current['development'] = {'backend': 'disabled', 'network': 'yes'}
    with pytest.raises(ValueError, match='development.network'):
        config.validate(current)
