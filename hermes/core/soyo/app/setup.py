# SPDX-License-Identifier: MIT
"""Native DSH operator setup, queued application, and private NapCat management."""
from __future__ import annotations
import copy
import hashlib
import os
from pathlib import Path
import secrets
import time

from .config import atomic_json, read_json, redacted, update, validate, valid_profile_label
from . import persona
from soyo.platform import file_lock

PENDING = {'queued', 'applying'}
EDITABLE = {'character_name', 'models', 'action_uses_character', 'onebot', 'host_permission_mode', 'time_zone'}


def ready(config):
    try:
        validate(copy.deepcopy(config), ready=True)
        return True
    except ValueError:
        return False


def view(manager):
    home = manager.home
    config = read_json(home / 'deployment.json')
    operation = read_json(home / 'run/setup-apply.json', default={})
    directory = Path(config['napcat']['directory'])
    receipt = read_json(home / 'private/napcat-runtime.json', default={})
    from .onebot import accounts
    launch_ready = bool(config['napcat'].get('command')) or os.name == 'nt' and (directory / 'napcat.bat').is_file()
    return {'config': redacted(config), 'persona': persona.view(home), 'status': manager.status(),
            'configured': ready(config), 'operation': {k: operation[k] for k in ('id', 'phase', 'error_type') if k in operation},
            'napcat': {'installed': directory.is_dir() and bool(receipt), 'version': receipt.get('version', ''),
                       'launch_ready': launch_ready,
                       'launch_hint': '' if launch_ready else ('此开发实例未装配 NapCat；预构建包包含干净组件。' if os.name == 'nt' else
                           'Linux Shell 仍需兼容的 QQ 宿主及显式启动命令；可连接另行安装的本机 NapCat。'),
                       'webui_url': f'http://127.0.0.1:{config["napcat_web_port"]}/',
                       'accounts': accounts(config['onebot'].get('config_directory', ''))}}


def queue(manager, request):
    if not isinstance(request, dict) or set(request) - {'revision', 'changes', 'persona', 'persona_digest', 'use_model_profile', 'save_model_profile'}:
        raise ValueError('Bounded native setup request required')
    home = manager.home
    with manager.lock:
        current = read_json(home / 'deployment.json')
        operation = read_json(home / 'run/setup-apply.json', default={})
        if operation.get('phase') in PENDING:
            raise ValueError('Setup application already pending')
        if request.get('revision') != current['revision']:
            raise ValueError('CONFIG_CONFLICT: reload before saving')
        changes = copy.deepcopy(request.get('changes', {}))
        if not isinstance(changes, dict) or set(changes) - EDITABLE:
            raise ValueError('Only Bot identity, brain models, permission and QQ settings can be edited here')
        saved_profile = request.get('use_model_profile')
        if saved_profile:
            saved = current.get('model_profiles', {}).get(saved_profile)
            if not saved: raise ValueError('Choose an existing named model profile')
            changes['models'] = copy.deepcopy(saved)
            changes['action_uses_character'] = saved['character'] == saved['action']
        # Validate using a temporary in-memory candidate; merge secrets exactly as the real config writer does.
        from .config import merge
        candidate = merge(current, changes)
        if 'models' in changes:
            candidate['routes'] = {}
        for lane, patch in changes.get('models', {}).items():
            if lane not in {'character', 'action'}: raise ValueError('Only two brain routes are editable here')
            old = current['models'].get(lane, {})
            if isinstance(patch, dict) and patch.get('base_url', old.get('base_url')) != old.get('base_url') and not patch.get('api_key') and candidate['models'][lane].get('auth_mode', 'bearer') == 'bearer':
                raise ValueError('Enter a new API key when changing provider endpoint; old credentials are not forwarded')
        if saved_profile:
            candidate['models']['fallbacks'] = []
            changes['models']['fallbacks'] = []
        validate(candidate, ready=True)
        save_name = request.get('save_model_profile')
        if save_name:
            if not valid_profile_label(save_name): raise ValueError('A short nonempty model profile name is required')
            library = copy.deepcopy(current.get('model_profiles', {}))
            library[save_name] = {lane: candidate['models'][lane] for lane in ('character', 'action')}
            if len(library) > 32: raise ValueError('At most 32 named model profiles are supported')
            changes['model_profiles'] = library  # Only a server-derived credential-bearing library enters the writer.
        text = request.get('persona')
        if not isinstance(text, str) or not text.strip() or len(text.encode('utf-8')) > 256 * 1024:
            raise ValueError('A nonempty bounded persona is required')
        if request.get('persona_digest') != persona.view(home)['digest']:
            raise ValueError('PERSONA_CONFLICT: reload before saving')
        pending = {'id': secrets.token_hex(16), 'phase': 'queued', 'created_at': time.time(),
                   'revision': current['revision'], 'changes': changes, 'persona': text, 'persona_digest': request['persona_digest']}
        atomic_json(home / 'run/setup-apply.json', pending)
        return {'accepted': True, 'id': pending['id'], 'phase': 'queued'}


def _idle(manager):
    if not manager.status()['services']['web']['running']: return True
    native = read_json(manager.home / 'private/channel.json', default={})
    # Setup-only Web has no model agent or QQ host. It cannot be executing tools.
    if read_json(manager.home / 'run/native-mode.json', default={}).get('setup') is True: return True
    from soyo.transport import private_client
    with private_client(native, timeout=3) as client:
        response = client.post('/health', json={}); response.raise_for_status(); health = response.json()
    return not any(health.get(key, 0) for key in ('native_active_turns', 'active_actions', 'active_turns', 'unfinished'))


