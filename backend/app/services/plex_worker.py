"""Optional SSH movie assembly on the isolated Plex B580 worker."""
import json
import logging
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

log = logging.getLogger(__name__)
HOST = 'Plex@192.168.2.170'
REMOTE = 'C:/Users/Plex/SovereignWorker'


def join_on_plex(clips: list[Path], out: Path) -> bool:
    if os.getenv('SOVEREIGN_PLEX_ASSEMBLY', '0') != '1' or not 2 <= len(clips) <= 64:
        return False
    key = Path.home() / '.ssh' / 'sovereign_plex_ed25519'
    options = ['-i', str(key), '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
               '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=8']
    job_id = uuid.uuid4().hex
    remote_job = f'{REMOTE}/jobs/{job_id}'

    def run(args, timeout=300):
        return subprocess.run(args, check=True, capture_output=True, timeout=timeout)

    try:
        run(['ssh', *options, HOST, f'powershell -NoProfile -Command "New-Item -ItemType Directory -Force {remote_job} | Out-Null"'], 30)
        with tempfile.TemporaryDirectory(prefix='sovereign-plex-') as tmp:
            request = Path(tmp) / 'request.json'
            request.write_text(json.dumps({'clip_count': len(clips)}))
            run(['scp', *options, str(request), f'{HOST}:{remote_job}/request.json'])
            for i, clip in enumerate(clips):
                run(['scp', *options, str(clip.resolve()), f'{HOST}:{remote_job}/clip-{i}.mp4'])
            run(['ssh', *options, HOST, f'powershell -NoProfile -File {REMOTE}/worker.ps1 -JobId {job_id}'], 1800)
            result = Path(tmp) / 'result.mp4'
            run(['scp', *options, f'{HOST}:{remote_job}/result.mp4', str(result)])
            if result.stat().st_size < 100:
                raise ValueError('Empty worker output')
            # Copy only a completed file into the movie output location.
            out.write_bytes(result.read_bytes())
        log.info('Plex B580 movie assembly completed: %s', job_id)
        return True
    except (subprocess.SubprocessError, OSError, ValueError):
        log.warning('Plex assembly unavailable; using local assembly (job %s)', job_id)
        return False
