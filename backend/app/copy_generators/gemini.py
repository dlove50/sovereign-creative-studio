"""Google Gemini copy generator (Generative Language API via httpx).

Uses the REST endpoint directly so there's no extra SDK dependency.
"""
import httpx

from ..config import GEMINI_API_KEY, GEMINI_COPY_MODEL
from .base import CopyGenerator, CopyResult
from .prompt import build_system_and_user

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_TIMEOUT_SECONDS = 60.0
_TEMPERATURE = 0.8


class GeminiCopyGenerator(CopyGenerator):
    def __init__(self, api_key: str = GEMINI_API_KEY, model: str = GEMINI_COPY_MODEL):
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
                "GEMINI_API_KEY is not set; cannot use the Gemini copy backend."
            )

        system, user = build_system_and_user(
            copy_type=copy_type,
            tone=tone,
            audience=audience,
            prompt=prompt,
            product_context=product_context,
        )
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": _TEMPERATURE},
        }
        url = f"{_GEMINI_BASE}/{self.model}:generateContent"

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    url, json=payload, headers={"x-goog-api-key": self.api_key}
                )
        except httpx.TimeoutException as exc:
            raise RuntimeError("Gemini request timed out") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Could not reach Gemini: {exc}") from exc

        if resp.status_code in (401, 403):
            raise RuntimeError("Gemini rejected the API key.")
        if resp.status_code == 404:
            raise RuntimeError(f"Gemini model '{self.model}' is unavailable (404).")
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Gemini request failed ({resp.status_code}): {resp.text[:200]}"
            )

        try:
            data = resp.json()
            candidates = data.get("candidates") or []
            parts = (
                candidates[0].get("content", {}).get("parts", [])
                if candidates
                else []
            )
            text = "".join(part.get("text", "") for part in parts).strip()
        except (ValueError, AttributeError, IndexError) as exc:
            raise RuntimeError(f"Gemini returned a malformed response: {exc}") from exc
        if not text:
            raise RuntimeError("Gemini returned an empty response")
        return CopyResult(result_text=text)
