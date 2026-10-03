"""Import an official ElevenLabs audio ZIP export into Sovereign Cloud Studio.

No network, API key, model cloning, extraction of ZIP paths, or provider charges.
Usage: backend/.venv/Scripts/python.exe tools/import_elevenlabs_audio.py EXPORT.zip
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services import cloud_media as cloud


def import_archive(archive: Path) -> dict:
    imported, existing = [], []
    with zipfile.ZipFile(archive) as bundle:
        entries = [entry for entry in bundle.infolist() if not entry.is_dir() and Path(entry.filename).suffix.lower() in {".mp3", ".wav", ".flac", ".ogg", ".m4a"}]
        if not entries:
            raise ValueError("No supported audio files in this archive")
        if sum(entry.file_size for entry in entries) > 1024**3 or any(entry.file_size > 100 * 1024**2 for entry in entries):
            raise ValueError("Archive exceeds 1 GB total or 100 MB per audio file")
        for entry in entries:
            audio = bundle.read(entry)
            if not audio:
                continue
            digest = hashlib.sha256(audio).hexdigest()
            job_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "sovereign:elevenlabs-export:" + digest))
            destination = cloud.folder(job_id)
            if (destination / "job.json").exists():
                existing.append(job_id)
                continue
            # Never extract a provider-controlled filename as a filesystem path.
            filename = "output" + Path(entry.filename).suffix.lower()
            destination.mkdir(parents=True, exist_ok=True)
            (destination / filename).write_bytes(audio)
            cloud.save({
                "id": job_id, "provider": "elevenlabs", "operation": "imported-audio",
                "title": Path(entry.filename.replace("\\", "/")).stem[:120],
                "status": "completed", "created_at": datetime.now(timezone.utc).isoformat(),
                "remote_id": None, "files": [filename], "error": None,
                "fingerprint": digest, "source": "Official ElevenLabs browser history export",
                "original_filename": entry.filename, "sha256": digest,
            })
            imported.append(job_id)
    return {"imported": imported, "already_present": existing, "output_directory": str(cloud.root().resolve())}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    print(json.dumps(import_archive(parser.parse_args().archive), indent=2))
