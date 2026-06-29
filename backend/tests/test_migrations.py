"""Migration tests. Prove that databases can be brought to the latest schema
without deletion — including an *older* SQLite database that predates the
mask_url/mode columns."""
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

BACKEND = Path(__file__).resolve().parent.parent
MIGRATIONS = BACKEND / "migrations"


def _cfg(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _columns(engine, table: str) -> set[str]:
    return {col["name"] for col in sa.inspect(engine).get_columns(table)}


def _current_revision(engine) -> str:
    with engine.connect() as conn:
        return conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()


def test_old_db_upgrades_without_deletion(tmp_path):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    cfg = _cfg(url)

    # Build an OLD database: baseline schema only (no mask_url / mode).
    command.upgrade(cfg, "0001")
    engine = sa.create_engine(url)
    assert "mask_url" not in _columns(engine, "product_assets")
    assert "mode" not in _columns(engine, "product_scene_generations")

    # Seed data that must survive the upgrade.
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO users (id,email,name,credits,created_at) "
                "VALUES ('u1','a@b.c','A',100,'2026-01-01 00:00:00')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO projects (id,user_id,name,created_at,updated_at) "
                "VALUES ('p1','u1','P','2026-01-01 00:00:00','2026-01-01 00:00:00')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO product_assets "
                "(id,user_id,project_id,filename,original_url,status,created_at,updated_at) "
                "VALUES ('a1','u1','p1','x.png','/storage/uploads/x.png','uploaded',"
                "'2026-01-01 00:00:00','2026-01-01 00:00:00')"
            )
        )

    # Upgrade to head — must add the new columns without dropping data.
    command.upgrade(cfg, "head")

    assert "mask_url" in _columns(engine, "product_assets")
    assert "mode" in _columns(engine, "product_scene_generations")
    assert "brand_voice" in _columns(engine, "projects")
    assert "asset_collections" in sa.inspect(engine).get_table_names()
    assert "production_projects" in sa.inspect(engine).get_table_names()
    assert "product_scene_id" in _columns(engine, "shots")
    assert "video_id" in _columns(engine, "shots")
    assert {"role", "status", "notes", "updated_at"} <= _columns(engine, "users")
    assert {
        "transaction_type",
        "related_feature",
        "related_id",
        "status",
        "note",
    } <= _columns(engine, "credit_transactions")
    assert {"provider", "provider_task_id", "credits_cost", "quality_preset"} <= _columns(
        engine, "video_generations"
    )
    assert {
        "provider",
        "provider_task_id",
        "provider_model",
        "source_image_url",
    } <= _columns(engine, "generations")
    assert "transcription_jobs" in sa.inspect(engine).get_table_names()
    assert {
        "source_video_url",
        "transcript_text",
        "summary_text",
        "error_message",
        "credits_cost",
    } <= _columns(engine, "transcription_jobs")
    assert {
        "avatar_preset",
        "avatar_width",
        "avatar_height",
        "avatar_frames",
        "avatar_steps",
        "avatar_cfg",
        "avatar_runtime_seconds",
    } <= _columns(engine, "avatar_jobs")
    assert _current_revision(engine) == "0024"
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT filename, mask_url FROM product_assets WHERE id='a1'")
        ).one()
    assert row[0] == "x.png"
    assert row[1] is None  # new column defaults to NULL
    engine.dispose()


def test_fresh_db_upgrades_to_head(tmp_path):
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    command.upgrade(_cfg(url), "head")

    engine = sa.create_engine(url)
    tables = set(sa.inspect(engine).get_table_names())
    assert {
        "users",
        "projects",
        "generations",
        "product_assets",
        "product_scene_generations",
        "credit_transactions",
        "alembic_version",
    } <= tables
    assert "mask_url" in _columns(engine, "product_assets")
    assert "mode" in _columns(engine, "product_scene_generations")
    assert "brand_voice" in _columns(engine, "projects")
    assert "asset_collections" in tables
    assert "production_projects" in tables
    assert "product_scene_id" in _columns(engine, "shots")
    assert "video_id" in _columns(engine, "shots")
    assert {"role", "status", "notes", "updated_at"} <= _columns(engine, "users")
    assert {
        "transaction_type",
        "related_feature",
        "related_id",
        "status",
        "note",
    } <= _columns(engine, "credit_transactions")
    assert {
        "avatar_preset",
        "avatar_width",
        "avatar_height",
        "avatar_frames",
        "avatar_steps",
        "avatar_cfg",
        "avatar_runtime_seconds",
    } <= _columns(engine, "avatar_jobs")
    engine.dispose()


def test_pre_baseline_db_raises_clear_error(tmp_path, monkeypatch):
    """A database older than the 0001 baseline (has users, no product_assets)
    can't be auto-upgraded — startup must fail with a clear, actionable error."""
    import app.db_migrate as db_migrate

    url = f"sqlite:///{tmp_path / 'ancient.db'}"
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE users (id TEXT PRIMARY KEY)"))

    monkeypatch.setattr(db_migrate, "engine", engine)
    monkeypatch.setattr(db_migrate, "DATABASE_URL", url)
    with pytest.raises(RuntimeError, match="predates the migration baseline"):
        db_migrate.upgrade_to_head()
    engine.dispose()


def test_legacy_create_all_db_can_be_stamped_and_upgraded(tmp_path):
    """A pre-Alembic DB created by Base.metadata.create_all (full current schema,
    no alembic_version) can be stamped at baseline and upgraded safely."""
    from app.database import Base
    import app.models  # noqa: F401 - register tables on Base.metadata

    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    engine = sa.create_engine(url)
    Base.metadata.create_all(engine)
    assert "alembic_version" not in sa.inspect(engine).get_table_names()

    cfg = _cfg(url)
    command.stamp(cfg, "0001")
    # 0002 add-columns are inspector-guarded, so this is a safe no-op here.
    command.upgrade(cfg, "head")

    assert _current_revision(engine) == "0024"
    assert "mask_url" in _columns(engine, "product_assets")
    assert "brand_voice" in _columns(engine, "projects")
    assert "asset_collections" in sa.inspect(engine).get_table_names()
    assert "production_projects" in sa.inspect(engine).get_table_names()
    assert "product_scene_id" in _columns(engine, "shots")
    assert "video_id" in _columns(engine, "shots")
    assert {"role", "status", "notes", "updated_at"} <= _columns(engine, "users")
    assert {
        "transaction_type",
        "related_feature",
        "related_id",
        "status",
        "note",
    } <= _columns(engine, "credit_transactions")
    assert {
        "avatar_preset",
        "avatar_width",
        "avatar_height",
        "avatar_frames",
        "avatar_steps",
        "avatar_cfg",
        "avatar_runtime_seconds",
    } <= _columns(engine, "avatar_jobs")
    assert {"provider", "provider_task_id", "credits_cost", "quality_preset"} <= _columns(
        engine, "video_generations"
    )
    assert {
        "provider",
        "provider_task_id",
        "provider_model",
        "source_image_url",
    } <= _columns(engine, "generations")
    engine.dispose()
