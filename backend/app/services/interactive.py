"""Interactive (branching) videos: a graph of clips where the viewer's choice picks the next clip."""
from __future__ import annotations

import json

MAX_NODES = 40
MAX_CHOICES = 4
LABEL_LIMIT = 80


def load_nodes(raw: str) -> list[dict]:
    try:
        nodes = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return nodes if isinstance(nodes, list) else []


def clean_nodes(nodes: list[dict], start_node_id: str | None) -> tuple[list[dict], str | None]:
    """Validate and normalise the graph. Raises ValueError with a plain-language message."""
    if len(nodes) > MAX_NODES:
        raise ValueError(f"An interactive video can have at most {MAX_NODES} clips.")
    ids = [str(n.get("id") or "").strip()[:32] for n in nodes]
    if any(not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("Every clip needs its own id.")
    known = set(ids)
    cleaned = []
    for node, node_id in zip(nodes, ids):
        url = str(node.get("video_url") or "").strip()
        if url and not url.startswith("/storage/"):
            raise ValueError("Clips must be videos made in this studio (their address starts with /storage/).")
        choices = []
        for choice in (node.get("choices") or [])[:MAX_CHOICES]:
            label = str(choice.get("label") or "").strip()[:LABEL_LIMIT]
            target = str(choice.get("next") or "").strip()
            if not label:
                raise ValueError(f"A choice in clip {node.get('title') or node_id} has no label.")
            if target not in known:
                raise ValueError(f"The choice {label} points at a clip that does not exist.")
            choices.append({"label": label, "next": target})
        cleaned.append({"id": node_id, "title": str(node.get("title") or "").strip()[:120], "video_url": url, "choices": choices})
    start = (start_node_id or "").strip() or (ids[0] if ids else None)
    if start is not None and start not in known:
        raise ValueError("The starting clip does not exist.")
    return cleaned, start
