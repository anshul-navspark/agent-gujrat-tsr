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

if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" fetch --quiet origin main && git -C "$REPO_DIR" reset --quiet --hard origin/main
else
  git clone --quiet --depth 50 "https://x-access-token:${GITHUB_TOKEN}@github.com/anshul-navspark/agent-gujrat-tsr.git" "$REPO_DIR" \
    || fail "could not clone $REPO_URL — check the GITHUB_TOKEN has read access"
fi

# .env is deliberately NOT in the repo (it leaked keys until 2026-08-27). Nothing
# in the zero-credit path needs it, but the app expects the file to be absent
# rather than empty, so we do not create one.

if [ ! -d "$REPO_DIR/.venv" ]; then
  python3 -m venv "$REPO_DIR/.venv"
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
