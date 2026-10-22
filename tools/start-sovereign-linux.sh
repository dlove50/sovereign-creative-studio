#!/usr/bin/env bash
# Start / stop / status for Sovereign Creative Studio on Linux.
#
# tools/local_launcher.py is Windows-only: it hardcodes
# backend/.venv/Scripts/python.exe, npm.cmd and taskkill. This is the Linux
# equivalent for the dedicated AI machine. See docs/AMD_ROCM_LINUX_GPU_SETUP.md.
#
#   bash tools/start-sovereign-linux.sh start
#   bash tools/start-sovereign-linux.sh status
#   bash tools/start-sovereign-linux.sh stop
#
# Options for `start`:
#   --skip-comfy    leave ComfyUI alone (already running, or started elsewhere)
#   --dev           run the frontend with `npm run dev` instead of a prod build
#
# Environment:
#   COMFY_PORT      ComfyUI port                  (default 8188)
#   BACKEND_PORT    backend port                  (default 8002)
#   FRONTEND_PORT   frontend port                 (default 3000)
#   NEXT_DIST_DIR   Next build dir                (passed through if set)
#   SOVEREIGN_LOG_DIR  where service logs go      (default <repo>/work/logs)

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

COMFY_PORT="${COMFY_PORT:-8188}"
BACKEND_PORT="${BACKEND_PORT:-8002}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
LOG_DIR="${SOVEREIGN_LOG_DIR:-$ROOT/work/logs}"

BACKEND_PY="$BACKEND/.venv/bin/python"
BACKEND_ORIGIN="http://127.0.0.1:${BACKEND_PORT}"

# The backend reaches ComfyUI through this. The repo default is 8001, but
# ComfyUI on this machine listens on 8188, so derive it from COMFY_PORT unless
# the operator has set it explicitly.
export COMFYUI_BASE_URL="${COMFYUI_BASE_URL:-http://127.0.0.1:${COMFY_PORT}}"

info() { printf '[info] %s\n' "$*"; }
warn() { printf '[warn] %s\n' "$*" >&2; }
die()  { printf '[error] %s\n' "$*" >&2; exit 1; }

# --- port helpers -----------------------------------------------------------
# Try each detector until one yields PIDs. No single one is reliable
# everywhere: lsof cannot see Next.js's listening socket in some containers
# (it reports nothing for a port that is demonstrably serving), while fuser
# finds it. Order matters, so do not collapse this into one command.
port_pids() {
  local port="$1" pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids=$(lsof -t -i "TCP:${port}" -s TCP:LISTEN 2>/dev/null)
  fi
  if [ -z "$pids" ] && command -v fuser >/dev/null 2>&1; then
    # fuser prints "<port>/tcp:" on stderr and the PIDs on stdout.
    pids=$(fuser -n tcp "$port" 2>/dev/null | tr -s ' ' '\n' | grep -E '^[0-9]+$')
  fi
  if [ -z "$pids" ] && command -v ss >/dev/null 2>&1; then
    pids=$(ss -ltnp "sport = :${port}" 2>/dev/null \
      | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u)
  fi
  printf '%s' "$pids"
}

port_open() { [ -n "$(port_pids "$1")" ]; }

# --- health -----------------------------------------------------------------
http_ok() { # url -> 0 if 2xx/3xx
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 "$1" 2>/dev/null)
  [ -n "$code" ] && [ "$code" -ge 200 ] && [ "$code" -lt 400 ]
}

backend_healthy() {
  # amd-sync serves /api/health; master only has /api/generations/presets.
  # Accept either so this works on both.
  http_ok "http://127.0.0.1:${BACKEND_PORT}/api/health" \
    || http_ok "http://127.0.0.1:${BACKEND_PORT}/api/generations/presets"
}

wait_for() { # label url timeout_seconds
  local label="$1" url="$2" timeout="$3" waited=0
  while [ "$waited" -lt "$timeout" ]; do
    if http_ok "$url"; then info "$label is up."; return 0; fi
    sleep 2; waited=$((waited + 2))
  done
  warn "$label did not come up within ${timeout}s."
  return 1
}

wait_backend() {
  local timeout="${1:-45}" waited=0
  while [ "$waited" -lt "$timeout" ]; do
    if backend_healthy; then info "Backend is up."; return 0; fi
    sleep 2; waited=$((waited + 2))
  done
  warn "Backend did not come up within ${timeout}s. Log: $LOG_DIR/backend.log"
  return 1
}

# --- commands ---------------------------------------------------------------
do_status() {
  # HEALTH is the authoritative column. PIDs can be blank for a service that is
  # genuinely serving, because process/port attribution is not reliable in every
  # environment, so never conclude "down" from a missing PID alone.
  printf '%-10s %-6s %-16s %s\n' SERVICE PORT PID HEALTH
  local pids health
  for spec in "ComfyUI:$COMFY_PORT" "Backend:$BACKEND_PORT" "Frontend:$FRONTEND_PORT"; do
    local name="${spec%%:*}" port="${spec##*:}"
    pids=$(port_pids "$port" | tr '\n' ' ')
    case "$name" in
      ComfyUI)  http_ok "http://127.0.0.1:${port}/system_stats" && health=serving || health="not responding" ;;
      Backend)  backend_healthy && health=serving || health="not responding" ;;
      Frontend) http_ok "http://127.0.0.1:${port}" && health=serving || health="not responding" ;;
    esac
    printf '%-10s %-6s %-16s %s\n' "$name" "$port" "${pids:-"-"}" "$health"
  done
  echo
  echo "COMFYUI_BASE_URL=$COMFYUI_BASE_URL"
}