def persona_preset(manager, request):
    if not isinstance(request, dict) or set(request) - {'operation', 'name', 'text'}: raise ValueError('Bounded persona preset request required')
    name = persona._name(request.get('name'))
    if request.get('operation') == 'read':
        return {'text': persona._read(manager.home / 'persona/presets' / (name + '.md'))}
    if request.get('operation') == 'save':
        with manager.lock:
            persona.save(manager.home, text=request.get('text'), operation='save_preset', name=name)
            return {'saved': True, 'presets': persona.view(manager.home)['presets']}
    raise ValueError('Unknown persona preset operation')


def _journal(manager, request, previous, old_persona):
    from .config import merge
    after = merge(previous, request['changes'])
    if 'models' in request['changes']: after['routes'] = {}
    validate(after, ready=True); after['revision'] += 1
    value = {'before': previous, 'after': after, 'persona_before': old_persona,
             'persona_after_digest': hashlib.sha256(request['persona'].encode()).hexdigest()}
    atomic_json(manager.home / 'backups' / ('setup-' + request['id'] + '.json'), value)
    return value


def _rollback(manager, journal):
    home = manager.home
    before, after = journal['before'], journal['after']
    actual_persona = persona.view(home)
    if actual_persona['digest'] not in {journal['persona_before']['digest'], journal['persona_after_digest']}:
        raise ValueError('Persona changed independently; recovery evidence retained without overwriting it')
    with file_lock(home / 'run/config.lock'):
        held = read_json(home / 'deployment.json')
        if held not in (before, after): raise ValueError('Rollback conflict; independent configuration retained')
        restored = copy.deepcopy(before); restored['revision'] = held['revision'] + 1
        atomic_json(home / 'deployment.json', restored)
    if actual_persona['digest'] != journal['persona_before']['digest']:
        text = journal['persona_before']['text']
        if text: persona.save(home, text=text, digest=journal['persona_after_digest'])
        else:
            with file_lock(home / 'run/persona.lock'):
                if persona.view(home)['digest'] != journal['persona_after_digest']: raise ValueError('Persona rollback conflict')
                (home / 'persona/SOUL.md').unlink()  # Only this failed transaction's newly-created file.
    manager.config = read_json(home / 'deployment.json')


def _finish(path, request):
    # No second live copy of provider/OneBot credentials in the operation receipt.
    receipt = {key: value for key, value in request.items() if key not in {'changes', 'persona'}}
    receipt['finished_at'] = time.time(); atomic_json(path, receipt)


def recover_interrupted(manager):
    path = manager.home / 'run/setup-apply.json'; request = read_json(path, default={})
    if request.get('phase') != 'applying': return
    if not _idle(manager): raise ValueError('Interrupted setup has an active owned turn; stop it explicitly before recovery')
    manager.stop_native()
    journal = read_json(manager.home / 'backups' / ('setup-' + request['id'] + '.json'))
    if not journal: raise ValueError('Interrupted setup journal unavailable; no configuration was overwritten')
    _rollback(manager, journal)
    request['phase'] = 'recovered_previous'; _finish(path, request)


def apply_pending(manager):
    home = manager.home; path = home / 'run/setup-apply.json'
    request = read_json(path, default={})
    if request.get('phase') != 'queued': return
    with manager.lock:
        previous = read_json(home / 'deployment.json'); old_persona = persona.view(home)
        try:
            if previous['revision'] != request['revision']: raise ValueError('Configuration changed before apply')
            if old_persona['digest'] != request['persona_digest']: raise ValueError('Persona changed before apply')
            if not _idle(manager): return
            manager.stop('gateway')
            if not _idle(manager): return
            journal = _journal(manager, request, previous, old_persona)
            request['phase'] = 'applying'; atomic_json(path, request)
            manager.stop('web')
            try:
                update(home, request['changes'], previous['revision'])
                persona.save(home, text=request['persona'], digest=request['persona_digest'])
                manager.start_native()
            except Exception:
                _rollback(manager, journal)
                manager.start_native()
                raise
            request['phase'] = 'applied'
        except Exception as error:
            request.update(phase='failed', error_type=type(error).__name__)
            manager.log('manager', 'Native setup application failed; configuration/recovery evidence retained')
        finally:
            if request.get('phase') in {'applied', 'failed'}: _finish(path, request)


def napcat_operation(manager, request):
    if not isinstance(request, dict) or set(request) - {'operation', 'account_id', 'revision'}:
        raise ValueError('Bounded NapCat operation required')
    with manager.lock:
        if read_json(manager.home / 'run/setup-apply.json', default={}).get('phase') in PENDING:
            raise ValueError('Wait for the pending native configuration before changing NapCat')
        return _napcat_operation(manager, request)


def _napcat_operation(manager, request):
    operation = request.get('operation')
    if operation in {'start', 'stop', 'restart'}:
        if operation == 'start': manager.start_optional('napcat')
        else:
            manager.stop('gateway'); manager.stop('napcat')
            if operation == 'restart': manager.start_optional('napcat')
    elif operation == 'link':
        from .napcat import configure_account
        current = read_json(manager.home / 'deployment.json')
        if request.get('revision') != current['revision']:
            raise ValueError('CONFIG_CONFLICT: reload before linking an account')
        manager.stop('gateway')
        result = configure_account(manager.home, request.get('account_id'))
        manager.config = read_json(manager.home / 'deployment.json')
        return result
    elif operation == 'connect':
        if not ready(read_json(manager.home / 'deployment.json')): raise ValueError('Configure both brains first')
        manager.connect_qq()
    elif operation == 'disconnect': manager.stop('gateway')
    elif operation == 'webui-key':
        value = read_json(manager.home / 'private/napcat-webui.json', default={})
        return {'key': value.get('token', '')}
    else: raise ValueError('Unknown NapCat operation')
    return {'status': manager.status()}
