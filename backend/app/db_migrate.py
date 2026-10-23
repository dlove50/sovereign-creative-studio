"""Programmatic Alembic runner shared by app startup and the dev migrate script.

Handles three database states:
  * brand new            -> upgrade head creates everything.
  * legacy create_all DB -> no alembic_version but app tables exist: stamp the
                            baseline, then upgrade head (0002 add-columns are
                            inspector-guarded, so this is safe even if the legacy
                            DB already had those columns).
  * already migrated     -> upgrade head is a no-op.
"""
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from .config import BASE_DIR, DATABASE_URL
from .database import engine

_BASELINE_REVISION = "0001"


def get_alembic_config() -> Config:
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    # Alembic stores options in a ConfigParser, which treats "%" as
    # interpolation syntax. A DATABASE_URL containing one -- which any
    # URL-encoded password has, since "@" in a password must be written %40 --
    # raised "invalid interpolation syntax" during startup, before anything
    # touched the database, and the error named neither DATABASE_URL nor the
    # password. Doubling it is the documented escape; ConfigParser restores
    # the single "%" on read.
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    return cfg


def upgrade_to_head() -> None:
    cfg = get_alembic_config()
    tables = set(inspect(engine).get_table_names())
    if "alembic_version" not in tables and "users" in tables:
        # Pre-Alembic database created by the old create_all. It can only be
        # stamped at the baseline if it actually matches it; "product_assets" is
        # a baseline table, so its absence means the DB predates the baseline and
        # has no clean upgrade path.
        if "product_assets" not in tables:
            raise RuntimeError(
                "This database predates the migration baseline and cannot be "
                "auto-upgraded. Back up any data, then delete it (e.g. "
                "backend/sovereign.db) so it is recreated at the latest schema."
            )
        # Tell Alembic the baseline already exists, then apply later migrations.
        command.stamp(cfg, _BASELINE_REVISION)
    command.upgrade(cfg, "head")
