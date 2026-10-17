# SPDX-License-Identifier: MIT
"""Build one pinned native fork, then select it without replacing user data."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

from soyo.platform import (bootstrap_directory, directory_link, file_lock, is_link,
                           protect, remove_directory_link, worker_environment)
from .config import atomic_json, executable, initialize, metadata, project_root, read_json, venv_python

PLUGINS = {"@soyo/dsh-host-boundary": "host", "@soyo/dsh-asuna-ui": "asuna-ui", "@soyo/dsh-dashboard": "dashboard"}


def run(argv, *, cwd=None, env=None):
    # argv, never shell expansion. Install output must not contain model credentials.
    result = subprocess.run([str(x) for x in argv], cwd=cwd, env=env, check=False)
    if result.returncode:
        raise RuntimeError("Installation step failed (exit " + str(result.returncode) + "); prior runtime retained")


def node_and_npm(config):
    node, npm = executable("node", config), executable("npm", config)
    if not node or not npm:
        raise ValueError("Install Node.js/npm at the application.toml minimum or configure explicit executables")
    version = subprocess.check_output([node, "--version"], text=True, timeout=15).strip().removeprefix("v")
    major, minor, patch = tuple(map(int, version.split(".")[:3]))
    spec = metadata()["runtime"]
    if (major, minor, patch) < tuple(map(int, spec["node_minimum"].split("."))) or major in spec.get("node_excluded_majors", []):
        raise ValueError("Node.js does not meet the supported versions in application.toml")
    candidates = [Path(npm).parent / "node_modules/npm/bin/npm-cli.js",
                  Path(npm).resolve().parent.parent / "lib/node_modules/npm/bin/npm-cli.js"]
    for script in candidates:
        if script.is_file():
            return node, [node, str(script)]
    if os.name != "nt":
        return node, [npm]
    raise ValueError("npm-cli.js missing; configure a complete Node.js installation")


def source_fingerprint():
    root = project_root()
    files = [root / "application.toml", root / "hermes/core/pyproject.toml"]
    files += sorted(p for p in (root / "hermes/core/soyo").rglob("*") if p.is_file()
                    and "__pycache__" not in p.parts and p.suffix != ".pyc")
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode()); digest.update(b"\0"); digest.update(path.read_bytes())
    return digest.hexdigest()


def native_build_key(node, config):
    """Business code/config changes do not require recompiling the pinned fork."""
    spec = metadata()['runtime']
    value = {'runtime': spec, 'node': subprocess.check_output([node, '--version'], text=True).strip(),
             'platform': sys.platform, 'registry': config['registries']['npm'],
             'plugins': {name: json.loads((project_root() / 'hermes/core/soyo/dsh' / directory / 'package.json').read_text(encoding='utf-8'))
                         for name, directory in PLUGINS.items()}}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def reuse_native(destination, previous, node, home):
    """New plugin snapshot over immutable prior fork packages; never npm-mix hosts."""
    origin = Path(previous['modules'])
    origin.resolve(strict=True).relative_to((Path(home) / 'runtimes').resolve())
    modules = destination / 'native/node_modules'
    modules.mkdir(parents=True)
    links = []
    for entry in origin.iterdir():
        if entry.name.startswith('.') or entry.name == '@soyo': continue
        if entry.name.startswith('@'):
            scope = modules / entry.name; scope.mkdir()
            links.extend((package.resolve(strict=True), scope / package.name) for package in entry.iterdir() if package.is_dir())
        elif entry.is_dir(): links.append((entry.resolve(strict=True), modules / entry.name))
    if os.name == 'nt':
        # Node creates junctions without elevation/developer mode. A single
        # argv+stdin invocation avoids hundreds of PowerShell startup calls.
        for target, _link in links: target.relative_to((Path(home) / 'runtimes').resolve())
        subprocess.run([node, '-e', "const fs=require('node:fs');for(const [target,link] of JSON.parse(fs.readFileSync(0,'utf8')))fs.symlinkSync(target,link,'junction');"],
                       input=json.dumps([[str(t), str(l)] for t, l in links]), text=True, check=True)
    else:
        for target, link in links: directory_link(target, link)
    for name, directory in PLUGINS.items():
        target = modules / name; target.parent.mkdir(exist_ok=True)
        shutil.copytree(project_root() / 'hermes/core/soyo/dsh' / directory, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    spec = metadata()['runtime']
    manifest = json.loads((modules / spec['dsh_package'] / 'package.json').read_text(encoding='utf-8'))
    entry = modules / spec['dsh_package'] / manifest['bin']['dsh']
    if not entry.is_file(): raise ValueError('Cached native CLI is missing')
    return {key: previous[key] for key in ('package_manager', 'upstream_commit', 'upstream_lock_sha256', 'deployment_roots', 'deployment_lock_sha256')} | {
        'node': node, 'modules': str(modules), 'cli': str(entry), 'native_reused_from': previous['directory']}


def native_cache(home, previous, key):
    if previous.get('build_key') == key: return previous
    # A completed fork build can outlive an interrupted selection or concurrent
    # source edit. Reuse only our explicit private completion receipt, never an
    # arbitrary directory that merely happens to contain a CLI.
    receipts = sorted((Path(home) / 'runtimes').glob('*/NATIVE_BUILD_RECEIPT.json'),
                      key=lambda path: path.stat().st_mtime, reverse=True)[:128]
    for path in receipts:
        receipt = read_json(path)
        if receipt.get('build_key') == key and receipt.get('directory') == str(path.parent): return receipt
    return {}


def require_stopped(home):
    import psutil
    supervisor = read_json(Path(home) / 'run/supervisor.json', default={})
    if supervisor.get('pid') and supervisor['pid'] != os.getpid():
        try:
            process = psutil.Process(supervisor['pid'])
            if abs(process.create_time() - supervisor.get('created_at', -1)) < 0.01:
                raise ValueError('Stop this instance supervisor before modifying installed dependencies')
        except psutil.NoSuchProcess:
            pass
    for row in read_json(Path(home) / "run/processes.json", default={}).values():
        try:
            process = psutil.Process(row["pid"])
            if abs(process.create_time() - row["created_at"]) < 0.01 and process.is_running():
                raise ValueError("Stop this instance's services before installation or rollback")
        except psutil.NoSuchProcess:
            pass


def overlay_closure(source, roots):
    """Add workspace-only deploy roots without re-resolving any registry version."""
    import yaml
    source = Path(source)
    closure_path = source / 'python/sdk-runtime/package.json'
    closure = json.loads(closure_path.read_text(encoding='utf-8'))
    lock_path = source / 'pnpm-lock.yaml'
    lock = yaml.safe_load(lock_path.read_text(encoding='utf-8'))
    importer = lock['importers']['python/sdk-runtime']['dependencies']
    # Search only declared workspace shapes; never recurse through node_modules.
    manifests = []
    for pattern in ('vendor/*/package.json', 'packages/*/*/package.json', 'apps/*/package.json',
                    'native/system/package.json', 'native/system/packages/*/package.json'):
        manifests.extend(source.glob(pattern))
    packages = {json.loads(path.read_text(encoding='utf-8'))['name']: path.parent for path in manifests}
    for name in sorted(roots):
        if name not in packages:
            raise ValueError('Deployment root is not in the pinned workspace: ' + name)
        closure['dependencies'][name] = 'workspace:*'
        link = 'link:' + Path(os.path.relpath(packages[name], closure_path.parent)).as_posix()
        # pnpm applies root link overrides to its effective importer specifiers
        # (the vendored schemastery/cosmokit packages use these).
        override = lock.get('overrides', {}).get(name, '')
        importer[name] = {'specifier': link if override.startswith('link:') else 'workspace:*', 'version': link}
    closure_path.write_text(json.dumps(closure, indent=2) + '\n', encoding='utf-8')
    lock_path.write_text(yaml.safe_dump(lock, sort_keys=False, width=10000), encoding='utf-8')
    return closure


def _build_native(destination, config, node, npm):
    """The whole fork, including host, native modules, Web, UI and patched dependencies."""
    import psutil
    if psutil.virtual_memory().total + psutil.swap_memory().total < 6 * 1024 ** 3:
        raise ValueError('Full source build needs at least 6 GiB combined RAM/swap; provide build capacity first (8 GiB+ recommended). No system memory settings were changed')
    spec = metadata()["runtime"]
    git = executable("git", config)
    if not git:
        raise ValueError("Git is required for the pinned native fork")
    env = worker_environment(extra={key: value for key, value in os.environ.items()
        if key.upper() in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "SSL_CERT_FILE", "SSL_CERT_DIR"}})
    env["PATH"] = str(Path(node).parent) + os.pathsep + env.get("PATH", "")
    env["npm_config_registry"] = config["registries"]["npm"]
    source = destination / "upstream"
    # Fetch the exact tree, not an unbounded branch history (and not a moving
    # branch tip). The full corresponding source at the pinned commit remains.
    run([git, "init", source], env=env)
    run([git, "-C", source, "remote", "add", "origin", spec["inline_repository"]], env=env)
    run([git, "-C", source, "-c", "http.lowSpeedLimit=1024", "-c", "http.lowSpeedTime=60",
         "fetch", "--depth=1", "origin", spec["inline_commit"]], env=env)
    run([git, "-C", source, "checkout", "--detach", spec["inline_commit"]], env=env)
    actual = subprocess.check_output([git, "-C", source, "rev-parse", "HEAD"], text=True, env=env).strip()
    if actual != spec["inline_commit"]:
        raise ValueError("Native fork commit mismatch")
    package = json.loads((source / "package.json").read_text(encoding="utf-8"))
    if package.get("version") != spec["dsh_version"]:
        raise ValueError("Native fork version differs from application.toml")
    manager = package.get("packageManager", "")
    if not re.fullmatch(r"pnpm@[0-9]+\.[0-9]+\.[0-9]+(?:\+[a-zA-Z0-9.]+)?", manager):
        raise ValueError("Native fork must declare an exact pnpm version")
    # Install the pinned package-manager CLI once. Do not execute .cmd launchers
    # through a shell or rely on PATH resolution for subsequent pnpm children.
    manager_root = destination / "package-manager"
    manager_root.mkdir()
    run([*npm, "install", "--prefix", manager_root, "--ignore-scripts", "--no-audit", "--no-fund", manager.split("+", 1)[0]], env=env)
    pm_manifest = json.loads((manager_root / "node_modules/pnpm/package.json").read_text(encoding="utf-8"))
    pnpm = manager_root / "node_modules/pnpm" / pm_manifest["bin"]["pnpm"]
    pm = [node, str(pnpm)]
    env["PATH"] = str(manager_root / "node_modules/.bin") + os.pathsep + env["PATH"]
    # Upstream allowBuilds owns the reviewed native install scripts (PTY/Koffi/
    # esbuild). Dropping them would silently ship a broken Windows runtime.
    run([*pm, "install", "--frozen-lockfile"], cwd=source, env=env)
    run([*pm, "run", "build:native-system"], cwd=source, env=env)
    run([*pm, "run", "build"], cwd=source, env=env)
    closure_path = source / "python/sdk-runtime/package.json"
    closure = json.loads(closure_path.read_text(encoding="utf-8"))
    if spec["dsh_package"] not in closure.get("dependencies", {}):
        raise ValueError("Pinned upstream runtime closure has no native CLI")
    # Make the plugin imports and Web client roster direct roots of the deployed
    # closure. This is a manifest-only overlay; all implementation is the pinned
    # fork. Keep both original and overlaid lock hashes in the receipt.
    original_lock = hashlib.sha256((source / "pnpm-lock.yaml").read_bytes()).hexdigest()
    roots = {spec["dsh_package"], "@deepseek-ai/dsh-web-app", "@deepseek-ai/dsh-web-frontend", *spec["inline_packages"]}
    for directory in PLUGINS.values():
        data = json.loads((project_root() / "hermes/core/soyo/dsh" / directory / "package.json").read_text(encoding="utf-8"))
        roots.update(name for name in data.get("peerDependencies", {}) if name.startswith("@deepseek-ai/"))
        roots.update(data.get("dsh", {}).get("client", {}).get("inject", []))
    closure = overlay_closure(source, roots)
    # A changed importer hash makes pnpm recheck supply-chain metadata. Permit
    # that read-only network check; --offline fails with a cold metadata cache.
    # The frozen overlay still cannot upgrade/re-resolve registry dependencies.
    run([*pm, "install", "--frozen-lockfile", "--ignore-scripts"], cwd=source, env=env)
    native = destination / "native"
    # Deploy preserves pnpm's patched dependencies and the complete workspace
    # closure. Never mix two fork UI packages with an official npm host.
    run([*pm, "--filter", closure["name"], "deploy", "--prod", "--legacy", native], cwd=source, env=env)
    modules = native / "node_modules"
    for name, directory in PLUGINS.items():
        target = modules / name
        if target.exists() or is_link(target):
            raise ValueError("Unfamiliar native plugin destination")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(project_root() / "hermes/core/soyo/dsh" / directory, target,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in [spec["dsh_package"], "@deepseek-ai/dsh-web-app", *spec["inline_packages"]]:
        data = json.loads((modules / name / "package.json").read_text(encoding="utf-8"))
        if data.get("version") != spec["dsh_version"]:
            raise ValueError("Native runtime contains a mismatched fork package")
    cli_manifest = json.loads((modules / spec["dsh_package"] / "package.json").read_text(encoding="utf-8"))
    entry = cli_manifest["bin"]["dsh"]
    cli = modules / spec["dsh_package"] / entry
    if not cli.is_file():
        raise ValueError("Built native CLI is missing")
    return {"node": node, "cli": str(cli), "modules": str(modules), "package_manager": manager,
            "upstream_commit": actual, "upstream_lock_sha256": original_lock, "deployment_roots": sorted(roots),
            "deployment_lock_sha256": hashlib.sha256((source / "pnpm-lock.yaml").read_bytes()).hexdigest()}


def select_runtime(home, receipt):
    """Journal the small profile-link transaction; leave all session/data files alone."""
    home = Path(home)
    config = read_json(home / "deployment.json")
    profile = home / "profiles" / config["profile"]
    profile.mkdir(parents=True, exist_ok=True, mode=0o700); protect(profile, directory=True)
    modules = profile / "node_modules"
    if modules.exists() and not is_link(modules):
        raise ValueError("Existing real profile/node_modules is not owned by this installer")
    old = read_json(home / "private/runtime.json", default={})
    manifest_path = profile / "package.json"
    manifest = read_json(manifest_path, default={})
    if manifest and manifest.get("agent_qqbot_managed") is not True:
        raise ValueError("Unfamiliar profile manifest; choose a new profile")
    before = dict(manifest)
    marker = home / "private/runtime-switch.json"
    if read_json(marker, default={}).get("phase") == "switching":
        raise ValueError("Interrupted runtime selection; inspect private/runtime-switch.json before retrying")
    backup = profile / (".node_modules.previous-" + uuid.uuid4().hex)
    pending = profile / (".node_modules.pending-" + uuid.uuid4().hex)
    directory_link(Path(receipt["modules"]), pending)
    transaction = {"phase": "switching", "before": old, "after": receipt, "backup_link": str(backup),
                   "pending_link": str(pending), "profile": str(profile), "manifest_before": before}
    atomic_json(marker, transaction)
    switched = False
    try:
        if is_link(modules):
            os.replace(modules, backup)
        os.replace(pending, modules); switched = True
        manifest.update({"name": "agent-qqbot-profile", "private": True, "type": "module", "version": "0.0.0",
            "agent_qqbot_managed": True, "dsh": {"profile": {"bundles": ["@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app"]}},
            "dependencies": {name: "file:" + (Path(receipt["modules"]) / name).as_posix() for name in PLUGINS}})
        atomic_json(manifest_path, manifest)
        selected = {**receipt, "profile": config["profile"], "previous_directory": old.get("directory")}
        atomic_json(home / "private/runtime.json", selected)
        transaction["phase"] = "selected"; atomic_json(marker, transaction)
    except BaseException:
        if switched and is_link(modules): remove_directory_link(modules)
        if is_link(backup): os.replace(backup, modules)
        if before: atomic_json(manifest_path, before)
        else: manifest_path.unlink(missing_ok=True)
        if old: atomic_json(home / "private/runtime.json", old)
        else: (home / "private/runtime.json").unlink(missing_ok=True)
        transaction["phase"] = "rolled_back"; atomic_json(marker, transaction)
        raise
    finally:
        if is_link(pending): remove_directory_link(pending)
    # Keep the backup junction and receipt for diagnosis/rollback; no recursive cleanup.


def install(home, *, log=print, install_python=True):
    root, home = project_root(), Path(home)
    minimum = tuple(map(int, metadata()["runtime"]["python_minimum"].split(".")))
    if sys.version_info[:2] < minimum:
        raise ValueError("Python version is below the configured minimum")
    if install_python:
        # An existing native home can be read with its installed interpreter.
        if (home / "deployment.json").is_file():
            require_stopped(home)
        bootstrap_directory(home)
        interpreter = venv_python(home)
        if not interpreter.is_file(): run([sys.executable, "-m", "venv", home / "venv"])
        run([interpreter, "-m", "pip", "install", "--index-url", metadata()["registries"]["pypi"], "-e", root / "hermes/core"])
        if Path(sys.prefix).resolve() != (home / "venv").resolve():
            run([interpreter, "-B", "-m", "soyo.app", "--home", home, "install", "--inside-venv"])
            return
    config = initialize(home)
    node, npm = node_and_npm(config)
    with file_lock(home / "run/lifecycle.lock", blocking=False), file_lock(home / "run/install.lock", blocking=False):
        require_stopped(home)
        fingerprint = source_fingerprint()
        previous = read_json(home / "private/runtime.json", default={})
        if previous.get("source_fingerprint") == fingerprint and previous.get("profile") == config["profile"] and Path(previous["cli"]).is_file():
            log("Matching native runtime already installed; configuration/data retained")
            return
        destination = home / "runtimes" / (fingerprint[:16] + "-" + uuid.uuid4().hex[:8])
        destination.mkdir(mode=0o700); protect(destination, directory=True)
        shutil.copytree(root / "hermes/core/soyo", destination / "worker/soyo", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        build_key = native_build_key(node, config)
        cached = native_cache(home, previous, build_key)
        built = (reuse_native(destination, cached, node, home) if cached
                 else _build_native(destination, config, node, npm))
        atomic_json(destination / 'NATIVE_BUILD_RECEIPT.json', {**built, 'directory': str(destination), 'build_key': build_key})
        if source_fingerprint() != fingerprint:
            # Do not claim a source snapshot was installed if a developer edited
            # files while it was being copied/built. Keep the native build proof
            # for diagnosis, but never select an inconsistent worker/plugin set.
            raise ValueError('Source changed during installation; build retained but not selected. Retry after edits finish')
        receipt = {**built, "directory": str(destination), 'build_key': build_key,
                   "source_fingerprint": fingerprint, "dsh_version": metadata()["runtime"]["dsh_version"]}
        atomic_json(destination / "INSTALL_RECEIPT.json", receipt)
        select_runtime(home, receipt)
        log("Native runtime built/selected. No services, models or QQ were started; configure before starting")


def rollback(home):
    home = Path(home)
    with file_lock(home / "run/lifecycle.lock", blocking=False):
        require_stopped(home)
        selected = read_json(home / "private/runtime.json")
        previous = Path(selected.get("previous_directory") or "")
        previous.resolve().relative_to((home / "runtimes").resolve())
        receipt = read_json(previous / "INSTALL_RECEIPT.json")
        if not receipt or not Path(receipt["cli"]).is_file():
            raise ValueError("Previous installed runtime not available")
        select_runtime(home, {**receipt, "allow_source_mismatch": True})


def recover_runtime(home):
    home = Path(home)
    with file_lock(home / 'run/lifecycle.lock', blocking=False):
        require_stopped(home)
        marker = home / 'private/runtime-switch.json'
        transaction = read_json(marker, default={})
        if transaction.get('phase') != 'switching':
            return {'state':'not_needed'}
        config = read_json(home / 'deployment.json')
        profile = home / 'profiles' / config['profile']
        if Path(transaction['profile']) != profile:
            raise ValueError('Recovery profile changed; no paths were overwritten')
        modules = profile / 'node_modules'
        backup, pending = Path(transaction['backup_link']), Path(transaction['pending_link'])
        for path, prefix in ((backup,'.node_modules.previous-'),(pending,'.node_modules.pending-')):
            if path.parent != profile or not path.name.startswith(prefix):
                raise ValueError('Recovery link identity rejected')
        before, after = transaction['before'], transaction['after']
        if is_link(modules):
            current = modules.resolve(strict=True)
            candidates = {Path(after['modules']).resolve(strict=True)}
            if before: candidates.add(Path(before['modules']).resolve(strict=True))
            if current not in candidates: raise ValueError('Unfamiliar profile link retained')
            if current == Path(after['modules']).resolve(strict=True): remove_directory_link(modules)
        elif modules.exists():
            raise ValueError('Real profile node_modules retained; not an installer link')
        if is_link(backup):
            if not before or backup.resolve(strict=True) != Path(before['modules']).resolve(strict=True):
                raise ValueError('Recovery backup link target rejected')
            if modules.exists() or is_link(modules): raise ValueError('Recovery destination already present')
            os.replace(backup, modules)
        elif before and not is_link(modules):
            directory_link(Path(before['modules']), modules)
        if is_link(pending):
            if pending.resolve(strict=True) != Path(after['modules']).resolve(strict=True):
                raise ValueError('Recovery pending link target rejected')
            remove_directory_link(pending)
        manifest = profile / 'package.json'
        if transaction['manifest_before']: atomic_json(manifest, transaction['manifest_before'])
        else: manifest.unlink(missing_ok=True)
        if before: atomic_json(home / 'private/runtime.json', before)
        else: (home / 'private/runtime.json').unlink(missing_ok=True)
        transaction['phase']='recovered_previous'; atomic_json(marker,transaction)
        return {'state':'recovered_previous','services_started':False,'data_changed':False}


def install_live2d(home):
    home = Path(home)
    config = read_json(home / 'deployment.json')
    if not config: raise ValueError('Install/configure the core instance first')
    with file_lock(home / 'run/lifecycle.lock', blocking=False):
        require_stopped(home)
        _node, npm = node_and_npm(config)
        destination = home / 'runtimes' / ('live2d-' + uuid.uuid4().hex)
        source = Path(config['live2d']['directory'])
        shutil.copytree(source, destination, ignore=shutil.ignore_patterns('node_modules', 'models', 'figure', 'conf.json', 'window_state.json', 'live2d_pref.json'))
        protect(destination, directory=True)
        (destination / 'tools').mkdir(exist_ok=True)
        shutil.copy2(project_root() / 'extras/scripts/decrypt_cvpkg.py', destination / 'tools/decrypt_cvpkg.py')
        run([sys.executable, '-m', 'pip', 'install', '--index-url', config['registries']['pypi'], '-e', str(project_root() / 'hermes/core') + '[live2d]'])
        run([*npm, 'install', '--registry', config['registries']['npm'], '--no-audit', '--no-fund'], cwd=destination)
        if os.name == 'nt': electron = destination / 'node_modules/electron/dist/electron.exe'
        elif sys.platform == 'darwin': electron = destination / 'node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'
        else: electron = destination / 'node_modules/electron/dist/electron'
        if not electron.is_file(): raise ValueError('Optional Electron distribution is missing')
        atomic_json(home / 'private/live2d-runtime.json', {'directory': str(destination), 'electron': str(electron)})
