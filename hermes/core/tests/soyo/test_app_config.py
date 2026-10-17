"""Portable 1.0 setup contracts. No external provider, QQ, or user home access."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from soyo.app import config, persona
from soyo.platform import assert_private, file_lock, worker_environment


def route(**changes):
    return {"name": "fixture-model", "base_url": "http://127.0.0.1:12345/v1", "auth_mode": "none", "api_key": "",
            "api": "openai-completions", "context_window": 8192, "max_tokens": 1024, "vision": False, **changes}


def configured(tmp_path):
    home = tmp_path / "instance"
    value = config.initialize(home)
    config.update(home, {"character_name": "Fixture", "models": {"character": route()}, "action_uses_character": True}, value["revision"])
    return home, config.read_json(home / "deployment.json")


def test_new_instance_is_web_only_and_two_brains_can_share_a_local_model(tmp_path):
    home, value = configured(tmp_path)
    assert value['onebot']['enabled'] is False
    assert value['management_require_key'] is False and value['native_require_key'] is False
    assert value['models']['action'] == value['models']['character']
    config.validate(value, ready=True)
    assert_private(home / 'deployment.json')
    assert_private(home / 'private/control-key')


def test_enabling_qq_requires_explicit_identity_endpoints_and_owner(tmp_path):
    _, value = configured(tmp_path)
    value['onebot']['enabled'] = True
    with pytest.raises(ValueError, match='NapCat account'): config.validate(value, ready=True)


@pytest.mark.parametrize('url', ['http://192.0.2.1:12345/v1', 'https://provider.invalid/v1'])
def test_no_key_mode_cannot_leak_to_a_remote_provider(url):
    with pytest.raises(ValueError, match='local loopback'): config.model(route(base_url=url), required=True)


def test_bearer_mode_requires_a_key_and_no_key_mode_forgets_old_credentials():
    with pytest.raises(ValueError, match='API key'): config.model(route(auth_mode='bearer'), required=True)
    assert config.model(route(api_key='fixture-previous-secret'), required=True)['api_key'] == ''


def test_none_reasoning_alias_is_a_native_off_level_not_an_invalid_wire_name():
    assert config.model(route(reasoning_effort='none'), required=True)['reasoning_effort'] == 'off'
    mapping = {'off': 'none', 'low': 'low'}
    assert config.model(route(reasoning_effort='none', reasoning_efforts=mapping), required=True)['reasoning_efforts'] == mapping
    with pytest.raises(ValueError, match='at least one thinking level'):
        config.model(route(reasoning_efforts={'off': 'none'}), required=True)


def test_revision_conflicts_and_write_only_keys(tmp_path):
    home, value = configured(tmp_path)
    config.update(home, {'models': {'character': route(auth_mode='bearer', api_key='fixture-secret-not-real')}}, value['revision'])
    held = config.read_json(home / 'deployment.json')
    visible = config.update(home, {'models': {'character': {'api_key': ''}}}, held['revision'])
    assert 'fixture-secret-not-real' not in json.dumps(visible)
    assert config.read_json(home / 'deployment.json')['models']['character']['api_key'] == 'fixture-secret-not-real'
    with pytest.raises(ValueError, match='CONFIG_CONFLICT'): config.update(home, {}, value['revision'])


def test_named_supplier_profiles_keep_secrets_private_and_clear_stale_routes(tmp_path):
    home, value = configured(tmp_path)
    config.model_profile(home, 'save', '本地方案', value['revision'])
    held = config.read_json(home / 'deployment.json')
    config.update(home, {'routes': {'character': {'provider': 'qqbot-character', 'model': 'fixture-model', 'maxTokens': 512}}}, held['revision'])
    held = config.read_json(home / 'deployment.json')
    result = config.model_profile(home, 'use', '本地方案', held['revision'])
    assert result['routes'] == {} and result['action_uses_character']
    result = config.model_profile(home, 'delete', '本地方案', result['revision'])
    assert result['model_profiles'] == {}


def test_switching_model_clears_native_ui_route_selection(tmp_path):
    home, value = configured(tmp_path)
    config.update(home, {'routes': {'character': {'provider': 'qqbot-character', 'model': 'fixture-model', 'maxTokens': 512}}}, value['revision'])
    held = config.read_json(home / 'deployment.json')
    result = config.update(home, {'models': {'character': {'name': 'fixture-other-model'}}}, held['revision'])
    assert result['routes'] == {} and result['models']['action']['name'] == 'fixture-other-model'


def test_persona_presets_back_up_and_detect_editor_conflicts(tmp_path):
    home, _ = configured(tmp_path)
    initial = persona.save(home, text='# First role')
    saved = persona.save(home, text='# Second role', operation='save_preset', name='第二角色', digest=initial['digest'])
    assert saved['text'] == '# First role'
    applied = persona.save(home, operation='use_preset', name='第二角色', digest=initial['digest'])
    assert applied['text'] == '# Second role'
    assert any(p.read_text() == '# First role' for p in (home / 'backups').glob('persona-*.md'))
    with pytest.raises(ValueError, match='PERSONA_CONFLICT'): persona.save(home, text='stale', digest=initial['digest'])
    with pytest.raises(ValueError, match='preset name'): persona.save(home, operation='use_preset', name='../escape')


def test_private_file_lock_rejects_a_second_writer(tmp_path):
    path = tmp_path / 'fixture.lock'
    with file_lock(path):
        with pytest.raises(OSError):
            with file_lock(path, blocking=False): pass


def test_child_environment_retains_case_insensitive_os_keys_but_no_provider_secrets(monkeypatch):
    monkeypatch.setenv('SYSTEMROOT', r'C:\Windows')
    monkeypatch.setenv('Fixture_Model_API_Key', 'must-not-be-inherited')
    value = worker_environment()
    assert next(v for k, v in value.items() if k.upper() == 'SYSTEMROOT') == r'C:\Windows'
    assert all('must-not-be-inherited' != v for v in value.values())


def test_web_only_manager_never_initializes_napcat_or_gateway(tmp_path, monkeypatch):
    from soyo.app import manager, install
    from soyo import transport
    from soyo.qq import runtime as qq_runtime
    home, _ = configured(tmp_path)
    config.atomic_json(home / 'private/runtime.json', {'directory': str(home / 'runtime'), 'node': 'node', 'cli': 'fixture-cli', 'source_fingerprint': 'fixture'})
    monkeypatch.setattr(install, 'source_fingerprint', lambda: 'fixture')
    monkeypatch.setattr(manager, 'render', lambda *args: ({}, home / 'profiles/qqbot'))
    def forbidden(*args, **kwargs): raise AssertionError('QQ was accessed in Web-only mode')
    monkeypatch.setattr(qq_runtime, 'NapCat', forbidden)
    monkeypatch.setattr(qq_runtime, 'other_gateway_idle', forbidden)
    instance = manager.Manager(home)
    monkeypatch.setattr(instance, 'start_gateway', forbidden)
    spawned = []
    monkeypatch.setattr(instance, 'spawn', lambda name, *args, **kwargs: spawned.append(name) or SimpleNamespace(poll=lambda: None))
    class Client:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, *args, **kwargs): return SimpleNamespace(status_code=200, json=lambda: {'backend': 'dsh-native'})
    monkeypatch.setattr(transport, 'private_client', lambda *args, **kwargs: Client())
    result = instance.start_native()
    assert spawned == ['web'] and result['mode'] == 'web-only'
    assert result['services']['gateway']['state'] == 'disabled'
    with pytest.raises(ValueError, match='NapCat launch command'): instance.start_optional('napcat')


def test_legacy_process_fence_is_read_only_and_fails_closed(monkeypatch):
    from soyo.qq import runtime
    import psutil
    process = SimpleNamespace(pid=-99, info={'name': 'python'}, cmdline=lambda: ['python', '-m', 'hermes_cli.main', 'gateway'])
    monkeypatch.setattr(psutil, 'process_iter', lambda *args: [process])
    with pytest.raises(RuntimeError, match='Legacy Hermes writer'): runtime.other_gateway_idle({})


@pytest.mark.parametrize('host,allowed', [('127.0.0.1', True), ('100.64.0.1', False), ('100.127.255.254', False),
    ('0.0.0.0', False), ('192.168.1.2', False), ('8.8.8.8', False), ('100.128.0.1', False), ('localhost', False)])
def test_product_ui_binding_is_loopback_only(host, allowed):
    assert config.trusted_ui_host(host) is allowed


def test_direct_ui_checks_actual_peer_instead_of_proxy_headers():
    assert not config.trusted_ui_peer('100.64.0.2', '100.64.0.1')
    assert config.trusted_ui_peer('::ffff:127.0.0.1', '127.0.0.1')
    assert not config.trusted_ui_peer('100.64.0.2', '127.0.0.1')
    assert not config.trusted_ui_peer('192.168.1.2', '100.64.0.1')
    assert not config.trusted_ui_peer('127.0.0.1', '0.0.0.0')
