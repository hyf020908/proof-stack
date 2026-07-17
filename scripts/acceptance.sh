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

TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/proofstack-acceptance.XXXXXX")"

safe_remove_temp() {
    python3 - "${TEMP_ROOT}" <<'PY'
from pathlib import Path
import shutil
import sys
import tempfile

target = Path(sys.argv[1]).resolve()
temporary_root = Path(tempfile.gettempdir()).resolve()
if temporary_root not in target.parents or not target.name.startswith("proofstack-acceptance."):
    raise SystemExit(f"Refusing to remove unexpected path: {target}")
shutil.rmtree(target, ignore_errors=True)
PY
}
trap safe_remove_temp EXIT INT TERM

run_step() {
    local label="$1"
    shift
    printf '\n==> %s\n' "${label}"
    "$@"
}

run_step "1/17 Repository configuration" "${PYTHON_BIN}" scripts/verify_repository.py --structure-only
run_step "2/17 Python format" "${PYTHON_BIN}" -m ruff format --check .
run_step "3/17 Python lint" "${PYTHON_BIN}" -m ruff check .
run_step "4/17 Python typecheck" "${PYTHON_BIN}" -m mypy apps packages scripts
run_step "5/17 Python unit tests" "${PYTHON_BIN}" -m pytest tests/unit
run_step "6/17 Python integration and contract tests" "${PYTHON_BIN}" -m pytest tests/integration tests/contract
run_step "7/17 Python security tests" "${PYTHON_BIN}" -m pytest tests/security
run_step "8/17 Frontend format" pnpm format:check
run_step "9/17 Frontend lint" pnpm lint
run_step "10/17 Frontend typecheck" pnpm typecheck
run_step "11/17 Frontend tests" pnpm test
run_step "12/17 Frontend production build" pnpm build
run_step "13/17 CLI smoke" "${PROOFSTACK_BIN}" version
run_step "14/17 Deterministic Demo" "${PROOFSTACK_BIN}" --json demo --output "${TEMP_ROOT}/demo-evidence"
run_step "15/17 Evidence verification" "${PROOFSTACK_BIN}" evidence verify "${TEMP_ROOT}/demo-evidence"
run_step "16/17 Live API smoke" scripts/smoke_test.sh

printf '\n==> 17/17 Final cleanup and repository verification\n'
make clean
make clean-check
python3 scripts/verify_repository.py

echo "ProofStack acceptance passed."
