"""Film Studio routing policy: transformation-first.

Transform Mode -> Qwen Image Edit (default). Preserve Mode -> Flux Kontext
(explicit only). Pose Mode -> SDXL+OpenPose -> Qwen refine. No live ComfyUI
required: these check factory routing, workflow templates, Workflow Manager
availability (Qwen-missing messaging), and schema/API acceptance.
"""
import json
import os
import tempfile

_TMP = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(_TMP, 'test.db')}")
os.environ.setdefault("STORAGE_DIR", os.path.join(_TMP, "storage"))
os.environ.setdefault("GENERATOR_BACKEND", "mock")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.config as config  # noqa: E402
import app.product_scene_generators as scene_generators  # noqa: E402
from app.main import app  # noqa: E402
from app.pose_assets import ensure_pose_presets  # noqa: E402
from app.product_scene_generators.comfyui import (  # noqa: E402
    ComfyUIProductSceneGenerator,
)
from app.services import workflow_manager  # noqa: E402

TRANSFORM_MODES = [
    "creative_edit",
    "character_reimagination",
    "fashion_transformation",
    "cinematic_scene_builder",
    "film_scene",
]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _gen(mode, monkeypatch):
    monkeypatch.setattr(scene_generators, "PRODUCT_SCENE_BACKEND", "comfyui")
    return scene_generators.get_product_scene_generator(mode)


# --- Transform Mode routes to Qwen (no silent Flux) --------------------------
def test_transform_modes_route_to_qwen_gguf_by_default(monkeypatch):
    monkeypatch.setattr(config, "CREATIVE_QWEN_PRECISION", "gguf")
    for mode in TRANSFORM_MODES:
        gen = _gen(mode, monkeypatch)
        assert isinstance(gen, ComfyUIProductSceneGenerator)
        assert str(gen.workflow_path).endswith("product_scene_creative_qwen_edit.json")
        # model_key forces Qwen validation -> clear error if Qwen missing.
        assert gen.model_key == "qwen-image-gguf"
        # No silent Flux fallback for any transform mode.
        assert "creative_fashion_edit" not in str(gen.workflow_path)


def test_transform_precision_fp8_selects_fp8_workflow(monkeypatch):
    monkeypatch.setattr(config, "CREATIVE_QWEN_PRECISION", "fp8")
    gen = _gen("creative_edit", monkeypatch)
    assert str(gen.workflow_path).endswith("product_scene_creative_qwen_edit_fp8.json")
    assert gen.model_key == "qwen-image"


# --- Preserve Mode stays on Flux / composite (explicit only) -----------------
def test_preserve_mode_still_uses_flux(monkeypatch):
    gen = _gen("creative_fashion_edit", monkeypatch)
    assert str(gen.workflow_path).endswith("product_scene_creative_fashion_edit.json")
    assert gen.model_key == ""


def test_segmented_composite_polished_unchanged(monkeypatch):
    gen = _gen("segmented_composite_polished", monkeypatch)
    assert str(gen.workflow_path).endswith(
        "product_scene_segmented_composite_polished.json"
    )


# --- Clothing & Style Edit: dedicated targeted-edit workflow -----------------
def test_clothing_style_edit_routes_to_dedicated_workflow(monkeypatch):
    gen = _gen("clothing_style_edit", monkeypatch)
    assert str(gen.workflow_path).endswith("product_scene_clothing_style_edit.json")
    assert gen.model_key == "qwen-image-gguf"


def test_clothing_workflow_uses_plus_and_negative():
    workflow = json.loads(
        (
            config.BASE_DIR / "workflows" / "product_scene_clothing_style_edit.json"
        ).read_text(encoding="utf-8")
    )
    classes = [n.get("class_type") for n in workflow.values()]
    # Uses the Plus encoder, twice (positive + a real negative), with CLIPLoader.
    assert classes.count("TextEncodeQwenImageEditPlus") == 2
    assert "CLIPLoader" in classes
    # The negative node carries anti-duplication / anti-drift language.
    neg = [
        n["inputs"]["prompt"]
        for n in workflow.values()
        if n.get("class_type") == "TextEncodeQwenImageEditPlus"
        and "__PROMPT__" not in n["inputs"]["prompt"]
    ]
    assert neg and "duplicate person" in neg[0] and "changing the shirt" in neg[0]


