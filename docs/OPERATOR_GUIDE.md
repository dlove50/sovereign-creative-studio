# Sovereign Creative Studio — Operator Guide

This guide covers normal daily use of the private, local V1 release candidate.
It is written for David, family creators, and the owner/admin who maintains the
machine.

## Start and stop

Start the full local stack with:

```text
Start-Sovereign-Creative-Studio.bat
```

The launcher starts ComfyUI, the FastAPI backend, and the Next.js frontend. Open
`http://localhost:3000` if the browser does not open automatically.

Stop the studio with:

```text
Stop-Sovereign-Creative-Studio.bat
```

For port cleanup or a damaged frontend process, run:

```powershell
python tools/local_launcher.py clean
```

Detailed startup diagnostics are in
[LOCAL_STARTUP_AND_RECOVERY.md](LOCAL_STARTUP_AND_RECOVERY.md).

## Recommended creative workflow

The Home page presents **Quick Chain** as the recommended workflow. It guides a
creator through:

1. Text prompt to image.
2. Image to video.
3. Optional video upscale.
4. Optional local voice narration.
5. Video transcription and optional local summary.
6. Downloading the finished outputs.

Individual studios remain available for creators who want direct control:

- **Image Studio** for text-to-image and image editing.
- **Video Generator** for text-to-video, image-to-video, video-to-video,
  extension, and upscale.
- **Avatars & Voices** for reusable avatar sources, Piper voices, and local
  talking-avatar jobs.
- **Transcribe Video** for Whisper transcription and Qwen summaries.
- **Assets** and **My Projects** for organizing finished work.

On smaller screens, use the menu button in the top-left corner to reach the same
creator and admin destinations available in the desktop sidebar.

## Local defaults

| Capability | Normal provider |
| --- | --- |
| Image generation | ComfyUI / local image workflows |
| Product scenes | ComfyUI / Flux Kontext |
| Copy and summaries | Ollama / `qwen3:4b` |
| Video | ComfyUI / LTX or approved local Wan mode |
| Transcription | Faster Whisper |
| Voice | Piper |
| Talking avatar | ComfyUI / Wan InfiniteTalk |

Premium OpenAI image and Seedance/C-Dance video providers remain disabled until
the owner explicitly configures and enables them in **Admin → Provider
Integrations**.

## Accounts and credits

- `owner_admin` can manage users, credits, providers, jobs, storage, backups,
  models, and workflows.
- `family_user` sees the creator-focused experience and their own work.
- `guest` is limited and should not be used as an administration account.

Credits are charged only after successful billable jobs. Failed, cancelled,
setup-required, and out-of-memory jobs charge zero credits. The current defaults
are:

| Job | Credits |
| --- | ---: |
| Local LTX video | 10 |
| Seedance/C-Dance video | 30 |
| Whisper transcription | 5 |
| Qwen summary | 2 |
| Piper voice generation | 2 |
| Wan InfiniteTalk avatar | 15 |

The admin can review the ledger and make a documented adjustment when needed.

## Owner/admin routine

Before a longer creative session:

1. Open **Status** and confirm the required local services are ready.
2. Check **Job Monitor** for stale or failed work.
3. Confirm enough free disk space is available for video generation.
4. Create a backup before changing workflows, models, or provider settings.

After a session:

1. Confirm important outputs appear in Assets or the relevant project.
2. Download any deliverables that must live outside app storage.
3. Review failed jobs before removing temporary files.
4. Stop the studio cleanly.

## Where data lives

- SQLite database: `backend/sovereign.db`
- Generated assets and uploads: `backend/storage/`
- Backups: `backend/storage/backups/`
- Workflow templates: `backend/workflows/`
- Server-side secrets: `backend/storage/secrets/`
- External ComfyUI models: normally `C:\Users\David\ComfyUI-Shared\models`

Secrets and large external model files are intentionally excluded from app
backups. Preserve the external model directory separately.

## Related guides

- [Recovery and maintenance](RECOVERY_AND_MAINTENANCE.md)
- [Architecture](ARCHITECTURE.md)
- [Model and dependency setup](MODEL_AND_DEPENDENCY_MANIFEST.md)
