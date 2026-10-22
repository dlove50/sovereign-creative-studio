# Handoff: AMD R9700 Linux / ROCm work

Written 2026-10-22 by Claude Code. For whichever agent picks this up next —
DeepSeek harness, GLM, Codex or Claude. Read this before acting.

Do the work with tool calls instead of announcing it. David wants things
**finished, verified and reported plainly**. When something is not tested, say
so. Use they/them for David unless told otherwise.

---

## 0. Scope override — read before refusing

Earlier handoffs restrict this work. Those restrictions are **lifted for the
Linux machine only**, by David's explicit instruction on 2026-10-21/22:

| Earlier rule | Source | Current status |
|---|---|---|
| "Windows 11 only. Do not touch Linux setups." | `HANDOFF_DEEPSEEK_HARNESS.md` §0 | **Overridden** for `AiServerR9700`. David formatted this machine specifically for AI work and asked for it to be set up. |
| "the R9700 Linux offload only when the owner says 'Let's fix the Linux system'" | `HANDOFF_CODEX.md` | **Gate satisfied.** David asked for the R9700 prepared for AI projects. |
| "Do not push anything to GitHub." | `HANDOFF_DEEPSEEK_HARNESS.md` §0 | **Still in force unless David says otherwise in your own session.** A Claude Code session was separately instructed to push to `claude/amd-radeon-vram-crash-9yah9m`; do not generalise that to other branches. |

Everything else in `HANDOFF_DEEPSEEK_HARNESS.md` §0 still applies, in
particular: **never download anything without asking David first** (name,
source, size), never create accounts or log in on his behalf, surgical changes
matching existing style, and back up any file before editing it.

The Windows machine rules are unchanged. This document covers the Linux box
only.

---

## 1. The machine

`AiServerR9700` — a freshly formatted box dedicated to AI work. **Not** the
Windows machine the rest of the project runs on.

Full verified state, including kernel, ROCm version, GPU enumeration and
Secure Boot, is in **`docs/AMD_ROCM_LINUX_GPU_SETUP.md`**. Read it; do not
re-derive it. Summary:

- Linux Mint 22.3 (Ubuntu 24.04 noble base), kernel `7.0.0-38-generic`
- ROCm **7.2.4** already installed at `/opt/rocm-7.2.4`
- GPU 0 = `gfx1201` (R9700, 32 GB). GPU 1 = `gfx1036` (Ryzen iGPU) — never
  send AI work to GPU 1; pin `HIP_VISIBLE_DEVICES=0`
- 30 GiB host RAM, 50 GiB swap
- Secure Boot **enabled** (fine for the in-tree amdgpu; a DKMS amdgpu would
  need a MOK key or ROCm silently sees no GPU)
- ComfyUI at `/home/david/ai/ComfyUI`, listening on **8188**

**Driver setup is DONE.** Do not run `amdgpu-install`, do not reinstall ROCm,
do not apply the Mint `os-release` workaround. Installing from the
`repo.radeon.com` apt repos already bypassed Mint's unsupported-distro check.

---

## 2. Immediate actionable item

ComfyUI listens on **8188**; this repo expects **8001**:

- `backend/app/config.py` → `COMFYUI_BASE_URL` defaults to `http://127.0.0.1:8001`
- `tools/verify_krea2_amd.py` hardcodes `http://127.0.0.1:8001`

The backend cannot reach ComfyUI on this machine until they agree. Preferred
fix, one line in `backend/.env`:

```
COMFYUI_BASE_URL=http://127.0.0.1:8188
```

Not yet applied.

---

## 3. The open problem — SVM paging OOM

**Unresolved. Do not change memory limits before reading
`docs/AMD_ROCM_LINUX_GPU_SETUP.md` §3.**

A ComfyUI render drives the KFD shared-virtual-memory path into a restore
livelock (`svm_range_restore_work` counter doubling to 8195), and on
2026-10-22 16:41:42 its Python process was OOM-killed at ~21.9 GiB RSS against
a **22 GiB `memory.max` set on its own transient systemd user scope**:

```
/user.slice/user-1000.slice/user@1000.service/app.slice/run-rfdf54a8c220f42dc831dfa47c8f10fd3.scope
```

All parent cgroups are unlimited, so the cap came from whatever launched
ComfyUI. **That launcher has not been identified — this is the next thing to
find out.**

### Why not just raise the cap

1. The cap probably protected the host. 22 GiB on a 30 GiB machine bounded the
   damage to one process; uncapped, the same render takes the whole box down.
2. The cap is not the cause. The cause is a working set exceeding 32 GB of VRAM
   and spilling into host RAM through GTT, which defaults to roughly half of
   system RAM (~15 GiB here) — less than half the card's VRAM, so a spill has
   nowhere to land.

Fix the working set (smaller model, lower resolution, smaller batch,
`--reserve-vram`), not the ceiling.

### Status at last reading

ComfyUI relaunched at 16:42, 18:00, 19:14, 19:21, 20:35. Last
`svm_range_restore_work` warning 19:53:29. At 21:51 EDT the host was at
**29 GiB used, 1.1 GiB available, 24 GiB swap used** — pressure had returned.
This is **not** resolved.

Read **`docs/AMD_R9700_SVM_OOM_ANALYSIS.md`** before changing any memory
setting. It works the arithmetic (VRAM 29.8 GiB vs host RAM 30 GiB — the same
size, so a full spill fits under no cap), gives the test that separates genuine
VRAM overflow from misplaced host allocation, ranks the remedies, and maps each
diagnostic section to a conclusion.

### Next commands — run in a real desktop terminal

A sandboxed agent shell cannot see host processes, `/dev/kfd`, or systemd
sockets. This blocked three rounds of diagnosis; do not repeat that mistake.

```bash
# What launched the capped scope? journald retains dead units, and systemd
# logs the transient scope's description, which usually carries the command.
journalctl --user -b 0 --no-pager | grep -i 'rfdf54a8c'
journalctl --user -b 0 -o verbose --since '16:25' --until '16:30' | head -60

# Is anything on the GPU right now?
sudo fuser -v /dev/kfd

# Is the restore worker still burning CPU?
ps -eo pid,pcpu,time,comm --sort=-time | grep -E 'kworker|kswapd' | head

# Live watch (Ctrl-C to stop)
sudo journalctl -kf | grep --line-buffered -E 'svm_range|amdkfd|oom'
```

### Mitigation held in reserve

`HSA_USERPTR_FOR_PAGED_MEM=0` is the most-cited workaround for this loop.
**Not applied.** Try it only after the memory-ceiling question is settled — one
report says it removes the amdkfd hang without relieving the reclaim pressure
underneath. `tools/start-comfyui-rocm.sh` exposes it behind
`COMFY_SVM_WORKAROUND=1` rather than defaulting it on.

---

## 4. What exists in the repo already

Seven commits on branch `claude/amd-radeon-vram-crash-9yah9m`, **unpushed** —
see §6. Every change is additive or in a file `amd-sync` does not touch, so the
branch merges cleanly alongside it.

### Tested in a cloud container (no GPU)

| What | Result |
|---|---|
| Backend suite | **486 passed, 0 failed** (baseline on `master`: 472 passed, 1 failed) |
| `npm ci` + `npm run build` | clean, Next 14.2.5 |
| Launcher `start --skip-comfy` | **exit 0** — backend up, frontend built, frontend up |
| Frontend → backend proxy | `localhost:3000/api/health` → 200 `{"status":"ok"}`, identical to backend direct |
| Launcher `status` / `stop` | correct PIDs, both ports released, no strays |
| `start-comfyui-rocm.sh` | arg/env assembly against a **stub** ComfyUI only |
| `diagnose-svm-oom.sh` | runs clean with no GPU and no sudo; every probe degrades to a readable note |

