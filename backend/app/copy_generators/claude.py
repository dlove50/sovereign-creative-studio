"""Anthropic Claude copy generator (Messages API via httpx).

Uses the REST endpoint directly so there's no extra SDK dependency.
"""
import httpx

from ..config import ANTHROPIC_API_KEY, ANTHROPIC_COPY_MODEL
from .base import CopyGenerator, CopyResult
from .prompt import build_system_and_user

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_TIMEOUT_SECONDS = 60.0
_MAX_TOKENS = 1024
_TEMPERATURE = 0.8


class ClaudeCopyGenerator(CopyGenerator):
    def __init__(
        self, api_key: str = ANTHROPIC_API_KEY, model: str = ANTHROPIC_COPY_MODEL
    ):
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
                "ANTHROPIC_API_KEY is not set; cannot use the Claude copy backend."
            )

        system, user = build_system_and_user(
            copy_type=copy_type,
            tone=tone,
            audience=audience,
            prompt=prompt,
            product_context=product_context,
        )
        payload = {
            "model": self.model,
            "max_tokens": _MAX_TOKENS,
            "temperature": _TEMPERATURE,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                resp = await client.post(_ANTHROPIC_URL, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise RuntimeError("Claude request timed out") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Could not reach Claude: {exc}") from exc

        if resp.status_code == 401:
            raise RuntimeError("Claude rejected the API key (401 Unauthorized).")
        if resp.status_code == 404:
            raise RuntimeError(f"Claude model '{self.model}' is unavailable (404).")
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Claude request failed ({resp.status_code}): {resp.text[:200]}"
            )

        try:
            data = resp.json()
            blocks = data.get("content") or []
            text = "".join(
                block.get("text", "")
                for block in blocks
                if block.get("type") == "text"
            ).strip()
        except (ValueError, AttributeError) as exc:
            raise RuntimeError(f"Claude returned a malformed response: {exc}") from exc
        if not text:
            raise RuntimeError("Claude returned an empty response")
        return CopyResult(result_text=text)
