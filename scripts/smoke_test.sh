#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
    PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
else
    PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

if [[ -x "${ROOT_DIR}/.venv/bin/proofstack" ]]; then
    PROOFSTACK_BIN="${ROOT_DIR}/.venv/bin/proofstack"
else
    PROOFSTACK_BIN="${PROOFSTACK_BIN:-proofstack}"
fi

PORT="${PROOFSTACK_SMOKE_PORT:-8765}"
BASE_URL="http://127.0.0.1:${PORT}/api/v1"
TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/proofstack-smoke.XXXXXX")"
API_LOG="${TEMP_ROOT}/api.log"
SERVER_PID=""

safe_remove_temp() {
    "${PYTHON_BIN}" - "${TEMP_ROOT}" <<'PY'
from pathlib import Path
import shutil
import sys
import tempfile

target = Path(sys.argv[1]).resolve()
temporary_root = Path(tempfile.gettempdir()).resolve()
if temporary_root not in target.parents or not target.name.startswith("proofstack-smoke."):
    raise SystemExit(f"Refusing to remove unexpected path: {target}")
shutil.rmtree(target, ignore_errors=True)
PY
}

on_exit() {
    status=$?
    trap - EXIT INT TERM
    if [[ -n "${SERVER_PID}" ]] && kill -0 "${SERVER_PID}" 2>/dev/null; then
        set +e
        kill "${SERVER_PID}" 2>/dev/null
        wait "${SERVER_PID}" 2>/dev/null
        set -e
    fi
    if [[ ${status} -ne 0 && -f "${API_LOG}" ]]; then
        echo "API log tail:" >&2
        tail -n 80 "${API_LOG}" >&2
    fi
    safe_remove_temp
    exit "${status}"
}
trap on_exit EXIT INT TERM

json_value() {
    local field="$1"
    "${PYTHON_BIN}" -c 'import json, sys; value = json.load(sys.stdin); print(value[sys.argv[1]])' "${field}"
}

api_get() {
    local path="$1"
    shift
    curl --fail --silent --show-error "${BASE_URL}${path}" "$@"
}

api_post() {
    local path="$1"
    shift
    curl --fail --silent --show-error -X POST "${BASE_URL}${path}" "$@"
}

export PROOFSTACK_ENV=test
export PROOFSTACK_DEMO_MODE=true
export PROOFSTACK_DATABASE_URL="sqlite:///${TEMP_ROOT}/smoke.db"
export PROOFSTACK_TASK_BACKEND=inline
export PROOFSTACK_RUNNER=native
export PROOFSTACK_SECRET_KEY
PROOFSTACK_SECRET_KEY="$("${PYTHON_BIN}" -c 'import secrets; print(secrets.token_urlsafe(48))')"
export PROOFSTACK_ARTIFACT_ROOT="${TEMP_ROOT}/artifacts"
export PROOFSTACK_WORKSPACE_ROOT="${TEMP_ROOT}/workspaces"
export PROOFSTACK_ALLOWED_ORIGINS="http://127.0.0.1:${PORT}"

"${PYTHON_BIN}" -m uvicorn proofstack_api.main:app \
    --host 127.0.0.1 \
    --port "${PORT}" \
    --no-access-log >"${API_LOG}" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 80); do
    if api_get "/health" >/dev/null 2>&1; then
        break
    fi
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
        echo "ProofStack API exited before becoming healthy." >&2
        exit 1
    fi
    sleep 0.25
done

api_get "/health" | "${PYTHON_BIN}" -c 'import json, sys; assert json.load(sys.stdin)["status"] == "healthy"'
api_get "/version" | "${PYTHON_BIN}" -c 'import json, sys; assert json.load(sys.stdin)["version"] == "0.1.0"'

TOKEN_RESPONSE="$(api_post "/auth/demo")"
ACCESS_TOKEN="$(printf '%s' "${TOKEN_RESPONSE}" | json_value access_token)"
AUTH_HEADER=(--header "Authorization: Bearer ${ACCESS_TOKEN}")
JSON_HEADER=(--header "Content-Type: application/json")

PROJECT_RESPONSE="$(api_post "/projects" \
    "${AUTH_HEADER[@]}" \
    "${JSON_HEADER[@]}" \
    --data '{"name":"Smoke Project","slug":"smoke-project","description":"Local acceptance smoke","repository_provider":"demo"}')"
PROJECT_ID="$(printf '%s' "${PROJECT_RESPONSE}" | json_value id)"

ANALYSIS_RESPONSE="$(api_post "/projects/${PROJECT_ID}/analyses/demo" \
    "${AUTH_HEADER[@]}" \
    "${JSON_HEADER[@]}" \
    --data '{"validation_commands":[["python","-m","compileall","-q","."]]}')"
ANALYSIS_ID="$(printf '%s' "${ANALYSIS_RESPONSE}" | json_value id)"

ANALYSIS_STATUS="queued"
for _ in $(seq 1 240); do
    ANALYSIS_RESPONSE="$(api_get "/analyses/${ANALYSIS_ID}" "${AUTH_HEADER[@]}")"
    ANALYSIS_STATUS="$(printf '%s' "${ANALYSIS_RESPONSE}" | json_value status)"
    if [[ "${ANALYSIS_STATUS}" == "completed" ]]; then
        break
    fi
    if [[ "${ANALYSIS_STATUS}" == "failed" || "${ANALYSIS_STATUS}" == "cancelled" ]]; then
        echo "Demo analysis ended with status ${ANALYSIS_STATUS}." >&2
        exit 1
    fi
    sleep 0.5
done

if [[ "${ANALYSIS_STATUS}" != "completed" ]]; then
    echo "Demo analysis did not complete before the smoke timeout." >&2
    exit 1
fi

api_get "/analyses/${ANALYSIS_ID}/progress" "${AUTH_HEADER[@]}" \
    | "${PYTHON_BIN}" -c 'import json, sys; value = json.load(sys.stdin); assert value["progress"] == 100'
api_get "/analyses/${ANALYSIS_ID}/findings?page=1&page_size=10" "${AUTH_HEADER[@]}" \
    | "${PYTHON_BIN}" -c 'import json, sys; value = json.load(sys.stdin); assert value["total"] > 0'
curl --fail --silent --show-error \
    "${BASE_URL}/analyses/${ANALYSIS_ID}/evidence/download" \
    "${AUTH_HEADER[@]}" \
    --output "${TEMP_ROOT}/api-evidence.zip"
"${PROOFSTACK_BIN}" --quiet evidence verify "${TEMP_ROOT}/api-evidence.zip"

"${PROOFSTACK_BIN}" --json version \
    | "${PYTHON_BIN}" -c 'import json, sys; assert json.load(sys.stdin)["version"] == "0.1.0"'
"${PROOFSTACK_BIN}" --json demo --output "${TEMP_ROOT}/cli-evidence" \
    | "${PYTHON_BIN}" -c 'import json, sys; value = json.load(sys.stdin); assert value["status"] == "completed"'
"${PROOFSTACK_BIN}" --quiet evidence verify "${TEMP_ROOT}/cli-evidence"

echo "ProofStack smoke test passed."
