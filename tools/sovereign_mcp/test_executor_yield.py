"""Run with the isolated sovereign-mcp Python; no live model is loaded."""
import json
import os
import unittest
from unittest.mock import patch

import httpx
import server


class ExecutorYieldTests(unittest.IsolatedAsyncioTestCase):
    async def test_unloads_only_configured_model_before_returning(self):
        calls = []
        unloaded = False

        def handler(request):
            nonlocal unloaded
            calls.append((request.method, request.url.path))
            if request.method == 'POST':
                self.assertEqual(json.loads(request.content), {'model': 'qa-executor', 'keep_alive': 0})
                unloaded = True
                return httpx.Response(200, json={'done': True})
            return httpx.Response(200, json={'models': [] if unloaded else [{'name': 'qa-executor'}]})

        client = httpx.AsyncClient(base_url='http://localhost', transport=httpx.MockTransport(handler))
        with patch.dict(os.environ, {'SOVEREIGN_MCP_OLLAMA_EXECUTOR_MODEL': 'qa-executor'}), \
                patch.object(server.httpx, 'AsyncClient', return_value=client):
            await server._yield_executor_gpu()
        self.assertEqual(calls, [('GET', '/api/ps'), ('POST', '/api/generate'), ('GET', '/api/ps')])

    async def test_other_owner_is_preserved_and_production_is_blocked(self):
        calls = []

        def handler(request):
            calls.append(request.method)
            return httpx.Response(200, json={'models': [{'name': 'someone-elses-model'}]})

        client = httpx.AsyncClient(base_url='http://localhost', transport=httpx.MockTransport(handler))
        with patch.dict(os.environ, {'SOVEREIGN_MCP_OLLAMA_EXECUTOR_MODEL': 'qa-executor'}), \
                patch.object(server.httpx, 'AsyncClient', return_value=client):
            with self.assertRaises(server.SovereignError):
                await server._yield_executor_gpu()
        self.assertEqual(calls, ['GET'])

    async def test_disabled_by_default(self):
        with patch.dict(os.environ, {'SOVEREIGN_MCP_OLLAMA_EXECUTOR_MODEL': ''}), \
                patch.object(server.httpx, 'AsyncClient') as client:
            await server._yield_executor_gpu()
            client.assert_not_called()


if __name__ == '__main__':
    unittest.main()
