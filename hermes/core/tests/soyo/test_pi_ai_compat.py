# SPDX-License-Identifier: MIT
"""Regression tests for the pinned native Responses-stream compatibility patch."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import pytest

from soyo.app import install
from soyo.platform import directory_link


OLD = install._PI_AI_DONE_OLD
MID = install._PI_AI_DONE_MID
ERROR_OLD = install._PI_AI_ERROR_OLD


def write_fixture_package(package, *, stream=OLD, error=ERROR_OLD):
    (package / "dist/api").mkdir(parents=True)
    (package / "package.json").write_text(json.dumps({"name": install.PI_AI_PACKAGE, "version": install.PI_AI_VERSION}))
    (package / "dist/api/openai-responses-shared.js").write_text(stream)
    (package / "dist/api/openai-responses.js").write_text(error)


def test_missing_terminal_arguments_falls_back_to_accumulated_delta():
    patched = install.patch_pi_ai_response_source(OLD)
    assert "typeof event.arguments === \"string\"" in patched
    assert "finalArguments.startsWith(previousPartialJson)" in patched
    assert "finalArguments.slice(previousPartialJson.length)" in patched
    assert install.patch_pi_ai_response_source(patched) == patched


def test_existing_partial_patch_gets_the_missing_slice_fallback():
    patched = install.patch_pi_ai_response_source(MID)
    assert "event.arguments.slice" not in patched
    assert "finalArguments.slice(previousPartialJson.length)" in patched


def test_changed_parser_shape_fails_closed():
    with pytest.raises(ValueError, match="parser shape changed"):
        install.patch_pi_ai_response_source("const unrelated = true;")


def test_connection_error_cause_is_bounded_and_redacted():
    patched = install.patch_pi_ai_error_source(ERROR_OLD)
    assert "let cause = error?.cause" in patched
    assert "slice(0, 500)" in patched
    assert "diagnosticErrorMessage" in patched
    assert install.patch_pi_ai_error_source(patched) == patched


def test_changed_error_shape_fails_closed():
    with pytest.raises(ValueError, match="error shape changed"):
        install.patch_pi_ai_error_source("const unrelated = true;")


def test_runtime_patch_materializes_only_the_new_linked_package(tmp_path):
    source = tmp_path / "source" / "@earendil-works" / "pi-ai"
    write_fixture_package(source)
    modules = tmp_path / "runtime" / "node_modules"
    (modules / "@earendil-works").mkdir(parents=True)
    directory_link(source, modules / "@earendil-works" / "pi-ai")

    result = install.patch_pi_ai_runtime(modules, isolate=True)

    copied = modules / "@earendil-works" / "pi-ai"
    assert result["changed"] is True
    assert not copied.is_symlink()
    assert "finalArguments" in (copied / "dist/api/openai-responses-shared.js").read_text()
    assert "diagnosticErrorMessage" in (copied / "dist/api/openai-responses.js").read_text()
    assert "finalArguments" not in (source / "dist/api/openai-responses-shared.js").read_text()


def test_runtime_patch_does_not_follow_a_linked_parent_package(tmp_path):
    source = tmp_path / "source"
    package = source / "@earendil-works" / "pi-ai"
    write_fixture_package(package)
    (source / "node_modules").mkdir()
    (source / "node_modules/@earendil-works").mkdir()
    directory_link(package, source / "node_modules/@earendil-works/pi-ai")
    modules = tmp_path / "runtime" / "node_modules"
    modules.mkdir(parents=True)
    linked_parent = modules / "@deepseek-ai" / "dsh-llm-pi-ai"
    linked_parent.parent.mkdir(parents=True)
    directory_link(source, linked_parent)

    install.patch_pi_ai_runtime(modules, isolate=True)

    copied = modules / "@deepseek-ai/dsh-llm-pi-ai"
    assert not copied.is_symlink()
    assert "finalArguments" in (copied / "node_modules/@earendil-works/pi-ai/dist/api/openai-responses-shared.js").read_text()
    assert "finalArguments" not in (package / "dist/api/openai-responses-shared.js").read_text()


def test_runtime_patch_prefers_pnpm_alias_over_its_old_store_copy(tmp_path):
    old = tmp_path / "old" / "@earendil-works" / "pi-ai"
    write_fixture_package(old)
    modules = tmp_path / "runtime" / "node_modules"
    alias = modules / ".pnpm/p-parent/node_modules/@earendil-works/pi-ai"
    alias.parent.mkdir(parents=True)
    directory_link(old, alias)
    store = modules / ".pnpm/p-store/node_modules/@earendil-works/pi-ai"
    write_fixture_package(store)

    install.patch_pi_ai_runtime(modules, isolate=True)

    assert "finalArguments" in (alias / "dist/api/openai-responses-shared.js").read_text()
    assert "finalArguments" not in (store / "dist/api/openai-responses-shared.js").read_text()


def test_runtime_patch_keeps_alias_when_store_candidate_resolves_to_same_copy(tmp_path):
    source = tmp_path / "old" / "@earendil-works" / "pi-ai"
    write_fixture_package(source)
    modules = tmp_path / "runtime" / "node_modules"
    alias = modules / ".pnpm/p-parent/node_modules/@earendil-works/pi-ai"
    alias.parent.mkdir(parents=True)
    directory_link(source, alias)
    store_alias = modules / ".pnpm/p-store/node_modules/@earendil-works/pi-ai"
    store_alias.parent.mkdir(parents=True)
    directory_link(source, store_alias)

    install.patch_pi_ai_runtime(modules, isolate=True)

    assert not install.is_link(alias)
    assert install.is_link(store_alias)
    assert "finalArguments" in (alias / "dist/api/openai-responses-shared.js").read_text()
    assert "finalArguments" not in (source / "dist/api/openai-responses-shared.js").read_text()


def test_exported_tree_patches_all_exact_version_copies(tmp_path):
    root = tmp_path / "bundle"
    for name in ("pnpm-copy", "portable-copy"):
        package = root / name / "node_modules/@earendil-works/pi-ai"
        write_fixture_package(package)

    result = install.patch_pi_ai_tree(root)

    assert result == {"package": install.PI_AI_PACKAGE, "version": install.PI_AI_VERSION,
                      "copies": 2, "changed": 2}
    for package in root.rglob("package.json"):
        if package.read_text().find(install.PI_AI_PACKAGE) >= 0:
            assert "finalArguments" in (package.parent / "dist/api/openai-responses-shared.js").read_text()


@pytest.mark.parametrize('filename, original', [('openai-responses-shared.js', OLD), ('openai-responses.js', ERROR_OLD)])
def test_package_patch_does_not_mutate_an_older_hardlinked_copy(tmp_path, filename, original):
    old = tmp_path/'old'
    current = tmp_path/'current'
    write_fixture_package(old)
    write_fixture_package(current)
    target = current/'dist/api'/filename
    target.unlink()
    os.link(old/'dist/api'/filename, target)

    install.patch_pi_ai_package(current)

    assert (old/'dist/api'/filename).read_text() == original
    assert target.read_text() != original


@pytest.mark.parametrize('failure', ['stream', 'error', 'version'])
def test_export_preflight_rejects_every_copy_before_writing_any_file(tmp_path, failure):
    root = tmp_path/'bundle'
    good, bad = root/'a/node_modules/pi-ai', root/'z/node_modules/pi-ai'
    write_fixture_package(good)
    write_fixture_package(bad, stream='unreviewed shape' if failure == 'stream' else OLD,
                          error='unreviewed shape' if failure == 'error' else ERROR_OLD)
    if failure == 'version':
        (bad/'package.json').write_text(json.dumps({'name': install.PI_AI_PACKAGE, 'version': '99.0.0'}))
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}

    with pytest.raises(ValueError, match='shape changed|Unsupported pi-ai'):
        install.patch_pi_ai_tree(root)

    assert {p: p.read_bytes() for p in before} == before


@pytest.mark.parametrize('stream, error, patch_id', [
    (MID, install._PI_AI_ERROR_NEW, install.PI_AI_PATCH_ID),
    (install._PI_AI_DONE_NEW, ERROR_OLD, install.PI_AI_PATCH_ID),
    (install._PI_AI_DONE_NEW, install._PI_AI_ERROR_NEW, 'responses-compat-v1'),
])
def test_cached_compatibility_is_verified_read_only_before_creating_links(tmp_path, stream, error, patch_id):
    home = tmp_path/'home'
    modules = home/'runtimes/old/native/node_modules'
    write_fixture_package(modules/install.PI_AI_PACKAGE, stream=stream, error=error)
    previous = {'modules': str(modules), 'native_compat_patch_id': patch_id}
    before = {p: p.read_bytes() for p in modules.rglob('*') if p.is_file()}
    destination = home/'runtimes/new'

    with pytest.raises(ValueError, match='compatibility patch'):
        install.reuse_native(destination, previous, 'unused-node', home)

    assert not destination.exists()
    assert {p: p.read_bytes() for p in before} == before


def test_reuse_native_accepts_the_real_pnpm_dependency_layout(tmp_path):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for immutable runtime resolution')
    home = tmp_path/'home'
    old = home/'runtimes/old'
    modules = old/'native/node_modules'
    package = modules/'.pnpm/pi/node_modules/@earendil-works/pi-ai'
    write_fixture_package(package)
    install.patch_pi_ai_package(package)
    original = (package/'dist/api/openai-responses-shared.js').read_bytes()
    adapter = modules/'.pnpm/adapter/node_modules/@deepseek-ai/dsh-llm-pi-ai'
    adapter.mkdir(parents=True)
    (adapter/'package.json').write_text(json.dumps({'name':'@deepseek-ai/dsh-llm-pi-ai','main':'index.cjs'}))
    (adapter/'index.cjs').write_text("module.exports=require.resolve('@earendil-works/pi-ai/package.json');")
    (adapter.parent.parent/'@earendil-works').mkdir()
    directory_link(package, adapter.parent.parent/'@earendil-works/pi-ai')
    (modules/'@deepseek-ai').mkdir()
    directory_link(adapter, modules/'@deepseek-ai/dsh-llm-pi-ai')
    cli = modules/'@deepseek-ai/dsh'
    cli.mkdir()
    (cli/'package.json').write_text(json.dumps({'bin':{'dsh':'index.cjs'}}))
    (cli/'index.cjs').write_text('// fixture')
    previous = {'directory':str(old),'modules':str(modules),'package_manager':'fixture',
                'upstream_commit':'fixture','upstream_lock_sha256':'fixture','deployment_roots':[],
                'deployment_lock_sha256':'fixture','native_compat_patch_id':install.PI_AI_PATCH_ID}
    install.atomic_json(old/'INSTALL_RECEIPT.json', previous)

    result = install.reuse_native(home/'runtimes/new', previous, node, home)

    assert result['native_compat_patch_id'] == install.PI_AI_PATCH_ID
    resolved = subprocess.check_output([node,'-e',
        "console.log(require(process.argv[1]));", str(Path(result['modules'])/'@deepseek-ai/dsh-llm-pi-ai')],text=True).strip()
    assert Path(resolved).resolve() == (package/'package.json').resolve()
    assert (package/'dist/api/openai-responses-shared.js').read_bytes() == original

    # Repeated business updates link back to the same physical adapter. Follow
    # the private receipt chain instead of trying to patch a new logical alias.
    previous = {**result, 'directory': str(home/'runtimes/new')}
    install.atomic_json(home/'runtimes/new/NATIVE_BUILD_RECEIPT.json', previous)
    result = install.reuse_native(home/'runtimes/newest', previous, node, home)
    assert result['native_compat_patch_id'] == install.PI_AI_PATCH_ID
    resolved = subprocess.check_output([node,'-e',
        "console.log(require(process.argv[1]));", str(Path(result['modules'])/'@deepseek-ai/dsh-llm-pi-ai')],text=True).strip()
    assert Path(resolved).resolve() == (package/'package.json').resolve()
    assert (package/'dist/api/openai-responses-shared.js').read_bytes() == original


def test_cached_receipt_cycle_is_rejected_without_modifying_the_closure(tmp_path):
    home = tmp_path/'home'
    directory = home/'runtimes/cycle'
    directory.mkdir(parents=True)
    previous = {'native_reused_from': str(directory)}
    receipt = directory/'INSTALL_RECEIPT.json'
    install.atomic_json(receipt, previous)
    before = receipt.read_bytes()
    with pytest.raises(ValueError, match='reuse cycle'):
        install._verify_cached_native_compat(previous, home)
    assert receipt.read_bytes() == before
