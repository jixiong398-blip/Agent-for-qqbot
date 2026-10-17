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
