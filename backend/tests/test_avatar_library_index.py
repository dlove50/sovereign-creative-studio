from datetime import datetime, timezone
from types import SimpleNamespace
from test_cinematic_plan_storage import stored_api
from app.models import AvatarAsset, Project
from app.services.library import build_library_items


def test_owned_avatar_and_looks_are_indexed_without_copying_or_foreign_leaks(stored_api):
    _, _, sessions = stored_api
    with sessions() as db:
        db.add(Project(id='project',user_id='alice',name='Only project'))
        for aid,owner,status,deleted,group in [('base','alice','ready',None,None),('look','alice','ready',None,'base'),('foreign','bob','ready',None,None),('failed','alice','failed',None,None),('deleted','alice','ready',datetime.now(timezone.utc),None)]:
            db.add(AvatarAsset(id=aid,user_id=owner,name=aid,avatar_type='photo_avatar',status=status,deleted_at=deleted,group_id=group,source_file_path=f'/storage/avatars/{aid}.png'))
        for aid, path in [('empty', ''), ('whitespace', '   '), ('null', None)]:
            db.add(AvatarAsset(id=aid,user_id='alice',name=aid,avatar_type='photo_avatar',status='ready',source_file_path=path))
        db.commit()
        result=build_library_items(db,SimpleNamespace(id='alice'))
        images=[x for x in result if x.source_entity_type=='avatar_asset']
        assert {x.source_entity_id for x in images}=={'base','look'}
        assert all(x.type=='image' and x.status=='completed' and x.asset_url==f'/storage/avatars/{x.source_entity_id}.png' for x in images)
        assert not build_library_items(db,SimpleNamespace(id='alice'),'project')
        assert len([x for x in build_library_items(db,SimpleNamespace(id='alice')) if x.source_entity_type=='avatar_asset'])==2
