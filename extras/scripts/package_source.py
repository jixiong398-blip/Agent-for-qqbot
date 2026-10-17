#!/usr/bin/env python3
"""Explicit source-only staging. No dependency install, service, Git commit or publish."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[2]
ROOT_FILES = {'README.md', 'USER_AGENTS.md', 'UPGRADE.md', 'MIGRATION.md', 'VALIDATION.md', 'THIRD_PARTY_NOTICES.md',
    'LICENSE', 'VERSION', 'CHANGELOG.md', 'application.toml', 'install.bat', 'start.bat', 'Stop-All.bat',
    '配置API.bat', 'update.bat', 'install.sh', 'start.sh', 'configure.sh', 'stop.sh', 'update.sh', '.gitignore', '.gitattributes'}
SCRIPT_FILES = {'bootstrap.py', 'bootstrap.ps1', 'portable_launcher.py', 'build_portable.py', 'install.py', 'setup_config.py', 'upgrade.py', 'decrypt_cvpkg.py', 'package_source.py'}


def allowed(name):
    p = Path(name)
    if name in ROOT_FILES or name in {'hermes/README.md', 'hermes/.gitattributes', 'hermes/core/LICENSE', 'hermes/core/pyproject.toml'}: return True
    if name.startswith('templates/'): return p.name in {'deployment.example.json', 'deployment.local.example.json', 'SOUL-template.md', 'README.md', 'BEHAVIOR-template.md', '.env.template', 'config-template.yaml'}
    if name.startswith('hermes/templates/'): return p.name in {'SOUL-template.md', 'CORTEX.md', 'CEREBELLUM.md', '.env.template', 'config-template.yaml'}
    if name.startswith('extras/scripts/'): return p.name in SCRIPT_FILES
    if name in {'extras/build-release.ps1', 'extras/build-installer.iss', 'extras/build-installer.nsi'}: return True
    if name.startswith('hermes/core/soyo/'):
        return '__pycache__' not in p.parts and p.suffix in {'.py', '.mjs', '.js', '.json', '.md'} or name.startswith('hermes/core/soyo/') and p.name == 'LICENSE'
    if name.startswith('hermes/core/tests/soyo/'):
        return '__pycache__' not in p.parts and (p.name == 'conftest.py' or p.name.startswith('test_') and p.suffix == '.py'
            or p.name.endswith('.test.mjs') or p.name.startswith('dsh_') and p.name.endswith('_test.mjs'))
    if name.startswith('modules/dashboard/'):
        return name in {'modules/dashboard/server.py', 'modules/dashboard/static/index.html', 'modules/dashboard/static/app.css', 'modules/dashboard/static/app.js'}
    if name.startswith('modules/live2d/'):
        return not any(part in {'node_modules', 'models', 'figure', 'downloads'} for part in p.parts) and p.name not in {'conf.json', 'window_state.json', 'live2d_pref.json', 'package-lock.json'} and p.suffix in {'.js', '.css', '.html', '.json', '.png', '.ico', '.md'}
    return False  # NapCat login/runtime, knowledge vaults, internal docs and all homes are excluded.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New empty staging directory outside the checkout')
    parser.add_argument('--acknowledge-unverified', action='store_true')
    args = parser.parse_args()
    if not args.acknowledge_unverified: raise SystemExit('This source candidate is unreleased and has outstanding gates. Explicitly acknowledge before packaging; this is not a release approval.')
    destination = args.output.expanduser().resolve()
    if destination == ROOT or ROOT in destination.parents or destination.exists(): raise SystemExit('Use a new directory outside the source checkout; never overwrite an existing destination')
    version = (ROOT/'VERSION').read_text(encoding='utf-8-sig').strip()
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version): raise SystemExit('VERSION must be a numeric release version')
    meta = tomllib.loads((ROOT/'application.toml').read_text(encoding='utf-8'))['project']
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT).split(b'\0')
    selected = sorted({x.decode('utf-8').replace('\\','/') for x in names if x and allowed(x.decode('utf-8').replace('\\','/'))})
    payloads = {}
    for name in selected:
        file = ROOT/name
        if not file.is_file(): continue  # Expected source deletions are not restored.
        if file.is_symlink() or getattr(file, 'is_junction', lambda:False)(): raise SystemExit('Linked package input rejected: '+name)
        if any(part.startswith('_') and part not in {'__init__.py','__main__.py'} for part in Path(name).parts): continue
        data=file.read_bytes()
        if re.search(rb'\bsk-[A-Za-z0-9_-]{20,}', data): raise SystemExit('Credential-shaped source content requires review: '+name)
        payloads[name]=data
    required = {'application.toml','hermes/core/soyo/app/__main__.py','hermes/core/soyo/dsh/host/package.json','hermes/core/soyo/dsh/asuna-ui/vendor/source.json'}
    if required-set(payloads): raise SystemExit('Required source inputs ignored or missing: '+','.join(sorted(required-set(payloads))))
    destination.mkdir(parents=True, exist_ok=False)
    manifest=[]
    for name,data in payloads.items():
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        manifest.append({'path':name,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
    product=meta['name'];url='https://github.com/'+meta['repository']
    if not re.fullmatch(r'[A-Za-z0-9_-]+',product) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',meta['repository']): raise SystemExit('Unsupported installer product metadata')
    defines={'APP_NAME':product,'APP_VERSION':version,'APP_URL':url}
    for name,prefix,suffix in [('installer-defines.iss','#define',''),('installer-defines.nsh','!define','')]:
        (destination/name).write_text('\n'.join(f'{prefix} {key} "{value}"{suffix}' for key,value in defines.items())+'\n',encoding='utf-8')
    (destination/'SOURCE_MANIFEST.json').write_text(json.dumps({'unverified_candidate':True,'files':manifest,'dependency_bundles_included':False},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'source_stage':str(destination),'files':len(manifest),'tests_run':False,'services_started':False,'published':False}))

if __name__=='__main__':main()
