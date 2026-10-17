# SPDX-License-Identifier: MIT
"""No QQ/model calls: real private setup transactions and synthetic lifecycle boundaries."""
from pathlib import Path
from types import SimpleNamespace
import copy
import json
import pytest

from soyo.app import config, persona, setup, napcat
from soyo.app.manager import Manager


def route():
    return {'name':'fixture-model', 'base_url':'http://127.0.0.1:12345/v1', 'api':'openai-completions',
            'auth_mode':'none', 'api_key':'', 'context_window':8192, 'max_tokens':1024, 'vision':False}


def request(manager):
    value=config.read_json(manager.home/'deployment.json')
    return {'revision':value['revision'], 'changes':{'character_name':'My name', 'models':{'character':route()}, 'action_uses_character':True},
            'persona':'# My name\n\nMy custom persona.', 'persona_digest':persona.view(manager.home)['digest']}


def test_native_setup_is_available_before_models_and_qq_are_configured(tmp_path):
    instance=Manager(tmp_path/'instance'); value=setup.view(instance)
    assert value['configured'] is False and value['config']['models']['character']=={}
    assert value['config']['onebot']['enabled'] is False
    assert value['napcat']['webui_url'].startswith('http://127.0.0.1:')


def test_native_setup_queue_is_private_and_does_not_apply_or_start_anything(tmp_path):
    instance=Manager(tmp_path/'instance'); before=config.read_json(instance.home/'deployment.json')
    result=setup.queue(instance,request(instance))
    assert result['phase']=='queued' and config.read_json(instance.home/'deployment.json')==before
    assert not persona.view(instance.home)['text'] and not instance.retained
    with pytest.raises(ValueError,match='already pending'): setup.queue(instance,request(instance))


def test_native_apply_configures_both_brains_without_any_qq_or_model_requests(tmp_path,monkeypatch):
    instance=Manager(tmp_path/'instance'); setup.queue(instance,request(instance)); started=[]
    monkeypatch.setattr(instance,'start_native',lambda:started.append('native-web'))
    setup.apply_pending(instance)
    current=config.read_json(instance.home/'deployment.json')
    assert current['models']['character']==current['models']['action'] and current['character_name']=='My name'
    assert started==['native-web'] and current['onebot']['enabled'] is False
    receipt=config.read_json(instance.home/'run/setup-apply.json')
    assert receipt['phase']=='applied' and 'changes' not in receipt and 'persona' not in receipt


def test_failed_native_apply_restores_config_and_persona(tmp_path,monkeypatch):
    instance=Manager(tmp_path/'instance'); before=config.read_json(instance.home/'deployment.json')
    setup.queue(instance,request(instance)); calls=[]
    def start():
        calls.append('start')
        if len(calls)==1: raise RuntimeError('synthetic boot failure')
    monkeypatch.setattr(instance,'start_native',start); setup.apply_pending(instance)
    current=config.read_json(instance.home/'deployment.json')
    assert current['models']==before['models'] and not persona.view(instance.home)['text']
    assert calls==['start','start'] and config.read_json(instance.home/'run/setup-apply.json')['phase']=='failed'


def test_setup_refuses_stale_revision_and_arbitrary_runtime_or_listener_changes(tmp_path):
    instance=Manager(tmp_path/'instance'); value=request(instance); value['revision']-=1
    with pytest.raises(ValueError,match='CONFLICT'): setup.queue(instance,value)
    value=request(instance); value['changes']['management_host']='0.0.0.0'
    with pytest.raises(ValueError,match='Only Bot'): setup.queue(instance,value)


def test_model_route_change_clears_prior_native_selection_before_validation(tmp_path):
    instance=Manager(tmp_path/'instance'); c=config.read_json(instance.home/'deployment.json')
    config.update(instance.home, {'models':{'character':route()}, 'routes':{}, 'action_uses_character':True}, c['revision'])
    c=config.read_json(instance.home/'deployment.json')
    config.update(instance.home, {'routes':{'character':{'provider':'qqbot-character','model':'fixture-model','maxTokens':1024}}}, c['revision'])
    value=request(instance);value['changes']['models']['character']['name']='fixture-model-next'
    assert setup.queue(instance,value)['accepted']


def test_provider_endpoint_change_never_reuses_a_different_cloud_credential(tmp_path):
    instance=Manager(tmp_path/'instance'); c=config.read_json(instance.home/'deployment.json')
    r={**route(),'auth_mode':'bearer','api_key':'fake-fixture-key-only','base_url':'https://first.invalid/v1'}
    config.update(instance.home,{'models':{'character':r},'action_uses_character':True},c['revision'])
    value=request(instance);value['changes']['models']['character']={**r,'api_key':'','base_url':'https://second.invalid/v1'}
    with pytest.raises(ValueError,match='old credentials are not forwarded'):setup.queue(instance,value)


