"""Sovereign Creative Studio MCP server (official MCP Python SDK, stdio transport).

Exposes Sovereign's production pipeline to DeepSeek Harness, Claude Code or any MCP client.
It is a thin, validated layer over Sovereign's own HTTP API (default http://127.0.0.1:8012),
so every rule the app enforces (ownership, validation, no faked output) still applies.

Safety
  * Expensive GPU work (rendering, video enhancement, stem separation) returns a plan first and
    only runs with confirm=true, so an agent cannot skip the user's review.
  * Nothing here deletes user content.
  * Local files are read/written only under SOVEREIGN_MCP_ALLOWED_DIRS (colon separated;
    default: your home folder and /mnt/storage/Projects).

Tool names use underscores (sovereign_render_video): several MCP clients reject dots.

Run:  ~/ai/venvs/sovereign-mcp/bin/python tools/sovereign_mcp/server.py
"""
from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any, Literal

import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

API = os.getenv("SOVEREIGN_API", "http://127.0.0.1:8012").rstrip("/")
ALLOWED = [Path(p).expanduser().resolve() for p in
           os.getenv("SOVEREIGN_MCP_ALLOWED_DIRS", f"{Path.home()}:/mnt/storage/Projects").split(":") if p]
POLL = 3.0
STATES = Literal["SINGING", "SPEAKING", "BACKGROUND_VOCAL", "LISTENING", "MOVING", "IDLE"]
MODES = Literal["alternating", "call_response", "harmony", "lead_background", "shared_stage"]

mcp = MCPServer(
    name="sovereign",
    title="Sovereign Creative Studio",
    instructions=(
        "Local creative production studio. Typical duet workflow: sovereign_create_performance -> "
        "sovereign_assign_performer (identity picture + vocal stem for each singer) -> sovereign_compose_duet "
        "(master song, mode, detect parts) -> sovereign_preview_timeline (check the director sheet with the user) "
        "-> sovereign_render_video with confirm=true only after the user agrees. Tools marked 'costly' return a "
        "plan unless confirm=true. All processing runs locally on the user's GPU."
    ),
)


class SovereignError(ToolError):
    """Shown to the agent verbatim (plain exceptions are masked by the SDK)."""


def _local(path: str, *, must_exist: bool = True) -> Path:
    p = Path(path).expanduser().resolve()
    if not any(p == root or root in p.parents for root in ALLOWED):
        raise SovereignError(f"{p} is outside the folders this server may use: {', '.join(map(str, ALLOWED))}")
    if must_exist and not p.is_file():
        raise SovereignError(f"File not found: {p}")
    return p


async def _call(method: str, path: str, *, json: Any = None, files: dict | None = None,
                data: dict | None = None) -> Any:
    async with httpx.AsyncClient(base_url=API, timeout=600.0) as client:
        try:
            resp = await client.request(method, path, json=json, files=files, data=data)
        except httpx.HTTPError as exc:
            raise SovereignError(f"Sovereign is not reachable at {API}: {exc}") from exc
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail")
        except ValueError:
            detail = resp.text[:300]
        raise SovereignError(f"{method} {path} failed ({resp.status_code}): {detail}")
    return resp.json() if resp.content else None


async def _upload(path: str, endpoint: str, field: str = "file", extra: dict | None = None) -> Any:
    local = _local(path)
    with local.open("rb") as fh:
        return await _call("POST", endpoint, files={field: (local.name, fh.read())}, data=extra)


def _summary(perf: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": perf["id"], "title": perf["title"], "mode": perf["mode"], "duration": perf["duration"],
        "performers": [{"id": p["id"], "name": p["name"], "role": p["role"], "stage_x": p["stage"]["x"],
                        "has_identity": bool(p.get("identity_url")), "has_stem": bool(p.get("stem_url")),
                        "regions": len(p["regions"])} for p in perf["performers"]],
        "has_master": bool(perf.get("master_audio_url")),
        "sheet": perf.get("sheet", []),
        "render": perf.get("render"),
    }


async def _wait_enhance(job_id: str, ctx: Context | None) -> dict[str, Any]:
    while True:
        job = await _call("GET", f"/api/enhance/jobs/{job_id}")
        if ctx:
            await ctx.report_progress(job["progress"], 1.0, f"{job['kind']} enhancement {job['status']}")
        if job["status"] not in ("queued", "running"):
            if job["status"] != "done":
                raise SovereignError(f"Enhancement {job['status']}: {job.get('error')}")
            return job
        await asyncio.sleep(POLL)


