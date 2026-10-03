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
| Avatar section panel: Avatars, Design a look, Voices | Same three pages in a hover panel on the Avatar rail item | Built (2026-10-03) |
| Create fly-out: Home, Video agent, Scene by scene, Single scene, Translate + Recents | Home, Video agent, Scene by scene, Single scene + Recents of finished videos | Partial (Translate lives in the Apps library, not the fly-out) |
| Ask Orby assistant | None | Not built |
| Developers / API page | None (Sovereign has its own local API) | Not built |

## Pages

| Area | Status | Notes |
|---|---|---|
| Home / Welcome: setup tracker (4 steps), video prompt cards | Built | Tracker reads real data; cards open the Video agent |
| Video agent: avatar / voice / brand chips, auto-pilot, idea tabs, "Create yours" cards | Built | Local Qwen writes the script; Review-first and Auto-pilot; Brand chip shapes the script |
| Avatars gallery: grouped cards, My / Public, search, grid/list, hover menu and favorite heart | Built | Public avatars are 15 locally generated presenters |
| Avatar page + Edit look (appearance, camera angle, custom edit, remix, use in video, delete) | Built | Qwen Image Edit 2509 keeps identity |
| Look studio: prompt, template chips, Look Packs, custom packs (3 to 12), recents | Built | 15 templates, own covers; Portrait/Landscape switch for looks not built |
| Digital Twin from 15 s of video footage | Partial | Photo avatars and video upload exist; footage-based twin training is not implemented |
| Voice: clone from footage, re-record | Partial | VibeVoice clones from an audio sample, in a separate app on :8010 |
| Brand systems: list, add, edit | Built | Colors, voice, audience, avoid-list; logo/fonts upload not built |
| Projects: search, sort, filter, folders, video grid, player, trash | Built | Draft badge for movies; per-project folders are Sovereign projects |
| Apps library: Featured + All/Create/Enhance/Edit/Interactive tabs, search | Built | Every app below links or is marked Coming next |
| Scene-by-scene editor (AI Studio): scenes, look, voice, script, Improve delivery, Generate, join | Built | Real 2-scene movie verified; landscape and 3+ scenes not rendered yet |

## Avatar creation, voices and looks (audited against the live product, 2026-10-03)

| HeyGen | Sovereign | Status |
|---|---|---|
| "Create a new avatar" page: Clone a real person / Create a virtual character | `/avatars/new`, same two cards, Upload photo and Design with AI on the second | Built |
| Design form: name, age, gender, ethnicity, description, orientation, pose, style; 4 previews; Generate again; Edit prompt; Save | Same form and steps, 6 styles; Orientation shapes the prompt only (image size is fixed by the model preset); 4 previews take about 100 s and cost 20 credits | Built |
| Choose a voice step after creating an avatar | VoiceStep: My voices, Built-in voices, search, play, Clone your voice, Select or Skip | Built |
| Clone a real person from 15 s of recorded footage (webcam or phone, Avatar V) | Upload a video: sharpest still becomes the face, speech becomes a VibeVoice clone. NOT motion cloning | Partial |
| Voices page: Clone your voice (record, upload, professional), Design a voice, Import from ElevenLabs, My voices, library with language/gender filters | `/voices`: record or upload clone, My voices, Library with gender filter and play. Library is 4 Piper plus 9 VibeVoice presets, not hundreds | Partial |
| Design a voice from a text description | Not possible with the installed voice models | Not possible |
| Import voice from ElevenLabs by API key | Skipped on purpose: it sends data to a cloud service | Not built (by design) |
| Avatar page: voice pill (play, Improve voice, Switch voice), favorite, menu (Edit, Share, Delete, Copy ID) | Voice pill, favorite, menu with Edit name, Make a video, Copy avatar ID, Delete | Built (no Share: nothing to share to) |
| Add looks page: upload video/photo, Record now, Add from phone, Google Drive link, tips | Upload video/photo, Record now (webcam), tips. Video looks use a still. No phone or Drive link | Partial |
| Design a look: prompt, References, orientation switch, "Improve likeness with a personal model", templates, Look Packs, recents | Prompt, templates, Look Packs, recents. References, orientation switch and personal-model training are not built | Partial |
| Per-avatar default voice used when making a video | Saved on the avatar (`default_voice_id`); the video agent and scene editor do not read it yet | Partial |

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
| AI video generator (text or image to video) | Built | LTX, Wan and MiniMax H3 (text, image, reference, ControlNet video-to-video; 10 effect chips) all run on the GPU |
| Cinematic shots | Partial | Same engines as above |
| Translate videos | Partial | Built 2026-10-03 at /translate: Whisper transcript, Qwen translation into 21 languages, .srt/.vtt subtitles, and a one-click draft where the avatar says the translation. Verified in French (25 s). Does NOT re-voice the original video or re-lip-sync it; spoken output depends on installed voices (Piper is English only) |
| PPT/PDF to video | Partial | Built at /slides: PDF or .pptx text becomes one draft scene per slide (optional Qwen rewrite to spoken style), opens in the scene editor. Slide images are NOT shown behind the avatar; scanned slides need OCR |
| Interactive video | Built | /interactive: link finished videos with up to 4 choices each, preview player with Start over; verified in the browser. Local only, no public share link |
| LiveAvatar (real-time) | Not possible | Local render is ~55 s per 1 s of video |

## Things that differ by nature

- **Speed:** HeyGen renders in the cloud in seconds to minutes; Sovereign on one 16 GB GPU takes minutes per few seconds of avatar video.
- **Quality ceiling:** open-weight models (InfiniteTalk, Wan, Qwen Edit) look good on short clips; HeyGen's tuned cloud models are better on long takes, gestures and 4K.
- **Languages:** 175+ languages is not reachable with local open voices.
- **Credits/billing:** Sovereign's credits are an internal counter, not payments.

## Highest-value next steps

1. Translate: a re-voiced (dubbed) output needs a multilingual TTS; VibeVoice language support is untested here.
2. Slides to video: render each slide as an image behind or beside the avatar (needs a PDF rasteriser such as pypdfium2).
3. Render a landscape and a 3-scene movie; run the "Create and render all" batch once.
4. Optional: a second render machine (the Linux R9700) when the owner says "Let's fix the Linux system".
