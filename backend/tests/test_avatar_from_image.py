import base64
import pytest
from app.models import Generation, AvatarAsset
from test_cinematic_plan_storage import stored_api

@pytest.fixture
def image_api(stored_api,tmp_path,monkeypatch):
    from app.routers import avatars
    from app.services import source_validation,transcription
    monkeypatch.setattr(avatars.config,'STORAGE_DIR',tmp_path)
    monkeypatch.setattr(source_validation,'STORAGE_DIR',tmp_path)
    monkeypatch.setattr(transcription,'STORAGE_DIR',tmp_path)
    path=tmp_path/'image.png'
    path.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jC1cAAAAASUVORK5CYII='))
    client,owner,sessions=stored_api
    with sessions() as db:
        db.add(Generation(id='image',user_id='alice',prompt='photo',media_type='image',status='completed',file_url='/storage/image.png'))
        db.commit()
    return client,owner,sessions,path


def test_owned_image_becomes_durable_avatar_without_generation(image_api):
    client,_,sessions,path=image_api
    original=path.read_bytes()
    result=client.post('/api/avatars/from-image',json={'source_url':'/storage/image.png','name':'My presenter'})
    assert result.status_code==201,result.text
    value=result.json()
    assert value['avatar_type']=='photo_avatar' and value['name']=='My presenter'
    assert value['source_file_path']!='/storage/image.png'
    copy=path.parent/value['source_file_path'].removeprefix('/storage/')
    assert copy.read_bytes()==original
    path.unlink()
    assert copy.exists()
    with sessions() as db:
        assert db.get(AvatarAsset,value['id']).user_id=='alice'


def test_cross_owner_unowned_and_unsafe_paths_rejected(image_api):
    client,owner,_,_=image_api
    owner[0]='bob'
    assert client.post('/api/avatars/from-image',json={'source_url':'/storage/image.png','name':'Other'}).status_code==404
    owner[0]='alice'
    for source in ['http://remote/image.png','/storage/../image.png','/storage/image.mp4']:
        assert client.post('/api/avatars/from-image',json={'source_url':source,'name':'Bad'}).status_code==400
    assert client.post('/api/avatars/from-image',json={'source_url':'/storage/unknown.png','name':'Unknown'}).status_code==404


def test_incomplete_or_deleted_image_rejected(image_api):
    client,_,sessions,_=image_api
    with sessions() as db:
        db.get(Generation,'image').status='running';db.commit()
    assert client.post('/api/avatars/from-image',json={'source_url':'/storage/image.png','name':'Incomplete'}).status_code==404
