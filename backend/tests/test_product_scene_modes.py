"""Phase C9: creative scene modes select the right workflow + inject mode style.

No live ComfyUI is required — these check factory selection and prompt building
against the workflow files on disk."""
import os
import tempfile

_TMP = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(_TMP, 'test.db')}")
os.environ.setdefault("STORAGE_DIR", os.path.join(_TMP, "storage"))
os.environ.setdefault("GENERATOR_BACKEND", "mock")

import app.product_scene_generators as scene_generators  # noqa: E402
from app.product_scene_generators.comfyui import (  # noqa: E402
    ComfyUIProductSceneGenerator,
)


def _gen(mode, monkeypatch):
    monkeypatch.setattr(scene_generators, "PRODUCT_SCENE_BACKEND", "comfyui")
    return scene_generators.get_product_scene_generator(mode)


def test_segmented_composite_selects_workflow(monkeypatch):
    gen = _gen("segmented_composite", monkeypatch)
    assert isinstance(gen, ComfyUIProductSceneGenerator)
    assert gen.mode == "segmented_composite"
    assert str(gen.workflow_path).endswith("product_scene_segmented_composite.json")
    # Self-contained workflow -> no per-image-model validation.
    assert gen.model_key == ""


def test_segmented_composite_polished_selects_workflow(monkeypatch):
    gen = _gen("segmented_composite_polished", monkeypatch)
    assert gen.mode == "segmented_composite_polished"
    assert str(gen.workflow_path).endswith(
        "product_scene_segmented_composite_polished.json"
    )
    assert gen.model_key == ""


def test_polished_workflow_has_refinement_and_color_match():
    from app.product_scene_generators.comfyui import ComfyUIProductSceneGenerator

    gen = ComfyUIProductSceneGenerator(
        "http://x:8001",
        "workflows/product_scene_segmented_composite_polished.json",
        mode="segmented_composite_polished",
        model_key="",
    )
    workflow = gen._build_workflow(
        gen.workflow_path,
        prompt="a model in a luxury storefront",
        preset="luxury",
        image_name="p.png",
        mask_name=None,
        require_mask=False,
        mode="segmented_composite_polished",
    )
    class_types = {node.get("class_type") for node in workflow.values()}
    # Edge refinement + color matching + masked composite are present.
    assert {"RemBGSession+", "MaskSmooth+", "ImageColorMatch+", "ImageCompositeMasked"} <= class_types
    # Exactly one SaveImage so the adapter returns the composite deterministically.
    assert sum(n.get("class_type") == "SaveImage" for n in workflow.values()) == 1


def test_advertising_scene_selects_workflow(monkeypatch):
    gen = _gen("advertising_scene", monkeypatch)
    assert gen.mode == "advertising_scene"
    assert str(gen.workflow_path).endswith("product_scene_advertising_scene.json")


def test_fashion_editorial_selects_workflow(monkeypatch):
    gen = _gen("fashion_editorial", monkeypatch)
    assert gen.mode == "fashion_editorial"
    assert str(gen.workflow_path).endswith("product_scene_fashion_editorial.json")


def test_creative_fashion_edit_selects_workflow(monkeypatch):
    gen = _gen("creative_fashion_edit", monkeypatch)
    assert gen.mode == "creative_fashion_edit"
    assert str(gen.workflow_path).endswith("product_scene_creative_fashion_edit.json")


def test_film_studio_transformation_modes_select_qwen_workflow(monkeypatch):
    # Transform-first policy: these now route to Qwen Image Edit, NOT Flux.
    for mode in [
        "creative_edit",
        "character_reimagination",
        "fashion_transformation",
        "cinematic_scene_builder",
    ]:
        gen = _gen(mode, monkeypatch)
        assert gen.mode == mode
        assert str(gen.workflow_path).endswith("product_scene_creative_qwen_edit.json")
        # No silent Flux fallback.
        assert "creative_fashion_edit" not in str(gen.workflow_path)


