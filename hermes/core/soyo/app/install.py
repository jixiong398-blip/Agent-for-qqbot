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
import tempfile
import uuid

from soyo.platform import (bootstrap_directory, directory_link, file_lock, is_link,
                           protect, remove_directory_link, worker_environment)
from .config import atomic_json, executable, initialize, metadata, project_root, read_json, venv_python

PLUGINS = {"@soyo/dsh-host-boundary": "host", "@soyo/dsh-asuna-ui": "asuna-ui", "@soyo/dsh-dashboard": "dashboard"}
PI_AI_PACKAGE = "@earendil-works/pi-ai"
PI_AI_VERSION = "1.1.0"
PI_AI_PATCH_ID = "responses-compat-v2"

# The pinned pi-ai release already stops parsing partial tool JSON on every
# delta. Some OpenAI-compatible gateways omit `arguments` on the terminal
# function_call_arguments.done event, however. Keep the accumulated delta and
# let the terminal event close the tool call instead of calling startsWith on
# undefined. This is applied to the immutable native closure at build/select
# time, never to an arbitrary user-installed package.
_PI_AI_DONE_OLD = """            const previousPartialJson = slot.block.partialJson;
            slot.block.partialJson = event.arguments;
            slot.block.arguments = parseStreamingJson(slot.block.partialJson);
            if (event.arguments.startsWith(previousPartialJson)) {
                const delta = event.arguments.slice(previousPartialJson.length);"""
_PI_AI_DONE_NEW = """            const previousPartialJson = slot.block.partialJson;
            const finalArguments = typeof event.arguments === "string" ? event.arguments : previousPartialJson;
            slot.block.partialJson = finalArguments;
            slot.block.arguments = parseStreamingJson(finalArguments);
            if (finalArguments.startsWith(previousPartialJson)) {
                const delta = finalArguments.slice(previousPartialJson.length);"""
_PI_AI_DONE_MID = """            const previousPartialJson = slot.block.partialJson;
            const finalArguments = typeof event.arguments === \"string\" ? event.arguments : previousPartialJson;
            slot.block.partialJson = finalArguments;
            slot.block.arguments = parseStreamingJson(finalArguments);
            if (finalArguments.startsWith(previousPartialJson)) {
                const delta = event.arguments.slice(previousPartialJson.length);"""

# The OpenAI SDK intentionally presents connection failures as a short public
# message and keeps the original exception in `cause`. The pi-ai provider
# currently discards that cause before the DSH adapter can classify/log it.
# Preserve only a bounded, redacted cause message in the adapter-visible error;
# never ship a stack, request body, authorization header or URL.
_PI_AI_ERROR_OLD = """            const errorMessage = formatProviderError(normalizeProviderError(error), `${model.provider === \"openai\" ? \"OpenAI\" : model.provider} API error`);
            // Sign in with ChatGPT shares the subscription's usage limit with other apps.
            output.errorMessage = errorMessage.includes(\"subscription_sharing_usage_limit_exceeded\")
                ? `${errorMessage}\\nCheck your ChatGPT usage: ${CHATGPT_USAGE_URL}`
                : errorMessage;"""
_PI_AI_ERROR_NEW = """            const errorMessage = formatProviderError(normalizeProviderError(error), `${model.provider === \"openai\" ? \"OpenAI\" : model.provider} API error`);
            const causeParts = [];
            const seenCauses = new Set();
            let cause = error?.cause;
            for (let depth = 0; depth < 4 && cause && !seenCauses.has(cause); depth++) {
                seenCauses.add(cause);
                try {
                    const message = String(cause?.message ?? cause).replace(/https?:\\/\\S+|Bearer\\s+\\S+|sk-[A-Za-z0-9_-]{12,}/g, '<redacted>').slice(0, 500);
                    if (message) causeParts.push(message);
                    cause = cause?.cause;
                } catch {
                    break;
                }
            }
            const causeMessage = causeParts.join(': ');
            const diagnosticErrorMessage = errorMessage === 'Connection error.' && causeMessage && causeMessage !== errorMessage
                ? `${errorMessage}: ${causeMessage}`
                : errorMessage;
            // Sign in with ChatGPT shares the subscription's usage limit with other apps.
            output.errorMessage = diagnosticErrorMessage.includes(\"subscription_sharing_usage_limit_exceeded\")
                ? `${diagnosticErrorMessage}\\nCheck your ChatGPT usage: ${CHATGPT_USAGE_URL}`
                : diagnosticErrorMessage;"""