def test_clothing_style_edit_unavailable_without_qwen():
    av = workflow_manager._scene_mode_availability({})
    available, reason = av["clothing_style_edit"]
    assert available is False and "Qwen not installed" in reason


# --- Masked Attribute Editor -------------------------------------------------
def test_attribute_edit_routes_to_masked_workflow(monkeypatch):
    gen = _gen("attribute_edit", monkeypatch)
    assert str(gen.workflow_path).endswith("product_scene_masked_attribute_edit.json")
    assert gen.model_key == "qwen-image-gguf-masked"


def test_masked_workflow_regenerates_only_inside_mask():
    workflow = json.loads(
        (
            config.BASE_DIR / "workflows" / "product_scene_masked_attribute_edit.json"
        ).read_text(encoding="utf-8")
    )
    classes = {n.get("class_type") for n in workflow.values()}
    # Mask-confined regeneration + composite-back is what prevents duplication.
    assert {"LoadImageMask", "SetLatentNoiseMask", "ImageCompositeMasked"} <= classes
    assert "TextEncodeQwenImageEditPlus" in classes


def test_masked_workflow_builds_with_mask_injection():
    gen = ComfyUIProductSceneGenerator(
        "http://x:8001",
        "workflows/product_scene_masked_attribute_edit.json",
        mode="attribute_edit",
        model_key="qwen-image-gguf-masked",
    )
    wf = gen._build_workflow(
        gen.workflow_path,
        prompt="change the shirt to white",
        preset="studio",
        image_name="p.png",
        mask_name="m.png",
        require_mask=True,
        mode="attribute_edit",
    )
    # Product + mask both injected; prompt placeholder consumed.
    assert any(
        n.get("class_type") == "LoadImage" and n["inputs"].get("image") == "p.png"
        for n in wf.values()
    )
    assert any(
        n.get("class_type") == "LoadImageMask" and n["inputs"].get("image") == "m.png"
        for n in wf.values()
    )
    blob = " ".join(
        v for n in wf.values() for v in n.get("inputs", {}).values() if isinstance(v, str)
    )
    assert "change the shirt to white" in blob and "__PROMPT__" not in blob


def test_attribute_edit_unavailable_without_qwen():
    av = workflow_manager._scene_mode_availability({})
    available, reason = av["attribute_edit"]
    assert available is False and "Qwen not installed" in reason


# --- Auto-seg integration (GroundingDINO + SAM) ------------------------------
def test_attribute_edit_manual_route_without_target(monkeypatch):
    # No target_attribute -> manual masked editor (user-supplied mask).
    monkeypatch.setattr(scene_generators, "PRODUCT_SCENE_BACKEND", "comfyui")
    gen = scene_generators.get_product_scene_generator("attribute_edit")
    assert str(gen.workflow_path).endswith("product_scene_masked_attribute_edit.json")
    assert gen.model_key == "qwen-image-gguf-masked"


def test_attribute_edit_autoseg_route_with_open_vocab(monkeypatch):
    # Open-vocab target (not a human-parse class) -> GroundingDINO autoseg.
    monkeypatch.setattr(scene_generators, "PRODUCT_SCENE_BACKEND", "comfyui")
    gen = scene_generators.get_product_scene_generator(
        "attribute_edit", target_attribute="necklace"
    )
    assert str(gen.workflow_path).endswith("product_scene_attribute_edit_autoseg.json")
    assert gen.model_key == "qwen-image-gguf-autoseg"


def test_attribute_edit_hair_now_uses_humanparse(monkeypatch):
    # Hair is a human-parse class now (precise), not GroundingDINO.
    monkeypatch.setattr(scene_generators, "PRODUCT_SCENE_BACKEND", "comfyui")
    gen = scene_generators.get_product_scene_generator(
        "attribute_edit", target_attribute="Hair"
    )
    assert str(gen.workflow_path).endswith(
        "product_scene_attribute_edit_humanparse.json"
    )


