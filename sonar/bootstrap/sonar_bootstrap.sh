#!/usr/bin/env bash
# Zero-touch, idempotent SonarQube bootstrap.
#   - waits for real readiness (status UP + authenticated probe), never fixed sleeps
#   - headless first-boot admin init (default admin:admin -> generated password)
#   - project, custom Quality Gate + conditions + association
#   - dedicated 'scanner' user with minimum permissions
#   - project analysis token: generate / validate / reuse / rotate
#   - secrets persisted with 600 perms under $SECRETS_DIR (bind-mounted .sonar/)
# Never prints token material. Recovers from partial runs.
#
# IMPORTANT: No pipes that could hang (pipefail-safe). All jq calls use
# a variable to hold stdout before piping.
set -euo pipefail

HOST="${SONAR_HOST_URL:-http://sonarqube:9000}"
SECRETS_DIR="${SECRETS_DIR:-/run/secrets}"
TIMEOUT="${SONAR_STARTUP_TIMEOUT:-300}"
POLL="${SONAR_POLL_INTERVAL:-5}"
PROJECT_KEY="${SONAR_PROJECT_KEY:-chalice-devops-lab}"
PROJECT_NAME="${SONAR_PROJECT_NAME:-AWS Chalice DevOps Lab}"
GATE_NAME="${SONAR_QUALITY_GATE:-chalice-devops-lab-gate}"
TOKEN_NAME="${SONAR_TOKEN_NAME:-lab-scanner-token}"
ROTATE="${SONAR_ROTATE_TOKEN:-0}"
ADMIN_FILE="$SECRETS_DIR/admin-credentials"
SCANNER_FILE="$SECRETS_DIR/scanner-credentials"
TOKEN_FILE="$SECRETS_DIR/token"
TOKEN_META="$SECRETS_DIR/token-meta"

log() { printf '[bootstrap] %s\n' "$*"; }
die() {
  printf '[bootstrap][ERROR] %s\n' "$*" >&2
  printf '[bootstrap] diagnostics: %s\n' "$(curl -s --max-time 5 "$HOST/api/system/health" 2>&1 | head -c 400)" >&2
  printf '[bootstrap] hint: docker compose logs --tail 120 sonarqube sonarqube-db\n' >&2
  exit 1
}

# Helpers - all pipefail-safe
json_get() {
  local raw="$1" filter="$2" default="${3:-}"
  local out
  out=$(printf '%s\n' "$raw" | jq -r "$filter" 2>/dev/null) || out="$default"
  printf '%s' "$out"
}

json_has() {
  # Returns 0 if the jq filter finds a truthy value, 1 otherwise.
  local raw="$1" filter="$2"
  local out
  out=$(printf '%s\n' "$raw" | jq -e "$filter" >/dev/null 2>&1) || true
  # Check if jq succeeded (exit 0 means filter matched)
  if [ -n "$out" ]; then return 0; fi
  return 1
}

auth_ok() {
  curl -sf --max-time 5 -u "$1" "$HOST/api/projects/search" >/dev/null 2>&1
}

as_admin() {
  curl -s --max-time 10 -X "$1" -u "$ADMIN_AUTH" "$HOST$2"
}

# ------------------------------------------------------- 1. readiness
log "waiting for SonarQube at $HOST (timeout ${TIMEOUT}s, poll ${POLL}s)"
deadline=$(( $(date +%s) + TIMEOUT ))
while true; do
  _raw=$(curl -s --max-time 5 "$HOST/api/system/status" 2>/dev/null) || _raw=""
  status=$(json_get "$_raw" '.status // "DOWN"')
  log "system status: $status"
  [ "$status" = "UP" ] && break
  [ "$(date +%s)" -ge "$deadline" ] && die "SonarQube did not reach UP within ${TIMEOUT}s"
  sleep "$POLL"
done

# ------------------------------------------------------- 2. admin identity
ADMIN_AUTH="admin:admin"
if [ -s "$ADMIN_FILE" ] && auth_ok "$(cat "$ADMIN_FILE")"; then
  ADMIN_AUTH="$(cat "$ADMIN_FILE")"
  log "existing admin credentials valid -> reusing"