async def _save_outputs(job: dict[str, Any], out_dir: str | None) -> list[str]:
    if not out_dir:
        return [f"{API}{o['url']}" for o in job["outputs"]]
    target = _local(out_dir, must_exist=False)
    target.mkdir(parents=True, exist_ok=True)
    saved = []
    async with httpx.AsyncClient(base_url=API, timeout=600.0) as client:
        for i, o in enumerate(job["outputs"]):
            resp = await client.get(o["url"])
            resp.raise_for_status()
            ext = {"image": ".png", "audio": ".wav", "video": ".mp4"}[o["kind"]]
            path = target / f"{Path(job['name']).stem}-{o['label'].lower()}-{job['id']}{ext}"
            path.write_bytes(resp.content)
            saved.append(str(path))
    return saved


# --- Inspect ------------------------------------------------------------------------------------

@mcp.tool(name="sovereign_inspect_project")
async def inspect_project() -> dict[str, Any]:
    """What Sovereign can do right now: renderer readiness, music engine, enhancement models, performances."""
    readiness = await _call("GET", "/api/performances/readiness")
    music = await _call("GET", "/api/music/status")
    ops = (await _call("GET", "/api/enhance/operations"))["operations"]
    perfs = await _call("GET", "/api/performances")
    return {
        "api": API,
        "duet_renderer": readiness,
        "music_engine": music.get("engine"),
        "enhancements": {o["id"]: (True if o["available"] else o["unavailable_reason"]) for o in ops},
        "performances": [{"id": p["id"], "title": p["title"], "mode": p["mode"], "duration": p["duration"],
                          "render": (p.get("render") or {}).get("status")} for p in perfs],
    }


# --- Avatars, scenes, songs --------------------------------------------------------------------

@mcp.tool(name="sovereign_create_avatar")
async def create_avatar(image_path: str, name: str) -> dict[str, Any]:
    """Add a photo avatar to the Avatar library from a local picture."""
    avatar = await _upload(image_path, "/api/avatars/photo", extra={"name": name})
    return {"id": avatar["id"], "name": avatar["name"], "status": avatar["status"],
            "image": avatar.get("source_file_path"), "thumbnail": avatar.get("thumbnail_path")}


@mcp.tool(name="sovereign_generate_scene")
async def generate_scene(prompt: str, ctx: Context) -> dict[str, Any]:
    """Generate a still image (e.g. a concert stage) with Sovereign's image engine and wait for it."""
    gen = await _call("POST", "/api/generations", json={"prompt": prompt})
    while gen["status"] in ("queued", "running"):
        await ctx.report_progress(0.5, 1.0, f"image {gen['status']}")
        await asyncio.sleep(POLL)
        gen = await _call("GET", f"/api/generations/{gen['id']}")
    if gen["status"] != "completed":
        raise SovereignError(f"Image generation {gen['status']}: {gen.get('error')}")
    return {"id": gen["id"], "image_url": f"{API}{gen['file_url']}" if gen.get("file_url") else None,
            "provider": gen.get("provider"), "status": gen["status"]}


@mcp.tool(name="sovereign_import_song")
async def import_song(path: str) -> dict[str, Any]:
    """Import a local song into Music Lab (returns its song id)."""
    local = _local(path)
    with local.open("rb") as fh:
        result = await _call("POST", "/api/music/import", files={"files": (local.name, fh.read())})
    if result["errors"]:
        raise SovereignError(result["errors"][0]["error"])
    song = result["songs"][0]
    return {"song_id": song["id"], "title": song.get("title"), "duration": song.get("duration")}


@mcp.tool(name="sovereign_separate_vocals")
async def separate_vocals(path: str, ctx: Context, out_dir: str | None = None, confirm: bool = False) -> dict[str, Any]:
    """Costly: split a song into vocals and instrumental with Demucs on the GPU. Without confirm=true, returns the plan."""
    local = _local(path)
    if not confirm:
        return {"plan": f"Separate {local.name} with Demucs htdemucs on the local GPU (about 10-40 s per minute "
                        "of audio). Call again with confirm=true to run."}
    job = await _upload(str(local), "/api/enhance/jobs", extra={"ops": '[{"op":"separate"}]', "name": local.name})
    job = await _wait_enhance(job["id"], ctx)
    return {"job_id": job["id"], "outputs": await _save_outputs(job, out_dir)}


# --- Multi-Performer Director ------------------------------------------------------------------

