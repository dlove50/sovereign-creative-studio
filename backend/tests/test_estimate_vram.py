"""Tests for tools/estimate_vram.py.

The tool's job is to be trustworthy about VRAM, and its risky parts are two
binary header parsers (safetensors and GGUF) plus the dtype arithmetic layered
on them. Those fail silently when they regress, so they are pinned here.

An earlier version of the tool ignored UNETLoader's `weight_dtype` and reported
disk size as runtime residency, which produced a confidently wrong conclusion.
The dtype tests below exist specifically to stop that recurring.

Nothing here touches the app, the database or a GPU; all fixtures are synthetic
files built in tmp_path.
"""
from __future__ import annotations

import importlib.util
import json
import os
import struct
from pathlib import Path

import pytest

_TOOL = Path(__file__).resolve().parents[2] / "tools" / "estimate_vram.py"

GIB = 1024 ** 3


def _load_tool():
    spec = importlib.util.spec_from_file_location("estimate_vram", _TOOL)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ev = _load_tool()


# --- fixture builders --------------------------------------------------------

def write_safetensors(path: Path, tensors: dict[str, tuple[str, int]]) -> Path:
    """tensors: {name: (dtype, element_count)}. Header-valid; data is sparse."""
    header: dict = {}
    offset = 0
    for name, (dtype, n) in tensors.items():
        nbytes = n * ev.DTYPE_BYTES[dtype]
        header[name] = {"dtype": dtype, "shape": [n],
                        "data_offsets": [offset, offset + nbytes]}
        offset += nbytes
    raw = json.dumps(header).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        fh.write(struct.pack("<Q", len(raw)))
        fh.write(raw)
    os.truncate(path, 8 + len(raw) + offset)
    return path


def _gstr(b: bytes) -> bytes:
    return struct.pack("<Q", len(b)) + b


def write_gguf(path: Path, tensors: list[tuple[str, int, int]], *,
               metadata: bytes = b"", n_kv: int = 0) -> Path:
    """tensors: [(name, element_count, ggml_type_id)]."""
    body = b"GGUF" + struct.pack("<I", 3)
    body += struct.pack("<QQ", len(tensors), n_kv) + metadata
    offset = 0
    for name, n, tid in tensors:
        body += _gstr(name.encode()) + struct.pack("<I", 1) + struct.pack("<Q", n)
        body += struct.pack("<I", tid) + struct.pack("<Q", offset)
        offset += n
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    os.truncate(path, len(body) + 4096)
    return path


def workflow(path: Path, nodes: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(nodes), encoding="utf-8")
    return path


# --- safetensors header ------------------------------------------------------

def test_safetensors_header_reports_dtype_element_counts(tmp_path):
    f = write_safetensors(tmp_path / "m.safetensors",
                          {"a": ("BF16", 1000), "b": ("BF16", 500), "c": ("F32", 10)})
    assert ev.read_safetensors_dtypes(f) == {"BF16": 1500, "F32": 10}


def test_safetensors_rejects_garbage_and_truncation(tmp_path):
    garbage = tmp_path / "g.safetensors"
    garbage.write_bytes(b"not a safetensors file at all")
    assert ev.read_safetensors_dtypes(garbage) is None

    truncated = tmp_path / "t.safetensors"
    truncated.write_bytes(struct.pack("<Q", 4096))  # claims a header, has none
    assert ev.read_safetensors_dtypes(truncated) is None

    empty = tmp_path / "e.safetensors"
    empty.write_bytes(b"")
    assert ev.read_safetensors_dtypes(empty) is None


# --- dtype arithmetic: the regression this tool got wrong once ---------------

def test_no_requested_dtype_keeps_on_disk_width():
    counts = {"BF16": 1_000_000}
    assert ev.resident_from_dtypes(counts, None) == 2_000_000


def test_fp8_request_narrows_bf16_to_one_byte():
    counts = {"BF16": 1_000_000}
    assert ev.resident_from_dtypes(counts, 1) == 1_000_000


def test_request_never_widens_an_already_smaller_dtype():
    # An fp8 encoder must not be charged 1 byte twice, nor inflated.
    assert ev.resident_from_dtypes({"F8_E4M3": 1_000_000}, 1) == 1_000_000
    # And a narrow request must not somehow enlarge it.
    assert ev.resident_from_dtypes({"F8_E4M3": 1_000_000}, 2) == 1_000_000