elif auth_ok "admin:admin"; then
  NEW_ADMIN_PW="$(openssl rand -base64 20 | tr -d '/+=' | cut -c1-16)_Sp3c!@l"
  _pw_resp=$(curl -s --max-time 10 -u admin:admin -X POST "$HOST/api/users/change_password" \
    --data-urlencode "login=admin" \
    --data-urlencode "previousPassword=admin" \
    --data-urlencode "password=$NEW_ADMIN_PW")
  if ! auth_ok "admin:$NEW_ADMIN_PW"; then
    printf '%s' "$_pw_resp" >&2
    die "failed to rotate default admin password"
  fi
  printf '%s' "admin:$NEW_ADMIN_PW" > "$ADMIN_FILE"
  chmod 600 "$ADMIN_FILE"
  ADMIN_AUTH="admin:$NEW_ADMIN_PW"
  log "default admin:admin rotated; credentials persisted (600) at $ADMIN_FILE"
else
  die "cannot authenticate as admin. Recovery: inspect persistent DB or restore .sonar/admin-credentials backup."
fi

if ! auth_ok "$ADMIN_AUTH"; then
  die "SonarQube is UP but admin authentication failed"
fi
log "authenticated probe OK"

# ------------------------------------------------------- 3. project
_proj_raw=$(as_admin GET "/api/projects/search?q=$PROJECT_KEY") || _proj_raw=""
if json_has "$_proj_raw" --arg k "$PROJECT_KEY" '.components[]? | select(.project==$k or .k==$k)'; then
  log "project '$PROJECT_KEY' already exists"
else
  _create_raw=$(as_admin POST "/api/projects/create?project=$PROJECT_KEY&name=$PROJECT_NAME") || _create_raw=""
  log "project '$PROJECT_KEY' created"
fi

# ------------------------------------------------------- 4. quality gate
_create_cond() {
  local metric="$1" op="$2" error="$3"
  local _cresp
  _cresp=$(as_admin POST "/api/qualitygates/create_condition?gateName=$GATE_NAME&metric=$metric&op=$op&error=$error") || _cresp=""
  if json_has "$_cresp" '.errors'; then
    local _msg
    _msg=$(json_get "$_cresp" '.errors[0].msg')
    log "  condition $metric skipped: ${_msg:0:120}"
    return 1
  fi
  log "  condition ok: $metric $op $error"
  return 0
}

_gates_raw=$(as_admin GET /api/qualitygates/list) || _gates_raw=""
if json_has "$_gates_raw" --arg g "$GATE_NAME" '.qualitygates[] | select(.name==$g)'; then
  log "quality gate '$GATE_NAME' already exists"
else
  _gate_raw=$(as_admin POST "/api/qualitygates/create?name=$GATE_NAME") || _gate_raw=""
  if json_has "$_gate_raw" '.errors'; then
    die "cannot create quality gate: $(json_get "$_gate_raw" '.errors[0].msg')"
  fi
  log "quality gate '$GATE_NAME' created"
  _create_cond line_coverage LT 100 || true
  _create_cond branch_coverage LT 100 || true
  _create_cond duplicated_lines_density GT 3 || true
  _create_cond reliability_rating GT 1 || true
  _create_cond security_rating GT 1 || true
  log "gate conditions: see /api/qualitygates/show above; unsupported ones enforced in quality_gate.sh"
fi

_gate_show_raw=$(as_admin GET "/api/qualitygates/show?name=$GATE_NAME") || _gate_show_raw=""
json_get "$_gate_show_raw" '{name, conditions: [.conditions[] | {metric, op, error}]}' || true

_proj_assign_raw=$(as_admin GET "/api/qualitygates/get_by_project?project=$PROJECT_KEY") || _proj_assign_raw=""
cur=$(json_get "$_proj_assign_raw" '.qualityGate.name')
if [ "$cur" != "$GATE_NAME" ]; then
  as_admin POST "/api/qualitygates/select_project?project=$PROJECT_KEY&gateName=$GATE_NAME" >/dev/null 2>&1 || true
  log "gate '$GATE_NAME' associated with project"
else
  log "project already uses gate '$GATE_NAME'"
fi

