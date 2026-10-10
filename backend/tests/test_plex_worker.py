from pathlib import Path
import subprocess

from app.services import plex_worker


def test_disabled_worker_never_connects(monkeypatch, tmp_path):
    monkeypatch.delenv('SOVEREIGN_PLEX_ASSEMBLY', raising=False)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: (_ for _ in ()).throw(AssertionError('unexpected connection')))
    assert not plex_worker.join_on_plex([Path('a'), Path('b')], tmp_path/'out.mp4')


def test_unavailable_worker_preserves_output(monkeypatch, tmp_path):
    monkeypatch.setenv('SOVEREIGN_PLEX_ASSEMBLY', '1')
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(75, args[0])
    monkeypatch.setattr(subprocess, 'run', fail)
    out = tmp_path/'out.mp4'
    out.write_bytes(b'previous')
    assert not plex_worker.join_on_plex([Path('a'), Path('b')], out)
    assert out.read_bytes() == b'previous'