def run(argv, *, cwd=None, env=None):
    # argv, never shell expansion. Install output must not contain model credentials.
    result = subprocess.run([str(x) for x in argv], cwd=cwd, env=env, check=False)
    if result.returncode:
        raise RuntimeError("Installation step failed (exit " + str(result.returncode) + "); prior runtime retained")


def patch_pi_ai_response_source(text):
    """Make the pinned Responses stream tolerant of omitted terminal arguments."""
    if _PI_AI_DONE_NEW in text:
        return text
    if _PI_AI_DONE_MID in text:
        return text.replace(_PI_AI_DONE_MID, _PI_AI_DONE_NEW, 1)
    if _PI_AI_DONE_OLD not in text:
        raise ValueError("Pinned pi-ai Responses parser shape changed; refuse an unreviewed patch")
    return text.replace(_PI_AI_DONE_OLD, _PI_AI_DONE_NEW, 1)


def patch_pi_ai_error_source(text):
    """Keep a bounded, redacted provider cause in Responses errors."""
    if _PI_AI_ERROR_NEW in text:
        return text
    if _PI_AI_ERROR_OLD not in text:
        raise ValueError("Pinned pi-ai Responses error shape changed; refuse an unreviewed patch")
    return text.replace(_PI_AI_ERROR_OLD, _PI_AI_ERROR_NEW, 1)


def _prepare_pi_ai_package_patch(package):
    """Validate and prepare every file before mutating this package."""
    package = Path(package).resolve(strict=True)
    manifest = json.loads((package / "package.json").read_text(encoding="utf-8"))
    if manifest.get("name") != PI_AI_PACKAGE or manifest.get("version") != PI_AI_VERSION:
        raise ValueError("Unsupported pi-ai package for the reviewed Responses compatibility patch")
    stream_target = package / "dist/api/openai-responses-shared.js"
    stream_source = stream_target.read_text(encoding="utf-8")
    stream_patched = patch_pi_ai_response_source(stream_source)
    error_target = package / "dist/api/openai-responses.js"
    error_source = error_target.read_text(encoding="utf-8")
    error_patched = patch_pi_ai_error_source(error_source)
    return manifest["version"], [(stream_target, stream_source, stream_patched),
                                 (error_target, error_source, error_patched)]


def _apply_pi_ai_package_patch(version, files):
    for target, source, patched in files:
        if patched != source:
            # pnpm can hardlink an artifact to another immutable runtime/store.
            # Replace this directory entry instead of overwriting that shared
            # inode, which would silently patch the rollback runtime as well.
            fd, temporary = tempfile.mkstemp(prefix='.pi-ai-', dir=target.parent)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
                    stream.write(patched); stream.flush(); os.fsync(stream.fileno())
                os.chmod(temporary, target.stat().st_mode & 0o777)
                os.replace(temporary, target)
            finally:
                Path(temporary).unlink(missing_ok=True)
    return {"package": PI_AI_PACKAGE, "version": version,
            "changed": any(patched != source for _target, source, patched in files),
            "files": {target.name: patched != source for target, source, patched in files}}


def patch_pi_ai_package(package):
    """Patch one already materialized, reviewed pi-ai package directory."""
    version, files = _prepare_pi_ai_package_patch(package)
    return _apply_pi_ai_package_patch(version, files)


