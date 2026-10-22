"""Phase 10 demo: drive the whole two-singer production through the Sovereign MCP server.

Builds (optionally trimmed) demo media, then uses the same MCP tools DeepSeek Harness would:
create_performance -> assign_performer (x2) -> compose_duet -> animate_performer (backing part) ->
preview_timeline -> render_video(confirm=true) -> export_project.

    ~/ai/venvs/sovereign-mcp/bin/python tools/demo/run_duet_demo.py --title T --start 24 --end 30 --out DIR
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

REPO = Path(__file__).resolve().parents[2]
DEMO = Path("/mnt/storage/Projects/sovereign-data/demo/duet")
STAGE = Path("/mnt/storage/Projects/sovereign-data/storage/e55402d2bc13476aba4fb026bcbf1719.png")
PY = Path.home() / "ai/venvs/sovereign-mcp/bin/python"
BACKING = (50.4, 55.3)  # B sings backing vocals here (Mode D)


def cut(src: Path, dst: Path, start: float, end: float) -> Path:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start}", "-to", f"{end}", "-i", str(src), str(dst)], check=True)
    return dst


def stage_assets(work: Path) -> tuple[Path, Path, Path]:
    """16:9 stage frame plus one identity crop per singer, all from the same generated picture."""
    from PIL import Image, ImageOps

    frame = ImageOps.fit(Image.open(STAGE).convert("RGB"), (832, 480))
    frame.save(work / "stage.png")
    frame.crop((0, 0, 416, 480)).save(work / "identity-a.png")
    frame.crop((416, 0, 832, 480)).save(work / "identity-b.png")
    return work / "stage.png", work / "identity-a.png", work / "identity-b.png"


def data(result) -> dict:
    if result.is_error:
        raise SystemExit("MCP tool failed: " + "".join(getattr(c, "text", "") for c in result.content))
    return json.loads("".join(getattr(c, "text", "") for c in result.content))


async def main(args) -> None:
    work = Path(args.out)
    work.mkdir(parents=True, exist_ok=True)
    master = cut(DEMO / "master-duet.wav", work / "master.wav", args.start, args.end)
    stem_a = cut(DEMO / "singer-a-stem.wav", work / "stem-a.wav", args.start, args.end)
    stem_b = cut(DEMO / "singer-b-stem.wav", work / "stem-b.wav", args.start, args.end)
    stage, id_a, id_b = stage_assets(work)

    params = StdioServerParameters(command=str(PY), args=[str(REPO / "tools/sovereign_mcp/server.py")],
                                   env={"SOVEREIGN_MCP_ALLOWED_DIRS": f"{work}:/mnt/storage/Projects"})
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            perf = data(await s.call_tool("sovereign_create_performance", {
                "performers": ["Ava", "Ben"], "title": args.title, "mode": "alternating"}))
            pid = perf["id"]
            a, b = (p["id"] for p in perf["performers"])
            print("performance", pid)
            await s.call_tool("sovereign_assign_performer", {"performance_id": pid, "performer_id": a,
                              "identity_image_path": str(id_a), "vocal_stem_path": str(stem_a), "stage_x": 0.30, "role": "lead"})
            await s.call_tool("sovereign_assign_performer", {"performance_id": pid, "performer_id": b,
                              "identity_image_path": str(id_b), "vocal_stem_path": str(stem_b), "stage_x": 0.66, "role": "co_lead"})
            perf = data(await s.call_tool("sovereign_compose_duet", {
                "performance_id": pid, "master_song_path": str(master), "stage_image_path": str(stage),
                "stage_prompt": "a professional concert stage with warm spotlights and purple haze", "detect_parts": True}))
            # Mode D: B's quieter harmony between 50.4 and 55.3 s is a backing vocal, not a lead.
            lo, hi = BACKING[0] - args.start, BACKING[1] - args.start
            if hi > 0 and lo < args.end - args.start:
                full = data(await s.call_tool("sovereign_preview_timeline", {"performance_id": pid}))
                import httpx
                regions = httpx.get(f"http://127.0.0.1:8012/api/performances/{pid}").json()["performers"][1]["regions"]
                for reg in regions:
                    if reg["state"] == "SINGING" and reg["start"] < hi and reg["end"] > lo:
                        reg["state"] = "BACKGROUND_VOCAL"
                data(await s.call_tool("sovereign_animate_performer", {
                    "performance_id": pid, "performer_id": b,
                    "regions": [{k: reg[k] for k in ("start", "end", "state", "intensity", "lyric", "source")} for reg in regions]}))
            preview = data(await s.call_tool("sovereign_preview_timeline", {"performance_id": pid}))
            print("director sheet:")
            for row in preview["sheet"]:
                print(f"  {row['start'] + args.start:6.2f}-{row['end'] + args.start:6.2f}  {row['performers']}  [{row['camera']}]")
            plan = data(await s.call_tool("sovereign_render_video", {"performance_id": pid}))
            print("plan:", plan)
            if args.render:
                done = data(await s.call_tool("sovereign_render_video", {"performance_id": pid, "confirm": True}))
                print("rendered:", done)
                print("exported:", data(await s.call_tool("sovereign_export_project", {
                    "performance_id": pid, "out_dir": str(work)})))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=75.0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--render", action="store_true")
    asyncio.run(main(ap.parse_args()))
