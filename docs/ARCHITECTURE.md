# Sovereign Creative Studio — Architecture

Sovereign Creative Studio is a private local monorepo designed to keep routine
creative work, media, accounts, and model execution on one Windows machine.

## Runtime stack

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Web UI | Next.js 14, React, TypeScript, Tailwind | Creator and admin workflows |
| API | FastAPI, Pydantic | Validation, authorization, orchestration |
| Persistence | SQLAlchemy, SQLite, Alembic | Accounts, projects, jobs, credits, metadata |
| Media storage | Local filesystem | Uploads, generated media, exports, backups |
| Image/video runtime | ComfyUI | Local diffusion and video workflows |
| Text runtime | Ollama | Local copy and summaries |
| Speech runtime | Piper, Faster Whisper, FFmpeg | Voice, transcription, media assembly |

## Request flow

1. The browser calls relative `/api/...` routes.
2. Next.js rewrites requests to FastAPI and preserves the first-party cookie.
3. FastAPI validates the payload and resolves the authenticated user.
4. A router delegates work to a service or provider adapter.
5. Long-running work creates a database job and runs through a monitored worker.
6. Output files are stored locally and returned through `/storage/...` URLs.
7. Completed assets become available to projects and downstream tools.

## Frontend organization

- `src/app/` contains route entry points.
- `src/components/` contains feature views and reusable media/UI components.
- `src/components/video-studio/` contains video history and storyboard panels.
- `src/components/project-workspace/` contains workspace and brief sections.
- `src/lib/api.ts` is the stable API facade.
- `src/lib/api/` contains transport plus admin, project, media, and production clients.
- `src/lib/types.ts` defines browser-side contracts.

## Backend organization

- `app/routers/` owns HTTP endpoints and authorization boundaries.
- `app/services/` owns orchestration, storage, jobs, backups, and readiness.
- provider folders implement common image, video, copy, and scene interfaces.
- `app/models.py` contains SQLAlchemy persistence models.
- `app/schemas.py` is the stable Pydantic compatibility facade.
- `schemas_core.py`, `schemas_workflows.py`, `schemas_admin.py`, and
  `schemas_accounts.py` contain focused contract families.
- `migrations/` contains Alembic history.
- `workflows/` contains ComfyUI API-format templates.

## Identity and authorization

Passwords use salted PBKDF2 hashes. Sessions use an HTTP-only cookie containing
an HMAC-signed token; the signing secret lives in the excluded secrets folder.

The owner may select a family user for attribution. That selection is not an
authentication mechanism: non-admin users cannot gain access by changing the
`X-SCS-Family-User-Id` header.

`OWNER_FALLBACK_ENABLED` is for private loopback use and must be disabled before
network or public exposure. Signup, origins, cookies, and provider access must
also be reviewed before exposure.

## Providers and local-first boundaries

Image, copy, video, scene, avatar, transcription, and voice features use provider
abstractions. Local providers are the normal V1 path. Premium providers are
server-configured, masked in responses, excluded from backups, and disabled until
the owner enables them.

Provider failures return setup/runtime messages and do not charge credits.
Successful billable operations write a ledger entry only after output acceptance.

## Persistence and recovery

SQLite stores metadata and ledger state; binary media stays on the filesystem.
Migrations run at startup. Backups use SQLite's online backup API rather than
copying an active database file.

Long-running work has explicit statuses. Startup and admin tools recover or mark
interrupted jobs without deleting audit history.

## Testing strategy

The backend suite covers contracts, migrations, authorization, credits,
providers, storage, backups, workflows, and failures. Frontend production builds
validate TypeScript, lint, routes, and static generation. Playwright covers local
end-to-end model flows.

See [RECOVERY_AND_MAINTENANCE.md](RECOVERY_AND_MAINTENANCE.md) for release checks.
