import importlib.util
import zipfile
from pathlib import Path

import pytest

from app.services import cloud_media as cloud

spec = importlib.util.spec_from_file_location("import_elevenlabs_audio", Path(__file__).resolve().parents[2] / "tools/import_elevenlabs_audio.py")
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)


def test_import_is_local_idempotent_and_does_not_extract_archive_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud, "root", lambda: tmp_path / "cloud")
    archive = tmp_path / "history.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("../../outside.mp3", b"ID3-test-audio")
        output.writestr("readme.txt", "untrusted archive metadata")
    result = importer.import_archive(archive, source="Official ElevenLabs Explore sound effects")
    assert len(result["imported"]) == 1
    job = cloud.read(result["imported"][0])
    assert job["operation"] == "imported-audio" and job["status"] == "completed"
    assert job["source"] == "Official ElevenLabs Explore sound effects"
    assert (cloud.folder(job["id"]) / "output.mp3").read_bytes() == b"ID3-test-audio"
    assert not (tmp_path / "outside.mp3").exists()
    again = importer.import_archive(archive)
    assert not again["imported"] and again["already_present"] == result["imported"]


def test_archive_without_audio_is_rejected(tmp_path):
    archive = tmp_path / "empty.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("script.exe", b"not audio")
    with pytest.raises(ValueError, match="No supported audio"):
        importer.import_archive(archive)
