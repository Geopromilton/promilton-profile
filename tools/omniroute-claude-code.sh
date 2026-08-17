#!/usr/bin/env bash
# omniroute-claude-code.sh — configure the Claude Code CLI to route through OmniRoute.
#
# Scope: the terminal Claude Code CLI only. The Claude Desktop app cannot be routed
# through OmniRoute — it overwrites ANTHROPIC_BASE_URL from its own internal API host
# and blanks ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN / ANTHROPIC_CUSTOM_HEADERS on the
# agent child process, injecting an OAuth token instead. This script will not pretend
# otherwise and has no desktop mode.
#
# Usage:
#   ./omniroute-claude-code.sh check                 # preflight only, changes nothing
#   ./omniroute-claude-code.sh models [substring]    # list model ids the install exposes
#   ./omniroute-claude-code.sh setup [model-or-combo]   # default: auto/best-free
#   ./omniroute-claude-code.sh verify [model]        # end-to-end test through claude CLI
#   ./omniroute-claude-code.sh revert                # remove block + GUI-level leftovers
#
# Flags:
#   --url <url>    gateway base URL           (default http://localhost:20128)
#   --key <key>    gateway API key            (default omniroute)
#   --rc <path>    rc file to edit            (default ~/.zshrc on macOS, ~/.bashrc on Linux)
#   --force        write a model id that /v1/models did not list (custom combos)
#   --yes          do not prompt for confirmation

set -uo pipefail

GATEWAY_URL="http://localhost:20128"
GATEWAY_KEY="omniroute"
# Default routes to free models only, so this works without a paid provider key.
DEFAULT_MODEL="auto/best-free"
RC_FILE=""
FORCE=0
ASSUME_YES=0

BEGIN_MARK="# === OmniRoute Configuration for Claude Code CLI ==="
END_MARK="# === End OmniRoute Configuration ==="

# Variables that, if pinned in settings.json's env block, beat the shell environment.
CONFLICT_KEYS=(
  ANTHROPIC_MODEL
  ANTHROPIC_DEFAULT_OPUS_MODEL
  ANTHROPIC_DEFAULT_SONNET_MODEL
  ANTHROPIC_DEFAULT_HAIKU_MODEL
  ANTHROPIC_SMALL_FAST_MODEL
)

red()  { printf '\033[31m%s\033[0m\n' "$*"; }
grn()  { printf '\033[32m%s\033[0m\n' "$*"; }
ylw()  { printf '\033[33m%s\033[0m\n' "$*"; }
bold() { printf '\033[1m%s\033[0m\n' "$*"; }
die()  { red "error: $*" >&2; exit 1; }

default_rc() {
  if [ "$(uname -s)" = "Darwin" ]; then echo "$HOME/.zshrc"; else echo "$HOME/.bashrc"; fi
}

# ---------------------------------------------------------------- arg parsing

CMD="${1:-}"; shift || true
ARG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --url)   GATEWAY_URL="${2:?--url needs a value}"; shift 2 ;;
    --key)   GATEWAY_KEY="${2:?--key needs a value}"; shift 2 ;;
    --rc)    RC_FILE="${2:?--rc needs a value}"; shift 2 ;;
    --force) FORCE=1; shift ;;
    --yes|-y) ASSUME_YES=1; shift ;;
    -*)      die "unknown flag: $1" ;;
    *)       ARG="$1"; shift ;;
  esac
done
[ -n "$RC_FILE" ] || RC_FILE="$(default_rc)"

# The gateway base URL must not carry a /v1 suffix; Claude Code appends the path itself.
case "$GATEWAY_URL" in
  */v1|*/v1/) die "ANTHROPIC_BASE_URL must not include a /v1 suffix. Use ${GATEWAY_URL%/v1*}" ;;
esac
GATEWAY_URL="${GATEWAY_URL%/}"

# ---------------------------------------------------------------- step 1: gateway preflight

