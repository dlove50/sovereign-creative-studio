# Sovereign Creative Studio — Recovery and Maintenance

Use this guide for backups, restoration, stale jobs, storage cleanup, database
migrations, and release verification.

## Backups

Create backups from **Admin → Backup & Recovery**. Each timestamped ZIP contains:

- a transactionally consistent SQLite snapshot;
- generated app storage except excluded transient and secret directories;
- workflow templates;
- the project README;
- a manifest containing the included file list and safe configuration summary.

SQLite is captured with its online backup API, so committed WAL data is included
while the studio remains running. The snapshot must pass an integrity check, and
the completed ZIP is moved into place atomically. A failed or partial archive is
not published as a restore point.

Backups intentionally exclude secrets, environment files, provider keys,
scratch/cache directories, earlier backups, and large external ComfyUI models.
Store a second copy of important backups away from the application data folder.

## Manual restore

Restore only while the studio, backend, and ComfyUI jobs are stopped.

1. Copy the current `backend/sovereign.db` and `backend/storage/` somewhere safe.
2. Inspect `backup_manifest.json` inside the chosen ZIP.
3. Extract the ZIP into a temporary directory.
4. Copy the backed-up database, storage, and workflows into matching locations.
5. Do not overwrite `.env` or `backend/storage/secrets/`.
6. Start the backend; Alembic will upgrade an older compatible schema.
7. Open Status, Projects, Assets, and Backup & Recovery to validate the restore.
8. Run the backend suite if the restore follows a code or migration change.

Never restore by deleting the live folders first. Keep the pre-restore copy until
normal use has been confirmed.

## Startup and port recovery

| Service | Endpoint |
| --- | --- |
| Frontend | `http://localhost:3000` |
| Backend | `http://127.0.0.1:8000` |
| ComfyUI | `http://127.0.0.1:8001` |

For a normal cleanup:

```powershell
python tools/local_launcher.py clean
```

For detailed service recovery, see
[LOCAL_STARTUP_AND_RECOVERY.md](LOCAL_STARTUP_AND_RECOVERY.md).

## Interrupted and stale jobs

In-process workers stop when the backend exits. Startup recovery marks supported
jobs that were left running as failed instead of allowing permanent spinners.
Use **Admin → Job Monitor** for remaining stale or legacy records.

Before marking work failed or cancelled, check whether ComfyUI is still working,
look for a completed output, and confirm the job exceeded its expected runtime.
Use targeted stale-job actions instead of deleting database records. Failed and
cancelled jobs do not consume credits.

## Storage cleanup and trash

Use the Storage page to create a cleanup plan before executing cleanup.

- Prefer soft-delete/trash actions for user-visible assets.
- Do not manually delete files still referenced by projects or jobs.
- Empty trash only after checking recent projects and exports.
- Preserve backups and external models separately.

Malformed pytest output directories can be removed after confirming they are
untracked and contain only generated test databases or media. Keep reusable tools
and intentional reference assets outside that cleanup decision.

## Database migrations

The backend upgrades the database to the current Alembic head during startup.
Manual migration from the backend directory:

```powershell
.\.venv\Scripts\python.exe migrate.py
```

Create a backup and stop active generation jobs before migration work. Never
reset the database as a first-line recovery action.

## Verification commands

```powershell
# backend
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp-final -p no:cacheprovider

# frontend
npm.cmd run typecheck
npm.cmd run build
```

Run `git diff --check` before staging a release commit.
