import io
import json
import shutil
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from app.models import Movie
from app.services import interactive_export
from test_cinematic_plan_storage import stored_api


def test_export_is_portable_and_escapes_user_text(stored_api):
    client, _, _ = stored_api
    payload = {"title": "<script> & Lesson", "nodes": [{"id": "end", "body": "</script><script>alert(1)</script>"}]}
    item = client.post("/api/interactive", json=payload).json()
    response = client.post(f"/api/interactive/{item['id']}/export/scorm")
    assert response.status_code == 200, response.text
    with ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {"imsmanifest.xml", "index.html", "player.js", "lesson.js"}
        manifest = ET.fromstring(archive.read("imsmanifest.xml"))
        ns = {"i": "http://www.imsproject.org/xsd/imscp_rootv1p1p2"}
        assert manifest.find("i:metadata/i:schemaversion", ns).text == "1.2"
        assert manifest.find("i:organizations/i:organization/i:title", ns).text == payload["title"]
        assert "</script>" not in archive.read("lesson.js").decode()
        assert b"\\u003c/script>" in archive.read("lesson.js")
        for file in manifest.findall(".//i:file", ns):
            assert file.attrib["href"] in archive.namelist()


def test_export_deduplicates_owned_media_and_rechecks_ownership(stored_api, tmp_path, monkeypatch):
    client, _, sessions = stored_api
    media = tmp_path / "original.mp4"
    media.write_bytes(b"test-owned-media")
    monkeypatch.setattr(interactive_export, "resolve_storage_url", lambda _: media)
    with sessions() as db:
        db.add(Movie(id="clip", user_id="alice", title="Owned", status="completed", output_video_path="/storage/videos/clip.mp4"))
        db.commit()
    nodes = [{"id": "a", "video_url": "/storage/videos/clip.mp4", "choices": [{"label": "Next", "next": "b"}]},
             {"id": "b", "video_url": "/storage/videos/clip.mp4"}]
    made = client.post("/api/interactive", json={"nodes": nodes})
    assert made.status_code == 201, made.text
    url = f"/api/interactive/{made.json()['id']}/export/scorm"
    with ZipFile(io.BytesIO(client.post(url).content)) as archive:
        assert [n for n in archive.namelist() if n.startswith("media/")] == ["media/clip-1.mp4"]
        assert archive.read("media/clip-1.mp4") == media.read_bytes()
        assert b"/storage/" not in archive.read("lesson.js")
    with sessions() as db:
        db.get(Movie, "clip").user_id = "bob"
        db.commit()
    assert client.post(url).status_code == 422


@pytest.mark.parametrize("nodes", [[], [{"id":"empty"}], [{"id":"loop", "body":"Retry", "choices":[{"label":"Again", "next":"loop"}]}]])
def test_incomplete_lessons_cannot_export(stored_api, nodes):
    client, _, _ = stored_api
    made = client.post("/api/interactive", json={"nodes": nodes}).json()
    assert client.post(f"/api/interactive/{made['id']}/export/scorm").status_code == 422


def test_scorm_runtime_resume_score_and_lifecycle():
    node = shutil.which("node")
    assert node, "Node is required for the SCORM runtime unit test"
    result = subprocess.run([node, str(Path(__file__).with_name("scorm_runtime.cjs")), str(interactive_export.STATIC / "player.js")], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("retry_target, expected", [("trap", 422), ("start", 200)])
def test_export_requires_escape_from_each_reachable_branch(stored_api, retry_target, expected):
    client, _, _ = stored_api
    nodes = [
        {"id": "start", "body": "Choose", "choices": [
            {"label": "Finish", "next": "end"}, {"label": "Retry", "next": "trap"}]},
        {"id": "trap", "body": "Try again", "choices": [{"label": "Continue", "next": retry_target}]},
        {"id": "end", "body": "Complete"},
    ]
    made = client.post("/api/interactive", json={"nodes": nodes})
    assert made.status_code == 201, made.text
    response = client.post(f"/api/interactive/{made.json()['id']}/export/scorm")
    assert response.status_code == expected, response.text if expected != 200 else ""


def _run_runtime(script, player):
    node = shutil.which("node")
    assert node, "Node is required for the lesson runtime tests"
    result = subprocess.run([node, str(Path(__file__).with_name(script)), str(interactive_export.STATIC / player)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_scorm_2004_runtime_resume_score_and_lifecycle():
    _run_runtime("scorm2004_runtime.cjs", "player2004.js")


def test_xapi_runtime_statements_resume_and_preview():
    _run_runtime("xapi_runtime.cjs", "playerxapi.js")


def test_scorm_2004_and_xapi_packages_have_their_own_manifests_and_players(stored_api):
    client, _, _ = stored_api
    item = client.post("/api/interactive", json={"title": "Safety & Basics", "nodes": [{"id": "end", "body": "Done"}]}).json()

    response = client.post(f"/api/interactive/{item['id']}/export/scorm2004")
    assert response.status_code == 200, response.text
    assert "sovereign-lesson-scorm2004.zip" in response.headers["content-disposition"]
    with ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {"imsmanifest.xml", "index.html", "player2004.js", "lesson.js"}
        manifest = ET.fromstring(archive.read("imsmanifest.xml"))
        ns = {"i": "http://www.imsglobal.org/xsd/imscp_v1p1"}
        assert manifest.find("i:metadata/i:schemaversion", ns).text == "2004 4th Edition"
        assert manifest.find("i:organizations/i:organization/i:title", ns).text == "Safety & Basics"
        resource = manifest.find("i:resources/i:resource", ns)
        assert resource.attrib["{http://www.adlnet.org/xsd/adlcp_v1p3}scormtype"] == "sco"
        assert {f.attrib["href"] for f in manifest.findall(".//i:file", ns)} == {"index.html", "player2004.js", "lesson.js"}
        assert b'"format": "scorm2004"' in archive.read("lesson.js") or b'"format":"scorm2004"' in archive.read("lesson.js")

    response = client.post(f"/api/interactive/{item['id']}/export/xapi")
    assert response.status_code == 200, response.text
    with ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {"tincan.xml", "index.html", "playerxapi.js", "lesson.js"}
        tincan = ET.fromstring(archive.read("tincan.xml"))
        ns = {"t": "http://projecttincan.com/tincan.xsd"}
        activity = tincan.find("t:activities/t:activity", ns)
        assert activity.attrib["id"] == f"urn:sovereign:lesson:{item['id']}"
        assert activity.find("t:name", ns).text == "Safety & Basics" and activity.find("t:launch", ns).text == "index.html"
        assert f"urn:sovereign:lesson:{item['id']}".encode() in archive.read("lesson.js")

    assert client.post(f"/api/interactive/{item['id']}/export/scorm12").status_code == 200
    assert client.post(f"/api/interactive/{item['id']}/export/pdf").status_code == 404
