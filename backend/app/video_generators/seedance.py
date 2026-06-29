"""Generic Seedance-compatible REST video provider.

David's exact Seedance/C-Dance vendor can vary (Seedance2AI, BytePlus/ModelArk,
fal.ai, Replicate-style proxy, etc.). This adapter therefore uses configurable
base URL, model id, create endpoint, and status endpoint from the admin-only
integrations store. It never returns or logs API keys.
"""
from __future__ import annotations

import asyncio
import ipaddress
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from ..config import STORAGE_DIR
from ..services.integrations import get_private_provider_config
from .base import VideoGenerator, VideoResult

_HTTP_TIMEOUT_SECONDS = 60.0
_POLL_INTERVAL_SECONDS = 5
_POLL_MAX_ATTEMPTS = 72


class SeedanceVideoGenerator(VideoGenerator):
    def __init__(self, provider_config: dict | None = None):
        self.config = provider_config or get_private_provider_config("seedance")

    def _require_configured(self) -> None:
        if not self.config.get("enabled") or not self.config.get("api_key"):
            raise RuntimeError("Seedance provider is not configured. Admin setup required.")
        if not self.config.get("base_url"):
            raise RuntimeError("Seedance provider is missing a base URL. Admin setup required.")

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        # Provider errors must never leak the API key.
        return str(exc).replace("\n", " ")[:500]

    def _url(self, endpoint: str) -> str:
        return urljoin(str(self.config["base_url"]).rstrip("/") + "/", endpoint.lstrip("/"))

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config['api_key']}",
            "Content-Type": "application/json",
        }

    async def generate(
        self,
        *,
        video_id: str,
        source_image_url: str,
        prompt: str,
        motion_preset: str,
        duration_seconds: int,
        mode: str = "text_to_video",
        quality_preset: str | None = None,
    ) -> VideoResult:
        self._require_configured()
        if mode not in {"text_to_video", "image_to_video"}:
            raise RuntimeError(f"Seedance provider does not support {mode}.")

        payload = {
            "model": self.config.get("model_id"),
            "prompt": prompt,
            "mode": mode,
            "duration_seconds": duration_seconds,
            "motion_preset": motion_preset,
        }
        if mode == "image_to_video":
            if not source_image_url:
                raise RuntimeError("Seedance Image -> Video requires a source image.")
            payload["image_url"] = source_image_url

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            try:
                create = await client.post(
                    self._url(str(self.config.get("create_endpoint") or "/v1/videos")),
                    headers=self._headers(),
                    json=payload,
                )
                create.raise_for_status()
                created = create.json()
                task_id = _first_string(created, "id", "task_id", "job_id", "request_id")
                video_url = _extract_video_url(created)
                if not video_url:
                    if not task_id:
                        raise RuntimeError("Seedance did not return a task id or video URL.")
                    video_url = await self._poll(client, task_id)
                data = await self._download_video(client, video_url)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"Seedance request failed: {self._safe_error(exc)}") from exc

        output_dir = STORAGE_DIR / "videos"
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"{video_id}.mp4"
        output.write_bytes(data)
        return VideoResult(
            result_url=f"/storage/videos/{output.name}",
            provider_task_id=task_id,
        )

    async def _poll(self, client: httpx.AsyncClient, task_id: str) -> str:
        endpoint = str(self.config.get("status_endpoint") or "/v1/videos/{task_id}")
        for _ in range(_POLL_MAX_ATTEMPTS):
            status_url = self._url(endpoint.replace("{task_id}", task_id))
            response = await client.get(status_url, headers=self._headers())
            response.raise_for_status()
            body = response.json()
            video_url = _extract_video_url(body)
            status = str(
                _first_string(body, "status", "state", "task_status") or ""
            ).lower()
            if video_url and status in {"", "success", "succeeded", "completed", "done"}:
                return video_url
            if status in {"failed", "error", "cancelled", "canceled"}:
                raise RuntimeError("Seedance task failed.")
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        raise TimeoutError("Seedance task timed out.")

    async def _download_video(self, client: httpx.AsyncClient, video_url: str) -> bytes:
        _validate_output_url(video_url)
        response = await client.get(video_url, follow_redirects=True)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        data = response.content
        if not data:
            raise RuntimeError("Seedance returned an empty video.")
        if "html" in content_type.lower():
            raise RuntimeError("Seedance output was HTML, not a video.")
        return data


def _first_string(data: dict, *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _extract_video_url(data: dict) -> str | None:
    for key in ("video_url", "output_url", "url", "download_url"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    output = data.get("output") or data.get("result") or data.get("data")
    if isinstance(output, dict):
        return _extract_video_url(output)
    if isinstance(output, list):
        for item in output:
            if isinstance(item, str) and item.startswith(("http://", "https://")):
                return item
            if isinstance(item, dict):
                nested = _extract_video_url(item)
                if nested:
                    return nested
    return None


def _validate_output_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError("Seedance returned an unsafe output URL.")
    host = parsed.hostname.lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("Seedance returned an unsafe output URL.")
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise RuntimeError("Seedance returned an unsafe output URL.")
    except ValueError:
        pass
