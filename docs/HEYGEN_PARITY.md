# Sovereign vs HeyGen: parity evaluation

Written 2026-10-02 from the HeyGen pages actually reviewed (Home, Video agent, Avatars and looks, Look studio,
Brand, Apps library, Projects, the scene editor) plus the owner's screenshots. "Perfect copy" is not achievable on
one local PC; this lists exactly where Sovereign matches, approximates, or cannot match HeyGen.

Rule followed: layout, structure and flow are mirrored; HeyGen's name, logo, photos and wording are not copied.
All images in the app were generated locally.

Legend: **Built** = works and was checked in the real app · **Partial** = works with a stated gap ·
**Not built** = buildable, not done yet · **Not possible** = needs HeyGen's cloud scale or real-time models.

## Navigation and shell

| HeyGen | Sovereign | Status |
|---|---|---|
| Icon rail: Home, Avatar, Brand, Apps, Projects | Same rail (plus Credits, Admin, profile) | Built |
| Create fly-out: Home, Video agent, Scene by scene, Single scene, Translate + Recents | Home, Video agent, Scene by scene, Single scene + Recents of finished videos | Partial (no Translate entry) |
| Ask Orby assistant | None | Not built |
| Developers / API page | None (Sovereign has its own local API) | Not built |

## Pages

| Area | Status | Notes |
|---|---|---|
| Home / Welcome: setup tracker (4 steps), video prompt cards | Built | Tracker reads real data; cards open the Video agent |
| Video agent: avatar / voice / brand chips, auto-pilot, idea tabs, "Create yours" cards | Built | Local Qwen writes the script; Review-first and Auto-pilot; Brand chip shapes the script |
| Avatars gallery: grouped cards, My / Public, search, grid/list, New avatar (upload, video, design with AI) | Built | Public avatars are 15 locally generated presenters |
| Avatar page + Edit look (appearance, camera angle, custom edit, remix, use in video, delete) | Built | Qwen Image Edit 2509 keeps identity |
| Look studio: prompt, template chips, Look Packs, custom packs (3 to 12), recents | Built | 15 templates, own covers; Portrait/Landscape switch for looks not built |
| Digital Twin from 15 s of video footage | Partial | Photo avatars and video upload exist; footage-based twin training is not implemented |
| Voice: clone from footage, re-record | Partial | VibeVoice clones from an audio sample, in a separate app on :8010 |
| Brand systems: list, add, edit | Built | Colors, voice, audience, avoid-list; logo/fonts upload not built |
| Projects: search, sort, filter, folders, video grid, player, trash | Built | Draft badge for movies; per-project folders are Sovereign projects |
| Apps library: Featured + All/Create/Enhance/Edit/Interactive tabs, search | Built | Every app below links or is marked Coming next |
| Scene-by-scene editor (AI Studio): scenes, look, voice, script, Improve delivery, Generate, join | Built | Real 2-scene movie verified; landscape and 3+ scenes not rendered yet |

## Apps in the library

| App | Status | Notes |
|---|---|---|
| Video agent | Built | |
| AI Studio / Scene by scene | Built | |
| Talking avatar (single video) | Built | Long scripts via chained 3-second chunks; ~55 s render per 1 s of video on the 5070 Ti |
| Batch videos | Built | CSV to many drafts or renders; verified creating drafts |
| Speech cleanup | Built | Pauses cut reliably; filler words ~3 of 5 caught in a test (Whisper drops some) |
| Auto clips | Built | Real Whisper + Qwen run verified |
| Video podcast | Partial | Alternating cuts between two avatars, not both in one frame |
| Upscale video | Built (existing) | Quick Chain / Video Generator upscale |
| Generate images / Image studio | Built (existing) | |
| AI video generator (text or image to video) | Partial | LTX and Wan work; **MiniMax H3 is wired but not yet run on the GPU** (download in progress) |
| Cinematic shots | Partial | Same engines as above |
| Translate videos | Not built | Whisper + Qwen + voice + re-lip-sync is possible; target languages limited by installed voices (not 175) |
| PPT/PDF to video | Not built | Possible: slide text to narration scenes, slide image as background |
| Interactive video | Not built | Branching player needed |
| LiveAvatar (real-time) | Not possible | Local render is ~55 s per 1 s of video |

## Things that differ by nature

- **Speed:** HeyGen renders in the cloud in seconds to minutes; Sovereign on one 16 GB GPU takes minutes per few seconds of avatar video.
- **Quality ceiling:** open-weight models (InfiniteTalk, Wan, Qwen Edit) look good on short clips; HeyGen's tuned cloud models are better on long takes, gestures and 4K.
- **Languages:** 175+ languages is not reachable with local open voices.
- **Credits/billing:** Sovereign's credits are an internal counter, not payments.

## Highest-value next steps

1. Run MiniMax H3 on the GPU once the download completes (see `docs/HANDOFF_CODEX.md`).
2. Render a landscape and a 3-scene movie; run the "Create and render all" batch once.
3. Translate videos (limited languages), then PPT/PDF to video.
4. Optional: a second render machine (the Linux R9700) when the owner says "Let's fix the Linux system".