preflight() {
  bold "Step 1 — proving the gateway is up at $GATEWAY_URL"
  local body
  body=$(curl -s -m 20 -X POST "$GATEWAY_URL/v1/messages" \
    -H "Content-Type: application/json" \
    -H "x-api-key: $GATEWAY_KEY" \
    -H "anthropic-version: 2023-06-01" \
    -d "{\"model\":\"$DEFAULT_MODEL\",\"max_tokens\":50,\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly: OMNIROUTE_OK\"}]}" 2>&1)
  local rc=$?

  if [ $rc -ne 0 ]; then
    red "  could not reach $GATEWAY_URL (curl exit $rc)."
    echo "  Start it with:  omniroute        # keep it running in its own terminal"
    return 1
  fi

  if printf '%s' "$body" | grep -q OMNIROUTE_OK; then
    grn "  gateway answered in Anthropic Messages format. OK."
    return 0
  fi

  # A model/provider error still proves the gateway is listening and speaking its own
  # error dialect — that is a routing success with a bad default probe model.
  if printf '%s' "$body" | grep -qiE 'provider|ambiguous|model'; then
    ylw "  gateway is up, but rejected the probe model '$DEFAULT_MODEL':"
    printf '    %s\n' "$(printf '%s' "$body" | head -c 400)"
    ylw "  That error came FROM OmniRoute, so routing works. Pick a model it does serve."
    return 0
  fi

  red "  unexpected response from $GATEWAY_URL:"
  printf '    %s\n' "$(printf '%s' "$body" | head -c 400)"
  return 1
}

# ---------------------------------------------------------------- model listing

list_models() {
  curl -s -m 20 "$GATEWAY_URL/v1/models" \
    | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin)
except Exception:
    sys.exit(3)
for m in d.get("data",[]):
    print(m.get("id",""))' 2>/dev/null
}

cmd_models() {
  local out; out="$(list_models)"
  [ -n "$out" ] || die "could not list models from $GATEWAY_URL/v1/models — is OmniRoute running?"
  if [ -n "$ARG" ]; then printf '%s\n' "$out" | grep -i -- "$ARG" || echo "(no id matching '$ARG')"
  else printf '%s\n' "$out"; fi
}

# A bare provider name is not a model id and fails with
# "Unable to determine provider for model '<name>'". Catch the common ones early.
reject_bare_provider() {
  local m="$1"
  case "$m" in
    openrouter|kimi|groq|anthropic|openai|gh|aug|together|fireworks|deepseek|mistral|ollama)
      red "'$m' is a provider, not a model id — it will fail with:"
      echo "    Unable to determine provider for model '$m'"
      echo
      echo "  Model ids that provider exposes in your install:"
      list_models | grep -i "^$m/" | sed 's/^/    /' | head -40
      echo
      echo "  Re-run with one of those ids, or an auto/* combo such as auto/best-coding."
      exit 1 ;;
  esac
}

validate_model() {
  local m="$1"
  reject_bare_provider "$m"
  local all; all="$(list_models)"
  if [ -z "$all" ]; then
    ylw "  could not read /v1/models; skipping id validation."
    return 0
  fi
  if printf '%s\n' "$all" | grep -qx -- "$m"; then
    grn "  '$m' exists in this install."
    return 0
  fi
  # Custom dashboard combos resolve on their own and need not appear in /v1/models.
  case "$m" in
    auto/*|*/*)
      red "  '$m' is not listed by /v1/models in this install."
      echo "  Close matches:"; printf '%s\n' "$all" | grep -i -- "${m##*/}" | sed 's/^/    /' | head -10
      [ "$FORCE" = "1" ] || { echo; echo "  Re-run with --force only if you are sure."; exit 1; }
      ylw "  --force given; writing it anyway." ;;
    *)
      ylw "  '$m' is not in /v1/models. Bare names are treated as dashboard combos,"
      ylw "  which resolve on their own and are often not listed — continuing."
      ylw "  If it is not a combo you created, this will fail at request time." ;;
  esac
}

# ---------------------------------------------------------------- step 3: settings.json conflicts