def test_autoseg_workflows_have_seg_and_compose_nodes():
    base = config.BASE_DIR / "workflows"
    plain = json.loads((base / "product_scene_attribute_edit_autoseg.json").read_text())
    fp = json.loads(
        (base / "product_scene_attribute_edit_autoseg_faceprotect.json").read_text()
    )
    plain_classes = [n["class_type"] for n in plain.values()]
    fp_classes = [n["class_type"] for n in fp.values()]
    assert "GroundingDinoSAMSegment (segment anything)" in plain_classes
    assert "SetLatentNoiseMask" in plain_classes and "ImageCompositeMasked" in plain_classes
    # Face-protected variant segments "face" and subtracts it.
    assert fp_classes.count("GroundingDinoSAMSegment (segment anything)") == 2
    assert "MaskComposite" in fp_classes
    seg_prompts = [
        n["inputs"]["prompt"]
        for n in fp.values()
        if n["class_type"] == "GroundingDinoSAMSegment (segment anything)"
    ]
    # Generic exclusion: target + exclusion placeholders (both filled at build).
    assert "__SEG_PROMPT__" in seg_prompts and "__EXCLUDE_PROMPT__" in seg_prompts


def test_autoseg_seg_prompt_injection():
    gen = ComfyUIProductSceneGenerator(
        "http://x:8001",
        "workflows/product_scene_attribute_edit_autoseg.json",
        mode="attribute_edit",
        model_key="qwen-image-gguf-autoseg",
    )
    wf = gen._build_workflow(
        gen.workflow_path,
        prompt="change to black tailored trousers",
        preset="studio",
        image_name="p.png",
        mask_name=None,
        require_mask=False,
        mode="attribute_edit",
        seg_prompt="pants",
    )
    seg_prompts = [
        n["inputs"]["prompt"]
        for n in wf.values()
        if n["class_type"] == "GroundingDinoSAMSegment (segment anything)"
    ]
    assert "pants" in seg_prompts and "__SEG_PROMPT__" not in seg_prompts
    blob = " ".join(
        v for n in wf.values() for v in n.get("inputs", {}).values() if isinstance(v, str)
    )
    assert "change to black tailored trousers" in blob


def test_seg_prompt_mapping_specificity():
    from app.product_scene_generators.comfyui import resolve_seg

    assert resolve_seg("shirt") == ("shirt, not jacket, not coat", "jacket, coat, outerwear")
    assert resolve_seg("Pants")[0] == "pants, trousers, legs"
    assert resolve_seg("hair") == ("hair, not face, not forehead", "face")
    assert resolve_seg("tie")[0] == "tie, necktie" and resolve_seg("tie")[1] is None
    assert resolve_seg("glasses")[1] is None  # no exclusion (would erase glasses)
    # Unknown attribute falls back to raw text, no exclusion.
    assert resolve_seg("scarf") == ("scarf", None)
    assert resolve_seg(None) == (None, None)


def test_exclusion_autoseg_for_open_vocab_with_exclusion(monkeypatch):
    # "beard" is open-vocab (not a parse class) and has a face exclusion in
    # resolve_seg -> the exclusion (faceprotect) autoseg workflow.
    monkeypatch.setattr(scene_generators, "PRODUCT_SCENE_BACKEND", "comfyui")
    gen = scene_generators.get_product_scene_generator(
        "attribute_edit", target_attribute="beard"
    )
    assert str(gen.workflow_path).endswith(
        "product_scene_attribute_edit_autoseg_faceprotect.json"
    )


def test_exclusion_autoseg_injects_seg_and_exclude():
    gen = ComfyUIProductSceneGenerator(
        "http://x:8001",
        "workflows/product_scene_attribute_edit_autoseg_faceprotect.json",
        mode="attribute_edit",
        model_key="qwen-image-gguf-autoseg",
    )
    wf = gen._build_workflow(
        gen.workflow_path,
        prompt="change to a white dress shirt",
        preset="studio",
        image_name="p.png",
        mask_name=None,
        require_mask=False,
        mode="attribute_edit",
        seg_prompt="shirt, not jacket, not coat",
        exclude_prompt="jacket, coat, outerwear",
    )
    seg_prompts = [
        n["inputs"]["prompt"]
        for n in wf.values()
        if n["class_type"] == "GroundingDinoSAMSegment (segment anything)"
    ]
    assert "shirt, not jacket, not coat" in seg_prompts
    assert "jacket, coat, outerwear" in seg_prompts
    assert "__SEG_PROMPT__" not in seg_prompts and "__EXCLUDE_PROMPT__" not in seg_prompts


