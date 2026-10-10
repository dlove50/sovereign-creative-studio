import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import User, VideoGeneration

spec = importlib.util.spec_from_file_location("owned_video_import", Path(__file__).resolve().parents[2] / "tools/import_owned_videos.py")
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg required")
def test_duplicate_files_in_one_batch_and_repeat_import_are_idempotent(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(importer, "SessionLocal", sessions)
    monkeypatch.setattr(importer.config, "STORAGE_DIR", tmp_path / "storage")
    with sessions() as db:
        db.add(User(id="owner", email="owner@example.test", name="Owner", role="owner_admin")); db.commit()
    first = tmp_path / "first.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=1", "-pix_fmt", "yuv420p", str(first)], check=True)
    second = tmp_path / "duplicate.mp4"; shutil.copy2(first, second)
    result = importer.import_videos([first, second], "owner")
    assert result["imported"] == ["first.mp4"]
    assert result["already_present"] == ["duplicate.mp4"]
    assert importer.import_videos([first], "owner")["already_present"] == ["first.mp4"]
    with sessions() as db:
        rows = db.scalars(select(VideoGeneration)).all()
        assert len(rows) == 1 and rows[0].credits_cost == 0
        assert rows[0].status == "completed"
    assert first.exists() and second.exists()
