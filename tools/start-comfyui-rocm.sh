#!/usr/bin/env bash
# Launch ComfyUI on the AMD Radeon AI PRO R9700 (gfx1201) with ROCm-safe
# settings. See docs/AMD_ROCM_LINUX_GPU_SETUP.md for why each setting is here.
#
# This script changes no system state: no cgroup limits, no sysctl, no driver
# settings. It only sets environment variables for the process it starts.
#
# Everything is overridable:
#   COMFY_DIR   ComfyUI checkout            (default: $HOME/ai/ComfyUI)
#   COMFY_PY    interpreter                 (default: $COMFY_DIR/.venv/bin/python)
#   COMFY_HOST  listen address              (default: 127.0.0.1)
#   COMFY_PORT  listen port                 (default: 8188)
#   COMFY_EXTRA_ARGS   appended to the command line
#   COMFY_SVM_WORKAROUND=1  opt in to HSA_USERPTR_FOR_PAGED_MEM=0 (see docs §3)
#   COMFY_SKIP_CHECKS=1     skip pre-flight checks

set -euo pipefail

COMFY_DIR="${COMFY_DIR:-$HOME/ai/ComfyUI}"
COMFY_PY="${COMFY_PY:-$COMFY_DIR/.venv/bin/python}"
COMFY_HOST="${COMFY_HOST:-127.0.0.1}"
COMFY_PORT="${COMFY_PORT:-8188}"

# --- GPU selection ----------------------------------------------------------
# GPU 0 is the R9700 (gfx1201). GPU 1 is the Ryzen integrated graphics
# (gfx1036) and must never receive AI work. Verify with: rocm-smi --showproductname
export HIP_VISIBLE_DEVICES="${HIP_VISIBLE_DEVICES:-0}"

# --- ROCm allocator ---------------------------------------------------------
# Reduces pointer-mapping failures and allocator fragmentation under ROCm.
export PYTORCH_HIP_ALLOC_CONF="${PYTORCH_HIP_ALLOC_CONF:-garbage_collection_threshold:0.8,max_split_size_mb:256}"

# --- Optional SVM workaround (NOT on by default) ----------------------------
# Mitigates the svm_range_restore_work livelock. Treats the symptom, not the
# cause. Settle the memory-ceiling question first — docs/AMD_ROCM_LINUX_GPU_SETUP.md §3.
if [ "${COMFY_SVM_WORKAROUND:-0}" = "1" ]; then
  export HSA_USERPTR_FOR_PAGED_MEM=0
  echo "[warn] HSA_USERPTR_FOR_PAGED_MEM=0 enabled (symptom mitigation)."
fi

# --- ComfyUI flags ----------------------------------------------------------
#   --disable-smart-memory   do not keep models resident in VRAM between runs;
#                            resident models are what get paged out under pressure
#   --disable-pinned-memory  avoids ROCm pinned-host-memory problems on RDNA4
#   --reserve-vram 0.05      leaves headroom for transient allocations
#   --cache-none             do not cache intermediate node results
#   --use-pytorch-cross-attention  stable attention path on ROCm
COMFY_ARGS=(
  main.py
  --listen "$COMFY_HOST"
  --port "$COMFY_PORT"
  --use-pytorch-cross-attention
  --disable-smart-memory
  --disable-pinned-memory
  --reserve-vram 0.05
  --cache-none
)
# shellcheck disable=SC2206
[ -n "${COMFY_EXTRA_ARGS:-}" ] && COMFY_ARGS+=(${COMFY_EXTRA_ARGS})

# --- Pre-flight -------------------------------------------------------------
if [ "${COMFY_SKIP_CHECKS:-0}" != "1" ]; then
  [ -d "$COMFY_DIR" ] || { echo "[error] COMFY_DIR not found: $COMFY_DIR" >&2; exit 1; }
  [ -x "$COMFY_PY" ]  || { echo "[error] interpreter not executable: $COMFY_PY" >&2; exit 1; }
  [ -f "$COMFY_DIR/main.py" ] || { echo "[error] no main.py in $COMFY_DIR" >&2; exit 1; }

  # Confirm the selected device really is the R9700. Warning only: rocm-smi may
  # be absent, and enumeration order is not guaranteed across kernel/ROCm changes.
  if command -v rocm-smi >/dev/null 2>&1; then
    if ! rocm-smi --showproductname 2>/dev/null | grep -qi 'gfx1201'; then
      echo "[warn] rocm-smi did not report gfx1201. Confirm HIP_VISIBLE_DEVICES"
      echo "       actually selects the R9700 and not the Ryzen iGPU (gfx1036)."
    fi
  else
    echo "[warn] rocm-smi not on PATH; skipping GPU identity check."
  fi

  # Host memory headroom. The known failure mode is a VRAM spill into host RAM
  # via GTT during KFD SVM paging, which OOMs when the host is already full.
  if avail_kb=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo 2>/dev/null) \
     && [ -n "$avail_kb" ]; then
    avail_gib=$(( avail_kb / 1024 / 1024 ))
    echo "[info] host memory available: ${avail_gib} GiB"
    if [ "$avail_gib" -lt 8 ]; then
      echo "[warn] Under 8 GiB available. A VRAM spill is likely to OOM."
      echo "       See docs/AMD_ROCM_LINUX_GPU_SETUP.md §3 before a large render."
    fi
  fi
fi

echo "[info] HIP_VISIBLE_DEVICES=$HIP_VISIBLE_DEVICES"
echo "[info] listening on http://$COMFY_HOST:$COMFY_PORT"
echo "[info] reminder: set COMFYUI_BASE_URL=http://127.0.0.1:$COMFY_PORT in backend/.env"
echo "[info] exec: $COMFY_PY ${COMFY_ARGS[*]}"

cd "$COMFY_DIR"
exec "$COMFY_PY" "${COMFY_ARGS[@]}"
