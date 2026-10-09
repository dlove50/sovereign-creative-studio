from test_cinematic_plan_storage import stored_api, payload
from app.models import CinematicProduction, VideoGeneration
from app.routers import projects
from sqlalchemy import select, func


def test_owned_existing_assemblies_index_without_generation_rows(stored_api, payload, tmp_path, monkeypatch):
    client, owner, sessions = stored_api
    monkeypatch.setattr(projects.config, 'STORAGE_DIR', tmp_path)
    (tmp_path / 'videos').mkdir()
    (tmp_path / 'videos' / 'final.mp4').write_bytes(b'fixture')
    plan = client.post('/api/video-agent/plans', json=payload).json()
    with sessions() as db:
        db.add_all([
            CinematicProduction(plan_id=plan['id'], revision=1, status='completed', result_url='/storage/videos/final.mp4'),
            CinematicProduction(plan_id=plan['id'], revision=2, status='completed', result_url='/storage/videos/missing.mp4'),
            CinematicProduction(plan_id=plan['id'], revision=3, status='rendering', result_url='/storage/videos/final.mp4'),
            CinematicProduction(plan_id=plan['id'], revision=4, status='completed', result_url='/storage/videos/../../outside.mp4'),
        ])
        db.commit()
    url = '/api/projects/cinematic-outputs'
    result = client.get(url)
    assert result.status_code == 200, result.text
    assert len(result.json()) == 1
    assert result.json()[0]['plan_id'] == plan['id']
    assert result.json()[0]['result_url'] == '/storage/videos/final.mp4'
    assert client.get(url).json() == result.json()
    owner[0] = 'bob'
    assert client.get(url).json() == []
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(VideoGeneration)) == 0
