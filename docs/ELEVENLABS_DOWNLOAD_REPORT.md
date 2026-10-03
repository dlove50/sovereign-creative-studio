# ElevenLabs downloads and Sovereign integration — 2026-10-03

## Downloaded and verified

- Exported all 20 recordings visible in Text to Speech History using the official individual MP3 download menus after the bulk export stalled.
- 20 unique MP3s, 8,440,510 bytes, 505.75 seconds (about 8 minutes 26 seconds). Every file passed ffprobe inspection.
- Voices represented: George, Brian, Eric, Alice, Matilda and Sarah. These are finished recordings, not installed voice models.
- The download folder has 22 MP3 filenames because two repeated downloads are byte-identical. Sovereign imports only the 20 unique recordings.
- Download folder: `C:\Users\David\Downloads\Sovereign ElevenLabs Exports`.
- Portable archive: `speech-history-2026-10-03.zip` in that folder. This was packaged locally from the official downloads.
- Inventory: `download-manifest.json` in that folder, including filenames, SHA-256 hashes, duration, size and duplicate flags.
- Sovereign copies: `backend/storage/cloud/<job-id>/output.mp3`, with provenance in each `job.json`.
- The earlier Adam preview remains separately available in Downloads. It is not included in the 20-recording count.

## Implemented in Sovereign

Cloud Studio already supports HeyGen avatar video and ElevenLabs TTS, sound effects, voice conversion, transcription, dubbing and voice isolation. This follow-up adds:

1. **Music:** prompt, 3–600 second duration, instrumental-only option, saved MP3. Uses the documented `music_v1` API model and explicit credit acknowledgement.
2. **Transcript timing:** audio plus exact transcript, with word/character timings saved as `alignment.json` and transcript text saved alongside. This is forced alignment, not automatic transcription or finished captions.
3. Switching tools clears the selected source file so an old upload cannot accidentally carry into another operation.

API credentials are still unconfigured. These integrations have mocked contract tests, not a paid live-provider test. The production frontend/backend still require their pending build/restart; the preview was checked on an isolated dev port. Active render workers were not restarted.

## More tools: inspected, with limits

| Tool | Observed account state | What can be brought into Sovereign |
| --- | --- | --- |
| Templates | Product shots, character sheets, background removal, posters, moodboards and video effects are listed. | Recreate selected workflows using Sovereign's owned assets and local image tools. No downloadable template package was established. |
| Audio Native | Requires Creator tier. | A comparable local narration/player workflow is possible with Piper/VibeVoice; ElevenLabs' hosted player remains a cloud service. Not added in this pass. |
| Productions | Managed delivery options for dubs, audiobooks, transcripts, captions and translated subtitles. | Sovereign already covers portions of these workflows. No downloadable production order was established; no order was placed. |
| Ads Engine | Alpha landing page with Contact Sales. | Local creative assembly is possible; ad-platform publishing/account integration is separate work. No account connection or campaign was created. |

## Other inspected features

- **Sound effects:** community downloads require an upgrade. Personal History and Favorites were empty at inspection.
- **Music:** marketplace says an upgrade is required for downloading/commercial use; personal Generations has no projects.
- **Voice Changer:** History is empty.
- **Voice Isolator:** displayed entries have disabled “Download not yet available” controls.
- **Speech to Text and Dubbing:** entries were visible, but tested options controls did not expose a working download menu. No exports were claimed or imported from those pages.
- **My Voices:** profiles and use/share/history controls are available. They do not provide downloadable model weights. Keeping the original voice requires the provider API; a preview MP3 is not the voice engine.

## Can / cannot do next

**Can:** reuse the downloaded recordings locally; import later official ZIP exports without duplicates; run existing CPU Piper/Whisper; use installed VibeVoice when GPU capacity is available; call the new cloud tools once credentials and account entitlements are configured.

**Cannot currently:** export proprietary ElevenLabs/HeyGen model weights, guarantee identical local replicas, bypass plan-gated downloads, use API features with website login alone, or claim the new routes have passed a live paid-provider test. Downloading a finished asset does not download the service that generated it.

The owner confirmed Linux GPU **AMD Radeon AI PRO R9700** at `192.168.2.126`. Windows has the **RTX 5070 Ti**. Both were rendering Qwen avatar/look images during the preceding audit. The R9700's greater VRAM is useful for larger local workloads; compatibility must still be checked per ROCm audio model. There is no cross-machine pooled VRAM.

## Validation

- 32 focused cloud/import/GPU guard tests passed without real credentials or GPU generation.
- TypeScript check passed; UI detector returned no findings.
- Music and transcript timing controls inspected at desktop and mobile widths on the isolated dev server. Live cloud requests remain untested.
- Download integrity checked with ffprobe and SHA-256; content hashes drive import deduplication.

Sources: [Music API](https://elevenlabs.io/docs/api-reference/music/compose), [forced alignment API](https://elevenlabs.io/docs/api-reference/forced-alignment/create), and the signed-in ElevenLabs UI inspected during this task.
