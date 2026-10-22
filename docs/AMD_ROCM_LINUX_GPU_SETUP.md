# AMD Radeon AI PRO R9700 — ROCm / Linux GPU Notes

Operational record for the dedicated AI machine (`AiServerR9700`). Written
2026-10-22 from a live diagnostic session. Everything in **Verified state** was
read off the machine itself; everything in **Unverified** is community reporting
that matched the symptoms but was not confirmed on this hardware.

The headline finding is at the bottom under *Open problem*: the recurring crash
is **not** a driver fault. It is a memory-ceiling failure during KFD SVM paging.

---

## 1. Verified state of the machine

| Item | Value |
|---|---|
| OS | Linux Mint 22.3 "Zena" (`ID=linuxmint`, `UBUNTU_CODENAME=noble`) |
| Upstream base | Ubuntu 24.04 (noble) |
| Kernel | `7.0.0-38-generic #38~24.04.4-Ubuntu` |
| Secure Boot | **Enabled** |
| GPU 0 | `gfx1201` — Radeon AI PRO R9700, 32 GB, PCI `03:00.0`, device `1002:7551` |
| GPU 1 | `gfx1036` — Ryzen integrated graphics, PCI `13:00.0`, device `1002:13c0` |
| ROCm | **7.2.4**, at `/opt/rocm-7.2.4` |
| Host RAM | 30 GiB |
| Swap | 50 GiB |
| Groups | `david` is in both `render` and `video` |

ROCm apt sources (note these are hand-added, not from `amdgpu-install`):

```
deb [arch=amd64 signed-by=/etc/apt/keyrings/rocm.gpg] https://repo.radeon.com/rocm/apt/7.2.4 noble main
deb [arch=amd64 signed-by=/etc/apt/keyrings/rocm.gpg] https://repo.radeon.com/graphics/7.2.4/ubuntu noble main
```

### Why Mint was never a blocker

`amdgpu-install` refuses to run on Mint because it checks `ID` in
`/etc/os-release`, which reads `linuxmint`. Installing straight from the
`repo.radeon.com` apt repositories (as above) bypasses that check entirely.
Do **not** bother with the os-release bind-mount workaround — it is unnecessary
here.

### Secure Boot

Harmless as configured, because this machine uses the **in-tree** `amdgpu`
module. If a DKMS `amdgpu` is ever installed, Secure Boot will refuse to load
the unsigned module and ROCm will silently see no GPU — a MOK key enrolment
would be required at that point.

### Always pin to the R9700

Two AMD GPUs are present and ROCm enumerates both. GPU 1 is the CPU's
integrated graphics and must never receive AI work:

```bash
export HIP_VISIBLE_DEVICES=0     # gfx1201, the R9700
```

Confirm the mapping after any kernel or ROCm change — enumeration order is not
guaranteed stable:

```bash
rocm-smi --showproductname
rocminfo | grep -E 'Marketing|^  Name:|gfx'
```

---

## 2. ComfyUI on this machine

Observed running command (from the systemd journal):

```
/home/david/ai/ComfyUI/.venv/bin/python main.py \
  --listen 127.0.0.1 --port 8188 \
  --use-pytorch-cross-attention --disable-pinned-memory --cache-none
```

### Port mismatch — action required

This repository expects ComfyUI on **port 8001**:

- `backend/app/config.py` → `COMFYUI_BASE_URL` defaults to `http://127.0.0.1:8001`
- `tools/verify_krea2_amd.py` hardcodes `http://127.0.0.1:8001`

ComfyUI on this machine listens on **8188**. The backend cannot reach it until
one of the two is aligned. Preferred fix — set this in `backend/.env`:

```
COMFYUI_BASE_URL=http://127.0.0.1:8188
```

(Changing ComfyUI's port to 8001 instead would also work, but `verify_krea2_amd.py`
hardcodes 8001, so matching the env var is the lower-friction direction.)

### Flags

Already set and correct: `--disable-pinned-memory`, `--cache-none`.

