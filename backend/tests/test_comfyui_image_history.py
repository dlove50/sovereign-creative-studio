"""History failures must surface before partial image outputs or another poll."""
import asyncio
from types import SimpleNamespace
import pytest
from app.generators.comfyui import ComfyUIGenerator

class HistoryClient:
    def __init__(self, entry):
        self.entry = entry
        self.calls = 0

    async def get(self, path):
        self.calls += 1
        assert path == '/history/image-job'
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'image-job': self.entry})

def test_image_history_failure_is_immediate_even_with_partial_output():
    client = HistoryClient({'status': {'status_str': 'error', 'messages': [
        ['execution_error', {'node_type': 'UNETLoader', 'exception_message': 'model cannot load'}]
    ]}, 'outputs': {'preview': {'images': [{'filename': 'partial.png'}]}}})
    with pytest.raises(RuntimeError, match='UNETLoader: model cannot load'):
        asyncio.run(ComfyUIGenerator()._await_outputs(client, 'image-job'))
    assert client.calls == 1

def test_image_history_generic_failure_is_immediate():
    client = HistoryClient({'status': {'status_str': 'error', 'messages': [None]}})
    with pytest.raises(RuntimeError, match='ComfyUI image workflow failed'):
        asyncio.run(ComfyUIGenerator()._await_outputs(client, 'image-job'))
    assert client.calls == 1

def test_image_history_normal_output_returns_unchanged():
    output = {'9': {'images': [{'filename': 'finished.png', 'type': 'output'}]}}
    client = HistoryClient({'status': {'status_str': 'success'}, 'outputs': output})
    assert asyncio.run(ComfyUIGenerator()._await_outputs(client, 'image-job')) == output
    assert client.calls == 1
