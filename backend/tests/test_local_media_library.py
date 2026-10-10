from types import SimpleNamespace

import pytest

from app.services import local_media_library as library


def test_owner_library_reads_media_and_rejects_escape(tmp_path, monkeypatch):
    root = tmp_path / "Sovereign"
    folder = root / "Sound Bites"
    folder.mkdir(parents=True)
    (folder / "cinematic.wav").write_bytes(b"RIFF")
    (folder / "secret.txt").write_text("private")
    (tmp_path / "outside.wav").write_bytes(b"RIFF")
    monkeypatch.setattr(library, "MEDIA_ROOT", root)
    items = library.local_media_items(SimpleNamespace(role="owner_admin"))
    assert len(items) == 1
    assert items[0].source_entity_type == "local_audio"
    assert "Sound%20Bites/cinematic.wav" in items[0].asset_url
    assert library.local_media_items(SimpleNamespace(role="member")) == []
    for invalid in ["../outside.wav", str(tmp_path / "outside.wav"), "Sound Bites/secret.txt", "Videos/missing.mp4"]:
        with pytest.raises(ValueError):
            library.resolve_media(invalid)