def test_wm_reports_autoseg_ready_when_seg_present():
    def loader(opt):
        return {"input": {"required": opt}}

    oi = {
        "UNETLoader": loader({"unet_name": [["qwen_image_edit_2509_fp8_e4m3fn.safetensors"]]}),
        "DualCLIPLoader": loader(
            {"clip_name1": [["qwen_2.5_vl_7b_fp8_scaled.safetensors"]],
             "clip_name2": [["qwen_2.5_vl_7b_fp8_scaled.safetensors"]]}
        ),
        "VAELoader": loader({"vae_name": [["qwen_image_vae.safetensors"]]}),
        "TextEncodeQwenImageEdit": {},
        "GroundingDinoSAMSegment (segment anything)": {},
    }
    available, reason = workflow_manager._scene_mode_availability(oi)["attribute_edit"]
    assert available is True and "auto-seg" in reason


# --- Human-parsing route (scoped: pants/hair/face/shoes/dress/garment) --------
def test_resolve_parse_class_mapping():
    from app.product_scene_generators.comfyui import resolve_parse_class, PARSE_MANUAL

    assert resolve_parse_class("pants") == "Pants"
    assert resolve_parse_class("Shoes") == "Shoes"
    assert resolve_parse_class("hair") == "Hair"
    assert resolve_parse_class("face") == "Face"
    assert resolve_parse_class("dress") == "Dress"
    assert resolve_parse_class("jacket") == "upper_garment"
    assert resolve_parse_class("coat") == "upper_garment"
    # Ambiguous garment -> manual mask required.
    assert resolve_parse_class("shirt") == PARSE_MANUAL
    # Open-vocab -> no human-parse (GroundingDINO handles it).
    assert resolve_parse_class("tie") is None
    assert resolve_parse_class("glasses") is None


def test_pants_routes_to_humanparse(monkeypatch):
    monkeypatch.setattr(scene_generators, "PRODUCT_SCENE_BACKEND", "comfyui")
    gen = scene_generators.get_product_scene_generator(
        "attribute_edit", target_attribute="pants"
    )
    assert str(gen.workflow_path).endswith(
        "product_scene_attribute_edit_humanparse.json"
    )
    assert gen.model_key == "qwen-image-gguf-humanparse"


def test_jacket_routes_to_humanparse_upper_garment(monkeypatch):
    monkeypatch.setattr(scene_generators, "PRODUCT_SCENE_BACKEND", "comfyui")
    gen = scene_generators.get_product_scene_generator(
        "attribute_edit", target_attribute="jacket"
    )
    assert str(gen.workflow_path).endswith(
        "product_scene_attribute_edit_humanparse.json"
    )


def test_shirt_requires_manual_mask(monkeypatch):
    monkeypatch.setattr(scene_generators, "PRODUCT_SCENE_BACKEND", "comfyui")
    gen = scene_generators.get_product_scene_generator(
        "attribute_edit", target_attribute="shirt"
    )
    # Ambiguous -> manual masked workflow.
    assert str(gen.workflow_path).endswith("product_scene_masked_attribute_edit.json")
    assert gen.model_key == "qwen-image-gguf-masked"


def test_tie_still_routes_to_autoseg(monkeypatch):
    monkeypatch.setattr(scene_generators, "PRODUCT_SCENE_BACKEND", "comfyui")
    gen = scene_generators.get_product_scene_generator(
        "attribute_edit", target_attribute="tie"
    )
    assert "autoseg" in str(gen.workflow_path)
    assert gen.model_key == "qwen-image-gguf-autoseg"


