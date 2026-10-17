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