check_settings() {
  bold "Step 3 — checking settings.json for an env block that overrides the shell"
  local found=0 f
  for f in "$HOME/.claude/settings.json" "$HOME/.claude/settings.local.json" \
           "./.claude/settings.json" "./.claude/settings.local.json"; do
    [ -f "$f" ] || continue
    local report
    report=$(python3 - "$f" <<'PY' 2>/dev/null
import json,sys
keys=["ANTHROPIC_MODEL","ANTHROPIC_DEFAULT_OPUS_MODEL","ANTHROPIC_DEFAULT_SONNET_MODEL",
      "ANTHROPIC_DEFAULT_HAIKU_MODEL","ANTHROPIC_SMALL_FAST_MODEL"]
try:
    d=json.load(open(sys.argv[1]))
except Exception as e:
    print("UNPARSEABLE %s"%e); sys.exit(0)
env=d.get("env") or {}
for k in keys:
    if k in env: print("ENV %s=%s"%(k,env[k]))
if "ANTHROPIC_BASE_URL" in env: print("BASEURL %s"%env["ANTHROPIC_BASE_URL"])
if "ANTHROPIC_API_KEY" in env: print("APIKEY")
if "model" in d: print("MODEL %s"%d["model"])
PY
)
    [ -n "$report" ] || continue
    echo "  in $f:"
    while IFS= read -r line; do
      case "$line" in
        ENV\ *)     red   "    ${line#ENV } — overrides your shell; remove it or set a valid OmniRoute id"; found=1 ;;
        MODEL\ *)   red   "    top-level \"model\": ${line#MODEL } — resolves via ANTHROPIC_DEFAULT_*; remove it"; found=1 ;;
        BASEURL\ *) ylw   "    env.ANTHROPIC_BASE_URL=${line#BASEURL } — only honored if nothing else set it" ;;
        APIKEY)     ylw   "    env.ANTHROPIC_API_KEY present — never honored as a credential" ;;
        UNPARSEABLE*) red "    not valid JSON: ${line#UNPARSEABLE }"; found=1 ;;
      esac
    done <<< "$report"
  done

  if [ "$found" = "1" ]; then
    echo
    ylw "  Precedence, highest wins:  --model flag  >  settings.json env  >  shell environment"
    ylw "  Fix those by hand before trusting the shell block. Not edited automatically —"
    ylw "  settings.json is yours and may hold unrelated configuration."
    return 1
  fi
  grn "  no conflicting model pins found."
  return 0
}

# ---------------------------------------------------------------- step 2: write the rc block

write_block() {
  local model="$1"
  bold "Step 2 — writing the env block to $RC_FILE"
  [ -f "$RC_FILE" ] || { touch "$RC_FILE" || die "cannot create $RC_FILE"; }

  if grep -qF "$BEGIN_MARK" "$RC_FILE" 2>/dev/null; then
    local backup="$RC_FILE.omniroute.bak.$(date +%Y%m%d%H%M%S)"
    cp "$RC_FILE" "$backup" || die "cannot back up $RC_FILE"
    echo "  existing block found; replacing it (backup: $backup)"
    python3 - "$RC_FILE" "$BEGIN_MARK" "$END_MARK" <<'PY' || die "failed to strip old block"
import sys
path,b,e=sys.argv[1],sys.argv[2],sys.argv[3]
out,skip=[],False
for ln in open(path):
    if ln.strip()==b: skip=True; continue
    if ln.strip()==e: skip=False; continue
    if not skip: out.append(ln)
open(path,"w").writelines(out)
PY
  fi

  {
    printf '\n%s\n' "$BEGIN_MARK"
    printf 'export ANTHROPIC_BASE_URL=%s\n' "$GATEWAY_URL"
    printf 'export ANTHROPIC_API_KEY=%s\n'  "$GATEWAY_KEY"
    printf 'export ANTHROPIC_MODEL=%s\n'    "$model"
    printf 'export CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1\n'
    printf 'export CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1\n'
    printf '%s\n' "$END_MARK"
  } >> "$RC_FILE" || die "cannot write $RC_FILE"

  grn "  block written."
  echo "  Run:  source $RC_FILE     # or open a new terminal"
}

# ---------------------------------------------------------------- step 4: verify

