#!/usr/bin/env bash
# Lock down the studio before other people can reach it.
#
# Written for the step David is taking: family members getting accounts on
# AiServerR9700, and the studio reachable from outside the house. Both are
# fine; the defaults that suit a single-user machine are not.
#
# What it addresses, in the order that matters:
#
#   1. ANONYMOUS OWNER ADMIN. OWNER_FALLBACK_ENABLED defaults to true, which
#      means a request with no login cookie is treated as the owner admin, with
#      no password. Harmless while the backend only talks to itself; an open
#      admin panel the moment it does not. This is a bigger problem than the
#      key file and is checked first.
#
#   2. THE SECRETS FOLDER. It holds the session signing key and the HeyGen /
#      OpenAI / ElevenLabs API keys, created world-readable under the default
#      umask. A service account owning it at 0700 is what actually keeps family
#      logins out -- not a permission bit they could flip, a different user.
#
#   3. THE BIND ADDRESS. Reported, not changed, because which interface to
#      serve is a decision about how the house uses the studio.
#
# It does NOT touch the Linux login, any password, Secure Boot or MOK signing.
# The account it creates has no password and no login shell: it never appears
# at a login prompt and cannot be logged into.
#
# Dry run by default -- it prints what it would do and changes nothing. Pass
# --apply to make the changes. Anything needing root says so rather than
# silently re-running itself with sudo.
#
#   bash tools/harden-sovereign.sh                 # show me what is wrong
#   sudo bash tools/harden-sovereign.sh --apply    # fix it
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$REPO/backend"
ENV_FILE="$BACKEND/.env"
SERVICE_USER="${SOVEREIGN_SERVICE_USER:-sovereign}"

APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

RED=$'\033[31m'; YEL=$'\033[33m'; GRN=$'\033[32m'; DIM=$'\033[2m'; OFF=$'\033[0m'
[ -t 1 ] || { RED=""; YEL=""; GRN=""; DIM=""; OFF=""; }

problems=0
changes=0

say()  { printf '%s\n' "$*"; }
ok()   { printf '  %sok%s    %s\n' "$GRN" "$OFF" "$*"; }
warn() { printf '  %swarn%s  %s\n' "$YEL" "$OFF" "$*"; problems=$((problems+1)); }
bad()  { printf '  %sFAIL%s  %s\n' "$RED" "$OFF" "$*"; problems=$((problems+1)); }
step() { printf '  %s->%s    %s\n' "$DIM" "$OFF" "$*"; }
did()  { printf '  %sdone%s  %s\n' "$GRN" "$OFF" "$*"; changes=$((changes+1)); }

is_root() { [ "$(id -u)" -eq 0 ]; }

# Read one KEY=value from backend/.env, ignoring comments and quotes.
env_value() {
  local key="$1"
  [ -f "$ENV_FILE" ] || return 0
  sed -n "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*//p" "$ENV_FILE" \
    | tail -1 | sed 's/[[:space:]]*#.*$//' | tr -d '"'"'" | tr -d '\r'
}

secrets_dir() {
  local configured; configured="$(env_value STORAGE_DIR)"
  if [ -n "$configured" ]; then printf '%s/secrets\n' "$configured"
  else printf '%s/storage/secrets\n' "$BACKEND"; fi
}

say ""
say "Sovereign hardening  ($( [ "$APPLY" -eq 1 ] && echo "APPLYING CHANGES" || echo "dry run -- nothing will change" ))"
say "repo: $REPO"
say ""

# --- 1. anonymous owner admin ------------------------------------------------
say "1. Anonymous owner admin"
fallback="$(env_value OWNER_FALLBACK_ENABLED)"
bind_host="$(env_value BACKEND_HOST)"; bind_host="${bind_host:-127.0.0.1}"
case "$(printf '%s' "$bind_host" | tr 'A-Z' 'a-z')" in
  127.0.0.1|localhost|::1|"") exposed=0 ;;
  *) exposed=1 ;;
esac

