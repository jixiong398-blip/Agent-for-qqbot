import pytest
from soyo.app import config


def test_drawing_permissions_default_private_and_roundtrip_without_model_secrets(tmp_path):
    home=tmp_path/'instance'
    before=config.initialize(home)
    assert before['image_permissions']=={'enabled':True,'allow_group_members':False,'group_ids':[]}
    changed=config.update(home,{'image_permissions':{'allow_group_members':True,'group_ids':['200001']}},before['revision'])
    assert changed['image_permissions']['group_ids']==['200001']
    assert changed['image_permissions']['enabled'] is True
    assert config.read_json(home/'deployment.json')['models']==before['models']


@pytest.mark.parametrize('value',[{'enabled':'true'},{'allow_group_members':1},{'group_ids':['not-a-group']},{'group_ids':'200001'},{'host_root':True}])
def test_invalid_drawing_policy_never_changes_the_saved_config(tmp_path,value):
    home=tmp_path/'instance';before=config.initialize(home)
    with pytest.raises(ValueError):config.update(home,{'image_permissions':value},before['revision'])
    assert config.read_json(home/'deployment.json')==before
