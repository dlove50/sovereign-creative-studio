import copy
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.deps import get_current_user
from app.main import app
from app.models import CinematicPlan, User


@pytest.fixture
def stored_api(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'plans.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        db.add_all([User(id="alice", email="alice@test", name="Alice"), User(id="bob", email="bob@test", name="Bob")])
        db.commit()
    owner = ["alice"]
    def database():
        with sessions() as db:
            yield db
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=owner[0])
    client = TestClient(app)
    yield client, owner, sessions
    client.close()
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)
    engine.dispose()


@pytest.fixture
def payload():
    return {"prompt": "A calm courtyard", "seconds": 10, "plan": {
        "title": "Quiet", "synopsis": "Sunrise in a courtyard.", "model": "local:test",
        "characters": [], "locations": [{"id": "yard", "name": "Yard", "description": "Stone courtyard"}],
        "shots": [{"id": "wide", "duration_seconds": 10, "location_id": "yard", "character_ids": [],
                   "description": "Sunlight appears", "camera": "Static", "dialogue": [], "narration": "",
                   "transition": "Fade", "image_prompt": "Stone courtyard at sunrise", "video_prompt": "Light warms the stones"}]}}


def test_saved_edited_plan_roundtrips_across_sessions(stored_api, payload):
    client, _, sessions = stored_api
    saved = client.post("/api/video-agent/plans", json=payload)
    assert saved.status_code == 201, saved.text
    record = saved.json()
    assert record["revision"] == 1 and record["plan"] == payload["plan"]
    assert "user_id" not in record
    edited = copy.deepcopy(payload)
    edited["plan"]["shots"][0]["video_prompt"] = "An edited camera prompt, kept exactly."
    response = client.put(f"/api/video-agent/plans/{record['id']}", json={**edited, "revision": 1})
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 2
    # A fresh SQL session confirms persistence independently of the response/UI state.
    with sessions() as db:
        assert db.get(CinematicPlan, record["id"]).plan == edited["plan"]
    loaded = client.get(f"/api/video-agent/plans/{record['id']}").json()
    assert loaded["plan"] == edited["plan"]
    assert client.get("/api/video-agent/plans").json() == [loaded]


def test_other_owner_cannot_load_list_or_update(stored_api, payload):
    client, owner, _ = stored_api
    record = client.post("/api/video-agent/plans", json=payload).json()
    owner[0] = "bob"
    assert client.get("/api/video-agent/plans").json() == []
    assert client.get(f"/api/video-agent/plans/{record['id']}").status_code == 404
    assert client.put(f"/api/video-agent/plans/{record['id']}", json={**payload, "revision": 1}).status_code == 404
    assert client.post("/api/video-agent/plans", json={**payload, "user_id": "alice"}).status_code == 422


def test_stale_revision_cannot_overwrite_edits(stored_api, payload):
    client, _, _ = stored_api
    record = client.post("/api/video-agent/plans", json=payload).json()
    path = f"/api/video-agent/plans/{record['id']}"
    assert client.put(path, json={**payload, "revision": 1}).status_code == 200
    assert client.put(path, json={**payload, "revision": 1}).status_code == 409
    assert client.get(path).json()["revision"] == 2


def test_invalid_edited_plan_is_not_persisted(stored_api, payload):
    client, _, _ = stored_api
    payload["plan"]["shots"][0]["location_id"] = "nonexistent"
    assert client.post("/api/video-agent/plans", json=payload).status_code == 422
    payload["plan"]["shots"][0]["location_id"] = "yard"
    payload["seconds"] = 20
    assert client.post("/api/video-agent/plans", json=payload).status_code == 422
    assert client.get("/api/video-agent/plans").json() == []


