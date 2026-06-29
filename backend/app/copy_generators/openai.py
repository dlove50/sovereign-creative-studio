"""OpenAI copy generator (Chat Completions REST API via httpx).

Uses the REST endpoint directly so there's no extra SDK dependency.
"""
import httpx

from ..config import OPENAI_API_KEY, OPENAI_COPY_MODEL
from .base import CopyGenerator, CopyResult
from .prompt import build_messages

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_TIMEOUT_SECONDS = 60.0
_TEMPERATURE = 0.8


class OpenAICopyGenerator(CopyGenerator):
    def __init__(self, api_key: str = OPENAI_API_KEY, model: str = OPENAI_COPY_MODEL):
        self.api_key = api_key
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
        if not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set; cannot use the OpenAI copy backend."
            )

        payload = {
            "model": self.model,
            "messages": build_messages(
                copy_type=copy_type,
                tone=tone,
                audience=audience,
                prompt=prompt,
                product_context=product_context,
            ),
            "temperature": _TEMPERATURE,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                resp = await client.post(_OPENAI_URL, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise RuntimeError("OpenAI request timed out") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Could not reach OpenAI: {exc}") from exc

        if resp.status_code == 401:
            raise RuntimeError("OpenAI rejected the API key (401 Unauthorized).")
        if resp.status_code == 404:
            raise RuntimeError(f"OpenAI model '{self.model}' is unavailable (404).")
        if resp.status_code >= 400:
            raise RuntimeError(
                f"OpenAI request failed ({resp.status_code}): {resp.text[:200]}"
            )

        data = resp.json()
        choices = data.get("choices") or []
        text = (
            (choices[0].get("message", {}).get("content", "") if choices else "")
            or ""
        ).strip()
        if not text:
            raise RuntimeError("OpenAI returned an empty response")
        return CopyResult(result_text=text)
