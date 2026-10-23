"""Exercise cross-feature contention without loading inference models."""
import threading
import time

from PIL import Image

from app.services import enhance, music


def wait_terminal(job_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = enhance.get_job(job_id)
        if job['status'] in {'done', 'error', 'cancelled'}:
            return job
        time.sleep(.01)
    raise AssertionError('Queued enhancement did not finish')


def test_music_blocks_model_enhancement_but_not_cpu_work(tmp_path, monkeypatch):
    source = tmp_path / 'source.png'
    Image.new('RGB', (8, 8), 'red').save(source)
    gpu_entered, cpu_entered = threading.Event(), threading.Event()
    monkeypatch.setattr(enhance, '_available', lambda op: (True, None))

    def chain(job_id, path, folder, kind, ops):
        (gpu_entered if ops[0]['op'] == 'upscale_ai' else cpu_entered).set()
        return {'path': str(path), 'kind': kind, 'label': 'Enhanced'}

    monkeypatch.setattr(enhance, '_chain', chain)
    with music._gpu_lock:
        gpu = enhance.create_job('test', source, 'GPU', [{'op': 'upscale_ai', 'params': {'scale': 2}}])
        cpu = enhance.create_job('test', source, 'CPU', [{'op': 'denoise', 'params': {}}])
        assert cpu_entered.wait(3), 'CPU enhancement incorrectly waited for music'
        assert not gpu_entered.is_set(), 'Model enhancement overlapped the music job'
        assert enhance.get_job(gpu['id'])['status'] == 'queued'
    assert gpu_entered.wait(3)
    assert wait_terminal(gpu['id'])['status'] == 'done'
    assert wait_terminal(cpu['id'])['status'] == 'done'


def test_cancelled_queued_enhancement_never_starts_the_model(tmp_path, monkeypatch):
    source = tmp_path / 'source.png'
    Image.new('RGB', (8, 8), 'red').save(source)
    entered = threading.Event()
    monkeypatch.setattr(enhance, '_available', lambda op: (True, None))
    monkeypatch.setattr(enhance, '_chain', lambda *a: entered.set())
    with music._gpu_lock:
        job = enhance.create_job('test', source, 'Cancelled', [{'op': 'upscale_ai', 'params': {'scale': 2}}])
        enhance.cancel(job['id'])
    assert wait_terminal(job['id'])['status'] == 'cancelled'
    assert not entered.is_set()
