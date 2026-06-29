"""Creative brief helpers: prompt context + a readable summary.

A brief is a lightweight campaign plan. When one is attached to a generation
request, a compact ``Creative brief:`` block is appended to the prompt so scenes,
copy, and videos stay on-plan."""
from sqlalchemy.orm import Session

from ..models import CreativeBrief

_CONTEXT_FIELDS = [
    ("campaign_goal", "Goal"),
    ("target_channels", "Channels"),
    ("deliverables", "Deliverables"),
    ("key_messages", "Key messages"),
    ("creative_direction", "Creative direction"),
    ("reference_notes", "Reference notes"),
]


def brief_context(brief: CreativeBrief) -> str | None:
    """A compact single-line context string for prompt injection."""
    parts = [f"Title: {brief.title.strip()}"] if brief.title else []
    for field, label in _CONTEXT_FIELDS:
        value = (getattr(brief, field) or "").strip()
        if value:
            parts.append(f"{label}: {value}")
    return "; ".join(parts) or None


def with_brief_context(prompt: str, brief: CreativeBrief | None) -> str:
    if brief is None:
        return prompt
    context = brief_context(brief)
    if not context:
        return prompt
    return f"{prompt}\n\nCreative brief: {context}"


def load_project_brief(
    db: Session, project_id: str, brief_id: str
) -> CreativeBrief | None:
    """Load a brief that belongs to the given project, or None."""
    brief = db.get(CreativeBrief, brief_id)
    if brief is None or brief.project_id != project_id:
        return None
    return brief


def brief_summary(brief: CreativeBrief) -> str:
    """A readable, copy-pasteable multi-line summary of the brief."""
    lines = [f"# {brief.title}", f"Status: {brief.status}"]
    for field, label in _CONTEXT_FIELDS:
        value = (getattr(brief, field) or "").strip()
        if value:
            lines.append(f"\n{label}:\n{value}")
    if brief.selected_asset_ids:
        lines.append(f"\nSelected assets: {len(brief.selected_asset_ids)}")
    return "\n".join(lines)
