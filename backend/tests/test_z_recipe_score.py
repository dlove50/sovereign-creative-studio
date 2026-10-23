"""Recipe scoring, checked against images whose properties are known by construction.

Every fixture below is generated so the ground truth is not in question: the
blurred image really is the sharp one blurred, the dark one really is the same
image scaled down in luminance. That matters more than usual here, because a
module that claims to measure image properties is easy to write and hard to
trust -- if the measurements were wrong, the advice built on them would be
confidently wrong too.

The API contract is pinned as well: this module must never grow a single
"quality" scalar. That would read as a measurement without being one, and it
is the thing most likely to get added later by someone who wants one number.
"""
from __future__ import annotations

import os
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PIL import Image, ImageFilter  # noqa: E402

from app.services import recipe_score as rs  # noqa: E402

SIZE = 256


def _save(array: np.ndarray, path) -> str:
    Image.fromarray(np.clip(array, 0, 255).astype(np.uint8)).save(path)
    return str(path)


def _detailed(seed: int = 0) -> np.ndarray:
    """An image with real high-frequency content, so blurring is measurable."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:SIZE, 0:SIZE]
    # Overlapping gratings plus a smooth gradient: sharp edges and broad tones.
    base = (
        128
        + 60 * np.sin(x / 3.0)
        + 40 * np.sin(y / 5.0)
        + 25 * ((x // 16 + y // 16) % 2)
    )
    rgb = np.stack([base, base * 0.85, base * 0.7], axis=-1)
    rgb += rng.normal(0, 2, rgb.shape)        # a little grain, not noise-test
    return np.clip(rgb, 0, 255)


@pytest.fixture
def reference(tmp_path):
    return _save(_detailed(), tmp_path / "reference.png")


# --------------------------------------------------------------------------
# Measurement: does it measure what it says it measures
# --------------------------------------------------------------------------

def test_blurring_lowers_the_sharpness_reading(tmp_path, reference):
    blurred = Image.open(reference).filter(ImageFilter.GaussianBlur(3))
    soft = str(tmp_path / "soft.png")
    blurred.save(soft)

    assert rs.measure(soft).sharpness < rs.measure(reference).sharpness * 0.5, (
        "a visibly blurred image did not read as less sharp")


def test_scaling_luminance_lowers_the_brightness_reading(tmp_path, reference):
    dark = _save(np.asarray(Image.open(reference), dtype=np.float64) * 0.5,
                 tmp_path / "dark.png")
    assert rs.measure(dark).brightness < rs.measure(reference).brightness * 0.75


def test_pulling_toward_grey_lowers_the_contrast_reading(tmp_path, reference):
    arr = np.asarray(Image.open(reference), dtype=np.float64)
    flat = _save(128 + (arr - 128) * 0.25, tmp_path / "flat.png")
    assert rs.measure(flat).contrast < rs.measure(reference).contrast * 0.5


def test_pulling_channels_together_lowers_the_saturation_reading(tmp_path, reference):
    arr = np.asarray(Image.open(reference), dtype=np.float64)
    grey = arr.mean(axis=-1, keepdims=True).repeat(3, axis=-1)
    washed = _save(arr * 0.2 + grey * 0.8, tmp_path / "washed.png")
    assert rs.measure(washed).saturation < rs.measure(reference).saturation * 0.5


def test_added_speckle_raises_the_noise_reading(tmp_path):
    clean_arr = np.full((SIZE, SIZE, 3), 120.0)
    clean = _save(clean_arr, tmp_path / "clean.png")
    rng = np.random.default_rng(7)
    noisy = _save(clean_arr + rng.normal(0, 25, clean_arr.shape),
                  tmp_path / "noisy.png")

    assert rs.measure(noisy).noise > rs.measure(clean).noise * 3


def test_dimensions_are_the_originals_not_the_downscaled_ones(tmp_path):
    big = _save(np.resize(_detailed(), (SIZE, SIZE, 3)), tmp_path / "b.png")
    m = rs.measure(big)
    assert (m.width, m.height) == (SIZE, SIZE)
    assert m.pixels == SIZE * SIZE


def test_a_tiny_image_does_not_crash_the_kernels(tmp_path):
    """The Laplacian and box blur both need 3 rows; 1x1 must not raise."""
    one = _save(np.full((1, 1, 3), 200.0), tmp_path / "one.png")
    m = rs.measure(one)
    assert m.sharpness == 0.0 and m.noise == 0.0


# --------------------------------------------------------------------------
# Comparison and the implicated parameters
# --------------------------------------------------------------------------

def test_an_image_compared_with_itself_reports_nothing_to_change(reference):
    m = rs.measure(reference)
    assert rs.compare(m, m) == []
    assert "already matches" in rs.interpret([])[0]


def test_a_soft_local_render_implicates_steps_and_the_sampler(tmp_path, reference):
    Image.open(reference).filter(ImageFilter.GaussianBlur(3)).save(
        tmp_path / "soft.png")
    diffs = rs.compare(rs.measure(tmp_path / "soft.png"), rs.measure(reference))

    sharp = next((d for d in diffs if d.name == "sharpness"), None)
    assert sharp is not None, "the blur was not reported"
    assert sharp.direction == "low"
    assert "steps" in sharp.implicates


def test_differences_are_ordered_largest_first(tmp_path, reference):
    arr = np.asarray(Image.open(reference), dtype=np.float64)
    grey = arr.mean(axis=-1, keepdims=True).repeat(3, axis=-1)
    worse = _save(128 + (arr * 0.1 + grey * 0.9 - 128) * 0.2,
                  tmp_path / "worse.png")
    diffs = rs.compare(rs.measure(worse), rs.measure(reference))

    assert len(diffs) >= 2
    magnitudes = [abs(d.relative) for d in diffs]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_a_smaller_render_implicates_the_latent_size(tmp_path, reference):
    Image.open(reference).resize((64, 64)).save(tmp_path / "small.png")
    diffs = rs.compare(rs.measure(tmp_path / "small.png"), rs.measure(reference))

    res = next((d for d in diffs if d.name == "resolution"), None)
    assert res is not None
    assert "latent_width" in res.implicates


def test_differences_under_threshold_are_not_reported(reference):
    """A 2% gap is noise; reporting it would send someone chasing nothing."""
    m = rs.measure(reference)
    nudged = rs.Measurements(
        width=m.width, height=m.height,
        sharpness=m.sharpness * 1.02, contrast=m.contrast * 0.98,
        saturation=m.saturation * 1.01, brightness=m.brightness * 0.99,
        noise=m.noise * 1.05,
    )
    assert rs.compare(nudged, m) == []


def test_a_zero_reference_property_is_skipped_not_divided_by(tmp_path):
    """A flat grey reference has zero contrast; relative change is undefined."""
    flat = _save(np.full((SIZE, SIZE, 3), 128.0), tmp_path / "flat.png")
    diffs = rs.compare(rs.measure(tmp_path / "flat.png"), rs.measure(flat))
    assert isinstance(diffs, list)   # no ZeroDivisionError, no inf


# --------------------------------------------------------------------------
# The under-denoising signature
# --------------------------------------------------------------------------

def test_noisy_and_soft_together_is_called_out_as_too_few_steps():
    """Single-metric advice would be contradictory here -- noise says lower
    denoise, softness says raise steps. The combination has one answer."""
    ref = rs.Measurements(SIZE, SIZE, sharpness=0.01, contrast=0.2,
                          saturation=0.3, brightness=0.5, noise=0.002)
    local = rs.Measurements(SIZE, SIZE, sharpness=0.002, contrast=0.2,
                            saturation=0.3, brightness=0.5, noise=0.02)
    lines = rs.interpret(rs.compare(local, ref))

    assert any("too few" in line and "steps" in line for line in lines), lines


# --------------------------------------------------------------------------
# Structure, and the seed caveat
# --------------------------------------------------------------------------

def test_an_image_is_structurally_identical_to_itself(reference):
    assert rs.structure(reference, reference) == pytest.approx(1.0, abs=1e-6)


def test_a_different_aspect_ratio_returns_zero_rather_than_a_number(tmp_path, reference):
    Image.open(reference).resize((SIZE, SIZE // 2)).save(tmp_path / "wide.png")
    assert rs.structure(tmp_path / "wide.png", reference) == 0.0, (
        "comparing structure across a reframe is meaningless and must not "
        "produce a plausible-looking score")


def test_the_same_content_at_a_different_scale_still_matches(tmp_path, reference):
    Image.open(reference).resize((SIZE // 2, SIZE // 2)).save(tmp_path / "half.png")
    assert rs.structure(tmp_path / "half.png", reference) > 0.5


def test_low_structure_with_matching_properties_is_named_as_a_seed_difference():
    """The trap: a low SSIM between two seeds means nothing about quality."""
    lines = rs.interpret([], ssim=0.2)
    joined = " ".join(lines)
    assert "different composition" in joined
    assert "do not chase" in joined


# --------------------------------------------------------------------------
# API contract
# --------------------------------------------------------------------------

def test_the_module_exposes_no_single_quality_score():
    """A scalar 'quality' reads as a measurement without being one. If someone
    adds it later, this test is where the argument happens."""
    banned = {"quality", "score", "grade", "rating", "overall"}
    public = {n for n in dir(rs) if not n.startswith("_")}
    assert not {n for n in public if any(b in n.lower() for b in banned)}, (
        "a quality scalar was added; see the module docstring for why not")


def test_every_implication_is_a_real_parameter_name():
    """Advice naming a knob that does not exist is worse than no advice."""
    known = {
        "steps", "sampler", "cfg", "vae", "denoise", "refiner_pass",
        "upscaler", "latent_width", "latent_height",
    }
    for key, params in rs.IMPLICATES.items():
        assert params, f"{key} implicates nothing"
        unknown = set(params) - known
        assert not unknown, f"{key} names unknown parameters: {unknown}"


def test_every_threshold_has_a_matching_measurement():
    for name in rs.THRESHOLDS:
        assert hasattr(rs.Measurements(0, 0, 0, 0, 0, 0, 0), name)
