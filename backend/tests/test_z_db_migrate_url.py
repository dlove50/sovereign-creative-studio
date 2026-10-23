"""A DATABASE_URL containing "%" must survive Alembic's ConfigParser.

Alembic keeps its options in a ConfigParser, which treats "%" as interpolation
syntax. Setting sqlalchemy.url to a URL containing one raised

    ValueError: invalid interpolation syntax in '...' at position 19

during startup, before anything touched the database, and the message named
neither DATABASE_URL nor the password that caused it.

This is latent on the current SQLite path, which has no "%" in it. It becomes
immediate the moment the database moves anywhere with a password, because a
password containing "@" *must* be URL-encoded as %40 to be a valid URL -- so
the obvious, correct way to write the credential is the thing that breaks.

The test asserts on a round trip rather than on the escaping, because what
matters is that SQLAlchemy is handed back the URL that was put in. An escape
that double-counted would pass an "it contains %%" check and still connect to
the wrong place.
"""
from __future__ import annotations

import os
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")

import pytest  # noqa: E402

from app import db_migrate  # noqa: E402

URLS = [
    # The case that motivated this: "@" in a password encoded as %40.
    "postgresql://dave:p%40ssw0rd@localhost/scs",
    # A literal percent, e.g. a generated password.
    "postgresql://user:100%pure@host:5432/scs",
    # Several, including adjacent ones.
    "mysql://u:a%b%%c@host/db",
    # The shapes already in use, which must be unaffected.
    "sqlite:///./sovereign.db",
    "sqlite:////home/david/sovereign-creative-studio/backend/sovereign.db",
    "postgresql+psycopg://user:plain@localhost/scs",
]


@pytest.mark.parametrize("url", URLS)
def test_the_url_alembic_receives_is_the_one_configured(url, monkeypatch):
    monkeypatch.setattr(db_migrate, "DATABASE_URL", url)
    cfg = db_migrate.get_alembic_config()

    assert cfg.get_main_option("sqlalchemy.url") == url, (
        "Alembic would connect to a different URL than configured")


@pytest.mark.parametrize("url", URLS)
def test_building_the_config_does_not_raise(url, monkeypatch):
    """The original bug was a crash, not a wrong value."""
    monkeypatch.setattr(db_migrate, "DATABASE_URL", url)
    db_migrate.get_alembic_config()


def test_the_script_location_still_points_at_the_migrations_folder(monkeypatch):
    """Guard against the escape being applied to the wrong option."""
    monkeypatch.setattr(db_migrate, "DATABASE_URL", "sqlite:///x.db")
    cfg = db_migrate.get_alembic_config()
    location = cfg.get_main_option("script_location")

    assert location.endswith("migrations")
    assert "%%" not in location


def test_a_percent_in_a_path_based_url_is_preserved(monkeypatch):
    """Storage paths can contain encoded characters too."""
    url = "sqlite:////home/david/My%20Files/sovereign.db"
    monkeypatch.setattr(db_migrate, "DATABASE_URL", url)
    assert db_migrate.get_alembic_config().get_main_option("sqlalchemy.url") == url
