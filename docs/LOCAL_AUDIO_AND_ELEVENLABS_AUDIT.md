# Local audio and ElevenLabs audit — 2026-10-03

## Verified machine state

Read-only checks were performed while existing renders continued. No models were installed, unloaded, or benchmarked, and no provider credits were spent.

| Machine | Verified resources | Work observed |
| --- | --- | --- |
| Windows / AMD-DESKTOP | RTX 5070 Ti, 16,303 MiB VRAM; approximately 32 GB system RAM | One ComfyUI Qwen Image Edit 2509 job; 14,909 MiB GPU memory occupied and 100% utilization at sampling time |
| Linux, 192.168.2.126 | Ryzen 7 1700X; approximately 32 GB RAM; AMD gfx1201 GPU; ComfyUI reports 32,061,259,776 usable VRAM bytes | One ComfyUI Qwen Image Edit 2509 job; ROCm PyTorch 2.9.1+rocm7.2.1 |

The owner confirmed the Linux GPU is **AMD Radeon AI PRO R9700**. ROCm reports it generically as AMD Radeon Graphics (gfx1201). It has approximately 30 GiB usable device memory according to ComfyUI; do not confuse this with system RAM.

The existing SSH tunnel forwards Windows `127.0.0.1:18001` to Linux `127.0.0.1:8001`. ComfyUI intentionally listens on Linux loopback. Direct HTTP connections to the Linux LAN address therefore do not establish renderer readiness; the tunnel does.

Both sampled rendering graphs used `qwen_image_edit_2509_fp8_e4m3fn.safetensors`, `qwen_2.5_vl_7b_fp8_scaled.safetensors`, and `qwen_image_vae.safetensors`. The local public-avatar manifest contained 24 character entries at inspection. The resumable library script creates fictional people and additional looks; it is not extracting HeyGen people.

Personal AI Router is a separate language-model routing path. The supplied screenshot shows requests originating on Linux but executing on AMD-DESKTOP. Ollama/LM Studio routing is not proof that ComfyUI graphics jobs are automatically routed by that same service. GPU memories are not pooled between machines.

## ElevenLabs account observations

The signed-in browser exposed TTS, voice creation, sound effects, voice changer, voice isolation, speech-to-text, dubbing, music, Studio/audiobooks, image/video, Flows and templates.

- The community sound-effects page explicitly required a plan upgrade to download effects.
- Sound-effects History was empty; Favorites reported no saved sound effects.
- The Assets root displayed a My Avatars folder; no downloadable audio files were visible at that root.
- Text-to-speech History displayed 20 recordings. The bulk download remained Loading, so the recordings were exported individually. All 20 unique recordings are now saved and imported.
- Sovereign's HeyGen/ElevenLabs API settings remain unconfigured. Website sign-in does not configure API authentication.
- All 20 unique speech-history recordings were downloaded and imported. The earlier Adam preview is also available. These are audio files, not offline voice models.

ElevenLabs supports downloading generated audio through its UI/history APIs. Its voice catalogs expose profiles for use through the provider, not a local model installation. Preserve provider provenance and applicable usage rights for exported media; do not present exported samples as independently usable voice models.

## Feature mapping and priorities

| ElevenLabs feature | Sovereign now | Best local path / remaining gap |
| --- | --- | --- |
| Text to speech | Piper readiness passes; English Lessac low model configured. Optional ElevenLabs cloud route implemented. | Keep Piper for quick CPU speech. Reuse installed VibeVoice 1.5B for richer speech when the GPU is idle. |
| Voice cloning / expressive narration | VibeVoice service reachable; both 1.5B and 7B models present, no model loaded, queue empty. | Use recordings the owner can use for voice creation. Service estimates 5.4 GB for 1.5B and 18.7 GB for 7B; these are service-reported sizes, not measured peak inference VRAM. 7B needs offload on the 5070 Ti. |
| Speech to text | Local Whisper base configured for CPU; cloud transcription implemented. | Already useful without consuming render VRAM. Upgrade model/acceleration only after a representative accuracy and memory test. CUDA CTranslate2 support is not proof of ROCm support on Linux. |
| Voice changer | ElevenLabs cloud path implemented. No local equivalent verified. | Chatterbox has a voice-conversion example; evaluate in a separate environment after render work finishes. This is not an identical ElevenLabs voice replica. |
| Voice isolation | Cloud path implemented. Existing local speech cleanup cuts pauses/fillers. | Add an isolated Demucs worker for vocals/music separation; it supports CPU fallback. Separation and speech denoising are different quality targets. |
| Sound effects | Prompt-based ElevenLabs route implemented, including duration/loop controls. | First import permitted finished WAV/MP3 files. AudioGen is an experimental local candidate, but its documented 16 GB requirement is tight on a busy 5070 Ti and its model weights are noncommercial. Do not choose it as an unrestricted commercial default. |
| Dubbing | Cloud automatic dubbing implemented. Local Whisper → Qwen translation → subtitles/script exists. | Local spoken dubbing still needs multilingual voices, segmentation/timing, mixing and QA. The installed English Piper voice is not multilingual dubbing. |
| Music | Prompt-based cloud music generation added with duration and instrumental controls. | API credentials and plan access required. No live generation was charged or tested. |
| Studio / audiobooks | Local scene editor, podcast and batch tools already exist. | Reuse voice generation plus chapter/scene assembly; importing a vendor project is different from importing its finished audio. |
| Image/video, templates, Flows | Existing ComfyUI, image edit, video and product-scene tools cover parts of these workflows. | Continue the running local avatar/look library. Build equivalent task workflows using owned assets, rather than assuming proprietary templates/models can be exported. |

