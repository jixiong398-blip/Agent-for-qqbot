# SPDX-License-Identifier: MIT
"""Install a reviewed prebuilt closure; no pip/npm/Git/compiler or provider discovery."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess

from soyo.platform import bootstrap_directory, file_lock, is_link
from .config import atomic_json, home_path, initialize, read_json
from .install import require_stopped, select_runtime, source_fingerprint


def relative(root, value):
    if not isinstance(value, str) or not value: raise ValueError('Portable path missing')
    path = Path(value)
    if path.anchor or value.startswith('/') or '..' in path.parts or ':' in value or '\\' in value:
        raise ValueError('Portable manifest paths must be bounded relative paths')
    return root / path


def manifest(root):
    root = Path(root).resolve()
    value = json.loads((root / 'portable-manifest.json').read_text(encoding='utf-8'))
    expected = 'windows-x64' if os.name == 'nt' else 'linux-x64'
    if value.get('schema') != 1 or value.get('platform') != expected or platform.machine().lower() not in {'amd64', 'x86_64'}:
        raise ValueError('Download the prebuilt package for this OS and architecture')
    for name, digest in value['files'].items():
        path = relative(root, name)
        path.resolve(strict=True).relative_to(root)
        if is_link(path) or not path.is_file():
            raise ValueError('Prebuilt file missing or modified: ' + name)
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != digest:
            raise ValueError('Prebuilt file missing or modified: ' + name)
    return root, value


def restore_links(root, value):
    node = relative(root, value['node']); rows = []
    for row in value['links']:
        link, target = relative(root, row['path']), relative(root, row['target'])
        target.resolve(strict=True).relative_to(root)
        link.parent.resolve().relative_to(root)
        if is_link(link):
            if link.resolve(strict=True) != target.resolve(strict=True): raise ValueError('Unfamiliar prebuilt link retained')
            continue
        if link.exists(): raise ValueError('Real prebuilt link destination retained')
        if not target.is_dir(): raise ValueError('Prebuilt link target unavailable')
        link.parent.mkdir(parents=True, exist_ok=True); rows.append([str(target), str(link)])
    script = "const fs=require('node:fs');for(const [target,link] of JSON.parse(fs.readFileSync(0,'utf8')))fs.symlinkSync(target,link,process.platform==='win32'?'junction':'dir');"
    if rows: subprocess.run([str(node), '-e', script], input=json.dumps(rows), text=True, check=True)


def install(root, home):
    root, value = manifest(root); home = home_path(home)
    bootstrap_directory(home); initialize(home)
    with file_lock(home / 'run/lifecycle.lock', blocking=False), file_lock(home / 'run/install.lock', blocking=False):
        require_stopped(home); restore_links(root, value)
        runtime = relative(root, value['runtime'])
        receipt = {'directory': str(runtime), 'modules': str(runtime / 'native/node_modules'),
                   'node': str(relative(root, value['node'])), 'cli': str(relative(root, value['cli'])),
                   'source_fingerprint': source_fingerprint(), 'dsh_version': value['dsh_version'],
                   'portable_bundle_id': value['bundle_id'], 'portable_root': str(root), 'prebuilt': True}
        select_runtime(home, receipt)
        from .napcat import provision
        provision(home, relative(root, value['napcat']), value['napcat_version'])
        atomic_json(home / 'private/portable-install.json', {'bundle_id': value['bundle_id'], 'version': value['version'],
                    'platform': value['platform'], 'network_installs': False, 'models_called': False, 'qq_started': False})
    return home


def ensure(root, home):
    value = json.loads((Path(root) / 'portable-manifest.json').read_text(encoding='utf-8'))
    selected = read_json(Path(home) / 'private/runtime.json', default={})
    if selected.get('portable_bundle_id') != value['bundle_id'] or selected.get('portable_root') != str(Path(root).resolve()):
        return install(root, home)
    return Path(home)