**Missing and recommended** for this card:

| Flag | Why |
|---|---|
| `--disable-smart-memory` | ComfyUI otherwise keeps models resident in VRAM between runs — exactly the state that gets paged out under pressure |
| `--reserve-vram 0.05` | Leaves headroom; reduces ROCm pointer-mapping failures |

`tools/start-comfyui-rocm.sh` in this repo launches with all of the above and
pins `HIP_VISIBLE_DEVICES=0`.

---

## 3. Open problem — SVM paging OOM

**This is unresolved. Read before changing memory settings.**

### What happens

A ComfyUI render drives the KFD shared-virtual-memory path into a restore loop.
Kernel log shows `svm_range_restore_work` warnings whose counter **doubles**
each time — 35, 67, 131, 259, 515, 1027, 2051, 4099, 8195 — alongside
`amdgpu_amdkfd_restore_userptr_worker` climbing 4 → 259, and a stack trace
through:

```
kfd_ioctl → kfd_ioctl_svm → svm_range_set_attr
          → svm_range_validate_and_map → amdgpu_hmm_range_get_pages
```

Mechanism (per community reports, see §4): memory pressure evicts pages
belonging to SVM ranges, the MMU notifier invalidates them, the restore worker
immediately faults them back in, reclaim evicts them again. The worker abandons
its whole restore walk on the first per-entry failure and reschedules after
1 ms, which is why the counter explodes.

### The kill

On 2026-10-22 at 16:41:42, ComfyUI's Python process (PID 173296) was OOM-killed
at ~21.9 GiB RSS against a **22 GiB scope-local `memory.max`** (plus a 2 GiB swap
limit), having accumulated **90,523 failed memory charges**. The cgroup was a
transient systemd user scope:

```
/user.slice/user-1000.slice/user@1000.service/app.slice/run-rfdf54a8c220f42dc831dfa47c8f10fd3.scope
```

Started 16:27:31. All four surviving parent cgroups show unlimited `memory.max`
and `memory.high`, so **the 22 GiB limit came from the transient scope itself**.
Whatever launched ComfyUI supplied it. That launcher has not been identified.

### Do not simply raise the cap

Two reasons:

1. **The cap was probably protecting the host.** 22 GiB on a 30 GiB machine
   bounded the damage to one process. Uncapped, the same workload takes the
   whole box down.
2. **The cap is not the cause.** The cause is the render's working set exceeding
   32 GB of VRAM and spilling into host RAM through GTT. GTT defaults to roughly
   half of system RAM (~15 GiB here), which is *less than half* the card's VRAM,
   so there is nowhere for a spill to land.

The real fix is keeping the workload inside VRAM — smaller model, lower
resolution, smaller batch, `--reserve-vram` — not granting it more host memory.

### Current status: NOT resolved

ComfyUI relaunched at 16:42, 18:00, 19:14, 19:21 and 20:35. Last recorded
`svm_range_restore_work` warning: 19:53:29. At 21:51 EDT the host showed
**29 GiB used, 1.1 GiB available, 24 GiB swap used** — so pressure had returned.
An earlier "nothing is thrashing now" reading was taken during a lull and does
not hold.

Separately, the kernel log carries **global** OOM events involving
`app-com.anthropic.Claude-12662.scope` and `claude-desktop`. Those are a
different trigger from the ComfyUI scope OOM, but they show desktop apps also
competing for memory on a 30 GiB host.

### How to interpret the results

**`docs/AMD_R9700_SVM_OOM_ANALYSIS.md`** reads the diagnostic output section by
section and says what each finding implies. Its headline: raising the 22 GiB cap
cannot fix this, because VRAM (29.8 GiB) and host RAM (30 GiB) are the same size
on this machine, so a full spill does not fit under *any* cap. It also gives the
test that distinguishes genuine VRAM overflow from tensors being misplaced into
host memory — the two have different fixes.

### Next diagnostic steps