@mcp.tool(name="sovereign_create_performance")
async def create_performance(performers: list[str], title: str = "", mode: MODES = "alternating") -> dict[str, Any]:
    """Create a Multi-Performer Director project (duet, trio, choir, dialogue) with named performers."""
    return _summary(await _call("POST", "/api/performances", json={"title": title, "performers": performers, "mode": mode}))


@mcp.tool(name="sovereign_assign_performer")
async def assign_performer(performance_id: str, performer_id: str, identity_image_path: str | None = None,
                           vocal_stem_path: str | None = None, name: str | None = None,
                           stage_x: float | None = None,
                           role: Literal["lead", "co_lead", "background", "actor"] | None = None) -> dict[str, Any]:
    """Give one performer their identity picture, their OWN vocal stem, a name, role and stage position (0 left..1 right)."""
    base = f"/api/performances/{performance_id}"
    perf = None
    if identity_image_path:
        perf = await _upload(identity_image_path, f"{base}/performers/{performer_id}/identity")
    if vocal_stem_path:
        perf = await _upload(vocal_stem_path, f"{base}/performers/{performer_id}/stem")
    patch: dict[str, Any] = {}
    if name:
        patch["name"] = name
    if role:
        patch["role"] = role
    if stage_x is not None:
        if not 0 <= stage_x <= 1:
            raise SovereignError("stage_x must be between 0 (left) and 1 (right).")
        patch["stage"] = {"x": stage_x, "scale": 1.0, "facing": "audience"}
    if patch:
        perf = await _call("PATCH", f"{base}/performers/{performer_id}", json=patch)
    return _summary(perf or await _call("GET", base))


@mcp.tool(name="sovereign_compose_duet")
async def compose_duet(performance_id: str, master_song_path: str | None = None, mode: MODES | None = None,
                       stage_image_path: str | None = None, stage_prompt: str | None = None,
                       detect_parts: bool = True) -> dict[str, Any]:
    """Set the master song, stage and mode, then find each performer's parts in THEIR stem. Returns the director sheet."""
    base = f"/api/performances/{performance_id}"
    if master_song_path:
        await _upload(master_song_path, f"{base}/master")
    if stage_image_path:
        await _upload(stage_image_path, f"{base}/stage-image")
    if mode or stage_prompt is not None:
        body: dict[str, Any] = {}
        if mode:
            body["mode"] = mode
        if stage_prompt is not None:
            body["stage"] = {"prompt": stage_prompt, "aspect": "16:9"}
        await _call("PATCH", base, json=body)
    perf = await _call("POST", f"{base}/analyze") if detect_parts else await _call("GET", base)
    return _summary(perf)


@mcp.tool(name="sovereign_animate_performer")
async def animate_performer(performance_id: str, performer_id: str, regions: list[dict[str, Any]]) -> dict[str, Any]:
    """Replace one performer's timeline. Each region: {start, end, state, lyric?, intensity?}. States: SINGING,
    SPEAKING, BACKGROUND_VOCAL (mouth moves, needs their stem) or LISTENING, MOVING, IDLE (mouth still)."""
    allowed = {"SINGING", "SPEAKING", "BACKGROUND_VOCAL", "LISTENING", "MOVING", "IDLE"}
    for r in regions:
        if r.get("state") not in allowed:
            raise SovereignError(f"Unknown state {r.get('state')!r}.")
    perf = await _call("PUT", f"/api/performances/{performance_id}/performers/{performer_id}/regions",
                       json={"regions": regions})
    return _summary(perf)


@mcp.tool(name="sovereign_generate_lipsync")
async def generate_lipsync(performance_id: str) -> dict[str, Any]:
    """Build each performer's lip-sync drive audio: their own voiced parts only, silence everywhere else."""
    perf = await _call("POST", f"/api/performances/{performance_id}/drive-audio")
    return {"performers": [{"id": p["id"], "name": p["name"], "drive_audio": f"{API}{p['drive_audio_url']}"}
                           for p in perf["performers"] if p.get("drive_audio_url")]}


@mcp.tool(name="sovereign_preview_timeline")
async def preview_timeline(performance_id: str) -> dict[str, Any]:
    """The director sheet (who sings, listens, moves; camera per stretch) and what the render still needs."""
    perf = await _call("GET", f"/api/performances/{performance_id}")
    plan = await _call("GET", f"/api/performances/{performance_id}/render-plan")
    return {"sheet": perf["sheet"], "camera": perf["camera"], "ready": plan["ready"], "missing": plan["missing"],
            "strategy": plan["strategy"], "duration": plan["duration"]}


