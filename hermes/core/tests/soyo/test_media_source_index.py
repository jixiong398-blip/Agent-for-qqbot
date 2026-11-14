import io
import json
import sys
from types import SimpleNamespace
from soyo.qq import native_media
import soyo.platform


def test_a_failed_first_image_does_not_relabel_the_second(monkeypatch, capsys):
    monkeypatch.setattr(sys,'argv',['native_media.py','fixture.json'])
    request={'media':[{'kind':'image','ref':'missing'},{'kind':'image','ref':'second'}]}
    monkeypatch.setattr(sys,'stdin',SimpleNamespace(buffer=io.BytesIO(json.dumps(request).encode())))
    monkeypatch.setattr(soyo.platform,'load_private_json',lambda _:{})
    monkeypatch.setattr(native_media,'cached_media',lambda _,ref: {'path':'second.png','media_type':'image/png'} if ref=='second' else None)
    monkeypatch.setattr(native_media,'read_media',lambda *_:{'ok':False})
    native_media.main()
    result=json.loads(capsys.readouterr().out)
    assert len(result['items'])==1
    assert result['items'][0]['source_index']==1
    assert result['items'][0]['ref']=='second'
