"""OpenAI Image API adapter for optional premium image/art generation."""
from __future__ import annotations

import base64
import ipaddress
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from ..config import STORAGE_DIR
from ..services.integrations import get_private_provider_config
from .base import GenerationResult, Generator

_HTTP_TIMEOUT_SECONDS = 120.0


class OpenAIImageGenerator(Generator):
    def __init__(self, provider_config: dict | None = None):
        self.config = provider_config or get_private_provider_config("openai")

    def _require_configured(self) -> None:
        if not self.config.get("enabled") or not self.config.get("api_key"):
            raise RuntimeError("OpenAI provider is not configured. Admin setup required.")
        if not self.config.get("base_url"):
            raise RuntimeError("OpenAI provider is missing a base URL. Admin setup required.")

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        return str(exc).replace("\n", " ")[:500]

    def _url(self, endpoint: str) -> str:
        return urljoin(str(self.config["base_url"]).rstrip("/") + "/", endpoint.lstrip("/"))

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.config['api_key']}"}
        if self.config.get("organization"):
            headers["OpenAI-Organization"] = str(self.config["organization"])
        if self.config.get("project"):
            headers["OpenAI-Project"] = str(self.config["project"])
        return headers

    async def generate(
        self,
        *,
        generation_id: str,
        prompt: str,
        media_type: str,
        mode: str = "text_to_image",
        source_image_url: str | None = None,
        reference_image_urls: list[str] | None = None,
    ) -> GenerationResult:
        self._require_configured()
        if media_type != "image":
            raise RuntimeError("OpenAI Image API supports image generation only.")
        if mode == "image_edit":
            if not source_image_url:
                raise RuntimeError("OpenAI image edit requires a source image.")
            data = await self._edit_image(prompt, source_image_url)
        elif mode == "text_to_image":
            data = await self._generate_image(prompt)
        else:
            raise RuntimeError(f"OpenAI Image API does not support {mode}.")

        output_dir = STORAGE_DIR / "generated"
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"{generation_id}.png"
        output.write_bytes(data)
        return GenerationResult(file_url=f"/storage/generated/{output.name}")

    async def _generate_image(self, prompt: str) -> bytes:
        payload = {
            "model": self.config.get("image_model"),
            "prompt": prompt,
            "size": self.config.get("image_size") or "1024x1024",
            "quality": self.config.get("image_quality") or "low",
            "output_format": "png",
        }
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            try:
                response = await client.post(
                    self._url("/images/generations"),
                    headers={**self._headers(), "Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
                return await _image_bytes_from_response(client, response.json())
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"OpenAI image request failed: {self._safe_error(exc)}") from exc

    async def _edit_image(self, prompt: str, source_image_url: str) -> bytes:
        source = _resolve_storage_path(source_image_url)
        if source is None or not source.is_file():
            raise RuntimeError("OpenAI image edit source image was not found in local storage.")

        data = {
            "model": str(self.config.get("image_model") or ""),
            "prompt": prompt,
            "size": str(self.config.get("image_size") or "1024x1024"),
            "quality": str(self.config.get("image_quality") or "low"),
            "output_format": "png",
        }
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            try:
                with source.open("rb") as fh:
                    response = await client.post(
                        self._url("/images/edits"),
                        headers=self._headers(),
                        data=data,
                        files={"image": (source.name, fh, _mime_for(source))},
                    )
                response.raise_for_status()
                return await _image_bytes_from_response(client, response.json())
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"OpenAI image request failed: {self._safe_error(exc)}") from exc


async def _image_bytes_from_response(client: httpx.AsyncClient, body: dict) -> bytes:
    image_item = None
    data = body.get("data")
    if isinstance(data, list) and data:
        image_item = data[0]
    elif isinstance(body.get("output"), list):
        for item in body["output"]:
            if isinstance(item, dict) and (item.get("b64_json") or item.get("url")):
                image_item = item
                break
    if not isinstance(image_item, dict):
        raise RuntimeError("OpenAI response did not include an image.")

    encoded = image_item.get("b64_json")
    if isinstance(encoded, str) and encoded:
        return base64.b64decode(encoded)

    url = image_item.get("url")
    if isinstance(url, str) and url:
        _validate_output_url(url)
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "html" in content_type.lower():
            raise RuntimeError("OpenAI output was HTML, not an image.")
        if not response.content:
            raise RuntimeError("OpenAI returned an empty image.")
        return response.content

    raise RuntimeError("OpenAI response did not include image bytes or URL.")


def _resolve_storage_path(file_url: str) -> Path | None:
    parsed = urlparse(file_url)
    path = parsed.path if parsed.scheme else file_url
    prefix = "/storage/"
    if not path.startswith(prefix):
        return None
    relative = path[len(prefix) :].replace("/", "\\")
    candidate = (STORAGE_DIR / relative).resolve()
    try:
        candidate.relative_to(STORAGE_DIR.resolve())
    except ValueError:
        return None
    return candidate


def _validate_output_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError("OpenAI returned an unsafe output URL.")
    host = parsed.hostname.lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("OpenAI returned an unsafe output URL.")
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise RuntimeError("OpenAI returned an unsafe output URL.")
    except ValueError:
        pass


def _mime_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"