cmd_verify() {
  local model="${ARG:-${ANTHROPIC_MODEL:-$DEFAULT_MODEL}}"
  bold "Step 4 — verifying the request actually reaches the gateway"
  command -v claude >/dev/null 2>&1 || { ylw "  claude CLI not on PATH; skipping."; return 0; }

  local out
  out=$(claude -p "Reply with exactly: OMNIROUTE_OK" --model "$model" --max-turns 1 2>&1)

  if printf '%s' "$out" | grep -q OMNIROUTE_OK; then
    grn "  working — Claude Code is routing through OmniRoute."; return 0
  fi
  if printf '%s' "$out" | grep -qiE 'provider|ambiguous'; then
    ylw "  routing works (this error came from OmniRoute), but the model id is wrong:"
    printf '    %s\n' "$(printf '%s' "$out" | head -c 400)"
    echo "  Fix ANTHROPIC_MODEL, and re-check settings.json (step 3)."; return 1
  fi
  if printf '%s' "$out" | grep -qi 'invalid api key'; then
    red "  still hitting Anthropic directly — the env block did not apply."
    echo "  Did you 'source $RC_FILE' or open a new terminal?"
    echo "  A settings.json env block may also be overriding it (step 3)."; return 1
  fi
  ylw "  unrecognized result:"; printf '    %s\n' "$(printf '%s' "$out" | head -c 400)"; return 1
}

# ---------------------------------------------------------------- revert

cmd_revert() {
  bold "Reverting to stock Claude"
  if [ -f "$RC_FILE" ] && grep -qF "$BEGIN_MARK" "$RC_FILE"; then
    local backup="$RC_FILE.omniroute.bak.$(date +%Y%m%d%H%M%S)"
    cp "$RC_FILE" "$backup"
    python3 - "$RC_FILE" "$BEGIN_MARK" "$END_MARK" <<'PY'
import sys
path,b,e=sys.argv[1],sys.argv[2],sys.argv[3]
out,skip=[],False
for ln in open(path):
    if ln.strip()==b: skip=True; continue
    if ln.strip()==e: skip=False; continue
    if not skip: out.append(ln)
open(path,"w").writelines(out)
PY
    grn "  removed the block from $RC_FILE (backup: $backup)"
  else
    echo "  no OmniRoute block in $RC_FILE"
  fi

  # Clean up GUI-level variables a previous desktop-app guide may have set. These never
  # worked for the desktop app, but they do leak into other GUI-launched tools.
  if [ "$(uname -s)" = "Darwin" ]; then
    for v in ANTHROPIC_BASE_URL ANTHROPIC_API_KEY ANTHROPIC_MODEL \
             CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY \
             CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT; do
      launchctl unsetenv "$v" 2>/dev/null
    done
    launchctl remove com.omniroute.env 2>/dev/null
    rm -f "$HOME/Library/LaunchAgents/com.omniroute.env.plist"
    grn "  cleared launchctl variables and removed any com.omniroute.env Launch Agent"
  fi
  echo "  Open a new terminal for this to take effect."
}

# ---------------------------------------------------------------- setup

cmd_setup() {
  local model="${ARG:-$DEFAULT_MODEL}"
  [ -n "$ARG" ] || ylw "No model given; defaulting to $DEFAULT_MODEL."

  preflight || die "gateway is not usable — fix OmniRoute before changing any config."
  echo
  bold "Validating '$model'"
  validate_model "$model"
  echo
  check_settings; local settings_rc=$?
  echo

  if [ "$ASSUME_YES" != "1" ]; then
    printf 'Write ANTHROPIC_MODEL=%s to %s? [y/N] ' "$model" "$RC_FILE"
    read -r reply </dev/tty || reply=""
    case "$reply" in y|Y|yes|YES) ;; *) echo "aborted."; exit 1 ;; esac
  fi
  write_block "$model"
  echo
  if [ "$settings_rc" != "0" ]; then
    ylw "Resolve the settings.json conflicts above, then run:"
  else
    echo "Now run, in a NEW terminal:"
  fi
  echo "  source $RC_FILE && $0 verify $model"
}

case "$CMD" in
  check)  preflight; pf=$?; echo; check_settings; cs=$?; [ $pf -eq 0 ] && [ $cs -eq 0 ] ;;
  models) cmd_models ;;
  setup)  cmd_setup ;;
  verify) cmd_verify ;;
  revert) cmd_revert ;;
  ""|-h|--help|help)
    sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//' ;;
  *) die "unknown command '$CMD' — try: check | models | setup <model> | verify | revert" ;;
esac