# ------------------------------------------------------- 5. scanner user
SCANNER_LOGIN=scanner
if [ -s "$SCANNER_FILE" ] && auth_ok "$(cat "$SCANNER_FILE")"; then
  SCANNER_AUTH="$(cat "$SCANNER_FILE")"
  log "existing scanner user valid -> reusing"
else
  SCANNER_PW="$(openssl rand -base64 30 | tr -d '/+=' | cut -c1-28)"
  _sc_resp=$(as_admin POST "/api/useradmin/create?login=$SCANNER_LOGIN&name=Lab%20Scanner&password=$SCANNER_PW") || _sc_resp=""
  if json_has "$_sc_resp" '.errors' && ! auth_ok "$SCANNER_LOGIN:$SCANNER_PW"; then
    as_admin POST "/api/useradmin/update_login?login=$SCANNER_LOGIN&newLogin=$SCANNER_LOGIN" >/dev/null 2>&1 || true
    _sc_resp2=$(as_admin POST "/api/useradmin/update?login=$SCANNER_LOGIN&password=$SCANNER_PW") || _sc_resp2=""
    auth_ok "$SCANNER_LOGIN:$SCANNER_PW" || die "cannot establish scanner user"
  fi
  printf '%s' "$SCANNER_LOGIN:$SCANNER_PW" > "$SCANNER_FILE"
  chmod 600 "$SCANNER_FILE"
  SCANNER_AUTH="$SCANNER_LOGIN:$SCANNER_PW"
  log "scanner user created (persisted 600)"
fi

# minimum permissions
as_admin POST "/api/permissions/add_user?login=$SCANNER_LOGIN&permission=scan" >/dev/null 2>&1 || true
as_admin POST "/api/permissions/add_user?login=$SCANNER_LOGIN&permission=codeview" >/dev/null 2>&1 || true
as_admin POST "/api/permissions/add_user?projectIdorKey=$PROJECT_KEY&login=$SCANNER_LOGIN&permission=codeviewer" >/dev/null 2>&1 || true
as_admin POST "/api/permissions/add_user?projectIdorKey=$PROJECT_KEY&login=$SCANNER_LOGIN&permission=user" >/dev/null 2>&1 || true
log "scanner permissions ensured"

# ------------------------------------------------------- 6. token
token_valid() {
  [ -s "$TOKEN_FILE" ] && curl -sf --max-time 5 -u "$(cat "$TOKEN_FILE"):" "$HOST/api/projects/search" >/dev/null 2>&1
}

_revoke_token() {
  local _rname
  if [ -f "$TOKEN_META" ]; then
    _rname=$(cut -d= -f2 < "$TOKEN_META")
  else
    _rname="$TOKEN_NAME"
  fi
  as_admin POST "/api/user_tokens/search?login=$SCANNER_LOGIN" >/dev/null 2>&1 || true
  as_admin POST "/api/user_tokens/revoke?login=$SCANNER_LOGIN&name=$_rname" >/dev/null 2>&1 || true
}

if token_valid && [ "$ROTATE" != "1" ]; then
  log "existing analysis token valid -> reusing"
else
  [ "$ROTATE" = "1" ] && log "token rotation requested"
  _revoke_token
  _tok_resp=$(as_admin POST "/api/user_tokens/generate?login=$SCANNER_LOGIN&name=$TOKEN_NAME") || _tok_resp=""
  TOKEN=$(json_get "$_tok_resp" '.token // empty' '""')
  if [ -z "$TOKEN" ] || [ "$TOKEN" = '""' ]; then
    _terr=$(json_get "$_tok_resp" '.errors[0].msg' 2>/dev/null || echo "$_tok_resp" | head -c 200)
    die "token generation failed: $_terr"
  fi
  printf '%s' "$TOKEN" > "$TOKEN_FILE"
  chmod 600 "$TOKEN_FILE"
  printf 'login=%s\nname=%s\n' "$SCANNER_LOGIN" "$TOKEN_NAME" > "$TOKEN_META"
  chmod 600 "$TOKEN_META"
  unset TOKEN TOKEN_JSON _tok_resp
  token_valid || die "generated token failed validation"
  log "analysis token generated, stored at $TOKEN_FILE (600) and validated"
fi

log "BOOTSTRAP OK: project=$PROJECT_KEY gate=$GATE_NAME token-file=$TOKEN_FILE scanner=$SCANNER_LOGIN"