do_stop() {
  local any=0
  # Frontend and backend first, ComfyUI last: it is the slowest to restart.
  for spec in "Frontend:$FRONTEND_PORT" "Backend:$BACKEND_PORT" "ComfyUI:$COMFY_PORT"; do
    local name="${spec%%:*}" port="${spec##*:}" pids
    pids=$(port_pids "$port")
    [ -z "$pids" ] && continue
    any=1
    info "Stopping $name on port $port (pid $(echo "$pids" | tr '\n' ' '))"
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null
    local waited=0
    while [ "$waited" -lt 10 ] && port_open "$port"; do sleep 1; waited=$((waited + 1)); done
    if port_open "$port"; then
      warn "$name did not exit; sending SIGKILL."
      # shellcheck disable=SC2086
      kill -9 $(port_pids "$port") 2>/dev/null
    fi
  done
  [ "$any" = "1" ] || info "Nothing was running."
}

do_start() {
  local skip_comfy=0 dev=0
  for a in "$@"; do
    case "$a" in
      --skip-comfy) skip_comfy=1 ;;
      --dev) dev=1 ;;
      *) die "unknown option for start: $a" ;;
    esac
  done

  [ -x "$BACKEND_PY" ] || die "backend venv missing: $BACKEND_PY
  Create it:  cd $BACKEND && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  [ -f "$FRONTEND/package.json" ] || die "frontend package.json missing: $FRONTEND/package.json"
  command -v npm >/dev/null 2>&1 || die "npm is not on PATH (install Node.js 20 LTS)"
  command -v curl >/dev/null 2>&1 || die "curl is not on PATH"
  mkdir -p "$LOG_DIR"

  # 1/3 ComfyUI
  if [ "$skip_comfy" = "1" ]; then
    info "[1/3] Skipping ComfyUI (--skip-comfy)."
  elif port_open "$COMFY_PORT"; then
    info "[1/3] ComfyUI already listening on $COMFY_PORT."
  else
    local comfy_sh="$ROOT/tools/start-comfyui-rocm.sh"
    [ -f "$comfy_sh" ] || die "missing $comfy_sh"
    info "[1/3] Starting ComfyUI on 127.0.0.1:$COMFY_PORT"
    COMFY_PORT="$COMFY_PORT" nohup bash "$comfy_sh" \
      >"$LOG_DIR/comfyui.log" 2>&1 &
    wait_for ComfyUI "http://127.0.0.1:${COMFY_PORT}/system_stats" 120 \
      || warn "Continuing without ComfyUI; local generation will not work."
  fi

  # 2/3 Backend
  if backend_healthy; then
    info "[2/3] Backend already healthy on $BACKEND_PORT."
  else
    port_open "$BACKEND_PORT" && die "port $BACKEND_PORT is taken by something that is not the backend; stop it first"
    info "[2/3] Starting backend on $BACKEND_ORIGIN"
    ( cd "$BACKEND" && COMFYUI_BASE_URL="$COMFYUI_BASE_URL" nohup "$BACKEND_PY" \
        -m uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" \
        >"$LOG_DIR/backend.log" 2>&1 & )
    wait_backend 60 || die "backend failed to start; see $LOG_DIR/backend.log"
  fi

  # 3/3 Frontend
  if http_ok "http://127.0.0.1:${FRONTEND_PORT}"; then
    info "[3/3] Frontend already serving on $FRONTEND_PORT."
  else
    # BACKEND_ORIGIN must be present at BUILD time: next.config.mjs otherwise
    # defaults the proxy target to port 8000 and nothing reaches the backend.
    if [ "$dev" = "1" ]; then
      info "[3/3] Starting frontend (development) on $FRONTEND_PORT"
      ( cd "$FRONTEND" && BACKEND_ORIGIN="$BACKEND_ORIGIN" nohup npm run dev \
          >"$LOG_DIR/frontend.log" 2>&1 & )
    else
      info "[3/3] Building frontend (BACKEND_ORIGIN=$BACKEND_ORIGIN)"
      ( cd "$FRONTEND" && BACKEND_ORIGIN="$BACKEND_ORIGIN" npm run build \
          >"$LOG_DIR/frontend-build.log" 2>&1 ) \
        || die "frontend build failed; see $LOG_DIR/frontend-build.log"
      info "[3/3] Starting frontend (production) on $FRONTEND_PORT"
      ( cd "$FRONTEND" && BACKEND_ORIGIN="$BACKEND_ORIGIN" nohup npm run start \
          >"$LOG_DIR/frontend.log" 2>&1 & )
    fi
    wait_for Frontend "http://127.0.0.1:${FRONTEND_PORT}" 120 \
      || die "frontend did not come up; see $LOG_DIR/frontend.log"
  fi

  echo
  info "All requested services are ready."
  echo "  ComfyUI:  http://127.0.0.1:$COMFY_PORT"
  echo "  Backend:  $BACKEND_ORIGIN"
  echo "  Frontend: http://localhost:$FRONTEND_PORT"
  echo "  Logs:     $LOG_DIR"
}

case "${1:-}" in
  start) shift; do_start "$@" ;;
  stop)  do_stop ;;
  status) do_status ;;
  *) echo "usage: $(basename "$0") {start [--skip-comfy] [--dev] | stop | status}" >&2
     exit 2 ;;
esac
