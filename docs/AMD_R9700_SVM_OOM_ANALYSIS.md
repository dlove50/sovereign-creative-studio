# R9700 SVM / OOM analysis — how to read the diagnostic and what to do

Companion to `docs/AMD_ROCM_LINUX_GPU_SETUP.md` §3 and
`tools/diagnose-svm-oom.sh`. Written 2026-10-22 from the kernel evidence
collected on `AiServerR9700`, without access to that machine.

Purpose: so that whoever runs the diagnostic can act on the output in the same
sitting instead of starting another round trip.

---

## 1. The conclusion first

**Raising the 22 GiB cgroup cap cannot fix this, and the reason is arithmetic,
not policy.**

| | |
|---|---|
| R9700 VRAM | 32 GB = **29.8 GiB** |
| Host RAM | **30 GiB** |
| GTT default (≈50% of RAM) | **15.0 GiB** |
| Scope cap that killed ComfyUI | **22 GiB** |
| Process anonymous RSS at kill | **21.9 GiB** |

VRAM and host RAM are **the same size on this machine**. A full VRAM working
set spilled to the host needs 29.8 GiB on a box that has 30 GiB total, before
the OS, the desktop, the backend and the frontend get any. There is no cap
value that makes that fit. Remove the cap entirely and a full spill takes the
whole machine down instead of one process — which is very likely what the
21:51 reading (29 GiB used, 1.1 GiB available, 24 GiB swap) was on its way to.

So the cap is not the bug. It is the thing that converted a machine-wide
failure into a single-process failure. **Treat it as a safety net that fired
correctly, and fix what overflowed.**

## 1a. RETRACTED — the "weights do not fit" finding was wrong

An earlier revision of this section claimed the repo's default product-scene
workflow loaded 29.28 GiB of weights onto a 29.80 GiB card, and named that as
the probable cause. **That was wrong.** Codex checked the real files on
`AiServerR9700` and refuted it. The claim is withdrawn.

What was wrong, and why:

- `tools/estimate_vram.py` read each loader's model filename and **ignored
  `weight_dtype`**. All eight cited workflows specify
  `weight_dtype: fp8_e4m3fn` on their `UNETLoader` — 15 of the 47 workflows do.
  The installed ComfyUI passes that FP8 dtype to the model loader, so a bf16
  checkpoint does not occupy its disk size in VRAM.
- The analysis then treated **disk size as proof of runtime residency**. It is
  not. That conflation is the whole error.
- Codex's measurements: `flux1-dev.safetensors` holds **22.17 GiB of BF16
  tensors** (not the 23.8 GiB this document estimated), and the four cited
  files total **27.51 GiB on disk** (not 29.28 GiB).

Corrected figures, from the rebuilt estimator reading real safetensors headers:

| | |
|---|---|
| four model files, on disk | ~27.5 GiB |
| `flux1-dev` requested at `fp8_e4m3fn` | 22.17 → **~11.1 GiB resident** |
| **estimated resident weights** | **~16.6 GiB** |
| estimated peak incl. latents + VAE | **~16.9 GiB** |
| R9700 VRAM | 29.80 GiB |

So the default workflow sits near **53% of the card**, not 93%. No workflow in
this repo is over budget on the corrected model.

**Do not substitute models or raise memory limits on the strength of the
retracted finding.** There was nothing to fix in those eight workflows: they
already request fp8.

One further caution Codex raised: local `backend/.env` sets
`PRODUCT_SCENE_BACKEND=mock`. Before attributing any process's memory use to a
ComfyUI workflow, confirm the running process's *effective* configuration —
the default in `config.py` is not necessarily what the running backend used.

The estimator now keeps four quantities apart — disk bytes, requested loading
precision, estimated residency, and unmeasured peak — precisely so this class
of error cannot recur. Residency is labelled an estimate and peak is labelled
UNMEASURED, in the output itself.

## 2. What actually happened

1. A ComfyUI render's working set exceeded 32 GB of VRAM.
2. The overflow went to host memory — through GTT, or through KFD SVM userptr
   mappings, or both.
3. Host memory came under pressure. Reclaim evicted pages belonging to SVM
   ranges.
4. The MMU notifier invalidated them; `svm_range_restore_work` faulted them
   straight back in; reclaim evicted them again. The worker abandons its whole
   restore walk on the first per-entry failure and reschedules after 1 ms,
   which is why the counter doubled 35 → 8195.