def test_existing_modes_unchanged(monkeypatch):
    monkeypatch.setattr(scene_generators, "PRODUCT_SCENE_MODEL", "flux-kontext")
    img = _gen("img2img", monkeypatch)
    assert img.mode == "img2img"
    assert str(img.workflow_path).endswith("product_scene_flux_kontext.json")
    ip = _gen("ipadapter", monkeypatch)
    assert ip.mode == "ipadapter"
    assert str(ip.workflow_path).endswith("product_scene_ipadapter.json")
    inp = _gen("inpaint", monkeypatch)
    assert inp.mode == "inpaint"
    assert str(inp.workflow_path).endswith("product_scene_inpaint.json")


def test_advertising_mode_injects_style_and_prompt():
    gen = ComfyUIProductSceneGenerator(
        "http://x:8001",
        "workflows/product_scene_advertising_scene.json",
        mode="advertising_scene",
        model_key="",
    )
    workflow = gen._build_workflow(
        gen.workflow_path,
        prompt="a leather handbag",
        preset="luxury",
        image_name="p.png",
        mask_name=None,
        require_mask=False,
        mode="advertising_scene",
    )
    texts = [
        node.get("inputs", {}).get(key, "")
        for node in workflow.values()
        for key in ("clip_l", "t5xxl", "text")
    ]
    blob = " ".join(t for t in texts if isinstance(t, str))
    assert "a leather handbag" in blob
    assert "advertising composition" in blob  # mode style injected
    assert "__PROMPT__" not in blob
    # LoadImage received the uploaded product filename.
    assert any(
        node.get("class_type") == "LoadImage"
        and node.get("inputs", {}).get("image") == "p.png"
        for node in workflow.values()
    )


def test_creative_fashion_edit_allows_transformation_prompt():
    gen = ComfyUIProductSceneGenerator(
        "http://x:8001",
        "workflows/product_scene_creative_fashion_edit.json",
        mode="creative_fashion_edit",
        model_key="",
    )
    workflow = gen._build_workflow(
        gen.workflow_path,
        prompt="Change pants to black tailored trousers",
        preset="luxury",
        image_name="p.png",
        mask_name=None,
        require_mask=False,
        mode="creative_fashion_edit",
    )
    texts = [
        node.get("inputs", {}).get(key, "")
        for node in workflow.values()
        for key in ("clip_l", "t5xxl", "text")
    ]
    blob = " ".join(t for t in texts if isinstance(t, str))
    assert "Change pants to black tailored trousers" in blob
    assert "allow stronger creative transformation" in blob
    assert "moderate pose" in blob
    assert "__PROMPT__" not in blob
    denoise = [
        node.get("inputs", {}).get("denoise")
        for node in workflow.values()
        if node.get("class_type") == "KSampler"
    ]
    assert denoise == [0.68]


def test_film_studio_modes_inject_distinct_transformation_language():
    expected = {
        "creative_edit": "creative image edit",
        "character_reimagination": "character reimagination",
        "fashion_transformation": "fashion transformation",
        "cinematic_scene_builder": "cinematic scene builder",
    }
    for mode, marker in expected.items():
        gen = ComfyUIProductSceneGenerator(
            "http://x:8001",
            "workflows/product_scene_creative_fashion_edit.json",
            mode=mode,
            model_key="",
        )
        workflow = gen._build_workflow(
            gen.workflow_path,
            prompt="make a dramatic campaign image",
            preset="luxury",
            image_name="p.png",
            mask_name=None,
            require_mask=False,
            mode=mode,
        )
        texts = [
            node.get("inputs", {}).get(key, "")
            for node in workflow.values()
            for key in ("clip_l", "t5xxl", "text")
        ]
        assert marker in " ".join(t for t in texts if isinstance(t, str))


def test_segmented_workflow_needs_no_external_mask():
    gen = ComfyUIProductSceneGenerator(
        "http://x:8001",
        "workflows/product_scene_segmented_composite.json",
        mode="segmented_composite",
        model_key="",
    )
    # require_mask=False: the mask is generated inside the workflow (RemBG).
    workflow = gen._build_workflow(
        gen.workflow_path,
        prompt="a model in a studio",
        preset="studio",
        image_name="p.png",
        mask_name=None,
        require_mask=False,
        mode="segmented_composite",
    )
    assert any(
        node.get("class_type") == "RemBGSession+" for node in workflow.values()
    )