@mcp.tool(name="sovereign_render_video")
async def render_video(performance_id: str, ctx: Context, confirm: bool = False, wait: bool = True) -> dict[str, Any]:
    """Costly: render the performance locally (Wan 2.1 + InfiniteTalk). Without confirm=true, returns the plan
    and an estimate so the user can review it first."""
    plan = await _call("GET", f"/api/performances/{performance_id}/render-plan")
    if not confirm or not plan["ready"]:
        parts = max(1, round(plan["duration"] * 25 / 72))
        return {"ready": plan["ready"], "missing": plan["missing"], "strategy": plan["strategy"],
                "estimate": f"{parts} GPU parts of about 1-4 minutes each on the R9700",
                "next": "Show this to the user; call again with confirm=true to render." if plan["ready"] else
                        "Provide what is missing first."}
    await _call("POST", f"/api/performances/{performance_id}/render")
    if not wait:
        return {"started": True}
    while True:
        perf = await _call("GET", f"/api/performances/{performance_id}")
        render = perf.get("render") or {}
        await ctx.report_progress(render.get("progress", 0.0), 1.0, render.get("stage"))
        if render.get("status") not in ("queued", "running"):
            if render.get("status") != "done":
                raise SovereignError(f"Render {render.get('status')}: {render.get('error')}")
            return {"video": f"{API}{render['video_url']}", "master_shot": f"{API}{render.get('master_shot_url')}"}
        await asyncio.sleep(POLL * 3)


@mcp.tool(name="sovereign_export_project")
async def export_project(performance_id: str, out_dir: str) -> dict[str, Any]:
    """Save the finished performance video (and its unframed master shot) to a local folder."""
    perf = await _call("GET", f"/api/performances/{performance_id}")
    render = perf.get("render") or {}
    if render.get("status") != "done":
        raise SovereignError("Nothing to export yet: the performance has not finished rendering.")
    target = _local(out_dir, must_exist=False)
    target.mkdir(parents=True, exist_ok=True)
    saved = []
    async with httpx.AsyncClient(base_url=API, timeout=600.0) as client:
        for key, suffix in (("video_url", ""), ("master_shot_url", "-master-shot")):
            if render.get(key):
                resp = await client.get(render[key])
                resp.raise_for_status()
                path = target / f"{perf['title'].replace('/', '-')}{suffix}.mp4"
                path.write_bytes(resp.content)
                saved.append(str(path))
    return {"saved": saved}


# --- Enhance ------------------------------------------------------------------------------------

async def _enhance(path: str, ops: list[dict[str, Any]], ctx: Context, out_dir: str | None) -> dict[str, Any]:
    import json as _json

    local = _local(path)
    job = await _upload(str(local), "/api/enhance/jobs", extra={"ops": _json.dumps(ops), "name": local.name})
    job = await _wait_enhance(job["id"], ctx)
    return {"job_id": job["id"], "outputs": await _save_outputs(job, out_dir), "ops": job["ops"]}


@mcp.tool(name="sovereign_enhance_image")
async def enhance_image(path: str, ops: list[dict[str, Any]], ctx: Context, out_dir: str | None = None) -> dict[str, Any]:
    """Enhance a picture non-destructively. ops: [{op, params}] e.g. denoise, sharpen, deblock, color, low_light,
    upscale_classic, upscale_ai, face_restore. See sovereign_inspect_project for what is installed."""
    return await _enhance(path, ops, ctx, out_dir)


@mcp.tool(name="sovereign_enhance_audio")
async def enhance_audio(path: str, ops: list[dict[str, Any]], ctx: Context, out_dir: str | None = None) -> dict[str, Any]:
    """Enhance audio non-destructively. ops e.g. audio_denoise, vocal_clarity, eq, stereo, loudness, master."""
    return await _enhance(path, ops, ctx, out_dir)


@mcp.tool(name="sovereign_enhance_video")
async def enhance_video(path: str, ops: list[dict[str, Any]], ctx: Context, out_dir: str | None = None,
                        confirm: bool = False) -> dict[str, Any]:
    """Costly: enhance a video non-destructively (denoise, deflicker, sharpen, color, upscale, interpolate...).
    Without confirm=true, returns the plan."""
    if not confirm:
        return {"plan": f"Enhance {Path(path).name} with {[o.get('op') for o in ops]}; long videos can take a while. "
                        "Call again with confirm=true to run."}
    return await _enhance(path, ops, ctx, out_dir)


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