def test_migration_creates_storage_and_is_repeatable(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    path = Path(__file__).parents[1] / "migrations/versions/0032_add_cinematic_plans.py"
    spec = importlib.util.spec_from_file_location("cinematic_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    User.__table__.create(engine)
    with engine.begin() as connection:
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.upgrade()
        migration.upgrade()
        assert "cinematic_plans" in inspect(connection).get_table_names()
        assert {column["name"] for column in inspect(connection).get_columns("cinematic_plans")} == {
            "id", "user_id", "prompt", "seconds", "plan", "revision", "created_at", "updated_at"
        }
    engine.dispose()

@pytest.fixture
def production_api(stored_api, payload, tmp_path, monkeypatch):
    from app.models import VideoGeneration, Project
    from app.routers import video_agent
    from app.services import source_validation
    monkeypatch.setattr(video_agent, 'STORAGE_DIR', tmp_path)
    monkeypatch.setattr(source_validation, 'STORAGE_DIR', tmp_path)
    (tmp_path / 'videos').mkdir()
    client, owner, sessions = stored_api
    with sessions() as db:
        db.add(Project(id='project',user_id='alice',name='Test'))
        for i, who in enumerate(['alice','alice','bob']):
            (tmp_path / f'videos/clip{i}.mp4').write_bytes(b'fixture')
            db.add(VideoGeneration(id=f'video{i}',user_id=who,project_id='project',source_image_url='',prompt='test',motion_preset='static',duration_seconds=5,status='completed',result_url=f'/storage/videos/clip{i}.mp4'))
        db.commit()
    second=copy.deepcopy(payload['plan']['shots'][0]);second['id']='second';second['duration_seconds']=5
    payload['plan']['shots'][0]['duration_seconds']=5
    payload['plan']['shots'].append(second)
    record=client.post('/api/video-agent/plans',json=payload).json()
    return client,owner,sessions,record,payload,tmp_path


def test_production_ownership_order_idempotence_and_revision(production_api, monkeypatch):
    from app.routers import video_agent
    client,owner,sessions,record,payload,root=production_api
    path=f"/api/video-agent/plans/{record['id']}"
    assert client.put(path+'/shots/wide',json={'revision':1,'video_id':'video2'}).status_code==404
    assert client.post(path+'/assemble',json={'revision':1}).status_code==409
    # Attach in reverse order; output must still follow plan order.
    assert client.put(path+'/shots/second',json={'revision':1,'video_id':'video1'}).status_code==200
    assert client.put(path+'/shots/wide',json={'revision':1,'video_id':'video0'}).status_code==200
    calls=[]
    def assemble(clips,destination):
        calls.append([p.name for p in clips]);destination.write_bytes(b'assembled')
    monkeypatch.setattr(video_agent,'assemble_clips',assemble)
    response=client.post(path+'/assemble',json={'revision':1})
    assert response.status_code==200,response.text
    assert response.json()['status']=='completed'
    assert calls==[['clip0.mp4','clip1.mp4']]
    assert client.post(path+'/assemble',json={'revision':1}).json()['status']=='completed'
    assert len(calls)==1
    owner[0]='bob'
    assert client.get(path+'/production').status_code==404
    assert client.post(path+'/assemble',json={'revision':1}).status_code==404
    owner[0]='alice'
    assert client.put(path,json={**payload,'revision':1}).status_code==200
    new=client.get(path+'/production').json()
    assert new['revision']==2 and new['status']=='draft' and new['result_url'] is None
    assert all(s['video_id'] is None for s in new['shots'])
    assert client.post(path+'/assemble',json={'revision':1}).status_code==409


def test_running_assembly_not_duplicated_and_restart_recovers(production_api, monkeypatch):
    from app.models import CinematicProduction
    from app.main import _recover_interrupted_jobs
    from app.routers import video_agent
    client,_,sessions,record,_,_=production_api
    path=f"/api/video-agent/plans/{record['id']}"
    with sessions() as db:
        db.add(CinematicProduction(plan_id=record['id'],revision=1,attachments={},version=1,status='assembling'))
        db.commit()
    monkeypatch.setattr(video_agent,'assemble_clips',lambda *args: pytest.fail('No duplicate'))
    assert client.post(path+'/assemble',json={'revision':1,'retry':True}).json()['status']=='assembling'
    with sessions() as db:
        _recover_interrupted_jobs(db)
    state=client.get(path+'/production').json()
    assert state['status']=='failed' and 'restart' in state['error']


def test_completed_missing_file_requires_explicit_retry(production_api):
    from app.models import CinematicProduction
    client,_,sessions,record,_,_=production_api
    with sessions() as db:
        db.add(CinematicProduction(plan_id=record['id'],revision=1,attachments={},version=1,status='completed',result_url='/storage/videos/missing.mp4'))
        db.commit()
    response=client.post(f"/api/video-agent/plans/{record['id']}/assemble",json={'revision':1})
    assert response.json()['status']=='failed'
    assert 'missing' in response.json()['error']
