# Sovereign Creative Studio

Sovereign Creative Studio is a private, local-first AI production workspace for
David and family. It combines image, video, copy, voice, transcription, avatar,
project, asset, and administration workflows in one Windows application.

## V1 release candidate

The studio is in V1 release-candidate status for private family use. The current
priority is stable normal operation, reliable backups, safe recovery, and a clear
creator workflow. Do not expose the application publicly without a dedicated
security-hardening pass.

Start the normal local stack with:

```text
Start-Sovereign-Creative-Studio.bat
```

Then open `http://localhost:3000`. Stop it with
`Stop-Sovereign-Creative-Studio.bat`.

## Documentation

The former all-in-one README has been replaced by focused guides:

| Guide | Use it for |
| --- | --- |
| [Operator guide](docs/OPERATOR_GUIDE.md) | Daily startup, creative workflows, accounts, credits, and admin routines |
| [Recovery and maintenance](docs/RECOVERY_AND_MAINTENANCE.md) | Backups, restore, stale jobs, cleanup, migrations, and verification |
| [Architecture](docs/ARCHITECTURE.md) | Runtime design, module boundaries, security, providers, and persistence |
| [Model setup and dependency manifest](docs/MODEL_AND_DEPENDENCY_MANIFEST.md) | ComfyUI models, FFmpeg, Ollama, Piper, Whisper, and machine restoration |
| [Detailed startup recovery](docs/LOCAL_STARTUP_AND_RECOVERY.md) | Service-by-service Windows startup troubleshooting |

## Recommended workflow

The Home page leads with **Quick Chain**, which guides a creator from a prompt to
an image, video, optional upscale, optional voice, transcription, summary, and
finished downloads. Direct studios remain available for experienced users.

Completed V1 capabilities include:

- local ComfyUI image generation and reference-image editing;
- Flux Kontext product scenes and transformation modes;
- local LTX and approved Wan video workflows;
- local Whisper transcription and Qwen summaries;
- Piper voice generation and Wan InfiniteTalk avatars;
- Asset Library, collections, projects, brand kits, and creative briefs;
- campaign, storyboard, film, production, and export studios;
- family accounts, credits, ledger, job monitoring, storage cleanup, and trash;
- backups, model readiness, workflow management, and service status;
- optional owner-enabled premium image and video providers.

## Local defaults

| Area | V1 default |
| --- | --- |
| Image generation | `GENERATOR_BACKEND=comfyui` |
| Product scenes | `PRODUCT_SCENE_BACKEND=comfyui` |
| Product-scene model | `PRODUCT_SCENE_MODEL=flux-kontext` |
| Copy and summaries | `COPY_BACKEND=local-qwen` |
| Video | `VIDEO_BACKEND=comfyui`, `COMFYUI_VIDEO_ENGINE=ltx` |
| Transcription | `TRANSCRIPTION_BACKEND=local_whisper` |
| Voice | `VOICE_BACKEND=piper` |
| Talking avatar | `AVATAR_BACKEND=comfyui_wan_infinite_talk` |

OpenAI image and Seedance/C-Dance video providers are optional, disabled by
default, and configured only by the owner in `/admin/integrations`.

## Credits

| Feature | Credits charged on success |
| --- | ---: |
| Local LTX video | 10 |
| Optional Seedance/C-Dance video | 30 |
| Local Whisper transcription | 5 |
| Qwen summary | 2 |
| Piper voice generation | 2 |
| Wan InfiniteTalk avatar | 15 |

Failed, cancelled, setup-required, and out-of-memory jobs charge zero credits.

## Runtime stack

The monorepo contains:

- a Next.js/React/TypeScript frontend in `frontend/`;
- a FastAPI/Pydantic/SQLAlchemy backend in `backend/`;
- SQLite metadata and ledger persistence;
- local filesystem media storage;
- ComfyUI, Ollama, Piper, Faster Whisper, and FFmpeg integrations.

Expected local endpoints:

| Service | URL |
| --- | --- |
| Frontend | `http://localhost:3000` |
| Backend | `http://127.0.0.1:8000` |
| ComfyUI | `http://127.0.0.1:8001` |

For manual startup and machine setup, use the linked operator and model guides.

## Backups and recovery

App backups live in `backend/storage/backups/`. They include a transactionally
consistent SQLite snapshot, app storage, workflows, and a manifest. SQLite's
online backup API includes committed WAL data while the studio is running; the
database is integrity-checked before the archive is published.

Backups exclude secrets, environment files, scratch space, earlier backups, and
large external ComfyUI models. Preserve
`C:\Users\David\ComfyUI-Shared\models` separately.

See [Recovery and maintenance](docs/RECOVERY_AND_MAINTENANCE.md) before restoring
or deleting application data.

## Security boundary

This build is for trusted local use. `OWNER_FALLBACK_ENABLED=true` allows
no-cookie loopback requests to act as the seeded owner for convenience. Disable
it before any network exposure. Provider keys stay server-side in
`backend/storage/secrets/`, are masked in the UI, excluded from backups, and
never belong in frontend environment variables or screenshots.

Family-user selection is attribution, not authentication. The backend ignores
attempted impersonation headers from non-admin accounts.

## Development verification

Backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp-final -p no:cacheprovider
```

Frontend:

```powershell
cd frontend
npm.cmd run typecheck
npm.cmd run build
```

Run `git diff --check` before staging. Keep generated test artifacts, local model
weights, secrets, databases, build output, and standalone downloader dependency
trees out of commits.

## Change policy

For the V1 release candidate:

1. Prefer stability and recovery improvements over new feature surfaces.
2. Preserve local-first defaults.
3. Keep premium providers optional and owner-controlled.
4. Add regression tests for billing, backups, migrations, authorization, and
   destructive storage behavior.
5. Update the focused guide that owns the changed behavior instead of expanding
   this README.
