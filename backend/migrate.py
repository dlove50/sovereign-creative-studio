"""Dev convenience: apply database migrations to the latest revision.

Usage (from the backend/ directory, venv active):
    python migrate.py

Equivalent to `alembic upgrade head`, but uses the app's DATABASE_URL and applies
the same legacy-database self-healing as app startup.
"""
from app.db_migrate import upgrade_to_head

if __name__ == "__main__":
    upgrade_to_head()
    print("Database is up to date (head).")
