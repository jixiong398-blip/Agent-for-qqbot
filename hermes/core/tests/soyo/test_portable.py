# SPDX-License-Identifier: MIT
"""Prebuilt path and integrity checks, without running dependencies or services."""
from pathlib import Path
import hashlib,json,os
import pytest
from soyo.app import portable


@pytest.mark.parametrize('name', ['../outside','/outside','C:/outside','a\\b','a/../b',''])
def test_prebuilt_manifest_cannot_escape_package(tmp_path,name):
    with pytest.raises(ValueError):portable.relative(tmp_path,name)


def test_modified_prebuilt_bytes_are_refused_before_any_install(tmp_path):
    file=tmp_path/'fixture';file.write_bytes(b'original')
    manifest={'schema':1,'platform':'windows-x64' if os.name=='nt' else 'linux-x64','files':{'fixture':hashlib.sha256(file.read_bytes()).hexdigest()}}
    (tmp_path/'portable-manifest.json').write_text(json.dumps(manifest))
    portable.manifest(tmp_path)
    file.write_bytes(b'modified')
    with pytest.raises(ValueError,match='modified'):portable.manifest(tmp_path)


@pytest.mark.parametrize('prefix', [b'C:\\Users\\fixture\\build\\upstream\\', b'/home/fixture/build/upstream/'])
def test_prebuilt_normalizes_only_generated_region_comments(prefix,monkeypatch):
    import importlib.util
    root=Path(__file__).resolve().parents[4];monkeypatch.syspath_prepend(str(root/'extras/scripts'))
    spec=importlib.util.spec_from_file_location('portable_builder_fixture',root/'extras/scripts/build_portable.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    code=b'const path = "'+prefix+b'unchanged";\n'
    notice=b'// Copyright retained.\n'
    data=notice+b'\t//#region \\0dsh-css:'+prefix+b'packages/a.css.mjs\n'+code
    result=module.normalize_build_regions(data)
    assert result==notice+b'\t//#region \\0dsh-css:dsh-source/packages/a.css.mjs\n'+code


def test_source_package_keeps_local_imports_of_shipped_javascript_tests(monkeypatch):
    import importlib.util
    import re
    root = Path(__file__).resolve().parents[4]
    spec = importlib.util.spec_from_file_location('source_package_fixture', root/'extras/scripts/package_source.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    tests = root/'hermes/core/tests/soyo'
    missing = []
    for file in tests.glob('*.test.mjs'):
        name = file.relative_to(root).as_posix()
        if not module.allowed(name):
            continue
        for local in re.findall(r"(?:from\s*|import\s*)['\"](\./[^'\"]+)['\"]", file.read_text(encoding='utf-8')):
            target = (file.parent/local).resolve()
            relative = target.relative_to(root).as_posix()
            if not target.is_file() or not module.allowed(relative):
                missing.append((name, relative))
    assert not missing, f'Shipped tests have missing source package dependencies: {missing}'


def test_prebuilt_keeps_napcat_original_license_and_reviewed_source_notices(tmp_path, monkeypatch):
    import importlib.util
    root = Path(__file__).resolve().parents[4]
    monkeypatch.syspath_prepend(str(root/'extras/scripts'))
    spec = importlib.util.spec_from_file_location('portable_notices_fixture', root/'extras/scripts/build_portable.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    name = 'third_party/NAPCAT-LICENSE.txt'
    assert module.allowed(name)
    assert (root/name).read_text(encoding='utf-8').startswith('Limited Redistribution License for NapCat\n')
    source = tmp_path/'inputs'; source.mkdir()
    (source/'sources').mkdir()
    (source/'sources/exact-source.tar.gz').write_bytes(b'fixture source archive')
    destination = tmp_path/'licenses'; destination.mkdir()
    module.copy_additional_notices(source, destination)
    assert (destination/'sources/exact-source.tar.gz').read_bytes() == b'fixture source archive'
    with pytest.raises(ValueError, match='replace an original'):
        module.copy_additional_notices(source, destination)


def test_prebuilt_refuses_runtime_caches_as_additional_notices(tmp_path, monkeypatch):
    import importlib.util
    root = Path(__file__).resolve().parents[4]
    monkeypatch.syspath_prepend(str(root/'extras/scripts'))
    spec = importlib.util.spec_from_file_location('portable_bad_notices_fixture', root/'extras/scripts/build_portable.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    source = tmp_path/'inputs'; source.mkdir()
    (source/'private.pyc').write_bytes(b'not a notice')
    with pytest.raises(ValueError, match='not a source notice'):
        module.copy_additional_notices(source, tmp_path/'licenses')


def test_posix_entrypoints_keep_lf_in_source_and_both_packagers():
    root = Path(__file__).resolve().parents[4]
    for name in ['install.sh', 'start.sh', 'configure.sh', 'stop.sh', 'update.sh']:
        data = (root/name).read_bytes()
        assert data.startswith(b'#!/usr/bin/env sh\n'), name
        assert b'\r' not in data, name
    assert '*.sh text eol=lf' in (root/'.gitattributes').read_text(encoding='utf-8')
    for name in ['package_source.py', 'build_portable.py']:
        source = (root/'extras/scripts'/name).read_text(encoding='utf-8')
        assert "replace(b'\\r\\n', b'\\n')" in source, name
