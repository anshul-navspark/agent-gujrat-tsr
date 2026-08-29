"""gujtsr — the four capabilities that matter, behind one small surface.

The rest of this repo (FastAPI, Streamlit, the MCP server, the GCS cache) is
optional packaging around these. This package deliberately depends on none of
it, so a QM skill sandbox can run it with requests + python-docx + a Chrome
binary and nothing else.

    fetch   village + survey -> land-record PDF   (AnyRoR, via residential proxy)
    text    PDF -> plain text                     (deterministic, no model)
    render  extraction JSON -> TSR .docx          (deterministic, no model)

Extraction (text -> JSON) is the one step that needs a model. It lives in
`gujtsr.extract`, which can either shell out to `claude -p` or hand the text
back to a calling agent; the drafting rules both paths follow are in
`references/extraction-rules.md` so they cannot drift apart.
"""

import sys

# Python floor. Docker (`FROM python:3.11-slim`) and CI (`python-version: "3.11"`)
# both build on 3.11, so anything older resolves a different dependency set than
# the one that is actually tested — and Python 3.9 reached end of life in October
# 2025. The skill sandboxes used to create their venv with an unversioned
# `python3`, which on macOS is /usr/bin/python3 == 3.9.6, because a shell script
# inherits no interactive shell alias. This guard makes that drift loud.
MIN_PYTHON_VERSION = (3, 11)

if sys.version_info[:2] < MIN_PYTHON_VERSION:
    raise RuntimeError(
        "gujtsr requires Python {}.{} or newer; this interpreter is {} at {}. "
        "Docker (python:3.11-slim) and CI both run 3.11, so an older interpreter "
        "installs a different dependency set and behaves differently, and Python "
        "3.9 is end-of-life (October 2025). Build the venv with an explicit "
        "python3.11 or newer -- see skills/*/scripts/ensure_env.sh -- never an "
        "unversioned `python3`.".format(
            MIN_PYTHON_VERSION[0],
            MIN_PYTHON_VERSION[1],
            ".".join(str(part) for part in sys.version_info[:3]),
            sys.executable,
        )
    )

__all__ = ["fetch", "text", "render"]
