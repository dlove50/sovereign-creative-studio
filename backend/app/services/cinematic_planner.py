"""Structured local cinematic planning; this never submits media or paid jobs."""
from __future__ import annotations

import os
from typing import Annotated

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .. import config


Text = Annotated[str, Field(min_length=1, max_length=4000)]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)


class Entity(StrictModel):
    id: Identifier
    name: Annotated[str, Field(min_length=1, max_length=160)]
    description: Text


class Dialogue(StrictModel):
    character_id: Identifier
    text: Annotated[str, Field(min_length=1, max_length=1500)]


class Shot(StrictModel):
    id: Identifier
    duration_seconds: int = Field(ge=2, le=30)
    location_id: Identifier
    character_ids: list[Identifier] = Field(max_length=12)
    description: Text
    camera: Text
    dialogue: list[Dialogue] = Field(max_length=12)
    narration: str = Field(max_length=1500)
    transition: Annotated[str, Field(min_length=1, max_length=160)]
    image_prompt: Text
    video_prompt: Text


class Plan(StrictModel):
    title: Annotated[str, Field(min_length=1, max_length=160)]
    synopsis: Text
    characters: list[Entity] = Field(max_length=12)
    locations: list[Entity] = Field(min_length=1, max_length=20)
    shots: list[Shot] = Field(min_length=1, max_length=60)

    @model_validator(mode="after")
    def references_are_valid(self):
        for label, items in (("character", self.characters), ("location", self.locations), ("shot", self.shots)):
            ids = [item.id for item in items]
            if len(ids) != len(set(ids)):
                raise ValueError(f"Duplicate {label} IDs")
        characters = {item.id for item in self.characters}
        locations = {item.id for item in self.locations}
        for shot in self.shots:
            if shot.location_id not in locations:
                raise ValueError(f"Shot {shot.id} references an unknown location")
            if len(shot.character_ids) != len(set(shot.character_ids)):
                raise ValueError(f"Shot {shot.id} repeats a character ID")
            if not set(shot.character_ids) <= characters:
                raise ValueError(f"Shot {shot.id} references an unknown character")
            if any(line.character_id not in shot.character_ids for line in shot.dialogue):
                raise ValueError(f"Shot {shot.id} dialogue references a character absent from the shot")
        total = sum(shot.duration_seconds for shot in self.shots)
        if not 10 <= total <= 180:
            raise ValueError("Total shot duration must be between 10 and 180 seconds")
        return self


class PlanOut(Plan):
    model: str


_SYSTEM = """You are a cinematic director planning a short film, not a presenter script.
Return only JSON matching the supplied schema. Use consistent character/location IDs.
Every shot needs a camera direction, image prompt, video prompt and transition.
Repeat identifying clothing/appearance and location details in prompts for continuity.
Describe each shot as a feasible visible action with a clear beginning and end state.
Preserve cause and effect across shots: carry forward character positions, wardrobe,
prop condition and story events; do not resurrect missing characters or repair props silently.
Use concrete camera framing and screen direction when action depends on spatial relationships.
Avoid cramming many actions into a short shot. For complex action, give ordered beats
within the shot duration or split into shots. Distinguish subject motion from camera motion.
Include suitable ambience and sound effects in video prompts; respect requests for silence,
no music, no speech or no text. Never invent a reference image that the user did not supply.
References and prompt instructions guide consistency; do not promise exact identity retention.
Use dialogue only for listed characters present in that shot, and narration separately.
Empty dialogue lists and empty narration are allowed. Do not invent dialogue for silent scenes.
Each shot is 2 to 30 seconds, and their durations MUST sum exactly to the requested duration.
Prefer shots of 3 to 8 seconds. Keep dialogue and narration short enough to fit each shot.
Follow the user's story request. The plan is for review; do not claim a film was generated."""


def _comfy_busy_or_unknown() -> bool:
    """Fail conservatively: never clear ComfyUI memory to make room for planning."""
    try:
        response = httpx.get(f"{config.COMFYUI_BASE_URL.rstrip('/')}/queue", timeout=3)
        response.raise_for_status()
        data = response.json()
        return bool(data["queue_running"] or data["queue_pending"])
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return True


def write_plan(prompt: str, seconds: int, model: str | None = None, exact: bool = True) -> dict:
    """Plan a film. `model` overrides the configured planner; with exact=False a plan whose shot
    durations do not add up to `seconds` is returned for the caller to rescale instead of rejected."""
    if not 10 <= seconds <= 180:
        raise ValueError("Plan duration must be between 10 and 180 seconds")
    model = model or config.VIDEO_AGENT_MODEL
    origin = os.getenv("VIDEO_AGENT_OLLAMA_BASE_URL", config.OLLAMA_BASE_URL).rstrip("/")
    options = {"temperature": 0.5, "num_predict": 12000}
    if _comfy_busy_or_unknown():
        # CPU planning leaves ongoing ComfyUI rendering alone. No /free request.
        options["num_gpu"] = 0
    try:
        response = httpx.post(
            f"{origin}/api/chat", timeout=600,
            json={"model": model, "stream": False, "think": False,
                  "format": Plan.model_json_schema(), "keep_alive": 0, "options": options,
                  "messages": [{"role": "system", "content": _SYSTEM},
                               {"role": "user", "content": f"Plan exactly {seconds} seconds.\nStory request:\n{prompt.strip()}"}]},
        )
    except httpx.HTTPError as exc:
        raise RuntimeError("Local Ollama planner is unavailable or timed out. Check Ollama and retry planning; no media was submitted.") from exc
    if response.status_code == 404:
        raise RuntimeError(f"Planner model '{model}' is missing. Install it locally with: ollama pull {model}")
    if response.status_code >= 400:
        raise RuntimeError(f"Local Ollama planner failed (HTTP {response.status_code}). Check model availability and memory, then retry; no media was submitted.")
    try:
        envelope = response.json()
        content = envelope["message"]["content"]
        plan = Plan.model_validate_json(content)
        actual = sum(shot.duration_seconds for shot in plan.shots)
        if exact and actual != seconds:
            raise ValueError(f"shot durations total {actual}s instead of the requested {seconds}s")
    except (ValidationError, ValueError, TypeError, KeyError) as exc:
        if isinstance(exc, ValidationError):
            first = exc.errors(include_input=False)[0]
            reason = f"{'.'.join(map(str, first['loc'])) or 'plan'}: {first['msg']}"
        else:
            reason = str(exc) if isinstance(exc, ValueError) else "missing structured plan content"
        raise RuntimeError(f"The local model returned an invalid cinematic plan ({reason[:240]}). Retry planning or simplify the story; no media was submitted.") from exc
    return {**plan.model_dump(), "model": model}