def test_humanparse_workflow_structure_and_injection():
    base = config.BASE_DIR / "workflows"
    wf = json.loads(
        (base / "product_scene_attribute_edit_humanparse.json").read_text()
    )
    classes = [n["class_type"] for n in wf.values()]
    assert "HumanParseMask" in classes
    assert "SetLatentNoiseMask" in classes and "ImageCompositeMasked" in classes
    gen = ComfyUIProductSceneGenerator(
        "http://x:8001",
        "workflows/product_scene_attribute_edit_humanparse.json",
        mode="attribute_edit",
        model_key="qwen-image-gguf-humanparse",
    )
    built = gen._build_workflow(
        gen.workflow_path,
        prompt="change to black",
        preset="studio",
        image_name="p.png",
        mask_name=None,
        require_mask=False,
        mode="attribute_edit",
        parse_class="Pants",
    )
    parse_vals = [
        n["inputs"]["parse_class"]
        for n in built.values()
        if n["class_type"] == "HumanParseMask"
    ]
    assert parse_vals == ["Pants"]


def test_wm_reports_humanparse_ready():
    def loader(opt):
        return {"input": {"required": opt}}

    oi = {
        "UNETLoader": loader({"unet_name": [["qwen_image_edit_2509_fp8_e4m3fn.safetensors"]]}),
        "DualCLIPLoader": loader(
            {"clip_name1": [["qwen_2.5_vl_7b_fp8_scaled.safetensors"]],
             "clip_name2": [["qwen_2.5_vl_7b_fp8_scaled.safetensors"]]}
        ),
        "VAELoader": loader({"vae_name": [["qwen_image_vae.safetensors"]]}),
        "TextEncodeQwenImageEdit": {},
        "HumanParseMask": {},
    }
    available, reason = workflow_manager._scene_mode_availability(oi)["attribute_edit"]
    assert available is True and "human-parse" in reason


# --- Pose Mode: two-stage hybrid ---------------------------------------------
def test_pose_edit_preset_routes_to_identity_workflow(monkeypatch):
    monkeypatch.setattr(scene_generators, "PRODUCT_SCENE_BACKEND", "comfyui")
    gen = scene_generators.get_product_scene_generator(
        "pose_edit", target_attribute="walking"
    )
    assert str(gen.workflow_path).endswith("product_scene_pose_identity_preset.json")
    assert gen.model_key == "pose-ipadapter"


def test_pose_edit_reference_routes_to_identity_reference_workflow(monkeypatch):
    gen = _gen("pose_edit", monkeypatch)
    assert str(gen.workflow_path).endswith("product_scene_pose_identity_reference.json")


def test_pose_stylized_routes_to_existing_fallback_workflow(monkeypatch):
    monkeypatch.setattr(scene_generators, "PRODUCT_SCENE_BACKEND", "comfyui")
    preset = scene_generators.get_product_scene_generator(
        "pose_stylized", target_attribute="walking"
    )
    assert str(preset.workflow_path).endswith("product_scene_pose_preset.json")
    assert preset.model_key == ""
    ref = scene_generators.get_product_scene_generator("pose_stylized")
    assert str(ref.workflow_path).endswith("product_scene_pose_reference.json")


def test_pose_preset_workflow_structure():
    base = config.BASE_DIR / "workflows"
    preset = json.loads((base / "product_scene_pose_identity_preset.json").read_text())
    ref = json.loads((base / "product_scene_pose_identity_reference.json").read_text())
    pc = {n["class_type"] for n in preset.values()}
    rc = {n["class_type"] for n in ref.values()}
    # Preset: skeleton LoadImage -> SDXL+OpenPose+IPAdapter -> Qwen refine.
    assert {
        "ControlNetLoader",
        "ControlNetApplyAdvanced",
        "IPAdapterUnifiedLoader",
        "IPAdapterAdvanced",
        "CLIPVisionLoader",
        "TextEncodeQwenImageEditPlus",
    } <= pc
    assert any(
        n["class_type"] == "LoadImage" and n["inputs"].get("image") == "__POSE_SKELETON__"
        for n in preset.values()
    )
    # Reference: the skeleton input is DWPose-d first.
    assert "DWPreprocessor" in rc


def test_pose_preset_skeletons_exist():
    ensure_pose_presets()
    presets = config.STORAGE_DIR / "pose_presets"
    for name in config.POSE_PRESETS:
        assert (presets / f"{name}.png").is_file(), f"missing preset skeleton {name}"


