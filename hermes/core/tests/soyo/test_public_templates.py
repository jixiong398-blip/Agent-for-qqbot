# SPDX-License-Identifier: MIT
"""Public examples are neutral, complete as documented, and ship without local bindings."""
import importlib.util
import json
from pathlib import Path
import re

import pytest

from soyo.app import config

ROOT = Path(__file__).resolve().parents[4]


def test_default_bot_name_does_not_replace_a_users_chosen_identity(tmp_path):
    home = tmp_path / 'instance'; value = config.initialize(home)
    assert value['character_name'] == 'Bot'
    config.update(home, {'character_name': 'My custom role'}, value['revision'])
    assert config.initialize(home)['character_name'] == 'My custom role'


@pytest.mark.parametrize('filename', ['deployment.example.json', 'deployment.local.example.json'])
def test_filled_public_examples_validate_without_model_qq_or_credential_discovery(tmp_path, filename):
    value = json.loads((ROOT / 'templates' / filename).read_text(encoding='utf-8'))
    assert value.pop('note')
    raw = json.dumps(value)
    assert not re.search(r'(?i)soyo|[A-Z]:\\\\', raw)
    route = value['models']['character']
    assert route['name'].startswith('{{') and '{{' in route['base_url']
    route.update(name='fixture-model', base_url='http://127.0.0.1:12345/v1' if route['auth_mode'] == 'none' else 'https://api.example.invalid/v1',
                 api_key='' if route['auth_mode'] == 'none' else 'fixture-not-a-real-key', context_window=8192, max_tokens=1024)
    home = tmp_path / 'instance'; initial = config.initialize(home)
    config.update(home, value, initial['revision'])
    saved = config.read_json(home / 'deployment.json'); config.validate(saved, ready=True)
    assert saved['models']['action'] == saved['models']['character']
    assert saved['onebot']['enabled'] is False and saved['automation_jobs'] == []
    assert saved['character_name'] == 'Bot'
    assert saved['management_require_key'] is False and saved['native_require_key'] is False


def test_every_public_template_and_legacy_pointer_is_in_source_staging_allowlist():
    spec = importlib.util.spec_from_file_location('package_source', ROOT / 'extras/scripts/package_source.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    for directory in [ROOT / 'templates', ROOT / 'hermes/templates']:
        for path in directory.iterdir():
            if not path.is_file(): continue
            name = path.relative_to(ROOT).as_posix()
            assert module.allowed(name), name
            text = path.read_text(encoding='utf-8')
            assert not re.search(r'(?i)\bsoyo\b|长崎素世|BanG\s*Dream', text), name
    assert not module.allowed('modules/live2d/conf.json')
    assert not module.allowed('private/deployment.json')


def test_visible_ui_and_role_prompt_do_not_inject_a_fixed_character():
    base = ROOT / 'hermes/core/soyo/dsh'
    for filename in ['asuna-ui/adapter.js', 'dashboard/client.js', 'host/character-prompt.mjs']:
        text = (base / filename).read_text(encoding='utf-8')
        # Compatibility IDs/classes and comments remain unchanged, not display/persona text.
        strings = re.findall(r"(['\"])((?:\\.|(?!\1).)*?)\1", text)
        assert not any(re.search(r'\bSoyo\b|长崎素世', value) for _, value in strings), filename
    builder = (base / 'asuna-ui/build_client.py').read_text(encoding='utf-8')
    assert '.replace("\'Asuna\'", "\'Bot\'")' in builder
    status = (base / 'host/business-ui.mjs').read_text(encoding='utf-8')
    assert "name: config.character_name || 'Bot'" in status
