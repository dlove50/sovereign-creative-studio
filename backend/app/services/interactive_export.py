"""Portable SCORM 1.2 lessons with no runtime dependency on the studio."""
from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import InteractiveVideo, Movie, VideoGeneration
from .interactive import clean_nodes, load_nodes
from .source_validation import VIDEO_EXTS, validate_source_media_url
from .transcription import resolve_storage_url

MAX_MEDIA_BYTES = 512 * 1024 * 1024
STATIC = Path(__file__).with_name("scorm")


def export_lesson(db: Session, item: InteractiveVideo, destination: Path) -> None:
    nodes, start = clean_nodes(load_nodes(item.nodes_json), item.start_node_id)
    if not nodes:
        raise ValueError("Add at least one lesson step before exporting.")
    reachable, pending = set(), [start]
    by_id = {n["id"]: n for n in nodes}
    while pending:
        node_id = pending.pop()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        pending.extend(c["next"] for c in by_id[node_id]["choices"])
    if not any(not by_id[i]["choices"] for i in reachable):
        raise ValueError("Connect a final step with no choices so learners can complete the lesson.")
    # A final step on one branch does not rescue learners trapped on another.
    can_finish = {i for i in reachable if not by_id[i]["choices"]}
    while True:
        predecessors = {i for i in reachable if any(
            c["next"] in can_finish for c in by_id[i]["choices"])}
        expanded = can_finish | predecessors
        if expanded == can_finish:
            break
        can_finish = expanded
    if reachable - can_finish:
        raise ValueError("Every reachable step needs a path to a final step. Add an exit to branches that loop forever.")
    assets: dict[str, tuple[Path, str]] = {}
    total = 0
    for node in nodes:
        url = node["video_url"]
        if not url:
            if not (node.get("body") or node.get("question")):
                raise ValueError("Each exported step needs a video, instructions, or a question.")
            continue
        if url not in assets:
            validate_source_media_url(url, allowed_exts=VIDEO_EXTS)
            owned = db.scalar(select(VideoGeneration.id).where(
                VideoGeneration.user_id == item.user_id, VideoGeneration.status == "completed",
                VideoGeneration.deleted_at.is_(None), VideoGeneration.result_url == url))
            owned = owned or db.scalar(select(Movie.id).where(
                Movie.user_id == item.user_id, Movie.status == "completed",
                Movie.deleted_at.is_(None), Movie.output_video_path == url))
            if not owned:
                raise ValueError("An attached clip is no longer available to this lesson's owner.")
            try:
                source = resolve_storage_url(url)
            except RuntimeError as exc:
                raise ValueError("An attached clip is missing. Restore it before exporting.") from exc
            size = source.stat().st_size
            total += size
            if not size or total > MAX_MEDIA_BYTES:
                raise ValueError("Export media must be nonempty and total no more than 512 MB.")
            assets[url] = (source, f"media/clip-{len(assets) + 1}{source.suffix.lower()}")
        node["video_url"] = assets[url][1]
    files = ["index.html", "player.js", "lesson.js"] + [a[1] for a in assets.values()]
    ims = "http://www.imsproject.org/xsd/imscp_rootv1p1p2"
    adl = "http://www.adlnet.org/xsd/adlcp_rootv1p2"
    ET.register_namespace("", ims)
    ET.register_namespace("adlcp", adl)
    def child(parent, tag, text=None, **attrs):
        result = ET.SubElement(parent, f"{{{ims}}}{tag}", attrs)
        result.text = text
        return result
    manifest = ET.Element(f"{{{ims}}}manifest", {"identifier": f"sovereign-{item.id}", "version": "1.0"})
    metadata = child(manifest, "metadata")
    child(metadata, "schema", "ADL SCORM")
    child(metadata, "schemaversion", "1.2")
    org = child(child(manifest, "organizations", default="course"), "organization", identifier="course")
    child(org, "title", item.title)
    sco = child(org, "item", identifier="lesson", identifierref="lesson-resource")
    child(sco, "title", item.title)
    resource = child(child(manifest, "resources"), "resource", identifier="lesson-resource", type="webcontent", href="index.html")
    resource.set(f"{{{adl}}}scormtype", "sco")
    for name in files:
        child(resource, "file", href=name)
    data = json.dumps({"id": item.id, "title": item.title, "nodes": nodes, "start": start}, ensure_ascii=True).replace("<", "\\u003c")
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        archive.writestr("imsmanifest.xml", ET.tostring(manifest, encoding="utf-8", xml_declaration=True))
        archive.writestr("lesson.js", f"window.SOVEREIGN_LESSON = {data};\n")
        for name in ("index.html", "player.js"):
            archive.write(STATIC / name, name)
        for source, name in assets.values():
            archive.write(source, name)
