#!/usr/bin/env python3
"""Estimate peak VRAM for a ComfyUI workflow, before running it.

Motivation: on AiServerR9700 a render that exceeds the R9700's 32 GB spills into
host memory, and host RAM (30 GiB) is the same size as VRAM (29.8 GiB), so the
spill cannot fit and the process is OOM-killed mid-SVM-fault. See
docs/AMD_R9700_SVM_OOM_ANALYSIS.md. Checking a workflow against the budget
beforehand is cheaper than discovering it afterwards.

    python3 tools/estimate_vram.py backend/workflows/text_to_image.json
    python3 tools/estimate_vram.py --models-dir ~/ai/ComfyUI/models WORKFLOW...
    python3 tools/estimate_vram.py --all --budget 32
    python3 tools/estimate_vram.py --all --json

Accuracy, stated honestly:

* Model weights dominate and are the reliable part. With --models-dir the tool
  reads real file sizes off disk ("measured"). Without it, it falls back to a
  table of approximate published sizes ("approx"), and reports anything it
  cannot size at all as "unknown" -- in which case the total is a LOWER BOUND
  and is labelled as such.
* Latent tensors are computed exactly from the workflow's own width/height/
  batch/length and the latent geometry of the model family.
* Activation and VAE-decode peaks are crude multipliers, not measurements. They
  are deliberately conservative and are called out separately in the output so
  they are never mistaken for the weight figure.

Stdlib only. Reads nothing but the files named. Starts no GPU work.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

GIB = 1024 ** 3

# --- what occupies VRAM -----------------------------------------------------

# Loader class_type -> input fields that name a weights file.
WEIGHT_FIELDS: dict[str, tuple[str, ...]] = {
    "CheckpointLoaderSimple": ("ckpt_name",),
    "UNETLoader": ("unet_name",),
    "UnetLoaderGGUF": ("unet_name",),
    "VAELoader": ("vae_name",),
    "CLIPLoader": ("clip_name",),
    "DualCLIPLoader": ("clip_name1", "clip_name2"),
    "CLIPVisionLoader": ("clip_name",),
    "ControlNetLoader": ("control_net_name",),
    "LoraLoaderModelOnly": ("lora_name",),
    "LoraLoader": ("lora_name",),
    "LTXAVTextEncoderLoader": ("text_encoder",),
    "StyleModelLoader": ("style_model_name",),
    "UpscaleModelLoader": ("model_name",),
    "IPAdapterModelLoader": ("ipadapter_file",),
}

# ComfyUI model subdirectories to search when resolving a filename.
MODEL_SUBDIRS = (
    "checkpoints", "diffusion_models", "unet", "vae", "clip", "text_encoders",
    "clip_vision", "controlnet", "loras", "style_models", "upscale_models",
    "ipadapter",
)

# Latent geometry per family: (channels, spatial_divisor, temporal_divisor).
# A latent element is stored at 2 bytes (fp16/bf16) unless overridden.
LATENT_NODES: dict[str, tuple[int, int, int]] = {
    "EmptyLatentImage":      (4, 8, 1),    # SD1.5 / SDXL
    "EmptySD3LatentImage":   (16, 8, 1),   # SD3 / Flux / Qwen-Image family
    "EmptyFlux2LatentImage": (16, 8, 1),
    "EmptyLTXVLatentVideo":  (128, 32, 8),
    "LTXVImgToVideo":        (128, 32, 8),
    "WanImageToVideo":       (16, 8, 4),
    "WanInfiniteTalkToVideo": (16, 8, 4),
}

# Approximate published sizes in bytes, used ONLY when the file is not on disk.
# Always reported as "approx" so it is never confused with a measurement.
KNOWN_SIZES: dict[str, int] = {
    "sd_xl_base_1.0.safetensors": int(6.94 * GIB),
    "flux1-dev.safetensors": int(23.8 * GIB),
    "flux1-dev_fp8_scaled.safetensors": int(11.9 * GIB),
    "flux1-fill-dev.safetensors": int(23.8 * GIB),
    "flux1-krea-dev_fp8_scaled.safetensors": int(11.9 * GIB),
    "flux-2-klein-4b.safetensors": int(8.0 * GIB),
    "t5xxl_fp8_e4m3fn_scaled.safetensors": int(4.9 * GIB),
    "t5xxl_fp16.safetensors": int(9.8 * GIB),
    "clip_l.safetensors": int(0.25 * GIB),
    "ae.safetensors": int(0.33 * GIB),
    "flux2-vae.safetensors": int(0.33 * GIB),
    "qwen_image_vae.safetensors": int(0.25 * GIB),
    "qwen_3_4b.safetensors": int(8.0 * GIB),
    "qwen3vl_4b_fp8_scaled.safetensors": int(4.3 * GIB),
    "qwen_2.5_vl_7b_fp8_scaled.safetensors": int(7.5 * GIB),
    "llama_3.1_8b_instruct_fp8_scaled.safetensors": int(8.5 * GIB),
    "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors": int(2.5 * GIB),
    "control-openpose-sdxl-1.0.safetensors": int(2.5 * GIB),
    "v1-5-pruned-emaonly-fp16.safetensors": int(2.13 * GIB),
    "Illustrious-XL-v0.1.safetensors": int(6.9 * GIB),   # SDXL architecture
    "umt5_xxl_fp8_e4m3fn_scaled.safetensors": int(5.0 * GIB),
    "wan_2.1_vae.safetensors": int(0.25 * GIB),
}
# Deliberately absent: hidream-e1-full, krea2_turbo_fp8_scaled, z_image_turbo_bf16,
# NetaYumev35, the Qwen-Image-Edit GGUFs, gemma_3_12B_it_fp4_mixed and the LTX
# LoRA. Their sizes are not known here with enough confidence, and a wrong entry
# would produce a false "fits" verdict -- the one failure mode this tool must
# not have. They report as unknown, which makes the total an explicit lower
# bound. Pass --models-dir on the GPU host to size them for real.

# Crude non-weight multipliers. Documented, conservative, and reported apart
# from the weight figure so they cannot be mistaken for it.
ACTIVATION_FACTOR = 3.0      # x latent bytes, sampling-time working set
VAE_BYTES_PER_PIXEL = 512    # x W*H*batch, decoder feature maps at full res
VAE_TILING_THRESHOLD = 1536  # above this edge, recommend tiled VAE decode


def human(n: float) -> str:
    if n >= GIB:
        return f"{n / GIB:.2f} GiB"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.0f} MiB"
    return f"{int(n)} B"


# --- workflow inspection ----------------------------------------------------

def load_workflow(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("not an API-format workflow (expected a JSON object)")
    # API format maps node id -> {class_type, inputs}. The UI format has a
    # top-level "nodes" list and is not what the backend submits.
    if "nodes" in data and isinstance(data.get("nodes"), list):
        raise ValueError(
            "this is a UI-format workflow; export it in API format "
            "(ComfyUI: Workflow > Export (API))"
        )
    return data


def resolve_size(name: str, models_dir: Path | None) -> tuple[int | None, str]:
    """Return (bytes, provenance): measured / approx / placeholder / unknown."""
    # The backend substitutes __NAME__ tokens at submit time (e.g.
    # __VIDEO_MODEL__ from COMFYUI_VIDEO_MODEL_NAME). Not a missing file.
    if name.startswith("__") and name.endswith("__"):
        return None, "placeholder"
    if models_dir:
        direct = models_dir / name
        if direct.is_file():
            return direct.stat().st_size, "measured"
        for sub in MODEL_SUBDIRS:
            cand = models_dir / sub / name
            if cand.is_file():
                return cand.stat().st_size, "measured"
        # Some installs nest by family; fall back to a bounded search.
        for cand in models_dir.glob(f"*/*/{name}"):
            if cand.is_file():
                return cand.stat().st_size, "measured"
    if name in KNOWN_SIZES:
        return KNOWN_SIZES[name], "approx"
    return None, "unknown"


def collect_weights(wf: dict, models_dir: Path | None) -> list[dict]:
    seen: dict[str, dict] = {}
    for node in wf.values():
        if not isinstance(node, dict):
            continue
        fields = WEIGHT_FIELDS.get(node.get("class_type", ""))
        if not fields:
            continue
        inputs = node.get("inputs") or {}
        for f in fields:
            name = inputs.get(f)
            if not isinstance(name, str) or not name:
                continue
            if name in seen:          # loaded once, resident once
                continue
            size, prov = resolve_size(name, models_dir)
            seen[name] = {
                "file": name,
                "loader": node.get("class_type"),
                "bytes": size,
                "provenance": prov,
            }
    return sorted(seen.values(), key=lambda w: -(w["bytes"] or 0))


def collect_latents(wf: dict) -> list[dict]:
    out = []
    for nid, node in wf.items():
        if not isinstance(node, dict):
            continue
        geom = LATENT_NODES.get(node.get("class_type", ""))
        if not geom:
            continue
        ins = node.get("inputs") or {}
        w, h = ins.get("width"), ins.get("height")
        if not isinstance(w, int) or not isinstance(h, int):
            continue
        batch = ins.get("batch_size")
        batch = batch if isinstance(batch, int) and batch > 0 else 1
        frames = ins.get("length")
        frames = frames if isinstance(frames, int) and frames > 0 else 1
        ch, sdiv, tdiv = geom
        lw, lh = max(1, w // sdiv), max(1, h // sdiv)
        lf = max(1, ((frames - 1) // tdiv) + 1) if frames > 1 else 1
        elems = lw * lh * lf * ch * batch
        out.append({
            "node": nid, "class_type": node["class_type"],
            "width": w, "height": h, "batch": batch, "frames": frames,
            "latent_bytes": elems * 2,
            "pixel_count": w * h * batch * (frames if frames > 1 else 1),
        })
    return out


def steps_of(wf: dict) -> list[int]:
    s = []
    for node in wf.values():
        if isinstance(node, dict) and "steps" in (node.get("inputs") or {}):
            v = node["inputs"]["steps"]
            if isinstance(v, int):
                s.append(v)
    return s


def estimate(path: Path, models_dir: Path | None) -> dict:
    wf = load_workflow(path)
    weights = collect_weights(wf, models_dir)
    latents = collect_latents(wf)

    weight_bytes = sum(w["bytes"] or 0 for w in weights)
    unknown = [w["file"] for w in weights if w["provenance"] == "unknown"]
    placeholders = [w["file"] for w in weights if w["provenance"] == "placeholder"]
    approx = [w["file"] for w in weights if w["provenance"] == "approx"]

    # Worst single latent drives the peak; concurrent latents are rare and the
    # term is small next to weights.
    latent_bytes = max((l["latent_bytes"] for l in latents), default=0)
    pixels = max((l["pixel_count"] for l in latents), default=0)
    activation_bytes = int(latent_bytes * ACTIVATION_FACTOR)
    vae_bytes = pixels * VAE_BYTES_PER_PIXEL

    total = weight_bytes + latent_bytes + activation_bytes + vae_bytes
    max_edge = max((max(l["width"], l["height"]) for l in latents), default=0)

    return {
        "workflow": str(path),
        "weights": weights,
        "latents": latents,
        "steps": steps_of(wf),
        "weight_bytes": weight_bytes,
        "latent_bytes": latent_bytes,
        "activation_bytes": activation_bytes,
        "vae_bytes": vae_bytes,
        "total_bytes": total,
        "unknown_files": unknown,
        "placeholder_files": placeholders,
        "approx_files": approx,
        "lower_bound": bool(unknown) or bool(placeholders),
        "suggest_tiled_vae": max_edge > VAE_TILING_THRESHOLD,
    }


# --- reporting --------------------------------------------------------------

def report(e: dict, budget_gib: float) -> None:
    print(f"\n=== {e['workflow']} ===")
    if not e["weights"]:
        print("  no weight-loading nodes recognised "
              "(a mask/preview-only graph, or an unknown loader type)")
    for w in e["weights"]:
        size = human(w["bytes"]) if w["bytes"] is not None else "   ?    "
        flag = {
            "measured": "",
            "approx": "  (approx)",
            "placeholder": "  (runtime placeholder - excluded)",
            "unknown": "  (UNKNOWN - excluded)",
        }[w["provenance"]]
        print(f"  {size:>10}  {w['loader']:<24} {w['file']}{flag}")

    for l in e["latents"]:
        dims = f"{l['width']}x{l['height']}"
        if l["frames"] > 1:
            dims += f"x{l['frames']}f"
        if l["batch"] > 1:
            dims += f" batch={l['batch']}"
        print(f"  {human(l['latent_bytes']):>10}  latent {l['class_type']} {dims}")

    print(f"  {'-' * 58}")
    print(f"  {human(e['weight_bytes']):>10}  model weights"
          f"{'  (LOWER BOUND)' if e['lower_bound'] else ''}")
    print(f"  {human(e['latent_bytes']):>10}  latent tensors")
    print(f"  {human(e['activation_bytes']):>10}  activations     (x{ACTIVATION_FACTOR:g} latent, rough)")
    print(f"  {human(e['vae_bytes']):>10}  VAE decode peak ({VAE_BYTES_PER_PIXEL} B/px, rough)")
    print(f"  {human(e['total_bytes']):>10}  ESTIMATED PEAK")

    budget = budget_gib * GIB
    pct = e["total_bytes"] / budget * 100 if budget else 0
    if e["lower_bound"]:
        why = []
        if e["unknown_files"]:
            why.append("unsized weights")
        if e["placeholder_files"]:
            why.append("runtime-substituted model")
        verdict = "INDETERMINATE - " + " and ".join(why)
    elif e["total_bytes"] > budget:
        verdict = f"OVER BUDGET by {human(e['total_bytes'] - budget)}"
    elif pct > 85:
        verdict = f"TIGHT - {pct:.0f}% of budget"
    else:
        verdict = f"fits - {pct:.0f}% of budget"
    print(f"  budget {budget_gib:g} GiB -> {verdict}")

    if e["unknown_files"]:
        print("  unsized (add --models-dir to measure): "
              + ", ".join(e["unknown_files"]))
    if e["placeholder_files"]:
        print("  substituted at submit time, size unknowable from the graph: "
              + ", ".join(e["placeholder_files"]))
    if e["suggest_tiled_vae"]:
        print(f"  note: edge > {VAE_TILING_THRESHOLD}px - use a tiled VAE decode; "
              "full-frame decode is often the true peak")
    if e["steps"]:
        print(f"  steps in graph: {sorted(set(e['steps']))} "
              "(affects time, not peak VRAM)")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Estimate peak VRAM for ComfyUI workflows.")
    ap.add_argument("workflows", nargs="*", type=Path)
    ap.add_argument("--all", action="store_true",
                    help="every .json under backend/workflows/")
    ap.add_argument("--models-dir", type=Path, default=None,
                    help="ComfyUI models dir; enables real file sizes")
    ap.add_argument("--budget", type=float, default=32.0,
                    help="VRAM budget in GiB (default 32, the R9700)")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)

    paths = list(args.workflows)
    if args.all:
        root = Path(__file__).resolve().parent.parent / "backend" / "workflows"
        paths += sorted(root.glob("*.json"))
    if not paths:
        ap.error("name at least one workflow, or pass --all")

    if args.models_dir and not args.models_dir.is_dir():
        print(f"[warn] --models-dir not found: {args.models_dir}; "
              "falling back to approximate sizes", file=sys.stderr)
        args.models_dir = None
    if not args.models_dir:
        print("[warn] no --models-dir: weights use approximate published sizes "
              "where known. Pass it on the GPU host for real figures.",
              file=sys.stderr)

    results, failed = [], 0
    for p in paths:
        try:
            results.append(estimate(p, args.models_dir))
        except Exception as exc:  # noqa: BLE001 - report and continue
            failed += 1
            print(f"[error] {p}: {exc}", file=sys.stderr)

    if args.as_json:
        print(json.dumps(results, indent=2))
        return 1 if failed else 0

    for e in results:
        report(e, args.budget)

    over = [e for e in results if not e["lower_bound"]
            and e["total_bytes"] > args.budget * GIB]
    indet = [e for e in results if e["lower_bound"]]
    print(f"\n=== {len(results)} workflow(s): {len(over)} over a "
          f"{args.budget:g} GiB budget, {len(indet)} indeterminate ===")
    for e in over:
        print(f"  OVER  {human(e['total_bytes'])}  {Path(e['workflow']).name}")
    return 1 if (over or failed) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