def test_mixed_precision_file_is_summed_per_dtype():
    counts = {"BF16": 1000, "F32": 1000, "F8_E4M3": 1000}
    assert ev.resident_from_dtypes(counts, None) == 1000 * (2 + 4 + 1)
    # fp8 requested: every tensor is capped at one byte per element.
    assert ev.resident_from_dtypes(counts, 1) == 3000


# --- GGUF header -------------------------------------------------------------

def test_gguf_quantised_byte_math_is_exact(tmp_path):
    # Q4_K is 256 elements per 144-byte block.
    elems = 256 * 1000
    f = write_gguf(tmp_path / "m.gguf", [("blk", elems, 12)])
    assert ev.read_gguf_tensors(f) == {"Q4_K": 1000 * 144}


def test_gguf_skips_metadata_including_nested_arrays(tmp_path):
    meta = (_gstr(b"general.architecture") + struct.pack("<I", 8) + _gstr(b"flux")
            + _gstr(b"n") + struct.pack("<I", 4) + struct.pack("<I", 7)
            + _gstr(b"toks") + struct.pack("<I", 9)
            + struct.pack("<IQ", 8, 3) + _gstr(b"a") + _gstr(b"bb") + _gstr(b"ccc"))
    f = write_gguf(tmp_path / "m.gguf", [("blk", 256, 12)],
                   metadata=meta, n_kv=3)
    assert ev.read_gguf_tensors(f) == {"Q4_K": 144}


def test_gguf_refuses_unknown_quantisation_rather_than_guessing(tmp_path):
    f = write_gguf(tmp_path / "m.gguf", [("blk", 256, 999)])
    assert ev.read_gguf_tensors(f) is None


def test_gguf_survives_deeply_nested_metadata(tmp_path):
    # Nested arrays recurse; a hostile file must not crash the tool.
    depth = 2000
    meta = _gstr(b"deep") + struct.pack("<I", 9)
    for _ in range(depth):
        meta += struct.pack("<IQ", 9, 1)
    meta += struct.pack("<IQ", 8, 1) + _gstr(b"x")
    f = write_gguf(tmp_path / "deep.gguf", [("blk", 256, 12)],
                   metadata=meta, n_kv=1)
    assert ev.read_gguf_tensors(f) in (None, {"Q4_K": 144})  # must not raise


def test_gguf_rejects_non_gguf_file(tmp_path):
    f = tmp_path / "x.gguf"
    f.write_bytes(b"GGUB" + b"\x00" * 64)
    assert ev.read_gguf_tensors(f) is None


# --- filename case sensitivity ----------------------------------------------

def test_exact_case_match_is_reported_as_exact(tmp_path):
    write_safetensors(tmp_path / "unet" / "Model.safetensors", {"a": ("BF16", 8)})
    path, exact = ev.find_file("Model.safetensors", tmp_path)
    assert path is not None and exact is True


def test_case_only_match_is_flagged_not_silently_accepted(tmp_path):
    write_safetensors(tmp_path / "unet" / "Model.safetensors", {"a": ("BF16", 8)})
    path, exact = ev.find_file("model.safetensors", tmp_path)
    assert path is not None, "a case-only match should still be located"
    assert exact is False, "and must be reported as inexact"


def test_absent_file_is_not_a_case_mismatch(tmp_path):
    (tmp_path / "unet").mkdir(parents=True)
    path, exact = ev.find_file("nope.safetensors", tmp_path)
    assert path is None and exact is True


# --- workflow parsing --------------------------------------------------------

def test_ui_format_workflow_is_rejected_with_guidance(tmp_path):
    f = workflow(tmp_path / "ui.json", {"nodes": [{"id": 1}], "links": []})
    with pytest.raises(ValueError, match="API format"):
        ev.load_workflow(f)


def test_runtime_placeholder_is_distinguished_from_a_missing_file(tmp_path):
    f = workflow(tmp_path / "w.json", {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": "__VIDEO_MODEL__"}}})
    e = ev.estimate(f, None)
    assert e["placeholder_files"] == ["__VIDEO_MODEL__"]
    assert e["unsized_files"] == []
    assert e["lower_bound"] is True


def test_weight_dtype_flows_from_the_graph_into_residency(tmp_path):
    models = tmp_path / "models"
    write_safetensors(models / "unet" / "big.safetensors", {"w": ("BF16", 1_000_000)})
    f = workflow(tmp_path / "w.json", {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": "big.safetensors",
                         "weight_dtype": "fp8_e4m3fn"}}})
    e = ev.estimate(f, models)
    assert e["disk_bytes"] >= 2_000_000           # bf16 on disk
    assert e["resident_bytes"] == 1_000_000       # fp8 requested -> halved
    assert e["lower_bound"] is False