if [ -z "$fallback" ] || [ "$fallback" = "true" ]; then
  if [ "$exposed" -eq 1 ]; then
    bad "OWNER_FALLBACK_ENABLED is on AND the backend binds $bind_host."
    say  "        Any request with no login cookie is the owner admin. No password."
  else
    warn "OWNER_FALLBACK_ENABLED is on (listening on $bind_host only, so not yet exposed)."
    say  "        Turn it off before anyone else can reach this port."
  fi
  if [ "$APPLY" -eq 1 ]; then
    touch "$ENV_FILE"
    if grep -q "^[[:space:]]*OWNER_FALLBACK_ENABLED" "$ENV_FILE" 2>/dev/null; then
      sed -i 's/^[[:space:]]*OWNER_FALLBACK_ENABLED.*/OWNER_FALLBACK_ENABLED=false/' "$ENV_FILE"
    else
      printf '\n# Anonymous requests must not be owner admin once others can reach this.\nOWNER_FALLBACK_ENABLED=false\n' >> "$ENV_FILE"
    fi
    did "set OWNER_FALLBACK_ENABLED=false in backend/.env"
    say "        Create a login before restarting, or you will lock yourself out."
  else
    step "would set OWNER_FALLBACK_ENABLED=false in backend/.env"
  fi
else
  ok "OWNER_FALLBACK_ENABLED=$fallback"
fi
say ""

# --- 2a. secrets served over HTTP --------------------------------------------
# SECRETS_DIR defaults to STORAGE_DIR/secrets, and the backend mounts
# STORAGE_DIR at /storage. So GET /storage/secrets/session_secret returns the
# key that signs every session cookie, and integrations.json returns the cloud
# API keys -- to anyone who can reach the port, with no login. Verified by
# request against the running app. This is worse than the file modes below:
# those need an account on the machine, this needs only network reach.
say "2a. Secrets reachable over HTTP"
SECRETS="$(secrets_dir)"
STORAGE_ROOT="$(env_value STORAGE_DIR)"; STORAGE_ROOT="${STORAGE_ROOT:-$BACKEND/storage}"
SAFE_SECRETS="$BACKEND/private/secrets"

