#!/usr/bin/env python3
"""Estimate ComfyUI workflow VRAM, keeping four different quantities apart.

The four are deliberately never collapsed into one number, because conflating
them is exactly how this tool produced a wrong answer once already:

  1. DISK BYTES        what the file occupies on disk. Measurable.
  2. REQUESTED DTYPE   the precision the graph asks the loader for
                       (UNETLoader's `weight_dtype`). Read from the graph.
  3. EST. RESIDENT     weights held in VRAM, derived from 1 and 2.
                       An ESTIMATE, never a measurement.
  4. PEAK              residency plus activations and VAE decode.
                       UNMEASURED. Crude multipliers, reported separately.

Disk size does not prove runtime residency. A bf16 checkpoint requested at
`fp8_e4m3fn` occupies roughly half its disk size in VRAM. When the real file is
available (--models-dir) this tool reads the safetensors header -- a few KB, no
weights loaded -- to get the exact on-disk dtype composition, then applies the
requested dtype to estimate residency.

    python3 tools/estimate_vram.py backend/workflows/text_to_image.json
    python3 tools/estimate_vram.py --all --models-dir ~/ai/ComfyUI/models
    python3 tools/estimate_vram.py --all --budget 32 --json

Peak is not a prediction of what the GPU will report. Allocator overhead,
fragmentation, tiling behaviour and concurrent jobs are all outside the model.
Treat it as a screen for "obviously will not fit", not as a budget guarantee.

Stdlib only. Reads only the files named. Starts no GPU work.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

GIB = 1024 ** 3

# Loader class_type -> (weight-file fields, dtype field or None)
LOADERS: dict[str, tuple[tuple[str, ...], str | None]] = {
    "CheckpointLoaderSimple": (("ckpt_name",), None),
    "UNETLoader": (("unet_name",), "weight_dtype"),
    "UnetLoaderGGUF": (("unet_name",), None),
    "VAELoader": (("vae_name",), None),
    "CLIPLoader": (("clip_name",), None),
    "DualCLIPLoader": (("clip_name1", "clip_name2"), None),
    "CLIPVisionLoader": (("clip_name",), None),
    "ControlNetLoader": (("control_net_name",), None),
    "LoraLoaderModelOnly": (("lora_name",), None),
    "LoraLoader": (("lora_name",), None),
    "LTXAVTextEncoderLoader": (("text_encoder",), None),
    "StyleModelLoader": (("style_model_name",), None),
    "UpscaleModelLoader": (("model_name",), None),
    "IPAdapterModelLoader": (("ipadapter_file",), None),
}

MODEL_SUBDIRS = (
    "checkpoints", "diffusion_models", "unet", "vae", "clip", "text_encoders",
    "clip_vision", "controlnet", "loras", "style_models", "upscale_models",
    "ipadapter",
)

# safetensors dtype -> bytes per element
DTYPE_BYTES = {
    "F64": 8, "I64": 8, "U64": 8,
    "F32": 4, "I32": 4, "U32": 4,
    "F16": 2, "BF16": 2, "I16": 2, "U16": 2,
    "F8_E4M3": 1, "F8_E5M2": 1, "I8": 1, "U8": 1, "BOOL": 1,
}

# What a requested weight_dtype costs per element. None = keep on-disk dtype.
REQUESTED_BYTES = {
    "default": None,
    "fp8_e4m3fn": 1,
    "fp8_e4m3fn_fast": 1,
    "fp8_e5m2": 1,
}

LATENT_NODES: dict[str, tuple[int, int, int]] = {
    "EmptyLatentImage":       (4, 8, 1),
    "EmptySD3LatentImage":    (16, 8, 1),
    "EmptyFlux2LatentImage":  (16, 8, 1),
    "EmptyLTXVLatentVideo":   (128, 32, 8),
    "LTXVImgToVideo":         (128, 32, 8),
    "WanImageToVideo":        (16, 8, 4),
    "WanInfiniteTalkToVideo": (16, 8, 4),
}

# Approximate DISK sizes, used only when the file is absent. Reported "approx".
# Confirmed against the real install where noted.
KNOWN_DISK_SIZES: dict[str, int] = {
    # Codex measured on AiServerR9700: 22.17 GiB of BF16 tensors.
    "flux1-dev.safetensors": int(22.17 * GIB),
    "sd_xl_base_1.0.safetensors": int(6.94 * GIB),
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
    "Illustrious-XL-v0.1.safetensors": int(6.9 * GIB),
    "umt5_xxl_fp8_e4m3fn_scaled.safetensors": int(5.0 * GIB),
    "wan_2.1_vae.safetensors": int(0.25 * GIB),
}
# Deliberately absent: hidream-e1-full, krea2_turbo_fp8_scaled, z_image_turbo_bf16,
# NetaYumev35, the Qwen-Image-Edit GGUFs, gemma_3_12B_it_fp4_mixed, the LTX LoRA.
# A wrong entry would produce a false "fits", the one failure this tool must not
# have. They report unknown, which makes the figure an explicit lower bound.

ACTIVATION_FACTOR = 3.0
VAE_BYTES_PER_PIXEL = 512
VAE_TILING_THRESHOLD = 1536


def human(n: float | None) -> str:
    if n is None:
        return "?"
    if n >= GIB:
        return f"{n / GIB:.2f} GiB"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.0f} MiB"
    return f"{int(n)} B"


# --- safetensors header ------------------------------------------------------

def read_safetensors_dtypes(path: Path) -> dict[str, int] | None:
    """{dtype: element_count} from the header alone. No weights are loaded."""
    try:
        with path.open("rb") as fh:
            raw = fh.read(8)
            if len(raw) < 8:
                return None
            hlen = struct.unpack("<Q", raw)[0]
            if not (0 < hlen <= 100 * 1024 * 1024):
                return None
            header = json.loads(fh.read(hlen).decode("utf-8"))
    except Exception:  # noqa: BLE001 - unreadable or not safetensors
        return None
    counts: dict[str, int] = {}
    for key, meta in header.items():
        if key == "__metadata__" or not isinstance(meta, dict):
            continue
        dtype, shape = meta.get("dtype"), meta.get("shape")
        if not isinstance(dtype, str) or not isinstance(shape, list):
            continue
        n = 1
        for d in shape:
            if not isinstance(d, int):
                n = 0
                break
            n *= d
        if n:
            counts[dtype] = counts.get(dtype, 0) + n
    return counts or None


def resident_from_dtypes(counts: dict[str, int], requested: int | None) -> int:
    """Bytes held in VRAM, honouring a requested per-element width."""
    total = 0
    for dtype, n in counts.items():
        on_disk = DTYPE_BYTES.get(dtype, 2)
        # A request only narrows; it never widens a tensor that is already smaller.
        width = min(on_disk, requested) if requested else on_disk
        total += n * width
    return total


# --- workflow inspection -----------------------------------------------------

def load_workflow(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("not an API-format workflow (expected a JSON object)")
    if isinstance(data.get("nodes"), list):
        raise ValueError("this is a UI-format workflow; export API format "
                         "(ComfyUI: Workflow > Export (API))")
    return data


def find_file(name: str, models_dir: Path | None) -> Path | None:
    if not models_dir:
        return None
    if (models_dir / name).is_file():
        return models_dir / name
    for sub in MODEL_SUBDIRS:
        if (models_dir / sub / name).is_file():
            return models_dir / sub / name
    for cand in models_dir.glob(f"*/*/{name}"):
        if cand.is_file():
            return cand
    return None


def collect_weights(wf: dict, models_dir: Path | None) -> list[dict]:
    seen: dict[str, dict] = {}
    for node in wf.values():
        if not isinstance(node, dict):
            continue
        spec = LOADERS.get(node.get("class_type", ""))
        if not spec:
            continue
        fields, dtype_field = spec
        ins = node.get("inputs") or {}
        requested_name = ins.get(dtype_field) if dtype_field else None
        for f in fields:
            name = ins.get(f)
            if not isinstance(name, str) or not name:
                continue
            if name in seen:
                continue

            if name.startswith("__") and name.endswith("__"):
                seen[name] = dict(file=name, loader=node["class_type"],
                                  disk=None, resident=None, provenance="placeholder",
                                  requested=requested_name, dtypes=None)
                continue

            path = find_file(name, models_dir)
            dtypes = read_safetensors_dtypes(path) if path else None
            requested_width = REQUESTED_BYTES.get(requested_name or "default")

            if path:
                disk = path.stat().st_size
                if dtypes:
                    resident = resident_from_dtypes(dtypes, requested_width)
                    prov = "measured"
                else:
                    # GGUF or an unparsable container: dequantisation behaviour
                    # is not modelled, so do not pretend to know residency.
                    disk, resident, prov = disk, None, "measured-disk-only"
            elif name in KNOWN_DISK_SIZES:
                disk = KNOWN_DISK_SIZES[name]
                # Without a header we cannot know the dtype mix. Assume 2 bytes
                # per element, which is right for bf16/fp16 checkpoints.
                resident = disk // 2 if requested_width == 1 else disk
                prov = "approx"
            else:
                disk, resident, prov = None, None, "unknown"

            seen[name] = dict(file=name, loader=node["class_type"], disk=disk,
                              resident=resident, provenance=prov,
                              requested=requested_name, dtypes=dtypes)
    return sorted(seen.values(), key=lambda w: -(w["resident"] or w["disk"] or 0))


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
        out.append(dict(node=nid, class_type=node["class_type"], width=w, height=h,
                        batch=batch, frames=frames,
                        latent_bytes=lw * lh * lf * ch * batch * 2,
                        pixel_count=w * h * batch * (frames if frames > 1 else 1)))
    return out


def estimate(path: Path, models_dir: Path | None) -> dict:
    wf = load_workflow(path)
    weights = collect_weights(wf, models_dir)
    latents = collect_latents(wf)

    disk_total = sum(w["disk"] or 0 for w in weights)
    resident_total = sum(w["resident"] or 0 for w in weights)
    unsized = [w["file"] for w in weights
               if w["provenance"] in ("unknown", "measured-disk-only")]
    placeholders = [w["file"] for w in weights if w["provenance"] == "placeholder"]

    latent_bytes = max((l["latent_bytes"] for l in latents), default=0)
    pixels = max((l["pixel_count"] for l in latents), default=0)
    activation_bytes = int(latent_bytes * ACTIVATION_FACTOR)
    vae_bytes = pixels * VAE_BYTES_PER_PIXEL
    peak = resident_total + latent_bytes + activation_bytes + vae_bytes
    max_edge = max((max(l["width"], l["height"]) for l in latents), default=0)

    return dict(workflow=str(path), weights=weights, latents=latents,
                disk_bytes=disk_total, resident_bytes=resident_total,
                latent_bytes=latent_bytes, activation_bytes=activation_bytes,
                vae_bytes=vae_bytes, peak_bytes=peak,
                unsized_files=unsized, placeholder_files=placeholders,
                lower_bound=bool(unsized or placeholders),
                any_measured=any(w["provenance"] == "measured" for w in weights),
                suggest_tiled_vae=max_edge > VAE_TILING_THRESHOLD)


# --- reporting ---------------------------------------------------------------

FLAGS = {
    "measured": "",
    "measured-disk-only": "  (disk measured; residency NOT modelled)",
    "approx": "  (approx disk size)",
    "placeholder": "  (runtime placeholder - excluded)",
    "unknown": "  (UNKNOWN - excluded)",
}


def report(e: dict, budget_gib: float) -> None:
    print(f"\n=== {e['workflow']} ===")
    if not e["weights"]:
        print("  no weight-loading nodes recognised")
    else:
        print(f"  {'disk':>10}  {'resident':>10}  requested     loader / file")
    for w in e["weights"]:
        req = w["requested"] or "-"
        mix = ""
        if w["dtypes"]:
            mix = " [" + ",".join(sorted(w["dtypes"])) + "]"
        print(f"  {human(w['disk']):>10}  {human(w['resident']):>10}  "
              f"{req:<12}  {w['loader']} {w['file']}{mix}{FLAGS[w['provenance']]}")

    for l in e["latents"]:
        dims = f"{l['width']}x{l['height']}"
        if l["frames"] > 1:
            dims += f"x{l['frames']}f"
        if l["batch"] > 1:
            dims += f" batch={l['batch']}"
        print(f"  {'':>10}  {human(l['latent_bytes']):>10}  "
              f"{'latent':<12}  {l['class_type']} {dims}")

    print(f"  {'-' * 66}")
    print(f"  {human(e['disk_bytes']):>10}  {'':>10}  on disk")
    print(f"  {'':>10}  {human(e['resident_bytes']):>10}  EST. RESIDENT weights"
          f"{'  (LOWER BOUND)' if e['lower_bound'] else ''}")
    print(f"  {'':>10}  {human(e['latent_bytes']):>10}  latent tensors")
    print(f"  {'':>10}  {human(e['activation_bytes']):>10}  activations "
          f"(x{ACTIVATION_FACTOR:g} latent, UNMEASURED)")
    print(f"  {'':>10}  {human(e['vae_bytes']):>10}  VAE decode "
          f"({VAE_BYTES_PER_PIXEL} B/px, UNMEASURED)")
    print(f"  {'':>10}  {human(e['peak_bytes']):>10}  EST. PEAK")

    budget = budget_gib * GIB
    pct = e["peak_bytes"] / budget * 100 if budget else 0
    if e["lower_bound"]:
        why = []
        if e["unsized_files"]:
            why.append("unmodelled weights")
        if e["placeholder_files"]:
            why.append("runtime-substituted model")
        verdict = "INDETERMINATE - " + " and ".join(why)
    elif e["peak_bytes"] > budget:
        verdict = f"OVER BUDGET by {human(e['peak_bytes'] - budget)}"
    elif pct > 85:
        verdict = f"TIGHT - {pct:.0f}% of budget"
    else:
        verdict = f"fits - {pct:.0f}% of budget"
    print(f"  budget {budget_gib:g} GiB -> {verdict}")

    if not e["any_measured"] and e["weights"]:
        print("  NOTE: no file was read. Residency is inferred from approximate "
              "disk sizes; pass --models-dir on the GPU host.")
    if e["unsized_files"]:
        print("  not modelled: " + ", ".join(e["unsized_files"]))
    if e["placeholder_files"]:
        print("  substituted at submit time: " + ", ".join(e["placeholder_files"]))
    if e["suggest_tiled_vae"]:
        print(f"  note: edge > {VAE_TILING_THRESHOLD}px - use a tiled VAE decode")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("workflows", nargs="*", type=Path)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--workflows-dir", type=Path, default=None,
                    help="where the workflow .json files are; only needed with "
                         "--all when this script is run from outside the repo")
    ap.add_argument("--models-dir", type=Path, default=None)
    ap.add_argument("--budget", type=float, default=32.0)
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)

    paths = list(args.workflows)
    if args.all:
        # This script is often copied out of the repo, so do not assume its own
        # location implies where the workflows are.
        candidates = []
        if args.workflows_dir:
            candidates.append(args.workflows_dir)
        candidates += [
            Path(__file__).resolve().parent.parent / "backend" / "workflows",
            Path.cwd() / "backend" / "workflows",
            Path.cwd() / "workflows",
            Path.cwd(),
        ]
        root = next((c for c in candidates
                     if c.is_dir() and any(c.glob("*.json"))), None)
        if root is None:
            ap.error("--all found no workflow .json files. Tried: "
                     + ", ".join(str(c) for c in candidates)
                     + ". Pass --workflows-dir.")
        print(f"[info] workflows: {root}", file=sys.stderr)
        paths += sorted(root.glob("*.json"))
    if not paths:
        ap.error("name at least one workflow, or pass --all")

    if args.models_dir and not args.models_dir.is_dir():
        print(f"[warn] --models-dir not found: {args.models_dir}", file=sys.stderr)
        args.models_dir = None
    if not args.models_dir:
        print("[warn] no --models-dir: residency is inferred from approximate "
              "disk sizes, not read from file headers.", file=sys.stderr)

    results, failed = [], 0
    for p in paths:
        try:
            results.append(estimate(p, args.models_dir))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"[error] {p}: {exc}", file=sys.stderr)

    if args.as_json:
        print(json.dumps(results, indent=2))
        return 1 if failed else 0

    for e in results:
        report(e, args.budget)

    over = [e for e in results
            if not e["lower_bound"] and e["peak_bytes"] > args.budget * GIB]
    indet = [e for e in results if e["lower_bound"]]
    print(f"\n=== {len(results)} workflow(s): {len(over)} over a "
          f"{args.budget:g} GiB budget, {len(indet)} indeterminate ===")
    for e in over:
        print(f"  OVER  {human(e['peak_bytes'])}  {Path(e['workflow']).name}")
    print("EST. PEAK is a screen, not a guarantee: allocator overhead, "
          "fragmentation and concurrent jobs are outside the model.")
    return 1 if (over or failed) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