def test_default_weight_dtype_keeps_full_width(tmp_path):
    models = tmp_path / "models"
    write_safetensors(models / "unet" / "big.safetensors", {"w": ("BF16", 1_000_000)})
    f = workflow(tmp_path / "w.json", {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": "big.safetensors", "weight_dtype": "default"}}})
    assert ev.estimate(f, models)["resident_bytes"] == 2_000_000


def test_a_model_loaded_twice_is_counted_once(tmp_path):
    models = tmp_path / "models"
    write_safetensors(models / "vae" / "v.safetensors", {"w": ("F32", 1000)})
    f = workflow(tmp_path / "w.json", {
        "1": {"class_type": "VAELoader", "inputs": {"vae_name": "v.safetensors"}},
        "2": {"class_type": "VAELoader", "inputs": {"vae_name": "v.safetensors"}}})
    assert ev.estimate(f, models)["resident_bytes"] == 4000


# --- latent geometry ---------------------------------------------------------

@pytest.mark.parametrize("class_type,inputs,expected", [
    # SD/SDXL: 4 channels, /8, fp16 -> (1024/8)^2 * 4 * 2
    ("EmptyLatentImage", {"width": 1024, "height": 1024, "batch_size": 1},
     (1024 // 8) ** 2 * 4 * 2),
    # SD3/Flux: 16 channels
    ("EmptySD3LatentImage", {"width": 1024, "height": 1024, "batch_size": 1},
     (1024 // 8) ** 2 * 16 * 2),
    # batch multiplies
    ("EmptyLatentImage", {"width": 512, "height": 512, "batch_size": 4},
     (512 // 8) ** 2 * 4 * 2 * 4),
    # Wan video: 16ch, /8 spatial, /4 temporal -> ((49-1)//4)+1 = 13 frames
    ("WanImageToVideo", {"width": 640, "height": 640, "length": 49, "batch_size": 1},
     (640 // 8) ** 2 * 13 * 16 * 2),
])
def test_latent_geometry_per_model_family(tmp_path, class_type, inputs, expected):
    f = workflow(tmp_path / "w.json", {"1": {"class_type": class_type,
                                             "inputs": inputs}})
    assert ev.estimate(f, None)["latent_bytes"] == expected


def test_peak_is_resident_plus_latent_activation_and_vae(tmp_path):
    models = tmp_path / "models"
    write_safetensors(models / "unet" / "m.safetensors", {"w": ("BF16", 1000)})
    f = workflow(tmp_path / "w.json", {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
        "2": {"class_type": "EmptyLatentImage",
              "inputs": {"width": 64, "height": 64, "batch_size": 1}}})
    e = ev.estimate(f, models)
    assert e["peak_bytes"] == (e["resident_bytes"] + e["latent_bytes"]
                               + e["activation_bytes"] + e["vae_bytes"])
    assert e["activation_bytes"] == int(e["latent_bytes"] * ev.ACTIVATION_FACTOR)
    assert e["vae_bytes"] == 64 * 64 * ev.VAE_BYTES_PER_PIXEL


# --- the repo's real workflows ----------------------------------------------

def test_every_shipped_workflow_is_parseable_or_explicitly_rejected():
    root = Path(__file__).resolve().parents[2] / "backend" / "workflows"
    files = sorted(root.glob("*.json"))
    assert files, "no workflows found; path assumption is wrong"
    for f in files:
        e = ev.estimate(f, None)          # must not raise
        assert e["peak_bytes"] >= 0
        assert isinstance(e["lower_bound"], bool)


def test_no_shipped_workflow_has_a_case_colliding_model_filename():
    """Two filenames differing only by case load on Windows and break on Linux."""
    import re
    root = Path(__file__).resolve().parents[2] / "backend" / "workflows"
    seen: dict[str, str] = {}
    for f in sorted(root.glob("*.json")):
        for name in re.findall(
                r'"([A-Za-z0-9_.\-]+\.(?:safetensors|gguf|ckpt|pt|bin))"',
                f.read_text(encoding="utf-8")):
            key = name.lower()
            if key in seen and seen[key] != name:
                pytest.fail(
                    f"model filenames differ only by case: {seen[key]!r} vs "
                    f"{name!r} (in {f.name}). Windows resolves both; a "
                    f"case-sensitive filesystem will not.")
            seen[key] = name
