# SPDX-License-Identifier: MIT
"""Provision only a clean bundled NapCat, never copy the maintainer's runtime/login data."""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil

from soyo.platform import is_link, protect
from .config import atomic_json, read_json, update


def provision(home, bundle, version):
    home, bundle = Path(home), Path(bundle)
    target = home / 'napcat'
    receipt = read_json(home / 'private/napcat-runtime.json', default={})
    if target.exists():
        if not receipt: raise ValueError('Unfamiliar NapCat directory retained; choose a new instance')
        return  # Updates never overwrite an existing login or QQ runtime in place.
    shutil.copytree(bundle, target)
    protect(target, directory=True)
    config = read_json(home / 'deployment.json')
    directory = target / 'napcat' if os.name == 'nt' else target
    settings = directory / 'config'; settings.mkdir(exist_ok=True)
    protect(settings, directory=True)
    token = secrets.token_urlsafe(32)
    webui = {'host': '127.0.0.1', 'port': config['napcat_web_port'], 'prefix': '', 'token': token,
             'loginRate': 3, 'disableWebUI': False}
    atomic_json(settings / 'webui.json', webui)
    atomic_json(home / 'private/napcat-webui.json', {'token': token})
    atomic_json(home / 'private/napcat-runtime.json', {'version': version, 'directory': str(target), 'managed': True})
    update(home, {'napcat': {'directory': str(target)}, 'onebot': {'config_directory': str(settings)}}, config['revision'])


def configure_account(home, account_id):
    home = Path(home); config = read_json(home / 'deployment.json')
    if not re.fullmatch(r'[1-9][0-9]{0,19}', str(account_id)):
        raise ValueError('Select an account generated after the user logged into NapCat')
    directory = Path(config['onebot'].get('config_directory', ''))
    expected = home / 'napcat'
    if is_link(directory) or any(is_link(parent) for parent in directory.parents):
        raise ValueError('Linked NapCat configuration rejected')
    try: directory.resolve(strict=True).relative_to(expected.resolve(strict=True))
    except (ValueError, OSError): raise ValueError('Automatic linking is limited to this instance bundled NapCat') from None
    file = directory / ('onebot11_' + str(account_id) + '.json')
    if not file.is_file() or is_link(file) or file.stat().st_size > 1024 * 1024:
        raise ValueError('Log into this NapCat instance first; no account file was found')
    original = file.read_bytes()
    current = json.loads(original.decode('utf-8-sig'))
    if not isinstance(current, dict): raise ValueError('Invalid account configuration')
    next_value = copy.deepcopy(current); network = next_value.setdefault('network', {})
    if not isinstance(network, dict): raise ValueError('Invalid OneBot network configuration')
    token = config['onebot']['token'] if config['onebot'].get('account_id') == str(account_id) and config['onebot'].get('token') else secrets.token_urlsafe(32)
    for key, name, port in [('httpServers', 'Bot HTTP', config['onebot_http_port']), ('websocketServers', 'Bot WS', config['onebot_ws_port'])]:
        old = network.setdefault(key, [])
        if not isinstance(old, list) or any(not isinstance(row, dict) for row in old): raise ValueError('Invalid OneBot listener list')
        unrelated = [row for row in old if row.get('name') != name]
        if any(row.get('enable', row.get('enabled', False)) for row in unrelated):
            raise ValueError('Another enabled listener exists; disable it in NapCat WebUI before automatic linking')
        network[key] = unrelated + [{'name': name, 'enable': True, 'host': '127.0.0.1', 'port': port,
                                     'token': token, 'messagePostFormat': 'array', 'reportSelfMessage': False}]
    # Read the third-party account file only at explicit operator request; keep a bounded recovery copy.
    atomic_json(home / 'backups' / ('napcat-account-' + secrets.token_hex(8) + '.json'), current)
    if file.read_bytes() != original: raise ValueError('NapCat account configuration changed; reload before linking')
    atomic_json(file, next_value)
    written = hashlib.sha256(file.read_bytes()).digest()
    try:
        return update(home, {'onebot': {'account_id': str(account_id), 'http_url': f'http://127.0.0.1:{config["onebot_http_port"]}',
            'ws_url': f'ws://127.0.0.1:{config["onebot_ws_port"]}', 'token': token}}, config['revision'])
    except Exception:
        # Restore only our own write. A concurrent WebUI edit must never be discarded.
        if hashlib.sha256(file.read_bytes()).digest() == written: atomic_json(file, current)
        raise