5. The process hit its 22 GiB scope cap at 21.9 GiB anonymous RSS, with 90,523
   failed memory charges, and was OOM-killed mid-`svm_ioctl`.

Steps 3–4 are the livelock. Step 1 is the cause. Fixing 3–4 without fixing 1
buys a slower failure.

## 3. Two numbers worth noticing

### 21.9 GiB exceeded the 15 GiB GTT default

If that memory were purely GTT-backed, it should have been bounded near
15 GiB (≈50% of RAM). It reached 21.9 GiB, which means at least one of:

- `amdgpu.gttsize` has been raised from the default;
- the allocation is KFD **SVM userptr**, which is host memory registered with
  the GPU rather than drawn from the GTT pool, so the GTT limit does not bound
  it;
- part of it is ordinary Python/PyTorch host allocation unrelated to the GPU.

`cat /sys/module/amdgpu/parameters/gttsize` (section "GPU STATE" of the
diagnostic) distinguishes the first from the others. This matters because the
remedies differ: a raised `gttsize` is a configuration decision someone made
and can unmake, whereas SVM userptr growth is driven by the workload.

### 22 GiB is not a round number for a 30 GiB box

It is, however, almost exactly **75% of 29.3 GiB**. `free -h` reporting "30Gi"
is consistent with `MemTotal` in the 29.3–30.0 GiB range, so a systemd
`MemoryMax=75%` is a strong candidate — systemd accepts percentages and
resolves them against total RAM.

This is worth settling because **the form of the setting changes the fix**:

- A **literal** `MemoryMax=22G` is a number someone chose. It stays 22 GiB if
  RAM is upgraded, silently becoming a tighter and tighter fraction.
- A **percentage** `MemoryMax=75%` tracks RAM automatically. Upgrading to
  64 GiB would move the cap to 48 GiB without anyone touching it — which also
  means a RAM upgrade would change this failure's shape without fixing cause 1.

Section "WHERE A 22 GiB CAP COULD COME FROM" of the diagnostic greps
`/etc/systemd/`, `~/.config/systemd/` and `~/ai/` for `MemoryMax`,
`MemoryHigh` and `systemd-run`. If it finds a percentage, prefer converting it
to an explicit value you have reasoned about rather than leaving it floating.

## 4. The discriminating test

Everything above assumes cause 1 — the working set genuinely exceeds 32 GB of
VRAM. That assumption should be checked, because the alternative has a
completely different fix.

Run a render while watching both numbers:

```bash
watch -n2 'rocm-smi --showmeminfo vram; echo; free -h | head -2'
```

- **VRAM climbs to ~32 GB, then host anon memory starts climbing.**
  Genuine overflow. Cause 1 confirmed. Go to §5.
- **Host anon memory climbs while VRAM stays well below 32 GB.**
  *Not* overflow — something is placing tensors in host memory that should be
  on the card. Suspects, in order: the workload is being pinned to the wrong
  device (confirm `HIP_VISIBLE_DEVICES=0` is actually selecting `gfx1201` and
  not the `gfx1036` iGPU), a model loaded with CPU offload enabled, or a
  `gttsize` large enough that the driver prefers GTT. This is a cheaper problem
  to fix than §5 and should be ruled out first.

`tools/start-comfyui-rocm.sh` pins `HIP_VISIBLE_DEVICES=0`, which removes the
first suspect. It has never been run on the real machine, so that pin is
unverified in practice.

## 5. Remedies, ranked

Assuming the discriminating test confirms genuine overflow.

**1. Establish what actually overflowed, before changing anything.** The
original "weights do not fit" theory is retracted (§1a): on the corrected model
no workflow in this repo exceeds the card, and the default sits near 53%. So
the overflow, if it was an overflow, came from something this estimator does
not model -- activations at an unusual resolution, a tiled-decode path, two
jobs resident at once, allocator fragmentation, or a workload that was not this
workflow at all (note `PRODUCT_SCENE_BACKEND=mock`). Run §4's discriminating
test and the estimator with `--models-dir` before acting.

**2. Keep `--disable-smart-memory` and `--reserve-vram`.** Already in
`tools/start-comfyui-rocm.sh`. Smart memory deliberately keeps models resident
in VRAM between runs, and resident models are precisely what gets paged out
under pressure. Note `--cache-none` was already set on the run that died, so
it is necessary but not sufficient.

**3. If a model genuinely cannot fit in 32 GB, do not spill it — replace it.**
On this hardware a spill cannot succeed, per §1.