Run in a real desktop terminal — a sandboxed agent shell cannot see host
processes, `/dev/kfd`, or systemd sockets:

```bash
# What launched the capped scope? journald retains dead units.
journalctl --user -b 0 --no-pager | grep -i 'rfdf54a8c'
journalctl --user -b 0 -o verbose --since '16:25' --until '16:30' | head -60

# Is anything on the GPU right now?
sudo fuser -v /dev/kfd

# Is the restore worker still burning CPU?
ps -eo pid,pcpu,time,comm --sort=-time | grep -E 'kworker|kswapd' | head

# Live kernel watch (Ctrl-C to stop)
sudo journalctl -kf | grep --line-buffered -E 'svm_range|amdkfd|oom'
```

### Mitigation held in reserve

`HSA_USERPTR_FOR_PAGED_MEM=0` is the most-cited workaround for this exact loop.
It is **not** applied on this machine and should only be tried after the memory
ceiling question is settled — one report notes it removes the amdkfd hang
without relieving the underlying reclaim pressure. `tools/start-comfyui-rocm.sh`
exposes it behind an explicit opt-in (`COMFY_SVM_WORKAROUND=1`) rather than
enabling it by default.

---

## 4. Unverified — community reports that matched

None of these are from `gfx1201` hardware. The symptom pattern matched closely,
but RDNA4-specific status is unconfirmed.

- [ROCm #6678](https://github.com/ROCm/legacy-rocm-build/issues/6678) — gfx1151
  Strix Halo: `svm_range_restore_work` busy-loops a kworker at 100% "for days"
  when an idle ROCm process has SVM pages swapped out.
- [Strata #2729](https://github.com/Niko1221/Strata/issues/2729) — gfx1100,
  RX 7900 XT with **31 GiB RAM** (comparable to this host's 30 GiB): amdkfd SVM
  restore hangs plus kswapd order-0 allocation failures.
- [TheRock #9184](https://github.com/ROCm/TheRock/issues/9184) — RDNA3: SVM
  mapping failure during sequential model loads; documents the doubling
  "hogged CPU" counter and the 1 ms reschedule behaviour.
- [TheRock #9267](https://github.com/ROCm/TheRock/issues/9267) — mmap-backed
  large-model upload stalls with SVM mapping failures.
- ComfyUI instability on the R9700 under **ROCm 7.1** produced
  `HIP error: an illegal memory access was encountered`; ROCm 6.4 was reported
  stable. This machine runs 7.2.4, which has native gfx1201 support — the
  version is not suspect.
- AMD known issue: **Wan 2.2 TI2V 5B** renders with abnormal colours / visual
  corruption on the R9700. Relevant because this repo wires Wan video and Wan
  InfiniteTalk avatar workflows.

### Windows, for reference

The original crash on this card occurred on Windows and has a separate, fully
confirmed cause — relevant only if that machine is still in use.
[llama.cpp #23443](https://github.com/ggml-org/llama.cpp/discussions/23443):
Adrenalin `32.0.31007.5012` (2026-05-12) and later builds up to
`32.0.31021.5001` install aggressive DPM power management that evicts the
*entire* VRAM allocation to system RAM after ~15 s idle — a genuine WDDM
eviction to the allocation backing store, not GTT spillover. 32 GB of VRAM
copied into 32 GB of RAM crashes the machine.

- Confirmed working: `32.0.22042.14002` (2026-03-09, base Windows driver, no
  Adrenalin package).
- Confirmed **ineffective**: `DisableGpuMemoryTrim` registry key,
  `KMD_EnableContextBasedPowerManagement=0`, disabling PCIe Link State Power
  Management.
- Affects both Vulkan and ROCm backends; WSL2 + ROCm does not escape it.

Note that `pipe.to("cuda")` is correct on ROCm — PyTorch keeps the `cuda`
device string on AMD. It is not a bug, and `enable_model_cpu_offload()` has no
place in this repository, which drives ComfyUI over HTTP rather than using
`diffusers` directly.
