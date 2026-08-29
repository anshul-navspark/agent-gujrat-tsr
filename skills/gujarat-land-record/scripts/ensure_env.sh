#!/usr/bin/env bash
# Idempotent setup for a QM sandbox. Safe to run before every invocation: it is a
# no-op once the sandbox is warm, and QM sandboxes are durable.
#
# QM materialises ONLY the skill directory, so the engine is not here — we clone it.
set -euo pipefail

REPO_DIR="${GUJTSR_HOME:-$HOME/gujrat_tsr_agent}"
REPO_URL="https://github.com/anshul-navspark/agent-gujrat-tsr.git"

fail() { echo "SETUP FAILED: $*" >&2; exit 1; }

[ -n "${GITHUB_TOKEN:-}" ] || fail "GITHUB_TOKEN is not set. The engine repo is private; ask an admin to add a GitHub read credential to this scope's keychain."

# Choose the interpreter — never inherit it. A script gets no interactive shell
# alias, and an unversioned `python3` is /usr/bin/python3 == 3.9.6 on a stock
# macOS. Docker (`FROM python:3.11-slim`) and CI (`python-version: "3.11"`) are
# both on 3.11, so an older sandbox installs a different resolved dependency set
# and behaves differently — and 3.9 went end-of-life in October 2025. Newest
# first, explicit names before the unversioned fallbacks.
MIN_PY="3.11"

py_meets_floor() { "$1" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 11) else 1)' >/dev/null 2>&1; }
py_version() { "$1" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null || echo "unusable"; }

PYTHON_BIN=""
PY_REJECTED=""
for candidate in python3.16 python3.15 python3.14 python3.13 python3.12 python3.11 python3 python; do
  command -v "$candidate" >/dev/null 2>&1 || continue
  if py_meets_floor "$candidate"; then
    PYTHON_BIN="$(command -v "$candidate")"
    break
  fi
  PY_REJECTED="${PY_REJECTED}${PY_REJECTED:+, }$candidate is $(py_version "$candidate")"
done
[ -n "$PYTHON_BIN" ] || fail "no Python >= $MIN_PY found on PATH (${PY_REJECTED:-nothing named python3.11+, python3 or python is installed}). Python >= $MIN_PY is required: Docker (python:3.11-slim) and CI already build on 3.11, and 3.9 is end-of-life. Install it (\`brew install python@3.11\` / \`apt-get install -y python3.11\`) and re-run."

if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" fetch --quiet origin main && git -C "$REPO_DIR" reset --quiet --hard origin/main
else
  git clone --quiet --depth 50 "https://x-access-token:${GITHUB_TOKEN}@github.com/anshul-navspark/agent-gujrat-tsr.git" "$REPO_DIR" \
    || fail "could not clone $REPO_URL — check the GITHUB_TOKEN has read access"
fi

# .env is deliberately NOT in the repo (it leaked keys until 2026-08-27). Nothing
# in the zero-credit path needs it, but the app expects the file to be absent
# rather than empty, so we do not create one.

# A sandbox is durable, so a .venv already built below the floor would stay broken
# forever. Detect it and rebuild rather than silently reusing it.
if [ -d "$REPO_DIR/.venv" ] && ! py_meets_floor "$REPO_DIR/.venv/bin/python"; then
  echo "REBUILDING $REPO_DIR/.venv: its interpreter is $(py_version "$REPO_DIR/.venv/bin/python"), below the required $MIN_PY."
  rm -rf "$REPO_DIR/.venv"
fi

if [ ! -d "$REPO_DIR/.venv" ]; then
  echo "Creating $REPO_DIR/.venv with $PYTHON_BIN ($(py_version "$PYTHON_BIN"))."
  "$PYTHON_BIN" -m venv "$REPO_DIR/.venv"
fi
"$REPO_DIR/.venv/bin/pip" install --quiet --upgrade pip
# The lean set: 13 packages / ~111 MB, versus ~623 MB for the full
# requirements.txt (streamlit, fastapi, langchain, google-cloud-storage).
# A skill sandbox needs none of that.
"$REPO_DIR/.venv/bin/pip" install --quiet -r "$REPO_DIR/requirements-skill.txt"

command -v pdftotext >/dev/null || echo "WARNING: pdftotext (poppler-utils) not found — PDF text extraction will fall back to PyMuPDF, which is worse on Gujarati." >&2

if ! command -v chromium >/dev/null && ! command -v google-chrome >/dev/null && [ -z "${CHROME_BIN:-}" ]; then
  echo "WARNING: no Chrome binary found. It renders fetched HTML to PDF locally (it never touches AnyRoR). Set CHROME_BIN or install chromium." >&2
fi

[ -n "${ANYROR_PROXY:-}" ] || echo "WARNING: ANYROR_PROXY is not set. AnyRoR blocks datacenter and previously-burned IPs; fetches will almost certainly return the WAF page." >&2

command -v claude >/dev/null || fail "the \`claude\` CLI is not on PATH. It solves the captcha and does extraction using the host's Claude subscription — there is no API-key fallback by design."

echo "READY: $REPO_DIR"