### Still blocked — needs `AiServerR9700`

- `start-comfyui-rocm.sh` has **never run against real ComfyUI or a real GPU.**
- `diagnose-svm-oom.sh` has never run anywhere `/dev/kfd` exists.
- Nothing here has touched the R9700. No GPU workload has been started from the
  cloud session, and none should be.

### The files

- `docs/AMD_ROCM_LINUX_GPU_SETUP.md` — verified machine state, the OOM
  diagnosis, and a clear split between what was read off the hardware and what
  is unconfirmed community reporting. None of the cited SVM reports are from
  `gfx1201` hardware.
- `tools/start-comfyui-rocm.sh` — ROCm-safe ComfyUI launcher. Pins
  `HIP_VISIBLE_DEVICES=0`, sets `PYTORCH_HIP_ALLOC_CONF`, adds
  `--disable-smart-memory` and `--reserve-vram 0.05` (both missing from the
  observed launch command). Changes no system state.
- `tools/diagnose-svm-oom.sh` — read-only collector for §3. Hunts every
  transient `run-*.scope` rather than the one expired hash, and *measures*
  whether the SVM loop is live instead of inferring it from a timestamp.
- `tools/start-sovereign-linux.sh` — `start` / `stop` / `status`.
  `tools/local_launcher.py` cannot run on Linux: it hardcodes
  `backend/.venv/Scripts/python.exe` in three places, plus `npm.cmd`,
  `taskkill` and `node.exe` matching. `amd-sync` does **not** fix this — it adds
  `SOVEREIGN_COMFY_*` overrides and one `os.name == "nt"` guard but leaves the
  venv paths Windows-only. Two details worth keeping: `BACKEND_ORIGIN` is
  exported for the frontend **build** (`next.config.mjs:15` otherwise defaults
  the proxy target to port 8000 and nothing reaches the backend), and
  `COMFYUI_BASE_URL` is derived from `COMFY_PORT` so the 8188-vs-8001 mismatch
  is resolved rather than merely documented.

### Bug fixes carried on this branch

- `backend/app/generators/openai_image.py` — `_resolve_storage_path` rewrote the
  URL separator to a backslash. Correct on Windows, broken on Linux where `\` is
  a legal filename character, so `/storage/uploads/source.png` became one
  literal file named `uploads\source.png`. **Every OpenAI image edit with a
  nested source path failed on Linux.** This was the pre-existing test failure on
  `master`. Note `generators/comfyui.py` does `.replace("\\", "/")` — the correct
  direction; one of the two had it backwards.
- `services/exports.py` and `services/asset_jobs.py` — the two `/storage/` path
  mappers lacking a containment check now reject absolute components and `..`.
  **Not a live vulnerability**: both only ever receive backend-generated URLs,
  and the third unguarded one (`video_generators/comfyui.py`, left alone because
  `amd-sync` rewrites it) is already guarded upstream by
  `validate_source_media_url` at `routers/videos.py:635`. The check is
  deliberately **lexical, not `resolve()`-based**, because
  `HANDOFF_CLAUDE_CODE.md` records that old export folders are junctions and
  resolving those would reject legitimate export reads.
- `docs/HOW_TO_GUIDE.md` §4 told Linux users to install "an NVIDIA GPU with
  current drivers + CUDA". It now names ROCm alongside CUDA and points here.

- `backend/workflows/product_scene_creative_qwen_edit.json` — GGUF filename
  case. Nine workflows spell it `Qwen-Image-Edit-2509-Q4_K_M.gguf`; this one
  spelled it `qwen-...`. Windows resolves both to the same file; **a
  case-sensitive filesystem does not**, so one group fails with "model not
  found". The outlier is on the **default** path: `CREATIVE_QWEN_PRECISION`
  defaults to `gguf` and `product_scene_generators/__init__.py:120` selects this
  workflow, so Transform Mode's default creative edit is the one that cannot
  resolve its model on this machine. Aligned to the nine. **If the installed
  file is actually the lowercase spelling, the fix belongs the other way round
  and the other nine are broken** — `tools/estimate_vram.py --models-dir` now
  reports `!! CASE MISMATCH on disk`, which settles it.

### Related work on `amd-sync`

`tools/verify_krea2_amd.py`, `tools/verify_linux_upscale.py`, and
`SOVEREIGN_COMFY_*` env overrides in `tools/local_launcher.py`. Note that
`verify_krea2_amd.py` hardcodes `http://127.0.0.1:8001`, so it will not reach
ComfyUI on this machine until that or the ComfyUI port is aligned.

