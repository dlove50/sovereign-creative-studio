from datetime import datetime, timezone
import io
import json
import re
import shutil
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import Base, get_db
from .. import config
from ..deps import get_current_user
from ..models import CampaignBundle, CreativeBrief, Project, User, CinematicPlan, CinematicProduction
from ..schemas import (
    BrandKitOut,
    BrandKitUpdate,
    ProjectCreate,
    ProjectOut,
    ProjectWorkspaceOut,
)
from ..services.brand import BRAND_FIELDS, project_brand_kit
from ..services.library import build_library_items
from ..services import brand_spec

router = APIRouter(prefix="/api/projects", tags=["projects"])


class BrandColor(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    hex: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class BrandFont(BaseModel):
    role: str = Field(min_length=1, max_length=40)
    family: str = Field(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9 -]+$")


class BrandVisualsIn(BaseModel):
    colors: list[BrandColor] = Field(default_factory=list, max_length=12)
    fonts: list[BrandFont] = Field(default_factory=list, max_length=10)


@router.get("/{project_id}/brand-visuals")
def get_brand_visuals(project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = get_project(project_id, db, user)
    return brand_spec.load_spec(project.brand_spec_json)


@router.put("/{project_id}/brand-visuals")
def put_brand_visuals(project_id: str, payload: BrandVisualsIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = get_project(project_id, db, user)
    spec = brand_spec.load_spec(project.brand_spec_json)
    spec.update(payload.model_dump())
    spec = brand_spec.clean_spec(spec)
    project.brand_spec_json = json.dumps(spec)
    # Keep existing prompt-based brand use consistent with the visual palette.
    project.primary_colors = ", ".join(c["hex"] for c in spec["colors"]) or None
    db.commit()
    return spec


@router.post("/{project_id}/brand-assets", status_code=201)
def upload_brand_asset(project_id: str, kind: Literal["logos", "assets"] = "logos", file: UploadFile = File(...),
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from PIL import Image, UnidentifiedImageError
    project = get_project(project_id, db, user)
    spec = brand_spec.load_spec(project.brand_spec_json)
    if len(spec[kind]) >= brand_spec.MAX_FILES:
        raise HTTPException(422, "This brand already has 20 files in that category.")
    raw = file.file.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, "Choose a PNG, JPEG, or WebP image under 10 MB.")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"} or image.width * image.height > 20_000_000:
                raise ValueError("Unsupported image")
            converted = image.convert("RGBA")
            converted.thumbnail((2048, 2048))
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, "Choose a valid PNG, JPEG, or WebP image up to 20 megapixels.") from exc
    directory = config.STORAGE_DIR / "brand" / project.id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid.uuid4().hex}.png"
    try:
        converted.save(path)
        spec[kind].append({"name": (file.filename or "Brand image")[:80], "url": f"/api/projects/{project.id}/brand-assets/{path.name}"})
        project.brand_spec_json = json.dumps(spec)
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    finally:
        converted.close()
    return spec


@router.get("/{project_id}/brand-assets/{name}")
def get_brand_asset(project_id: str, name: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = get_project(project_id, db, user)
    if not re.fullmatch(r"[a-f0-9]{32}\.png", name):
        raise HTTPException(404, "Brand image not found")
    spec = brand_spec.load_spec(project.brand_spec_json)
    asset_url = f"/api/projects/{project.id}/brand-assets/{name}"
    if not any(i["url"] == asset_url for kind in ("logos", "assets") for i in spec[kind]):
        raise HTTPException(404, "Brand image not found")
    path = config.STORAGE_DIR / "brand" / project.id / name
    if not path.is_file():
        raise HTTPException(404, "Brand image not found")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, no-store"})


@router.post("/{project_id}/brand-visuals/import-site")
def post_import_brand_site(project_id: str, source_url: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = get_project(project_id, db, user)  # authorize before any network request
    if not source_url.strip():
        raise HTTPException(422, "Enter a web address to import from.")
    try:
        detected = brand_spec.import_site(source_url)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    spec = brand_spec.load_spec(project.brand_spec_json)
    if detected.get("name") and not (project.brand_name or "").strip():
        project.brand_name = str(detected["name"])[:80]
    new_colors, new_fonts = [], []
    seen = {c["hex"] for c in spec["colors"]}
    for value in detected.get("colors", []):
        color = brand_spec.normalize_hex(value)
        if color and color not in seen and len(spec["colors"]) + len(new_colors) < brand_spec.MAX_COLORS:
            index = len(spec["colors"]) + len(new_colors)
            new_colors.append({"name": brand_spec.COLOR_ROLES[index] if index < len(brand_spec.COLOR_ROLES) else "Swatch", "hex": color})
            seen.add(color)
    seen_fonts = {f["family"].lower() for f in spec["fonts"]}
    for family in detected.get("fonts", []):
        safe = " ".join(brand_spec._FONT.sub("", str(family)).split())[:60]
        if safe and safe.lower() not in seen_fonts and safe.lower() not in brand_spec._GENERIC_FONTS and len(spec["fonts"]) + len(new_fonts) < brand_spec.MAX_FONTS:
            used_roles = {f["role"] for f in spec["fonts"] + new_fonts}
            new_fonts.append({"role": next((r for r in brand_spec.FONT_ROLES if r not in used_roles), "Brand font"), "family": safe})
            seen_fonts.add(safe.lower())
    spec["colors"].extend(new_colors)
    spec["fonts"].extend(new_fonts)
    project.brand_spec_json = json.dumps(spec)
    project.primary_colors = ", ".join(c["hex"] for c in spec["colors"]) or None
    db.commit()
    # Candidates require an explicit fetch before becoming private stored assets.
    return {**spec, "imported_from_page": detected.get("url", ""), "imported_colors": len(new_colors),
            "imported_fonts": len(new_fonts), "logo_candidates": detected.get("logo_candidates", [])}


@router.delete("/{project_id}/brand-assets/{name}")
def delete_brand_asset(project_id: str, name: str, kind: Literal["logos", "assets"] = "logos", db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = get_project(project_id, db, user)
    if not re.fullmatch(r"[a-f0-9]{32}\.png", name):
        raise HTTPException(404, "Asset not found")
    spec = brand_spec.load_spec(project.brand_spec_json)
    url = f"/api/projects/{project.id}/brand-assets/{name}"
    if not any(i["url"] == url for i in spec[kind]):
        raise HTTPException(404, "Asset not found")
    spec[kind] = [i for i in spec[kind] if i["url"] != url]
    project.brand_spec_json = json.dumps(spec)
    db.commit()
    if not any(i["url"] == url for category in ("logos", "assets") for i in spec[category]):
        (config.STORAGE_DIR / "brand" / project.id / name).unlink(missing_ok=True)
    return {**spec, "removed": {"kind": kind, "name": name}}


@router.post("/{project_id}/brand-assets/fetch-url", status_code=201)
def post_fetch_remote_image(project_id: str, kind: Literal["logos", "assets"] = "assets", image_url: str = "", db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = get_project(project_id, db, user)
    if len(brand_spec.load_spec(project.brand_spec_json)[kind]) >= brand_spec.MAX_FILES:
        raise HTTPException(422, "This brand category has reached its file limit.")
    if not image_url.strip():
        raise HTTPException(422, "Enter an image URL to download.")
    try:
        raw, extension = brand_spec.fetch_image(image_url)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    upload = UploadFile(filename=f"Imported image{extension}", file=io.BytesIO(raw))
    return upload_brand_asset(project_id, kind, upload, db, user)


@router.get("", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    stmt = (
        select(Project)
        .where(Project.user_id == user.id)
        .order_by(Project.created_at.desc())
    )
    return db.scalars(stmt).all()


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = Project(
        user_id=user.id, name=payload.name, description=payload.description
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/cinematic-outputs")
def list_cinematic_outputs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Index existing owned assemblies without copying media or creating generation jobs."""
    rows = db.execute(select(CinematicPlan, CinematicProduction).join(
        CinematicProduction, CinematicProduction.plan_id == CinematicPlan.id
    ).where(CinematicPlan.user_id == user.id, CinematicProduction.status == "completed")
      .order_by(CinematicPlan.updated_at.desc(), CinematicProduction.revision.desc())).all()
    items = []
    for plan, production in rows:
        url = production.result_url or ""
        if not url.startswith("/storage/videos/"):
            continue
        path = (config.STORAGE_DIR / url.removeprefix("/storage/")).resolve()
        if not path.is_relative_to(config.STORAGE_DIR.resolve()) or not path.is_file():
            continue
        items.append({"id": f"{plan.id}-r{production.revision}", "plan_id": plan.id,
                      "revision": production.revision, "title": plan.plan.get("title") or "Cinematic video",
                      "result_url": url, "status": "completed", "created_at": plan.updated_at})
    return items


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Delete a project or brand system. Only an empty one: if anything was made in it (videos, images, scenes,
    briefs, collections...) the request is refused and says what is still there, so nothing is lost by accident."""
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    attached: list[str] = []
    for table in Base.metadata.sorted_tables:
        for key in table.foreign_keys:
            if key.column.table.name == "projects" and table.name != "projects":
                count = db.scalar(select(func.count()).select_from(table).where(table.c[key.parent.name] == project_id)) or 0
                if count:
                    attached.append(f"{table.name.replace('_', ' ')} ({count})")
    if attached:
        raise HTTPException(status_code=409, detail="Still attached: " + ", ".join(attached) + ". Delete those first.")
    shutil.rmtree(config.STORAGE_DIR / "brand" / project_id, ignore_errors=True)
    db.delete(project)
    db.commit()


@router.get("/{project_id}/brand-kit", response_model=BrandKitOut)
def get_brand_kit(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project_brand_kit(project)


@router.put("/{project_id}/brand-kit", response_model=BrandKitOut)
def update_brand_kit(
    project_id: str,
    payload: BrandKitUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    for field in BRAND_FIELDS:
        value = getattr(payload, field)
        cleaned = value.strip() if isinstance(value, str) else value
        setattr(project, field, cleaned or None)
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(project)
    return project_brand_kit(project)


@router.get("/{project_id}/workspace", response_model=ProjectWorkspaceOut)
def get_project_workspace(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    briefs = db.scalars(
        select(CreativeBrief)
        .where(CreativeBrief.project_id == project.id)
        .order_by(CreativeBrief.updated_at.desc())
    ).all()

    bundles = db.scalars(
        select(CampaignBundle)
        .where(CampaignBundle.project_id == project.id)
        .order_by(CampaignBundle.created_at.desc())
    ).all()

    items = build_library_items(db, user, project.id)
    by_type = {
        "upload": [item for item in items if item.type == "upload"],
        "processed_asset": [
            item for item in items if item.type == "processed_asset"
        ],
        "scene": [item for item in items if item.type == "scene"],
        "copy": [item for item in items if item.type == "copy"],
        "video": [item for item in items if item.type == "video"],
        "campaign": [item for item in items if item.type == "campaign"],
    }
    counts = {key: len(value) for key, value in by_type.items()}
    latest = max(
        [project.updated_at or project.created_at, *[item.created_at for item in items]]
    )

    return ProjectWorkspaceOut(
        id=project.id,
        name=project.name,
        description=project.description,
        created_at=project.created_at,
        brand_kit=project_brand_kit(project),
        creative_briefs=briefs,
        campaign_bundles=bundles,
        uploaded_assets=by_type["upload"],
        processed_assets=by_type["processed_asset"],
        product_scenes=by_type["scene"],
        copy_generations=by_type["copy"],
        video_generations=by_type["video"],
        campaign_items=by_type["campaign"],
        counts_by_type=counts,
        latest_activity_at=latest,
    )