def locate_pi_ai_package(modules):
    """Find the one pinned pi-ai package in a pnpm closure or linked reuse."""
    modules = Path(modules)
    candidates = []
    direct = modules / PI_AI_PACKAGE
    if direct.exists() or is_link(direct):
        candidates.append(direct)
    nested = modules / "@deepseek-ai/dsh-llm-pi-ai/node_modules" / PI_AI_PACKAGE
    if nested.exists() or is_link(nested):
        candidates.append(nested)
    pnpm = modules / ".pnpm"
    if pnpm.is_dir():
        candidates.extend(pnpm.glob("*/node_modules/" + PI_AI_PACKAGE))
    resolved_candidates = {}
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
            manifest = json.loads((resolved / "package.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if manifest.get("name") == PI_AI_PACKAGE:
            resolved_candidates.setdefault(str(resolved), []).append(candidate)
    if not resolved_candidates:
        raise ValueError("Native closure is missing " + PI_AI_PACKAGE)
    # For reuse isolation prefer a logical linked dependency path. Materialize
    # that path copies only the new runtime's owning package chain; choosing the
    # physical store copy here would mutate the previous immutable runtime.
    all_candidates = [candidate for candidates in resolved_candidates.values() for candidate in candidates]
    linked = [candidate for candidate in all_candidates
              if any(is_link(parent) for parent in [candidate, *candidate.parents]
                     if parent == modules or modules in parent.parents)]
    if linked:
        return sorted(linked, key=lambda path: str(path))[0]
    # A pnpm alias may point to the same physical package; patching the physical
    # copy is correct only for a newly built closure, never for reuse isolation.
    real = [candidate for candidate in all_candidates if not is_link(candidate)]
    return sorted(real or all_candidates, key=lambda path: str(path))[0]


def _materialize_link_path(root, path):
    """Own every link on a dependency path before modifying its leaf."""
    root = Path(root).resolve(strict=True)
    path = Path(path)
    parts = path.relative_to(root).parts
    current = root
    for part in parts:
        current = current / part
        if not is_link(current):
            continue
        source = current.resolve(strict=True)
        if not source.is_dir():
            raise ValueError("Linked native dependency is not a directory")
        remove_directory_link(current)
        shutil.copytree(source, current, symlinks=True)
    return current


def patch_pi_ai_runtime(modules, *, isolate=False):
    """Apply the reviewed patch to exactly pi-ai 1.1.0 in a native closure.

    Reused runtimes link packages back to an older immutable build. In that
    case materialize only pi-ai into the new runtime before patching, so a
    rebuild never mutates the previous selected runtime in place.
    """
    modules = Path(modules)
    package = locate_pi_ai_package(modules)
    if isolate:
        package = _materialize_link_path(modules, package)
    package = package.resolve(strict=True)
    package.relative_to(modules.resolve())
    return patch_pi_ai_package(package)


def patch_pi_ai_tree(root):
    """Patch every materialized exact-version pi-ai copy in an exported tree."""
    root = Path(root).resolve(strict=True)
    packages, seen = [], set()
    for manifest_path in root.rglob("package.json"):
        package = manifest_path.parent
        if package.resolve() != package:
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if manifest.get("name") != PI_AI_PACKAGE:
            continue
        if manifest.get("version") != PI_AI_VERSION:
            raise ValueError("Unsupported pi-ai package for the reviewed Responses compatibility patch")
        resolved = package.resolve(strict=True)
        if resolved in seen:
            continue
        seen.add(resolved)
        packages.append(resolved)
    if not packages:
        raise ValueError("Native closure is missing " + PI_AI_PACKAGE)
    # Preflight every copy first; an unsupported second artifact must not leave
    # the exported bundle with only the first artifact patched.
    prepared = [_prepare_pi_ai_package_patch(package) for package in sorted(packages)]
    patches = [_apply_pi_ai_package_patch(version, files) for version, files in prepared]
    return {"package": PI_AI_PACKAGE, "version": PI_AI_VERSION,
            "copies": len(patches), "changed": sum(item["changed"] for item in patches)}


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
             'native_compat_patch': PI_AI_PATCH_ID,
             'plugins': {name: json.loads((project_root() / 'hermes/core/soyo/dsh' / directory / 'package.json').read_text(encoding='utf-8'))
                         for name, directory in PLUGINS.items()}}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _verify_cached_native_compat(previous, home):
    """Validate the original immutable closure, never patch a reused link."""
    boundary = (Path(home)/'runtimes').resolve(strict=True)
    receipt, seen = previous, set()
    while receipt.get('native_reused_from'):
        directory = Path(receipt['native_reused_from']).resolve(strict=True)
        directory.relative_to(boundary)
        if directory in seen or len(seen) >= 128:
            raise ValueError('Native reuse cycle')
        seen.add(directory)
        path = directory/'INSTALL_RECEIPT.json'
        if not path.is_file():
            path = directory/'NATIVE_BUILD_RECEIPT.json'
        receipt = read_json(path)
    modules = Path(receipt['modules']).resolve(strict=True)
    modules.relative_to(boundary)
    if receipt.get('native_compat_patch_id') != PI_AI_PATCH_ID:
        raise ValueError('Cached native compatibility patch differs; rebuild the pinned runtime')
    version, files = _prepare_pi_ai_package_patch(locate_pi_ai_package(modules))
    if any(source != patched for _target, source, patched in files):
        raise ValueError('Cached native compatibility patch is incomplete; prior runtime retained')
    return {'package': PI_AI_PACKAGE, 'version': version, 'changed': False,
            'files': {target.name: False for target, _source, _patched in files}}


def reuse_native(destination, previous, node, home):
    """New plugin snapshot over immutable prior fork packages; never npm-mix hosts."""
    origin = Path(previous['modules'])
    origin.resolve(strict=True).relative_to((Path(home) / 'runtimes').resolve())
    compat_patch = _verify_cached_native_compat(previous, home)
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
    # The linked adapter resolves dependencies beside its original realpath,
    # not beside this new logical link. Reuse only a verified, already-patched
    # immutable closure; patching a new top-level copy would not affect it.
    spec = metadata()['runtime']
    manifest = json.loads((modules / spec['dsh_package'] / 'package.json').read_text(encoding='utf-8'))
    entry = modules / spec['dsh_package'] / manifest['bin']['dsh']
    if not entry.is_file(): raise ValueError('Cached native CLI is missing')
    return {key: previous[key] for key in ('package_manager', 'upstream_commit', 'upstream_lock_sha256', 'deployment_roots', 'deployment_lock_sha256')} | {
        'node': node, 'modules': str(modules), 'cli': str(entry), 'native_reused_from': previous['directory'],
        'native_compat_patch_id': PI_AI_PATCH_ID, 'native_compat_patches': [compat_patch]}


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
    compat_patch = patch_pi_ai_runtime(modules)
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
            "deployment_lock_sha256": hashlib.sha256((source / "pnpm-lock.yaml").read_bytes()).hexdigest(),
            "native_compat_patch_id": PI_AI_PATCH_ID, "native_compat_patches": [compat_patch]}


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
        venv = destination / 'venv'
        run([sys.executable, '-m', 'venv', str(venv)])
        live_python = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        run([str(live_python), '-m', 'pip', 'install', '--index-url', config['registries']['pypi'],
             '--disable-pip-version-check', '-e', str(project_root() / 'hermes/core') + '[live2d]'])
        run([*npm, 'install', '--registry', config['registries']['npm'], '--no-audit', '--no-fund'], cwd=destination)
        if os.name == 'nt': electron = destination / 'node_modules/electron/dist/electron.exe'
        elif sys.platform == 'darwin': electron = destination / 'node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'
        else: electron = destination / 'node_modules/electron/dist/electron'
        if not electron.is_file(): raise ValueError('Optional Electron distribution is missing')
        atomic_json(home / 'private/live2d-runtime.json', {'directory': str(destination), 'electron': str(electron), 'python': str(live_python)})