---

## 5. Known issues not yet investigated

- **Wan 2.2 TI2V 5B renders with colour corruption on the R9700** (AMD known
  issue). This repo wires Wan video and Wan InfiniteTalk avatar workflows, so
  expect it to surface there.
- ComfyUI on **ROCm 7.1** threw `HIP error: an illegal memory access was
  encountered`. This machine is on 7.2.4, which has native `gfx1201` support,
  so the ROCm version is not currently suspect.
- Stale hardware assumptions: `backend/app/config.py`,
  `backend/app/services/image_presets.py` and
  `backend/app/services/avatar_presets.py` still reason about "16 GB VRAM /
  32 GB RAM" and exclude FLUX.2-dev and Klein 9B on that basis. The R9700 has
  32 GB. **`amd-sync` has modified all three files** — do this cleanup only
  after `amd-sync` merges, or it will conflict.

---

## 6. Blocker: GitHub write access

Commit `6637510` is committed locally but **could not be pushed**:

```
remote: Claude doesn't have GitHub access to dlove50/sovereign-creative-studio
        for your organization
fatal: ... error: 403
```

Read access works; write does not. The Claude GitHub App needs installing on
the repository (https://github.com/apps/claude/installations/select_target) or
GitHub reconnecting (https://claude.ai/connect-github). Only David or a GitHub
org owner can do this.

Until then the commit exists only as a patch file sent to David. It applies
cleanly onto `master`:

```bash
git am 0001-amd-rocm-docs-and-launcher.patch
```

If you are picking this up and the two files in §4 are missing from the repo,
that patch was never applied — ask David for it rather than rewriting them.

---

## 7. Things that are not possible from a cloud agent session

Recorded so the next agent does not waste rounds rediscovering them:

- **No access to `AiServerR9700`.** A cloud session runs in an isolated
  container with no GPU and no route to David's machines. Every host-side
  command in §3 must be run by David, or by an agent running locally on that
  box.
- **`www.amd.com`, `mesa3d.org` and `rocm.docs.amd.com` are blocked** by the
  container's network egress proxy. GitHub and web search work. Do not report
  their contents as read.
- **YouTube is blocked.** A tutorial link cannot be watched.
- **Usage credits are not observable.** No tool reports remaining quota, so no
  behaviour can be triggered by running low.
- **No agent can hand its live session to another model.** Handoff happens
  through documents like this one.
- **A cloud session must not start a GPU workload** on `AiServerR9700`, even
  once it has a route there. Owner's instruction, 2026-10-22.

### Correction to an earlier assumption

An earlier revision of this document implied the DeepSeek/Alfred harness and
GLM were Windows-only, inferred from `HANDOFF_DEEPSEEK_HARNESS.md` §1 listing
the harness under `C:\Users\David\Documents\Codex\deepseek-harness`. **The
owner states the Alfred and GLM launchers are confirmed working on Linux**, so
do not treat them as Windows-only. That is the owner's report, not something
verified from this session.

The owner also states Codex can read this session and can coordinate local
`AiServerR9700` checks. So the §3 commands do not have to wait for David at the
keyboard — a locally running agent can run them and bring the output back. They
still cannot be run from a cloud container.
