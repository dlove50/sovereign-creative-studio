"""Compare a local render against a reference, and say which knob to turn.

Step 6 of docs/CLOUD_ESCALATION_DESIGN.md -- the half of REA that makes the
local path actually improve. §4 of that document explains why the weights
cannot be learned from a cloud API: it returns a finished picture and nothing
about the model that made it. What *can* transfer is the recipe -- prompt,
sampler, steps, CFG, resolution, refiner -- and those live in the workflow
JSON, not in the weights.

So this module does not grade pictures. It measures a small number of
well-defined properties of both images, reports the signed difference, and
names the workflow parameter each difference implicates. That is what turns a
recipe search from random sampling into a directed one.

**It deliberately does not emit a single quality score.** A number like
"local scores 0.82" reads as a measurement and is not one -- there is no
defensible scalar for "how professional does this look", and inventing one
would get trusted. The same discipline the VRAM estimator uses applies here:

  MEASURED   a property computed from pixels. Reproducible, and that is all
             it claims. Sharpness is a Laplacian variance, not "quality".
  INFERRED   the parameter a difference implicates. A hypothesis to test by
             rendering again, never a diagnosis.

One trap worth naming, because it will otherwise waste someone's afternoon:
two renders of the same prompt with different seeds have genuinely different
composition, so a low structural similarity between them is expected and says
nothing about quality. `structure` is only meaningful when comparing a render
against its own reference, and `interpret` says so rather than letting anyone
chase it.

Depends on numpy and PIL only -- both already in the backend environment.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

# Differences smaller than these are treated as noise rather than signal.
# Chosen to be loose: a false "turn this knob" costs a wasted render, and the
# point is to direct a search, not to be sensitive.
THRESHOLDS = {
    "sharpness": 0.25,    # relative: |local - ref| / ref
    "contrast": 0.15,
    "saturation": 0.15,
    "brightness": 0.12,
    "noise": 0.30,
}

# Which workflow parameters a difference implicates, most likely first. These
# are hypotheses to test, not conclusions -- see the module note.
IMPLICATES = {
    "sharpness_low": ("steps", "sampler", "refiner_pass", "upscaler"),
    "sharpness_high": ("denoise", "upscaler"),
    "contrast_low": ("cfg", "vae"),
    "contrast_high": ("cfg",),
    "saturation_low": ("vae", "cfg"),
    "saturation_high": ("cfg", "vae"),
    "brightness_low": ("cfg", "vae"),
    "brightness_high": ("cfg", "vae"),
    "noise_high": ("steps", "denoise", "sampler"),
    "resolution_low": ("latent_width", "latent_height", "upscaler"),
}

MAX_SIDE = 1024  # images are downscaled to this before measuring, for speed


@dataclass(frozen=True)
class Measurements:
    """Properties of one image. Every field is computed from pixels."""

    width: int
    height: int
    sharpness: float    # variance of the Laplacian
    contrast: float     # standard deviation of luminance, 0-1
    saturation: float   # mean saturation, 0-1
    brightness: float   # mean luminance, 0-1
    noise: float        # mean absolute high-frequency residual

    @property
    def pixels(self) -> int:
        return self.width * self.height


@dataclass(frozen=True)
class Difference:
    """One measured gap, and what it implicates. `implicates` is a hypothesis."""

    name: str
    local: float
    reference: float
    relative: float          # signed: negative means local is lower
    implicates: tuple[str, ...]

    @property
    def direction(self) -> str:
        return "low" if self.relative < 0 else "high"

    def describe(self) -> str:
        return (
            f"{self.name} is {abs(self.relative) * 100:.0f}% "
            f"{'lower' if self.relative < 0 else 'higher'} than the reference "
            f"({self.local:.4g} vs {self.reference:.4g}); "
            f"try: {', '.join(self.implicates)}"
        )


def _load_luma(path: Path | str) -> tuple[np.ndarray, np.ndarray, int, int]:
    """Return (luma 0-1, saturation 0-1, width, height) for an image.

    Downscaled so a 4K render does not cost seconds, and converted through RGB
    so palettes, alpha and 16-bit sources all behave.
    """
    with Image.open(path) as img:
        img = img.convert("RGB")
        width, height = img.size
        longest = max(width, height)
        if longest > MAX_SIDE:
            scale = MAX_SIDE / longest
            img = img.resize(
                (max(1, int(width * scale)), max(1, int(height * scale))),
                Image.Resampling.BILINEAR,
            )
        rgb = np.asarray(img, dtype=np.float64) / 255.0

    # Rec. 601 luma, which is what both PIL's "L" and most video tooling use.
    luma = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    # HSV saturation without the hue/value cost.
    high = rgb.max(axis=-1)
    low = rgb.min(axis=-1)
    with np.errstate(divide="ignore", invalid="ignore"):
        sat = np.where(high > 0, (high - low) / high, 0.0)
    return luma, sat, width, height


def _laplacian_variance(luma: np.ndarray) -> float:
    """Sharpness proxy. A blurred image has little high-frequency energy.

    The 4-neighbour Laplacian, computed by shifting rather than convolving so
    this needs no scipy.
    """
    if luma.shape[0] < 3 or luma.shape[1] < 3:
        return 0.0
    middle = luma[1:-1, 1:-1]
    lap = (
        luma[:-2, 1:-1] + luma[2:, 1:-1] + luma[1:-1, :-2] + luma[1:-1, 2:]
        - 4.0 * middle
    )
    return float(lap.var())


def _noise_estimate(luma: np.ndarray) -> float:
    """High-frequency residual after a 3x3 box blur.

    This cannot separate noise from fine detail -- a brick wall and a grainy
    sky both score high. It is a proxy, and `interpret` only acts on it
    alongside a sharpness reading, where under-denoising shows up as high
    noise with low sharpness.
    """
    if luma.shape[0] < 3 or luma.shape[1] < 3:
        return 0.0
    stack = np.stack([
        luma[:-2, :-2], luma[:-2, 1:-1], luma[:-2, 2:],
        luma[1:-1, :-2], luma[1:-1, 1:-1], luma[1:-1, 2:],
        luma[2:, :-2], luma[2:, 1:-1], luma[2:, 2:],
    ])
    blurred = stack.mean(axis=0)
    return float(np.abs(luma[1:-1, 1:-1] - blurred).mean())


def measure(path: Path | str) -> Measurements:
    """Measure one image. Raises OSError/ValueError if it cannot be read."""
    luma, sat, width, height = _load_luma(path)
    return Measurements(
        width=width,
        height=height,
        sharpness=_laplacian_variance(luma),
        contrast=float(luma.std()),
        saturation=float(sat.mean()),
        brightness=float(luma.mean()),
        noise=_noise_estimate(luma),
    )


def structure(local: Path | str, reference: Path | str) -> float:
    """Global SSIM between two images, 0-1. Higher is more similar.

    Implemented directly: scikit-image is not installed, and SSIM is a defined
    formula rather than a judgement call. Uses global statistics instead of a
    sliding window, which is coarser than the windowed form but adequate for
    "is this the same composition" -- which is all it is used for.

    Returns 0.0 when the two differ in aspect ratio, since comparing structure
    across a reframe is meaningless.
    """
    a_luma, _, a_w, a_h = _load_luma(local)
    b_luma, _, b_w, b_h = _load_luma(reference)

    if a_w * b_h != b_w * a_h:        # aspect ratios differ
        return 0.0

    # Match sizes so the arrays line up; the smaller one sets the grid.
    if a_luma.shape != b_luma.shape:
        rows = min(a_luma.shape[0], b_luma.shape[0])
        cols = min(a_luma.shape[1], b_luma.shape[1])
        if rows < 2 or cols < 2:
            return 0.0
        a_luma = np.asarray(
            Image.fromarray((a_luma * 255).astype(np.uint8)).resize(
                (cols, rows), Image.Resampling.BILINEAR), dtype=np.float64) / 255.0
        b_luma = np.asarray(
            Image.fromarray((b_luma * 255).astype(np.uint8)).resize(
                (cols, rows), Image.Resampling.BILINEAR), dtype=np.float64) / 255.0

    c1 = 0.01 ** 2
    c2 = 0.03 ** 2
    mu_a, mu_b = a_luma.mean(), b_luma.mean()
    var_a, var_b = a_luma.var(), b_luma.var()
    cov = ((a_luma - mu_a) * (b_luma - mu_b)).mean()

    numerator = (2 * mu_a * mu_b + c1) * (2 * cov + c2)
    denominator = (mu_a**2 + mu_b**2 + c1) * (var_a + var_b + c2)
    if denominator == 0:
        return 1.0 if numerator == 0 else 0.0
    return float(np.clip(numerator / denominator, 0.0, 1.0))


def compare(local: Measurements, reference: Measurements) -> list[Difference]:
    """Signed, thresholded differences. Empty means the recipe already matches."""
    out: list[Difference] = []

    for name in ("sharpness", "contrast", "saturation", "brightness", "noise"):
        ref = getattr(reference, name)
        loc = getattr(local, name)
        if ref <= 0:
            continue                      # nothing to be relative to
        relative = (loc - ref) / ref
        if abs(relative) < THRESHOLDS[name]:
            continue
        direction = "low" if relative < 0 else "high"
        key = f"{name}_{direction}"
        if key not in IMPLICATES:
            continue                      # e.g. noise_low needs no action
        out.append(Difference(name, loc, ref, relative, IMPLICATES[key]))

    # Resolution is a count, not a ratio of appearance, so it is handled apart.
    if reference.pixels > 0 and local.pixels < reference.pixels * 0.9:
        relative = (local.pixels - reference.pixels) / reference.pixels
        out.append(Difference(
            "resolution", float(local.pixels), float(reference.pixels),
            relative, IMPLICATES["resolution_low"],
        ))

    # Largest gaps first: that is the order worth trying them in.
    out.sort(key=lambda d: abs(d.relative), reverse=True)
    return out


def interpret(
    differences: list[Difference], ssim: float | None = None
) -> list[str]:
    """Plain lines for a human or a log. Hypotheses, labelled as such."""
    if not differences:
        lines = ["No measured difference above threshold; the recipe already "
                 "matches the reference on what can be measured."]
    else:
        lines = [d.describe() for d in differences]

        # Under-denoising has a signature: noisy AND soft together. Worth
        # calling out, because the single-metric advice would be contradictory.
        names = {d.name: d for d in differences}
        if ("noise" in names and names["noise"].direction == "high"
                and "sharpness" in names and names["sharpness"].direction == "low"):
            lines.append(
                "noise is high while sharpness is low, which is what too few "
                "steps looks like; raise steps before changing anything else."
            )

    if ssim is not None:
        if ssim < 0.5 and not differences:
            lines.append(
                f"structure differs ({ssim:.2f}) while every measured property "
                "matches: this is a different composition, not a recipe "
                "problem. Expected when the seeds differ -- do not chase it."
            )
        elif ssim < 0.5:
            lines.append(
                f"structure is only {ssim:.2f}; if the seeds differ, that is "
                "expected and not evidence about quality."
            )
    return lines