def test_pose_workflow_is_sdxl_openpose_then_qwen():
    workflow = json.loads(
        (config.BASE_DIR / "workflows" / "product_scene_pose_identity_preset.json").read_text(
            encoding="utf-8"
        )
    )
    class_types = {node.get("class_type") for node in workflow.values()}
    # Stage 1: SDXL + OpenPose + IPAdapter.
    assert "CheckpointLoaderSimple" in class_types
    assert {"ControlNetLoader", "ControlNetApplyAdvanced"} <= class_types
    assert {"IPAdapterUnifiedLoader", "IPAdapterAdvanced"} <= class_types
    # Stage 2: Qwen refine.
    assert "TextEncodeQwenImageEditPlus" in class_types


# --- Qwen creative workflows favour transformation over preservation ---------
def test_qwen_creative_workflow_transforms_not_preserves():
    gen = ComfyUIProductSceneGenerator(
        "http://x:8001",
        "workflows/product_scene_creative_qwen_edit.json",
        mode="creative_edit",
        model_key="qwen-image-gguf",
    )
    workflow = gen._build_workflow(
        gen.workflow_path,
        prompt="change pose to walking in a neon city",
        preset="luxury",
        image_name="p.png",
        mask_name=None,
        require_mask=False,
        mode="creative_edit",
    )
    blob = " ".join(
        v
        for node in workflow.values()
        for v in node.get("inputs", {}).values()
        if isinstance(v, str)
    )
    assert "change pose to walking in a neon city" in blob
    assert "strong creative transformation" in blob
    # The preservation-heavy Qwen language must NOT be present here.
    assert "Preserve the same person" not in blob
    denoise = [
        node["inputs"]["denoise"]
        for node in workflow.values()
        if node.get("class_type") == "KSampler"
    ]
    assert denoise == [0.92]


# --- Workflow Manager: Qwen-missing messaging, no silent Flux ----------------
def test_wm_transform_modes_unavailable_without_qwen():
    # Empty object_info == ComfyUI offline / nothing installed.
    availability = workflow_manager._scene_mode_availability({})
    for mode in TRANSFORM_MODES:
        available, reason = availability[mode]
        assert available is False
        assert "Qwen not installed" in reason
    pose_available, pose_reason = availability["pose_edit"]
    assert pose_available is False
    assert pose_reason  # explicit reason, never silent


def test_wm_registers_new_modes(client):
    models = client.get("/api/workflow-manager/models").json()
    ids = {m["id"] for m in models["scene_modes"]}
    assert {"clothing_style_edit", "pose_edit", "pose_stylized", "film_scene"} <= ids


# --- Schema / API acceptance -------------------------------------------------
def test_new_modes_pass_schema_validation(client):
    project_id = client.post(
        "/api/projects", json={"name": "Film", "description": None}
    ).json()["id"]
    for mode in ["pose_edit", "pose_stylized", "film_scene", "clothing_style_edit", "creative_edit"]:
        resp = client.post(
            "/api/product-scenes",
            json={
                "project_id": project_id,
                "asset_id": "does-not-exist",
                "prompt": "x",
                "preset": "studio",
                "mode": mode,
            },
        )
        # Mode is valid (not 422); it fails later on the bogus asset instead.
        assert resp.status_code != 422, f"{mode} rejected by schema"


def test_target_attribute_accepted(client):
    project_id = client.post(
        "/api/projects", json={"name": "Attr", "description": None}
    ).json()["id"]
    resp = client.post(
        "/api/product-scenes",
        json={
            "project_id": project_id,
            "asset_id": "does-not-exist",
            "prompt": "change to black trousers",
            "preset": "studio",
            "mode": "attribute_edit",
            "target_attribute": "pants",
        },
    )
    # Schema accepts target_attribute (fails later on the bogus asset, not 422).
    assert resp.status_code != 422


def test_invalid_mode_rejected(client):
    project_id = client.post(
        "/api/projects", json={"name": "Film2", "description": None}
    ).json()["id"]
    resp = client.post(
        "/api/product-scenes",
        json={
            "project_id": project_id,
            "asset_id": "does-not-exist",
            "prompt": "x",
            "preset": "studio",
            "mode": "teleport",
        },
    )
    assert resp.status_code == 422
