"""Linux-only legacy presenter expansion; separate from NVIDIA's public batch."""
import json
import sys
import time
import uuid
import subprocess
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.generators.comfyui import ComfyUIGenerator
from app.database import SessionLocal
from app.models import AvatarAsset
from app.config import STORAGE_DIR
from expand_public_avatar_looks import VARIANTS

STATE = ROOT / 'work' / 'linux-presenter-looks.json'
OWNER = '4aed7ae645494e5da8497acbd150c87d'
ROWS = [('creator-studio', 'Creator studio presenter'), ('real-estate', 'Real estate presenter')]


def run():
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    def save():
        STATE.write_text(json.dumps(state, indent=2))
    generator = ComfyUIGenerator('http://127.0.0.1:18001')
    with httpx.Client(base_url=generator.base_url, timeout=60, trust_env=False) as client:
        for slug, name in ROWS:
            with SessionLocal() as db:
                bases = db.query(AvatarAsset).filter(AvatarAsset.user_id == OWNER, AvatarAsset.name == name, AvatarAsset.group_id.is_(None), AvatarAsset.deleted_at.is_(None)).all()
                if not bases:
                    print('No base:', name, flush=True)
                    continue
                base_ids = [base.id for base in bases]
                source = STORAGE_DIR / bases[0].source_file_path.removeprefix('/storage/')
            for label, prompt in VARIANTS:
                key = slug + ':' + label
                entry = state.setdefault(key, {})
                if entry.get('status') == 'completed':
                    continue
                if entry.get('status') in {'submission-unknown', 'failed'}:
                    raise RuntimeError('Inspect unresolved job: ' + key)
                if not entry.get('prompt_id'):
                    while True:
                        response = client.get('/queue'); response.raise_for_status()
                        queue = response.json()
                        if not queue['queue_running'] and not queue['queue_pending']:
                            break
                        time.sleep(10)
                    with source.open('rb') as file:
                        upload = client.post('/upload/image', files={'image': (slug + '.webp', file, 'image/webp')})
                    upload.raise_for_status()
                    workflow = generator._build_workflow('Keep the exact same person, face, skin tone, age and hair. ' + prompt,
                        mode='image_edit', source_image_name=upload.json()['name'])
                    entry['status'] = 'submission-unknown'; save()
                    response = client.post('/prompt', json={'prompt': workflow}); response.raise_for_status()
                    entry.update(status='rendering', prompt_id=response.json()['prompt_id']); save()
                    print('Submitted', key, entry['prompt_id'], flush=True)
                started = time.monotonic()
                while True:
                    try:
                        response = client.get('/history/' + entry['prompt_id']); response.raise_for_status()
                    except httpx.TransportError as exc:
                        if time.monotonic() - started > 7200:
                            raise TimeoutError('Connection did not recover; retain prompt ID') from exc
                        print('Connection interrupted; retrying stored prompt:', entry['prompt_id'], flush=True)
                        time.sleep(15)
                        continue
                    history = response.json().get(entry['prompt_id'])
                    if history and history.get('status', {}).get('status_str') == 'error':
                        entry['status'] = 'failed'; save(); raise RuntimeError(key)
                    if history and history.get('status', {}).get('completed'):
                        image = generator._first_image(history['outputs'])
                        response = client.get('/view', params={k: image.get(k, '') for k in ('filename', 'subfolder', 'type')}); response.raise_for_status()
                        stem = slug + '-' + label.lower().replace(' ', '-')
                        export = Path.home() / 'Downloads/Sovereign/Images/Avatar Library/Legacy Presenters' / (stem + '.png')
                        export.parent.mkdir(parents=True, exist_ok=True); export.write_bytes(response.content)
                        dest = STORAGE_DIR / 'avatars/library' / (stem + '.webp')
                        subprocess.run(['ffmpeg','-y','-v','error','-i',str(export),'-vf','scale=-2:960',str(dest)], check=True)
                        url = '/storage/avatars/library/' + dest.name
                        with SessionLocal() as db:
                            for base_id in base_ids:
                                look_id = uuid.uuid5(uuid.NAMESPACE_URL, base_id + ':linux-suite:' + label).hex
                                if not db.get(AvatarAsset, look_id):
                                    db.add(AvatarAsset(id=look_id, user_id=OWNER, name=name+' - '+label, group_id=base_id,
                                        look_label=label, source_file_path=url, thumbnail_path=url, provider='local', status='ready'))
                            db.commit()
                        entry['status'] = 'completed'; save()
                        print('Completed', key, flush=True)
                        break
                    if time.monotonic() - started > 7200:
                        raise TimeoutError('Resume stored prompt ID: ' + entry['prompt_id'])
                    time.sleep(10)


if __name__ == '__main__':
    run()