The hardware fit assessments above are engineering recommendations, not completed benchmarks. ROCm working for Qwen/ComfyUI does not establish that every audio package or custom CUDA kernel works on the AMD GPU. Use the NVIDIA machine for the first audio compatibility tests; leave graphics on Linux when scheduling allows. Do not start another GPU model while these full-memory render jobs are active.

## Concrete help added

The shared `_free_comfyui_vram()` helper previously posted `/free` without reading the render queue. It is called by local voice/AI work. It now checks `/queue`, refuses to unload while running or pending jobs exist, and refuses when queue state is malformed or times out. An offline renderer requires no cleanup. Focused guard, translation and avatar tests: **38 passed**.

This is a preflight guard, not an atomic cross-process scheduler. A new job could arrive between queue inspection and cleanup. The next infrastructure improvement should be one GPU reservation/queue per physical device shared by ComfyUI, VibeVoice and local LLM jobs. Nothing was restarted while current rendering was active; the change takes effect when the backend next restarts.

## Sources

- [ElevenLabs history downloads](https://elevenlabs.io/docs/api-reference/history/download) and [generated file exports](https://help.elevenlabs.io/hc/en-us/articles/13313879331601-Can-I-access-the-files-I-generated-in-the-past).
- [Chatterbox models and voice-conversion example](https://github.com/resemble-ai/chatterbox).
- [faster-whisper hardware/runtime support](https://github.com/SYSTRAN/faster-whisper).
- [Demucs installation and CPU fallback](https://github.com/facebookresearch/demucs).
- [AudioGen hardware requirements](https://github.com/facebookresearch/audiocraft/blob/main/docs/AUDIOGEN.md) and [model card/license](https://github.com/facebookresearch/audiocraft/blob/main/model_cards/AUDIOGEN_MODEL_CARD.md).

For configured cloud operations and output locations, see [CLOUD_PROVIDERS.md](CLOUD_PROVIDERS.md).

## Verified downloads and importer

The George recording is saved in `C:\Users\David\Downloads\Sovereign ElevenLabs Exports`. A locally packaged `verified-history-export.zip` contains that official MP3 download; it is not the missing 20-recording bulk export.

The importer `tools/import_elevenlabs_audio.py` accepts ZIP files, uses content hashes to skip duplicates, and writes fixed filenames rather than extracting ZIP paths. It imported one completed Cloud Studio job at `backend/storage/cloud/7d323f81-bb1b-5e70-9250-80ec53b9ae5d/output.mp3`. Imported audio remains usable without provider keys. The new Cloud Studio UI requires the pending application build/restart to become visible in the running app.

Importer, cloud-media and GPU guard tests: 26 passed. Frontend TypeScript check passed. Existing render workers were left running. Cloud calls still require configured API credentials; no proprietary ElevenLabs voice weights were downloaded.


## Follow-up completion

The owner confirmed the Linux GPU as AMD Radeon AI PRO R9700. See [ELEVENLABS_DOWNLOAD_REPORT.md](ELEVENLABS_DOWNLOAD_REPORT.md) for the complete download inventory and More tools review. Music generation and forced alignment have been added to Cloud Studio; focused tests: 32 passed, TypeScript passed. Deployment remains pending while render work is active.
