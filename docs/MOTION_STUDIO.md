# Motion Studio

## Release status

Implementation and the isolated production build are ready. Eight new Motion Studio tests plus 79 existing video/cloud regression tests passed (87 total). Desktop/mobile Playwright checks passed, including real local preparation, source approval, character upload, missing-key gating, project navigation, Apps filtering, overflow checks and a mocked native-draft export. Paid generation has not been exercised because no fal key is configured.

Live activation was attempted but automatic approval review rejected stopping/restarting the production backend and frontend, reporting only "blocked by policy." No production process was stopped. The old backend and frontend remain healthy on ports 8002 and 3000; temporary QA servers were stopped. The desktop startup script now selects `.next-motion-release`, which is ready for the next full application restart. The previous `.next-cinematic-fixed` build is retained. The database backup at `work/motion-transfer-backup/sovereign-before-motion.db` passed SQLite integrity checking.

No local-model coding run was claimed: a Harness task record was prepared, and the shared skill was validated and installed in the Harness's existing skill root, project Claude Code skills, and user Claude Code skills. New sessions can discover it; existing sessions may need their normal skill refresh.

Motion Studio is an additive, owner-controlled workspace at `/motion-studio`, also available from Create and the Apps library. Existing video generation and local-first defaults remain separate.

## Workflow

1. Upload an MP4 or MOV up to 200 MB. Select a start time and a 2-30 second section. Local FFmpeg creates a 24 fps editing reference and a scene still without modifying the uploaded source.
2. Watch and approve the prepared clip.
3. Upload one or two character references. Edit replacement direction and optional scene details. Approve the upload of these inputs to fal and its charges, then generate a 480p draft.
4. Review drafts and select a completed take. Approve the separate final charge to complete the original provider draft at 1080p. Download the draft or final output.

Original source audio is restored onto draft and final renders. Silent footage remains silent. A final is completed using the original provider `draft_id`, never by uploading a downloaded draft as a new source. Draft IDs expire seven days after submission and require the same provider account. Model output is probabilistic; motion and identity consistency require review.

## Setup

FFmpeg and FFprobe must be on PATH. The backend dependency is `fal-client==1.0.3`. Add and enable the new **fal Motion Studio** entry in `/admin/integrations`; an existing backend-only `FAL_KEY` environment variable is also supported. Existing generic Seedance credentials are not reused because the vendor and authentication contract may differ.

Official endpoints:

- https://fal.ai/models/bytedance/seedance-2.5/reference-to-video/api (`task: editing`, `draft: true`)
- https://fal.ai/models/bytedance/seedance-2.5/draft/complete/api

Preparation is local and does not spend provider credits. Each explicitly approved cloud render uses the provider account's billing, not Sovereign's local credit ledger. No automatic paid fallback or submit retry is performed. Uploaded references are sent only when a draft is requested. Provider storage URLs are temporary media hosting, not a new public Sovereign deployment.

## Persistence and recovery

Projects live in `backend/storage/motion_studio/<UUID>/`. This directory is denied by the public `/storage` mount. Metadata, source files and results are served through owner-authorized routes with project ownership checks. Operations use request UUIDs and fingerprints to prevent duplicate paid submissions on replay. Native request IDs are saved before results are polled. Interrupted preparation or submission is marked failed on startup; unknown submit billing outcomes are not automatically replayed. Rendering jobs can be refreshed after restart using the saved remote request ID.

There is no database migration. Removing this feature requires removing its router registration and navigation entries, then rebuilding; retain project storage for recovery. Pre-change copies of touched central files are in `work/motion-transfer-backup/` and the previous production build is retained during activation.

## Public demonstration scope

The public transcript of https://www.youtube.com/watch?v=d6spCMcfkew was reviewed, including the four-stage interface and draft completion explanation. This is an independent implementation based on visible behavior and documented provider contracts, not a verified reproduction of Higgsfield internals. No access to Higgsfield's paid app or proprietary implementation was used.

Depth masking, vocal pitch alteration and face concealment intended to defeat provider IP checks are not implemented. Ordinary authorized-media editing is submitted to the provider's normal checks. Automatic Demucs/SAM/depth preparation and facial-landmark tracking are not claimed as installed capabilities. Manual scene direction is available; automatic vision description and transcription are not part of this feature.

## Shared frontend libraries

The requested repositories are cloned under `work/creative-vendor/`. Source revisions and usage are recorded in the `creative-motion-library` skill installed in the existing Jarvis/DeepSeek skill root and the project's Claude Code skill directory. GSAP animates stage changes, Lenis enhances only the project history scroll container, and the React Bits AnimatedContent adaptation keeps content visible and supports reduced motion. Component licensing is retained in `docs/third-party/`.

## Verification

`backend/tests/test_motion_studio.py` uses actual FFmpeg media processing and mocked cloud responses. It exercises upload validation, approval gates, access controls, native draft completion, soundtrack restoration, duplicate-submit protection, interruption recovery and expiry. Cloud tests do not establish paid provider account access or generated visual quality; a configured account and approved render are required for that final verification.