case "$(cd "$(dirname "$SECRETS")" 2>/dev/null && pwd)/$(basename "$SECRETS")" in
  "$(cd "$STORAGE_ROOT" 2>/dev/null && pwd)"/*) inside_mount=1 ;;
  *) inside_mount=0 ;;
esac

if [ "$inside_mount" -eq 1 ]; then
  bad "$SECRETS sits inside $STORAGE_ROOT, which is served at /storage."
  say  "        GET /storage/secrets/session_secret returns the session signing key."
  say  "        GET /storage/secrets/integrations.json returns your API keys."
  if [ "$APPLY" -eq 1 ]; then
    mkdir -p "$(dirname "$SAFE_SECRETS")" && chmod 700 "$(dirname "$SAFE_SECRETS")"
    if [ -d "$SECRETS" ]; then
      mkdir -p "$SAFE_SECRETS" && chmod 700 "$SAFE_SECRETS"
      # cp then remove, so a failure never loses the only copy of the key.
      if cp -a "$SECRETS/." "$SAFE_SECRETS/" 2>/dev/null; then
        rm -rf "$SECRETS" && did "moved secrets to $SAFE_SECRETS"
      else
        bad "could not copy $SECRETS -- left in place, nothing removed"
      fi
    else
      mkdir -p "$SAFE_SECRETS" && chmod 700 "$SAFE_SECRETS"
      did "created $SAFE_SECRETS"
    fi
    touch "$ENV_FILE"
    if grep -q "^[[:space:]]*SECRETS_DIR" "$ENV_FILE" 2>/dev/null; then
      sed -i "s|^[[:space:]]*SECRETS_DIR.*|SECRETS_DIR=$SAFE_SECRETS|" "$ENV_FILE"
    else
      printf '\n# Must sit outside STORAGE_DIR, which is served at /storage.\nSECRETS_DIR=%s\n' "$SAFE_SECRETS" >> "$ENV_FILE"
    fi
    did "set SECRETS_DIR=$SAFE_SECRETS in backend/.env"
    SECRETS="$SAFE_SECRETS"
  else
    step "would move the folder to $SAFE_SECRETS and set SECRETS_DIR in backend/.env"
  fi
else
  ok "secrets folder is outside the served tree ($SECRETS)"
fi
say ""

# --- 2b. the secrets folder --------------------------------------------------
say "2b. Secrets folder permissions"
if [ ! -d "$SECRETS" ]; then
  ok "no secrets folder yet at $SECRETS (created on first run, already restricted)"
else
  mode="$(stat -c '%a' "$SECRETS" 2>/dev/null || echo '?')"
  owner="$(stat -c '%U' "$SECRETS" 2>/dev/null || echo '?')"
  if [ "$mode" = "700" ]; then ok "folder $SECRETS is $mode, owned by $owner"
  else
    warn "folder $SECRETS is mode $mode (owner $owner) -- other accounts can list it"
    if [ "$APPLY" -eq 1 ]; then chmod 700 "$SECRETS" && did "chmod 700 $SECRETS"
    else step "would chmod 700 $SECRETS"; fi
  fi

  loose=0
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    fmode="$(stat -c '%a' "$f" 2>/dev/null || echo '?')"
    [ "$fmode" = "600" ] && continue
    loose=$((loose+1))
    warn "$(basename "$f") is mode $fmode -- readable by other accounts"
    if [ "$APPLY" -eq 1 ]; then chmod 600 "$f" && did "chmod 600 $(basename "$f")"
    else step "would chmod 600 $(basename "$f")"; fi
  done < <(find "$SECRETS" -maxdepth 1 -type f 2>/dev/null)
  [ "$loose" -eq 0 ] && ok "every file in it is already 600"
fi
say ""

# --- 3. service account ------------------------------------------------------
say "3. Service account"
if id "$SERVICE_USER" >/dev/null 2>&1; then
  ok "user '$SERVICE_USER' exists"
  account_ready=1
else
  warn "no '$SERVICE_USER' account; the studio runs as a human user, so any"
  say  "        account that can read that user's files can read the API keys"
  account_ready=0
  if [ "$APPLY" -eq 1 ]; then
    if is_root; then
      useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER" \
        && { did "created system user '$SERVICE_USER' (no password, no shell)"; account_ready=1; } \
        || bad "could not create '$SERVICE_USER'"
    else
      bad "creating '$SERVICE_USER' needs root -- re-run with sudo"
    fi
  else
    step "would create system user '$SERVICE_USER' (no password, no login shell)"
  fi
fi

if [ -d "$SECRETS" ] && [ "$account_ready" -eq 1 ]; then
  current_owner="$(stat -c '%U' "$SECRETS" 2>/dev/null || echo '?')"
  if [ "$current_owner" = "$SERVICE_USER" ]; then
    ok "secrets folder is owned by '$SERVICE_USER'"
  elif [ "$APPLY" -eq 1 ] && is_root; then
    chown -R "$SERVICE_USER":"$SERVICE_USER" "$SECRETS" \
      && did "secrets folder now owned by '$SERVICE_USER'"
  elif [ "$APPLY" -eq 1 ]; then
    bad "changing ownership needs root -- re-run with sudo"
  else
    step "would chown the secrets folder to '$SERVICE_USER'"
    say  "        (run the backend as that user afterwards, or it cannot read them)"
  fi
fi
say ""

# --- 4. who else is on this machine -----------------------------------------
say "4. Other accounts on this machine"
# Only accounts a person could actually log into. A UID filter alone also
# catches service accounts -- Nix build users, container daemons -- which are
# not people and make the real answer hard to see.
others="$(awk -F: '$3>=1000 && $3<65534 && $1!="nobody" \
                   && $7!~/(nologin|\/false)$/ {print $1}' /etc/passwd 2>/dev/null \
          | grep -vx "$(id -un)" | tr '\n' ' ')"
if [ -z "${others// /}" ]; then
  ok "only $(id -un) -- nobody else was positioned to read the keys"
else
  warn "other accounts exist: $others"
  say  "        If the keys were loose before now, treat them as seen by these"
  say  "        accounts and rotate them in each provider's dashboard."
fi
say ""

# --- 5. bind address (reported, never changed) -------------------------------
say "5. Reachability"
if [ "$exposed" -eq 1 ]; then
  warn "backend binds $bind_host, so other machines can reach it"
  say  "        Prefer binding 127.0.0.1 and reaching it over a private network"
  say  "        (Tailscale, WireGuard). That removes the public internet entirely."
else
  ok "backend binds $bind_host -- this machine only"
  say  "        For access from outside the house, prefer a private network over"
  say  "        forwarding a port."
fi
say ""

# --- summary -----------------------------------------------------------------
if [ "$APPLY" -eq 1 ]; then
  say "Applied $changes change(s)."
  [ "$changes" -gt 0 ] && say "Restart the backend so it picks them up."
else
  say "Dry run. Found $problems thing(s) worth changing."
  [ "$problems" -gt 0 ] && say "Re-run with --apply (and sudo, for the service account) to fix them."
fi
say ""
[ "$problems" -gt 0 ] && [ "$APPLY" -eq 0 ] && exit 1
exit 0
