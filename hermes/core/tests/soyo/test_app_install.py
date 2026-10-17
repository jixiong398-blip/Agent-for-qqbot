# SPDX-License-Identifier: MIT
"""Real private files/locks/links; fake package contents, no dependency downloads."""
import json
from pathlib import Path

import pytest
import yaml

from soyo.app import config, install
from soyo.platform import directory_link, remove_directory_link


def runtime(home, name):
    directory = home / 'runtimes' / name
    modules = directory / 'native/node_modules'
    modules.mkdir(parents=True)
    cli = directory / 'fixture.mjs'; cli.write_text('')
    value = {'directory': str(directory), 'modules': str(modules), 'cli': str(cli), 'source_fingerprint': name}
    config.atomic_json(directory / 'INSTALL_RECEIPT.json', value)
    return value


def test_runtime_selection_and_rollback_preserve_persona_and_history(tmp_path):
    home = tmp_path / 'instance'; config.initialize(home)
    first, second = runtime(home, 'first'), runtime(home, 'second')
    history = home / 'workspace/user-history.txt'; history.write_text('keep this history')
    install.select_runtime(home, first)
    install.select_runtime(home, second)
    assert config.read_json(home / 'private/runtime.json')['previous_directory'] == first['directory']
    install.rollback(home)
    assert (home / 'profiles/qqbot/node_modules').resolve() == Path(first['modules']).resolve()
    assert config.read_json(home / 'private/runtime.json')['allow_source_mismatch'] is True
    assert history.read_text() == 'keep this history'


def test_selection_failure_restores_old_links_and_manifest(tmp_path, monkeypatch):
    home = tmp_path / 'instance'; config.initialize(home)
    first, second = runtime(home, 'first'), runtime(home, 'second')
    install.select_runtime(home, first)
    manifest = config.read_json(home / 'profiles/qqbot/package.json')
    real = install.atomic_json
    def fail_after_link(path, value):
        if Path(path) == home / 'private/runtime.json' and value.get('directory') == second['directory']:
            raise OSError('fixture interrupted selection')
        return real(path, value)
    monkeypatch.setattr(install, 'atomic_json', fail_after_link)
    with pytest.raises(OSError, match='interrupted'): install.select_runtime(home, second)
    assert config.read_json(home / 'private/runtime.json')['directory'] == first['directory']
    assert config.read_json(home / 'profiles/qqbot/package.json') == manifest
    assert (home / 'profiles/qqbot/node_modules').resolve() == Path(first['modules']).resolve()


def test_linked_instance_home_is_rejected_before_resolving_it(tmp_path):
    target, link = tmp_path / 'target', tmp_path / 'link'
    target.mkdir()
    directory_link(target, link)
    try:
        with pytest.raises(ValueError, match='links or junctions'): config.home_path(link)
    finally: remove_directory_link(link)


def test_deployment_overlay_changes_only_workspace_roots_not_registry_resolution(tmp_path):
    source = tmp_path / 'source'
    for name, path in [('fixture-native', 'apps/cli'), ('@deepseek-ai/schemastery', 'vendor/schemastery')]:
        directory = source / path; directory.mkdir(parents=True)
        (directory / 'package.json').write_text(json.dumps({'name': name}))
    directory = source / 'python/sdk-runtime'; directory.mkdir(parents=True)
    (directory / 'package.json').write_text(json.dumps({'name': 'fixture-closure', 'dependencies': {}}))
    original = {'lockfileVersion': '9.0', 'overrides': {'@deepseek-ai/schemastery': 'link:vendor/schemastery'},
                'importers': {'python/sdk-runtime': {'dependencies': {}}, 'apps/cli': {'dependencies': {'registry-fixture': {'version': '1.2.3', 'specifier': '^1'}}}},
                'packages': {'registry-fixture@1.2.3': {'resolution': {'integrity': 'fixture-locked-integrity'}}},
                'snapshots': {'registry-fixture@1.2.3': {}}}
    (source / 'pnpm-lock.yaml').write_text(yaml.safe_dump(original))
    install.overlay_closure(source, {'fixture-native', '@deepseek-ai/schemastery'})
    result = yaml.safe_load((source / 'pnpm-lock.yaml').read_text())
    assert result['packages'] == original['packages'] and result['snapshots'] == original['snapshots']
    assert result['importers']['apps/cli'] == original['importers']['apps/cli']
    item = result['importers']['python/sdk-runtime']['dependencies']['@deepseek-ai/schemastery']
    assert item == {'specifier': 'link:../../vendor/schemastery', 'version': 'link:../../vendor/schemastery'}


@pytest.mark.parametrize('host', ['127.0.0.1'])
def test_render_pins_browser_authority_to_connection_not_advertised_url(tmp_path, host):
    from soyo.app.persona import save
    from soyo.app.render import render

    home = tmp_path / 'instance'; value = config.initialize(home)
    route = {'name': 'fixture-model', 'base_url': 'http://127.0.0.1:12345/v1', 'auth_mode': 'none',
             'api_key': '', 'api': 'openai-completions', 'context_window': 8192, 'max_tokens': 1024}
    config.update(home, {'character_name': 'Fixture', 'models': {'character': route},
                        'action_uses_character': True, 'management_host': host, 'native_host': host}, value['revision'])
    value = config.read_json(home / 'deployment.json')
    save(home, text='# Fixture\n\nPrivate fixture persona.')
    selected = runtime(home, 'fixture')
    preset = Path(selected['modules']) / '@deepseek-ai/dsh-web-app/presets/standard.patch.yml'
    preset.parent.mkdir(parents=True)
    preset.write_text(yaml.safe_dump([{'insert': [{'config': {'plugins': [{}]}}]}]), encoding='utf-8')
    install.select_runtime(home, selected)
    render(home, value, selected['directory'])
    rows = yaml.safe_load((home / 'profiles/qqbot/cordis.patch.yml').read_text(encoding='utf-8'))
    entries = {row['id']: row for row in rows if 'id' in row}
    assert entries['connection']['config']['trustedHosts'] == [f'{host}:{value["native_port"]}']
    assert 'trustedHosts' not in entries['web-runtime']['config']
    assert entries['web-runtime']['config']['publicUrl'] == f'http://{host}:{value["native_port"]}/'
    inserted = {row['id']: row for group in rows for row in group.get('insert', [])}
    ingress = inserted['soyo-host-boundary']['config']
    assert ingress['host'] == host and ingress['requireAccessKey'] is False
    assert inserted['soyo-dashboard']['config']['apiURL'] == f'http://{host}:{value["management_port"]}'
    assert entries['webserver']['config']['host'] == '127.0.0.1'
