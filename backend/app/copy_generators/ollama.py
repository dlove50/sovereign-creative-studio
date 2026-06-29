"""Ollama copy generator (local LLM via the /api/chat endpoint)."""
import httpx

from ..config import OLLAMA_BASE_URL, OLLAMA_COPY_MODEL
from .base import CopyGenerator, CopyResult
from .prompt import build_messages

# Local models can be slow on first load, so allow a generous timeout.
_TIMEOUT_SECONDS = 120.0
_TEMPERATURE = 0.8


class OllamaCopyGenerator(CopyGenerator):
    def __init__(
        self, base_url: str = OLLAMA_BASE_URL, model: str = OLLAMA_COPY_MODEL
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def generate(
        self,
        *,
        copy_id: str,
        copy_type: str,
        tone: str,
        audience: str | None,
        prompt: str,
        product_context: str | None = None,
    ) -> CopyResult:
        payload = {
            "model": self.model,
            "messages": build_messages(
                copy_type=copy_type,
                tone=tone,
                audience=audience,
                prompt=prompt,
                product_context=product_context,
            ),
            "stream": False,
            "options": {"temperature": _TEMPERATURE},
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                resp = await client.post(f"{self.base_url}/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise RuntimeError("Ollama request timed out") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Could not reach Ollama at {self.base_url}: {exc}"
            ) from exc

        if resp.status_code == 404:
            raise RuntimeError(
                f"Ollama model '{self.model}' is not available (404). "
                f"Pull it first with `ollama pull {self.model}`."
            )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Ollama request failed ({resp.status_code}): {resp.text[:200]}"
            )

        data = resp.json()
        text = ((data.get("message") or {}).get("content", "") or "").strip()
        if not text:
            raise RuntimeError("Ollama returned an empty response")
        return CopyResult(result_text=text)