**4. `HSA_USERPTR_FOR_PAGED_MEM=0`** — a tourniquet for the livelock, not a
fix for the overflow. One upstream report says it removes the amdkfd hang
without relieving the reclaim pressure underneath. Exposed behind
`COMFY_SVM_WORKAROUND=1` rather than defaulted on. Apply only after §4's
cause question is settled, and expect it to change the symptom rather than
remove it.

**5. More RAM — conditional, and not the headline.** I previously recommended
64 GiB; I am narrowing that. More RAM only helps if you intend to spill, and
spilling is what you are trying to stop. It is worth having for the desktop,
the backend, the frontend and Claude Desktop (which has its own OOM entries in
this kernel log) to coexist with a 32 GB GPU workload — but it will not fix
cause 1, and a percentage-form cap would scale with it and mask the problem
for longer.

## 6. The swap finding — correcting earlier advice

I earlier suggested adding swap. That was wrong twice over: the machine already
had 50 GiB, and in this specific failure mode **swap makes things worse, not
better**.

Upstream report [ROCm #6678](https://github.com/ROCm/legacy-rocm-build/issues/6678)
describes the gfx1151 livelock as triggering specifically "when an idle ROCm
process has SVM pages **swapped out**", and the gfx1100 report pairs the
amdkfd restore hang with kswapd allocation failures. Swapped-out SVM pages are
the fuel for the restore loop.

With 50 GiB of swap, memory pressure does not end in a quick OOM — it ends in
hours of a kworker faulting pages back from disk while reclaim pushes them out
again. That matches the observed history: an OOM at 16:41, then warnings
continuing to 19:53, then 24 GiB of swap in use by 21:51.

This is a trade-off, not a blanket "remove swap": with less swap you OOM
sooner and more visibly. That is arguably the better failure for a dedicated AI
box — fast and legible rather than slow and mysterious. A measured option is
lowering `vm.swappiness` so GPU-mapped anonymous pages are evicted less
eagerly. **Do not change this while a job is running, and change one thing at
a time.**

## 7. Reading the diagnostic, section by section

| Section | What to look for | What it means |
|---|---|---|
| MEMORY NOW | `available` under ~2 GiB, swap climbing | pressure is live; the loop has fuel |
| TOP 15 BY RSS | a Python process with >15 GiB and a `run-*.scope` cgroup | the overflow, and the scope that caps it |
| COMFYUI PROCESSES | its cgroup line | confirms whether it is still launched into a capped transient scope |
| ACTIVE CGROUP MEMORY LIMITS | `23622320128` | the 22 GiB cap, still in force |
| USER SLICE TREE | any non-`max` parent | an inherited cap rather than a per-scope one — different fix |
| WHAT LAUNCHES COMFYUI | `Started run-*.scope - <description>` | **the open question.** The description usually carries the command |
| WHERE A 22 GiB CAP COULD COME FROM | `MemoryMax=` literal vs `%` | decides §3's fix |
| OOM EVENTS | `oom-kill:` with `oom_memcg=` | confirms cgroup-local vs machine-wide |
| SVM RESTORE LOOP | counter doubling | the livelock signature |
| IS THE LOOP ACTIVE | delta over the sample window | live vs idle. Idle is **not** proof — it only fires under pressure with a live ROCm process |
| GPU STATE | `gttsize`, and VRAM used per GPU | §3's first discriminator, plus whether work landed on the iGPU |
| COMFYUI REACHABILITY | which of 8188/8001 answers | the unrelated-but-real port mismatch |

## 8. What would falsify this analysis

Stated plainly, because none of it has been tested on the hardware:

- If the discriminating test shows host memory climbing while VRAM stays low,
  §1's arithmetic still holds but the *cause* is misplaced allocation, and §5's
  ranking is wrong — device pinning and offload settings move to the top.
- If `gttsize` turns out to be raised well above the default, the 15 GiB figure
  in §1 is wrong and the spill had more headroom than assumed.
- If the capped scope turns out to have been launched by something unrelated to
  the studio — an agent sandbox, for instance — then the 22 GiB cap is
  incidental to ComfyUI and the interesting question becomes why ComfyUI was
  running inside it at all.
- If `MemTotal` is materially above 30 GiB, the `MemoryMax=75%` hypothesis in
  §3 fails and the cap is more likely a literal.

Every one of these is answered by a single read-only run of
`tools/diagnose-svm-oom.sh` plus one watched render.
