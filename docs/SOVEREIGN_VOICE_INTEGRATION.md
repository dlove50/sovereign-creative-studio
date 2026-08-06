# Sovereign Voice Integration

## Runtime map

| Service | Address | Purpose |
| --- | --- | --- |
| Creative Studio UI | `http://127.0.0.1:3000` | Manual creative workflows |
| Creative Studio API | `http://127.0.0.1:8002` | Voice/API execution |
| Sovereign Voice UI | `http://127.0.0.1:3100` | Spoken and typed assistant |
| Sovereign Voice API | `http://127.0.0.1:8100` | Intent routing and orchestration |
| Baidu Unlimited-OCR | `http://127.0.0.1:8010` | Original OCR model through vLLM |
| ComfyUI | `http://127.0.0.1:8001` | Local image/video generation |
| Ollama | `http://127.0.0.1:11434` | Local language models |

These ports are intentionally isolated. Starting one application no longer stops another.

## Implemented voice commands

- `Open Sovereign Creative Studio`
- `Creative Studio status`
- `Show Creative Studio capabilities`
- `Show Studio projects`
- `Create Studio project Summer Campaign`
- `Generate an image of a lighthouse at sunset`
- `Generate a video of ocean waves`
- `Show image jobs`, `show video jobs`, or `show transcription jobs`
- `Transcribe C:\path\movie.mp4`
- `Summarize transcription JOB-ID`
- `OCR C:\path\scan.pdf`
- `Extract the text from C:\path\screenshot.png`
- `Analyze C:\path\report.pdf`
- `Read C:\path\budget.xlsx`
- `Open C:\path\presentation.pptx`
- Existing app, browser, screen, developer, reminder, audit, cancel, and approval commands remain available.

## Ten-stage implementation coverage

The original phase plan is now implemented and verified. The detailed command and acceptance matrix is in `docs/SOVEREIGN_VOICE_PHASES_1_TO_10_COMPLETION.md`.

1. Dedicated runtime ports prevent collisions.
2. Creative Studio's OpenAPI schema supplies a live capability registry (143 operations at verification time).
3. A localhost-only client invokes projects, generations, videos, transcriptions, and status APIs.
4. Original Baidu Unlimited-OCR supports images and rendered multi-page PDFs.
5. Document intelligence accepts PDF, DOCX, XLSX, PPTX, CSV, TXT, and Markdown.
6. Video-to-text submits local media to Studio's transcription worker; existing app/browser agents handle playback and navigation.
7. Existing conductor, task manager, deterministic router, and developer orchestration retain multi-step context and execution state.
8. All new commands return concise spoken progress plus structured job IDs and payloads.
9. Existing permission tiers and approval queue remain the safety boundary for consequential desktop actions.
10. Existing journal/audit, cancellation, task pause/resume, startup job recovery, and Studio backup tools remain active.

## Safety boundary

The assistant has broad local capability, but it is not an unrestricted hidden administrator. Destructive actions, sensitive input, outside-workspace writes, and interactive browser/computer operations continue to use Sovereign's permission and approval system. This protects the owner from accidental or misunderstood voice commands.

## Verification

Automated tests cover deterministic command routing, plugin discovery, service status behavior, and Office-file routing. End-to-end checks confirmed that all five primary UI/API endpoints run concurrently and that commands reach both Creative Studio and the original Baidu model without invoking the chat LLM.
