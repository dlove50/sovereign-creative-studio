#!/usr/bin/env bash
# Diagnose the KFD SVM restore loop / cgroup OOM on AiServerR9700.
# Background and interpretation: docs/AMD_ROCM_LINUX_GPU_SETUP.md section 3.
#
# READ-ONLY. Sets nothing, kills nothing, changes no cgroup or driver setting.
#
# Run in a REAL DESKTOP TERMINAL, not a sandboxed agent shell. A sandbox cannot
# see host processes, /dev/kfd, or systemd sockets, which blocked three earlier
# rounds of this investigation.
#
#   bash tools/diagnose-svm-oom.sh 2>&1 | tee svm-report.txt
#
# Prompts once for sudo (kernel log and /dev/kfd holders need it).
#   SKIP_SUDO=1        omit everything needing sudo
#   SAMPLE_SECONDS=30  live-loop sample window; 0 disables it

set -uo pipefail

SAMPLE_SECONDS="${SAMPLE_SECONDS:-30}"
h() { printf '\n========== %s ==========\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }

# Wrap sudo so one failure does not abort the run.
SUDO_OK=0
if [ "${SKIP_SUDO:-0}" != "1" ]; then
  if have sudo && sudo -v >/dev/null 2>&1; then SUDO_OK=1; fi
fi
ksudo() { if [ "$SUDO_OK" = "1" ]; then sudo "$@"; else return 1; fi; }

h "WHEN AND WHERE"
date
uptime
hostname
[ "$SUDO_OK" = "1" ] || echo "[note] sudo unavailable or declined; kernel-log sections will be skipped."

h "MEMORY NOW"
free -h
echo "--- swap devices ---"
swapon --show 2>/dev/null || echo "(no swap configured)"
echo "--- pressure (if available) ---"
cat /proc/pressure/memory 2>/dev/null || echo "(no PSI)"

h "TOP 15 BY RSS, WITH CGROUP"
# The cgroup column is the point: it ties each process to its container/scope.
# Lines are truncated: full command lines (ComfyUI's especially) are very long.
ps -eo pid,ppid,user,rss,etime,cgroup,args --sort=-rss 2>/dev/null \
  | head -16 | cut -c1-200

h "COMFYUI PROCESSES AND THEIR SCOPES"
if pgrep -af 'ComfyUI|main\.py' >/dev/null 2>&1; then
  pgrep -af 'ComfyUI|main\.py' | while read -r pid rest; do
    echo "pid=$pid  $rest"
    echo "   cgroup: $(cat /proc/"$pid"/cgroup 2>/dev/null | tail -1)"
    echo "   rss:    $(awk '/^VmRSS:/{print $2" "$3}' /proc/"$pid"/status 2>/dev/null)"
  done
else
  echo "(no ComfyUI process running)"
fi

h "ACTIVE CGROUP MEMORY LIMITS (non-'max' only)"
# 23622320128 == 22 GiB, the limit that killed ComfyUI on 2026-10-22.
found=0
while IFS= read -r f; do
  v=$(cat "$f" 2>/dev/null) || continue
  [ "$v" = "max" ] && continue
  [ -z "$v" ] && continue
  echo "$v  $f"
  found=1
done < <(find /sys/fs/cgroup -name memory.max 2>/dev/null)
[ "$found" = "1" ] || echo "(every memory.max reads 'max' - no active hard limit)"

h "USER SLICE TREE LIMITS"
for p in user.slice \
         user.slice/user-1000.slice \
         user.slice/user-1000.slice/user@1000.service \
         user.slice/user-1000.slice/user@1000.service/app.slice; do
  printf '%-62s max=%-12s high=%s\n' "$p" \
    "$(cat /sys/fs/cgroup/$p/memory.max 2>/dev/null || echo n/a)" \
    "$(cat /sys/fs/cgroup/$p/memory.high 2>/dev/null || echo n/a)"
done

h "WHAT LAUNCHES COMFYUI IN A TRANSIENT SCOPE"
# Generalised past the one known scope hash: find every transient run-*.scope
# systemd started, with its description (which usually carries the command).
journalctl --user -b 0 --no-pager 2>/dev/null \
  | grep -iE 'Started run-r?[0-9a-f]+\.scope' | tail -20 \
  || echo "(no transient user scopes logged this boot)"
echo "--- any scope mentioning ComfyUI ---"
journalctl --user -b 0 --no-pager 2>/dev/null | grep -i 'comfy' | tail -20 \
  || echo "(none)"
echo "--- systemd-run / MemoryMax references in the user journal ---"
journalctl --user -b 0 --no-pager 2>/dev/null \
  | grep -iE 'systemd-run|MemoryMax|MemoryHigh' | tail -15 || echo "(none)"

h "WHERE A 22 GiB CAP COULD COME FROM"
grep -rniE 'MemoryMax|MemoryHigh|systemd-run' \
  /etc/systemd/ "$HOME/.config/systemd/" "$HOME/ai/" 2>/dev/null \
  | grep -v '\.wants/' | head -20 || echo "(no MemoryMax/systemd-run in systemd config or ~/ai)"

h "OOM EVENTS (with cgroup attribution)"
if ksudo dmesg -T >/dev/null 2>&1; then
  ksudo dmesg -T 2>/dev/null \
    | grep -iE 'oom-kill:|Memory cgroup out of memory|Killed process|oom_reaper' \
    | tail -25 || echo "(no OOM events in the current kernel ring buffer)"
else
  echo "(skipped - needs sudo)"
fi
echo "--- systemd-oomd, if it acted ---"
journalctl -b 0 --no-pager 2>/dev/null | grep -i 'systemd-oomd' | tail -10 \
  || echo "(no systemd-oomd activity)"

h "SVM RESTORE LOOP - HISTORY"
if ksudo dmesg -T >/dev/null 2>&1; then
  total=$(ksudo dmesg -T 2>/dev/null | grep -c 'svm_range_restore_work' || true)
  echo "svm_range_restore_work warnings in ring buffer: ${total:-0}"
  echo "--- last 5 ---"
  ksudo dmesg -T 2>/dev/null | grep 'svm_range_restore_work' | tail -5 || echo "(none)"
  echo "--- other KFD workers ---"
  ksudo dmesg -T 2>/dev/null \
    | grep -iE 'restore_userptr_worker|svm_range_deferred|non-zero when fini' \
    | tail -8 || echo "(none)"
  echo "--- any stack traces through the SVM path ---"
  ksudo dmesg -T 2>/dev/null \
    | grep -iE 'amdgpu_hmm_range_get_pages|svm_range_validate_and_map|hung_task|BUG:|WARNING:' \
    | tail -10 || echo "(none)"
else
  echo "(skipped - needs sudo)"
fi

h "IS THE LOOP ACTIVE RIGHT NOW?"
echo "--- processes holding /dev/kfd (the direct answer) ---"
if ksudo fuser -v /dev/kfd >/dev/null 2>&1; then
  ksudo fuser -v /dev/kfd 2>&1 | head -20
else
  echo "(nothing holds /dev/kfd, or fuser needs sudo / is not installed)"
fi
echo "--- kernel workers by accumulated CPU time ---"
# A kworker with large TIME is the fingerprint of the busy-loop.
ps -eo pid,pcpu,time,comm --sort=-time 2>/dev/null \
  | grep -E 'kworker|kswapd' | head -10 || echo "(none notable)"

if [ "$SAMPLE_SECONDS" -gt 0 ] && ksudo dmesg >/dev/null 2>&1; then
  echo "--- live sample over ${SAMPLE_SECONDS}s ---"
  a=$(ksudo dmesg 2>/dev/null | grep -c 'svm_range_restore_work' || true)
  sleep "$SAMPLE_SECONDS"
  b=$(ksudo dmesg 2>/dev/null | grep -c 'svm_range_restore_work' || true)
  echo "warning count: ${a:-0} -> ${b:-0}  (delta $(( ${b:-0} - ${a:-0} )))"
  if [ "$(( ${b:-0} - ${a:-0} ))" -gt 0 ]; then
    echo "VERDICT: loop is ACTIVE - new warnings appeared during the sample."
  else
    echo "VERDICT: no new warnings in ${SAMPLE_SECONDS}s. Loop appears idle."
    echo "         Not proof: it only fires under memory pressure with a live"
    echo "         ROCm process. Re-run during a render to be sure."
  fi
else
  echo "(live sample skipped)"
fi

h "GPU STATE"
have rocm-smi && { rocm-smi --showproductname 2>&1 | head -12; echo "---"; \
  rocm-smi --showmeminfo vram 2>&1 | head -16; } || echo "(rocm-smi not on PATH)"
echo "--- agents rocminfo reports ---"
have rocminfo && rocminfo 2>&1 | grep -iE 'Marketing|^  Name:|gfx' | head -14 \
  || echo "(rocminfo absent, or cannot open /dev/kfd - check render group membership)"
echo "--- relevant env in this shell ---"
for v in HIP_VISIBLE_DEVICES ROCR_VISIBLE_DEVICES HSA_OVERRIDE_GFX_VERSION \
         HSA_USERPTR_FOR_PAGED_MEM PYTORCH_HIP_ALLOC_CONF GPU_MAX_HW_QUEUES; do
  echo "  $v=${!v:-<unset>}"
done
echo "--- amdgpu module params that matter for spill ---"
for p in gttsize vramlimit; do
  echo "  $p=$(cat /sys/module/amdgpu/parameters/$p 2>/dev/null || echo '<default>')"
done

h "COMFYUI REACHABILITY (port mismatch check)"
# The repo defaults COMFYUI_BASE_URL to 8001; this machine runs ComfyUI on 8188.
for port in 8188 8001; do
  if have curl; then
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 \
           "http://127.0.0.1:${port}/system_stats" 2>/dev/null)
    case "$code" in
      200) echo "  127.0.0.1:${port}  ComfyUI RESPONDING" ;;
      000|"") echo "  127.0.0.1:${port}  nothing listening" ;;
      *) echo "  127.0.0.1:${port}  HTTP $code" ;;
    esac
  fi
done
echo "  backend/.env COMFYUI_BASE_URL: $(grep -s '^COMFYUI_BASE_URL' backend/.env 2>/dev/null || echo '<not set - defaults to 8001>')"

printf '\n========== END OF REPORT ==========\n'
echo "Interpretation, section by section: docs/AMD_R9700_SVM_OOM_ANALYSIS.md"
echo "Background: docs/AMD_ROCM_LINUX_GPU_SETUP.md section 3."
echo
echo "Do NOT raise the cgroup memory cap based on this report alone. VRAM (29.8"
echo "GiB) and host RAM (30 GiB) are the same size on this machine, so a full"
echo "spill fits under no cap - the cap is a safety net, not the bug."
