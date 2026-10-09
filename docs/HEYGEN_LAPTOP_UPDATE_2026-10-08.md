# HeyGen parity: laptop update, 2026-10-08

Machine: Lenovo Legion laptop, RTX 4070 (8 GB), driver 577.02 (CUDA 12.9). Installed from the transfer kit at `C:\Sovereign`. Everything below was tested in the running app unless marked otherwise.

## Added in this pass
| Feature | Where | Evidence |
|---|---|---|
| Batch cross-product: every script with each ticked presenter and voice | `/batch`, `POST /api/movies/batch` (`avatar_ids`, `tts_voice_ids`) | 8 drafts from 2 scripts x 2 presenters x 2 voices; 14 movie tests |
| Document to presentation (PDF, PowerPoint, Word, .txt, .md) | `/slides` > Create from a prompt > Start from a document; `POST /api/slides/document-brief` | Word file to 3 slides in 10 s; 59,000 characters condensed in 17 s |
| Slide text wraps at words | `services/presentation._wrap` | slide images checked; test with long URL and Chinese text |
| SCORM 2004 (4th Ed.) and xAPI export | Interactive editor export menu; `POST /api/interactive/{id}/export/{scorm12,scorm2004,xapi}` | Node runtime tests with mock LMS / LRS; package manifests parsed |
| Screen recorder | `/record`, `POST /api/recordings` | Recording through the real page saved as H.264 MP4 and listed as a lesson clip |
| Studio assistant | Chat button on every page, `POST /api/assistant/chat` | Answers in about 1.3 s; opens pages, reads credits/avatars/videos from the database; refuses destructive requests |
| Developer API page | `/developers`, `GET /api/developers/endpoints` | 249 endpoints listed with curl examples |
| Scanned PDFs, slides and page photos read with OCR | `services/ocr.py` (RapidOCR on the CPU, models inside the package, about 14 MB); `/slides` Start from a document accepts scans and pictures; Slides to video reads picture-only slides into the narration | Rotated, noisy 2-page scan read almost word for word in 5 s; scanned deck became 2 scenes with the page picture kept |
| Spanish and French voices for translated speech | `backend/storage/models/piper/`; Translate page matches the voice to the target language | Read back by Whisper word for word; English clip translated to Spanish and French in the live app |
| Wan 2.1 1.3B text-to-video | Video generator, `workflows/text_to_video_wan13.json` | 4 s clip in 37 s; preset "Wan Natural Speed" (16 fps, 65 frames, about 77 s, 7 GB) |

## Honest limits on this hardware
- Real-time avatars, HeyGen-quality talking avatars from a photo, the full Director with its large models, and re-syncing lips for dubbed video are not possible on 8 GB.
- OCR works for printed text in clear scans (about 2 s per page, CPU only); handwriting and badly skewed or very low-resolution pages may read poorly, so the app tells you to check OCR text. The separate OCR Studio page still points at a different, heavier service on port 8010 that is not installed. Spanish (es_ES-davefx-medium) and French (fr_FR-siwis-medium) voices are installed and the Translate page picks them automatically; other languages need a cloned voice. Spoken translation re-voices the script with an avatar; it does not re-sync lip movement on existing footage.
- The studio assistant answers from a fixed guide and only reads data or opens pages. It never renders, deletes or spends credits.
- Cloud HeyGen / ElevenLabs connectors need the owner's own accounts and keys; nothing was signed in to.

## Known test notes
- Run the backend tests with the main ComfyUI (port 8001) stopped: with it running, `test_director` and `test_project_workspace` talk to the real engine and fail.
- `tests/test_vibevoice_voice.py::test_clone_speech_writes_wav_and_hands_gpu_back` was already out of step with `_free_comfyui_vram` (it now checks `/queue` before `/free`); it fails with ComfyUI up or down. Not changed.
- On the 8 GB card the music engine (port 8199) and the main image/video engine (port 8001) share one GPU. Before every song the app now asks the main engine to unload its models (and waits politely if it is rendering). Without that a song started after an image never finished. Songs also pause while a video renders; make them one at a time.
