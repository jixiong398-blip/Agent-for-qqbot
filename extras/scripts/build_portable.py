#!/usr/bin/env python3
"""Maintainer-only prebuilt packaging. Exports a compiled closure, never a running home."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hermes/core'))
from soyo.platform import is_link
from package_source import allowed
from soyo.app.install import source_fingerprint


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked_archive(path, expected):
    if sha(path) != expected: raise ValueError('Build asset hash differs from the reviewed product pin')


def normalize_build_regions(data):
    """Only generated region-comment prefixes; never rewrite code, CSS, maps or notices."""
    return re.sub(rb'(?m)^([ \t]*//#region [^\r\n]*?)(?:(?<![A-Za-z0-9_-])[A-Za-z]:[\\/]|/(?:home|mnt|Users)/)[^\r\n]*?[\\/]upstream[\\/]',
                  rb'\1dsh-source/', data)


def safe_name(name):
    path = Path(name)
    if path.anchor or name.startswith('/') or '..' in path.parts or ':' in name or '\\' in name:
        raise ValueError('Archive path rejected')
    return path


class ClosureExport:
    """Export pnpm plus fixed-fork vendor overrides without leaking builder junctions."""
    def __init__(self, modules, bundle, runtime):
        self.modules, self.bundle, self.runtime = modules, bundle, runtime.resolve()
        self.output = bundle / 'runtime/dsh/native/node_modules'
        self.links, self.pending, self.external = [], [], {}

    def mapped(self, source):
        source = source.resolve(strict=True)
        try:
            relative = source.relative_to(self.modules)
            parts = list(relative.parts)
            if len(parts) > 1 and parts[0] == '.pnpm' and parts[1] != 'node_modules':
                parts[1] = 'p-' + hashlib.sha256(parts[1].encode()).hexdigest()[:16]
            return self.output / Path(*parts)
        except ValueError:
            logical = source.relative_to(self.runtime).as_posix()  # Never export an arbitrary home/store.
            if source not in self.external:
                target = self.output / '.portable' / hashlib.sha256(logical.encode()).hexdigest()[:24]
                self.external[source] = target; self.pending.append((source, target))
            return self.external[source]

    def link(self, source, target):
        mapped = self.mapped(source)
        self.links.append({'path': target.relative_to(self.bundle).as_posix(), 'target': mapped.relative_to(self.bundle).as_posix()})

    def copy(self, source, destination, package_root=False):
        destination.mkdir(parents=True, exist_ok=True)
        for entry in source.iterdir():
            if entry.name in {'.git', '__pycache__', '.bin', '.modules.yaml', '.pnpm-workspace-state-v1.json'} or entry.suffix == '.pyc': continue
            if source.name == '.pnpm' and entry.name == 'lock.yaml': continue
            if package_root and entry.name == 'node_modules': continue  # Rebuild runtime deps only, not workspace dev tools.
            target = destination / entry.name
            if source == self.modules / '.pnpm' and entry.is_dir() and entry.name != 'node_modules':
                target = destination / ('p-' + hashlib.sha256(entry.name.encode()).hexdigest()[:16])
            if is_link(entry) and entry.is_dir(): self.link(entry, target)
            elif entry.is_dir(): self.copy(entry, target)
            else:
                shutil.copy2(entry.resolve(strict=True), target)
                if target.suffix in {'.js', '.mjs'}:
                    before = target.read_bytes(); after = normalize_build_regions(before)
                    if before != after: target.write_bytes(after)

    def export(self):
        self.copy(self.modules, self.output)
        while self.pending:
            source, target = self.pending.pop(0)
            self.copy(source, target, package_root=True)
            manifest = source / 'package.json'
            if not manifest.is_file(): raise ValueError('External native override must be a fixed-fork package')
            package = json.loads(manifest.read_text(encoding='utf-8'))
            optional = set(package.get('optionalDependencies', {})) | {name for name, info in package.get('peerDependenciesMeta', {}).items() if info.get('optional')}
            deps = set(package.get('dependencies', {})) | set(package.get('peerDependencies', {})) | optional
            for dep in sorted(deps):
                candidates = [parent / 'node_modules' / dep for parent in [source, *source.parents] if parent == self.runtime or self.runtime in parent.parents]
                candidates.append(self.modules / dep)
                found = next((path for path in candidates if path.is_dir()), None)
                if found is None:
                    if dep in optional: continue
                    raise ValueError('Fixed-fork runtime dependency unavailable: ' + dep)
                self.link(found, target / 'node_modules' / dep)
        return self.links


def origin_receipt(value):
    seen = set()
    while value.get('native_reused_from'):
        file = Path(value['native_reused_from']) / 'INSTALL_RECEIPT.json'
        if file in seen: raise ValueError('Native reuse cycle')
        seen.add(file); value = json.loads(file.read_text())
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True, help='Private selected INSTALL_RECEIPT.json or runtime.json')
    parser.add_argument('--python-archive', type=Path, required=True)
    parser.add_argument('--napcat-archive', type=Path, required=True)
    parser.add_argument('--node-license', type=Path, help='Original matching Node LICENSE when the system install omits it')
    parser.add_argument('--output', type=Path, required=True, help='New private artifact directory outside the checkout')
    parser.add_argument('--acknowledge-unverified', action='store_true')
    args = parser.parse_args()
    if not args.acknowledge_unverified: raise ValueError('Local candidate build only; acknowledge outstanding QQ/licence/release gates')
    destination = args.output.resolve()
    if destination.exists() or destination == ROOT or ROOT in destination.parents: raise ValueError('Use a new private output directory')
    meta = tomllib.loads((ROOT / 'application.toml').read_text(encoding='utf-8'))
    fingerprint = source_fingerprint()
    system = 'windows' if os.name == 'nt' else 'linux'
    checked_archive(args.python_archive, meta['portable']['python'][system + '_sha256'])
    checked_archive(args.napcat_archive, meta['napcat'][system + '_sha256'])
    selected = json.loads(args.runtime.read_text()); original = origin_receipt(selected)
    if original['upstream_commit'] != meta['runtime']['inline_commit']: raise ValueError('Native fork pin mismatch')
    version = (ROOT / 'VERSION').read_text(encoding='utf-8-sig').strip()
    destination.mkdir(parents=True)
    bundle = destination / ('Bot-' + version + '-' + system + '-x64'); bundle.mkdir()
    # Whitelist the product source and notices; never recurse through any private/runtime directories.
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT).split(b'\0')
    for raw in names:
        if not raw: continue
        name = raw.decode().replace('\\', '/'); source = ROOT / name
        if not allowed(name) or not source.is_file() or is_link(source): continue
        target = bundle / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
    runtime = bundle / 'runtime/dsh'
    shutil.copytree(ROOT / 'hermes/core/soyo', runtime / 'worker/soyo', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    modules = Path(original['modules']).resolve(strict=True)
    links = ClosureExport(modules, bundle, Path(original['directory'])).export()
    # Plugin source is current and neutral; compiled DSH/native modules remain the exact pinned build.
    for package, directory in {'dsh-host-boundary': 'host', 'dsh-dashboard': 'dashboard', 'dsh-asuna-ui': 'asuna-ui'}.items():
        target = runtime / 'native/node_modules/@soyo' / package
        if target.exists(): shutil.rmtree(target)  # Exact build-owned newly-created destination only.
        shutil.copytree(ROOT / 'hermes/core/soyo/dsh' / directory, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    # Python and wheel dependencies are assembled here, not on a user's computer.
    unpack = destination / 'python-unpack'; unpack.mkdir()
    with tarfile.open(args.python_archive) as archive: archive.extractall(unpack, filter='data')
    shutil.copytree(unpack / 'python', bundle / 'runtime/python', symlinks=False, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    site = bundle / ('runtime/python/Lib/site-packages' if os.name == 'nt' else 'runtime/python/lib/python3.12/site-packages')
    dependencies = tomllib.loads((ROOT / 'hermes/core/pyproject.toml').read_text(encoding='utf-8'))['project']['dependencies']
    bundled_python = bundle / ('runtime/python/python.exe' if os.name == 'nt' else 'runtime/python/bin/python3')
    # Resolve wheels with the shipped interpreter, not the builder's Python ABI.
    subprocess.run([str(bundled_python), '-I', '-m', 'pip', 'install', '--only-binary=:all:', '--no-compile', '--disable-pip-version-check',
                    '--no-warn-script-location', '--target', str(site), *dependencies], check=True)
    frozen = subprocess.check_output([str(bundled_python), '-I', '-m', 'pip', 'list', '--path', str(site), '--format=freeze'], text=True)
    (bundle / 'runtime/python-requirements.txt').write_text(frozen, encoding='utf-8')
    node_name = 'node.exe' if os.name == 'nt' else 'node'
    node = bundle / 'runtime/node' / node_name; node.parent.mkdir(parents=True); shutil.copy2(selected['node'], node)
    with zipfile.ZipFile(args.napcat_archive) as archive:
        napcat = bundle / 'runtime/napcat'; napcat.mkdir()
        for item in archive.infolist():
            relative = safe_name(item.filename)
            # Release assets are clean. Runtime/log/account files are still refused at packaging.
            if any(part in {'logs', 'cache'} for part in relative.parts) or relative.name.startswith('onebot11_'): raise ValueError('NapCat release contains runtime data')
            target = napcat / relative
            if item.is_dir(): target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, target.open('wb') as out: shutil.copyfileobj(source, out)
    # Complete fixed-fork corresponding source, not a credential-bearing builder directory.
    upstream = Path(original['directory']) / 'upstream'
    source_tar = subprocess.check_output(['git', '-C', str(upstream), 'archive', '--format=tar', original['upstream_commit']])
    notices = bundle / 'licenses'; notices.mkdir(exist_ok=True)
    with gzip.open(notices / 'dsh-corresponding-source.tar.gz', 'wb') as out: out.write(source_tar)
    node_license = args.node_license or next((path for path in (Path(selected['node']).parent / 'LICENSE', Path(selected['node']).parent.parent / 'LICENSE') if path.is_file()), None)
    if node_license is None: raise ValueError('Original Node licence required for a prebuilt candidate')
    shutil.copy2(node_license, notices / 'NODE-LICENSE')
    shutil.copy2(ROOT / 'THIRD_PARTY_NOTICES.md', notices / 'THIRD_PARTY_NOTICES.md')
    (notices / 'PREBUILT-SOURCES.json').write_text(json.dumps({
        'python': meta['portable']['python'], 'napcat': meta['napcat'], 'dsh': meta['runtime']['inline_repository'],
        'dsh_commit': original['upstream_commit'], 'licence_review_complete': False,
        'note': 'Private candidate only. Original package licences are retained; binary redistribution requires a full review.'
    }, indent=2), encoding='utf-8')
    # CLI can be below a package's lib/bin directory; use its declared relative bin entry.
    pkg = json.loads((modules / meta['runtime']['dsh_package'] / 'package.json').read_text())
    cli = runtime / 'native/node_modules' / meta['runtime']['dsh_package'] / pkg['bin']['dsh']
    if source_fingerprint() != fingerprint: raise ValueError('Source changed during packaging; partial build retained but not archived')
    files = {p.relative_to(bundle).as_posix(): sha(p) for p in bundle.rglob('*') if p.is_file()}
    value = {'schema': 1, 'bundle_id': uuid.uuid4().hex, 'version': version, 'platform': system + '-x64',
             'dsh_version': meta['runtime']['dsh_version'], 'upstream_commit': original['upstream_commit'],
             'python_version': meta['portable']['python']['version'], 'napcat_version': meta['napcat']['version'],
             'node_version': subprocess.check_output([str(node), '--version'], text=True).strip(),
             'source_fingerprint': fingerprint,
             'compiled_region_paths': 'logical dsh-source paths; generated comment prefixes only',
             'runtime': runtime.relative_to(bundle).as_posix(), 'node': node.relative_to(bundle).as_posix(),
             'cli': cli.relative_to(bundle).as_posix(), 'napcat': 'runtime/napcat', 'links': links, 'files': files,
             'unreleased_candidate': True, 'qq_integration_tested': False, 'release_licence_review_complete': False}
    (bundle / 'portable-manifest.json').write_text(json.dumps(value, indent=2), encoding='utf-8')
    archive_name = destination / (bundle.name + ('.zip' if os.name == 'nt' else '.tar.gz'))
    if os.name == 'nt':
        with zipfile.ZipFile(archive_name, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in bundle.rglob('*'):
                if path.is_file(): archive.write(path, path.relative_to(destination).as_posix())
    else:
        with tarfile.open(archive_name, 'w:gz') as archive: archive.add(bundle, arcname=bundle.name)
    receipt = {'artifact': str(archive_name), 'sha256': sha(archive_name), 'bytes': archive_name.stat().st_size,
               'platform': value['platform'], 'files': len(files), 'links': len(links), 'published': False}
    (destination / 'build-receipt.json').write_text(json.dumps(receipt, indent=2)); print(json.dumps(receipt))


if __name__ == '__main__': main()