def test_interrupted_apply_restores_only_the_matching_transaction(tmp_path):
    instance=Manager(tmp_path/'instance');setup.queue(instance,request(instance))
    path=instance.home/'run/setup-apply.json';pending=config.read_json(path)
    before=config.read_json(instance.home/'deployment.json');previous_persona=persona.view(instance.home)
    setup._journal(instance,pending,before,previous_persona)
    pending['phase']='applying';config.atomic_json(path,pending)
    config.update(instance.home,pending['changes'],before['revision'])
    persona.save(instance.home,text=pending['persona'])
    setup.recover_interrupted(instance)
    assert config.read_json(instance.home/'deployment.json')['models']==before['models']
    assert not persona.view(instance.home)['text']
    assert config.read_json(path)['phase']=='recovered_previous'
    assert not instance.retained


def test_interrupted_apply_preserves_an_independent_persona_edit(tmp_path):
    instance=Manager(tmp_path/'instance');setup.queue(instance,request(instance))
    path=instance.home/'run/setup-apply.json';pending=config.read_json(path)
    setup._journal(instance,pending,config.read_json(instance.home/'deployment.json'),persona.view(instance.home))
    pending['phase']='applying';config.atomic_json(path,pending)
    persona.save(instance.home,text='# Independent edit\nMust not be discarded.')
    with pytest.raises(ValueError,match='without overwriting'):setup.recover_interrupted(instance)
    assert persona.view(instance.home)['text'].startswith('# Independent edit')
    assert config.read_json(path)['phase']=='applying'


def test_native_saved_model_profile_reuses_private_credentials_without_returning_them(tmp_path,monkeypatch):
    instance=Manager(tmp_path/'instance');c=config.read_json(instance.home/'deployment.json')
    cloud={**route(),'auth_mode':'bearer','api_key':'fake-preset-secret-only','base_url':'https://saved.invalid/v1'}
    config.update(instance.home,{'model_profiles':{'Saved':{'character':cloud,'action':cloud}}},c['revision'])
    value=request(instance);del value['changes']['models'];value['use_model_profile']='Saved'
    value['save_model_profile']='Copied'
    accepted=setup.queue(instance,value)
    assert 'fake-preset-secret-only' not in json.dumps(accepted)
    monkeypatch.setattr(instance,'start_native',lambda:None);setup.apply_pending(instance)
    current=config.read_json(instance.home/'deployment.json')
    assert current['models']['character']['api_key']=='fake-preset-secret-only'
    assert current['model_profiles']['Copied']['action']==cloud
    assert 'fake-preset-secret-only' not in json.dumps(setup.view(instance))


def test_native_persona_presets_do_not_replace_the_running_identity(tmp_path):
    instance=Manager(tmp_path/'instance');persona.save(instance.home,text='# Current')
    result=setup.persona_preset(instance,{'operation':'save','name':'Alternative','text':'# My own character'})
    assert result['presets']==['Alternative'] and persona.view(instance.home)['text']=='# Current'
    assert setup.persona_preset(instance,{'operation':'read','name':'Alternative'})['text']=='# My own character'
    with pytest.raises(ValueError):setup.persona_preset(instance,{'operation':'read','name':'../escape'})


def test_manual_napcat_start_does_not_require_enabling_a_qq_writer(tmp_path,monkeypatch):
    instance=Manager(tmp_path/'instance'); directory=instance.home/'napcat'; directory.mkdir()
    c=config.read_json(instance.home/'deployment.json')
    config.update(instance.home,{'napcat':{'directory':str(directory),'command':[str(directory/'fixture-napcat.exe')]}},c['revision'])
    started=[];monkeypatch.setattr(instance,'spawn',lambda name,*a,**kw:started.append(name))
    instance.start_optional('napcat')
    assert started==['napcat'] and instance.config['onebot']['enabled'] is False


def test_clean_napcat_provision_is_private_local_and_does_not_copy_login_data(tmp_path):
    home=tmp_path/'instance';config.initialize(home);bundle=tmp_path/'official-release';bundle.mkdir()
    (bundle/'napcat').mkdir();(bundle/'napcat/config').mkdir();(bundle/'napcat/config/napcat.json').write_text('{}')
    (bundle/'napcat.bat').write_text('fixture only')
    napcat.provision(home,bundle,'fixture-version')
    c=config.read_json(home/'deployment.json');directory=Path(c['onebot']['config_directory'])
    webui=config.read_json(directory/'webui.json')
    assert webui['host']=='127.0.0.1' and len(webui['token'])>=32
    assert webui['token'] not in json.dumps(setup.view(Manager(home)))
    assert c['onebot']['enabled'] is False


def test_automatic_account_link_preserves_other_settings_and_requires_owned_directory(tmp_path):
    home=tmp_path/'instance';value=config.initialize(home);directory=home/'napcat/config';directory.mkdir(parents=True)
    fixture=directory/'onebot11_100001.json';fixture.write_text(json.dumps({'other':'keep','network':{'httpServers':[],'websocketServers':[]}}))
    config.update(home,{'onebot':{'config_directory':str(directory)}},value['revision'])
    napcat.configure_account(home,'100001');saved=config.read_json(home/'deployment.json');data=json.loads(fixture.read_text())
    assert data['other']=='keep' and saved['onebot']['enabled'] is False
    http=data['network']['httpServers'][0];ws=data['network']['websocketServers'][0]
    assert http['host']==ws['host']=='127.0.0.1' and http['token']==ws['token']==saved['onebot']['token']
    assert list((home/'backups').glob('napcat-account-*.json'))
