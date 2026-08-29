"""Python 3.11 is this repo's floor, and the skill sandboxes must honour it.

Bare `python3` on a stock macOS is `/usr/bin/python3` == 3.9.6, and a shell
script inherits no interactive shell alias. So `python3 -m venv` inside
`skills/*/scripts/ensure_env.sh` silently built the *lawyer-facing* sandbox on
an interpreter that neither Docker (`FROM python:3.11-slim`) nor CI
(`python-version: "3.11"`) ever sees — a different resolved dependency set, and
a hard block on any 3.10+ syntax. Python 3.9 also reached end of life in
October 2025.

The test that matters most is
`test_the_venv_is_not_created_with_an_unversioned_python`: it reads the shipped
script text and fails if the venv is ever built by an unversioned
`python`/`python3`. The three `test_selection_*` cases below run the script's own
selection block against fake interpreters, because reading text alone cannot tell
`PYTHON_BIN=python3.11` from `PYTHON_BIN=python3`.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import gujtsr

REPO = Path(__file__).resolve().parents[1]

SKILLS = ["gujarat-tsr", "gujarat-land-record", "gujarat-tsr-from-pdf",
          "gujarat-encumbrance"]
ENSURE_ENV_SCRIPTS = [REPO / "skills" / s / "scripts" / "ensure_env.sh" for s in SKILLS]

# Whatever token precedes `-m venv` is the interpreter that builds the sandbox.
VENV_CREATION = re.compile(r"(?P<interpreter>\S+)[ \t]+-m[ \t]+venv\b")

# Names that resolve to "whatever python3 happens to be on PATH" — the bug.
UNVERSIONED = {"python", "python3"}


def _interpreter_name(token: str) -> str:
    """Reduce a shell token to the interpreter name it names.

    `"python3"` -> python3, `/usr/bin/python3` -> python3,
    `$(command -v python3)` -> python3, `"$PYTHON_BIN"` -> $PYTHON_BIN (kept,
    because a variable is exactly what we want to see there).
    """
    token = token.strip("\"'`()[]{}")
    return token.rsplit("/", 1)[-1]


@pytest.fixture(params=ENSURE_ENV_SCRIPTS, ids=SKILLS)
def ensure_env(request):
    script = request.param
    assert script.is_file(), f"missing {script}"
    return script


def test_the_floor_is_3_11():
    assert gujtsr.MIN_PYTHON_VERSION == (3, 11)


def test_the_running_interpreter_meets_the_floor():
    assert sys.version_info[:2] >= gujtsr.MIN_PYTHON_VERSION, (
        f"the test suite itself is on {sys.version.split()[0]}; run it with an "
        "explicit /opt/homebrew/bin/python3.11")


def test_gujtsr_import_guard_names_the_version_and_the_requirement():
    """The guard has to explain itself, not just abort."""
    src = (REPO / "gujtsr" / "__init__.py").read_text(encoding="utf-8")
    assert "RuntimeError" in src, "gujtsr/__init__.py has no version guard"
    for expected in ("3.11", "version_info"):
        assert expected in src, f"the guard never mentions {expected!r}"


@pytest.mark.skipif(
    not Path("/usr/bin/python3").exists(),
    reason="no /usr/bin/python3 to test the guard against")
def test_importing_gujtsr_on_an_old_interpreter_fails_loudly():
    """Prove the guard fires, using the 3.9 interpreter that caused this."""
    probe = subprocess.run(
        ["/usr/bin/python3", "-c",
         "import sys; print('%d.%d.%d' % sys.version_info[:3])"],
        capture_output=True, text=True)
    if probe.returncode != 0:
        pytest.skip("/usr/bin/python3 is not runnable")
    full = probe.stdout.strip()
    major, minor = (int(part) for part in full.split(".")[:2])
    if (major, minor) >= gujtsr.MIN_PYTHON_VERSION:
        pytest.skip(f"/usr/bin/python3 is already {major}.{minor}")

    result = subprocess.run(
        ["/usr/bin/python3", "-c", "import gujtsr"],
        capture_output=True, text=True, cwd=REPO,
        env={"PYTHONPATH": str(REPO), "PATH": "/usr/bin:/bin"})
    assert result.returncode != 0, (
        f"gujtsr imported cleanly on Python {major}.{minor} — the guard is missing")
    assert "RuntimeError" in result.stderr, result.stderr[-1500:]
    # The full micro version, not just "3.9" — that substring is also in the
    # guard's static "3.9 is end-of-life" text, so it would pass vacuously.
    assert full in result.stderr, (
        f"the error never says which interpreter is actually running "
        f"(expected {full!r}):\n{result.stderr[-1500:]}")
    assert "requires Python 3.11" in result.stderr, (
        f"the error never states the requirement in so many words:"
        f"\n{result.stderr[-1500:]}")


def test_the_four_ensure_env_scripts_stay_identical():
    """They are byte-identical today; a fix to one is a fix to all four."""
    texts = {s: s.read_text(encoding="utf-8") for s in ENSURE_ENV_SCRIPTS}
    first = ENSURE_ENV_SCRIPTS[0]
    for script, text in texts.items():
        assert text == texts[first], (
            f"{script.relative_to(REPO)} has drifted from "
            f"{first.relative_to(REPO)} — keep the four sandboxes in lockstep")


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_ensure_env_is_valid_bash(ensure_env):
    result = subprocess.run(["bash", "-n", str(ensure_env)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_ensure_env_rebuilds_a_venv_that_is_below_the_floor(ensure_env):
    """QM sandboxes are durable: a .venv already built on 3.9 must be replaced."""
    text = ensure_env.read_text(encoding="utf-8")
    assert ".venv/bin/python" in text, (
        "ensure_env.sh never inspects the existing .venv interpreter, so a "
        "sandbox that already built a 3.9 venv stays broken forever")
    assert re.search(r"rm\s+-rf\s+.*\.venv", text), (
        "ensure_env.sh never removes a below-floor .venv")


def test_the_venv_is_not_created_with_an_unversioned_python(ensure_env):
    """The bug itself: `python3 -m venv` inherits 3.9.6 from /usr/bin."""
    text = ensure_env.read_text(encoding="utf-8")
    creations = VENV_CREATION.findall(text)
    assert creations, (
        f"{ensure_env.relative_to(REPO)} no longer creates a venv at all — "
        "this test must not pass vacuously")
    offenders = [tok for tok in creations if _interpreter_name(tok) in UNVERSIONED]
    assert not offenders, (
        f"{ensure_env.relative_to(REPO)} builds the sandbox venv with "
        f"{offenders!r}. Bare `python3` is /usr/bin/python3 == 3.9.6 here and a "
        "script inherits no shell alias; Docker and CI are both on 3.11. Select "
        "an explicit interpreter >= 3.11 instead.")


# --- the selection logic itself, run for real ------------------------------
# The text-reading tests above cannot tell `PYTHON_BIN=python3.11` from
# `PYTHON_BIN=python3`. These two run the script's own interpreter-selection
# block against fake interpreters on a controlled PATH.

# Absolute, because these tests hand the script a PATH holding nothing but fakes.
BASH = shutil.which("bash") or "/bin/bash"

FAIL_STUB = 'fail() { echo "SETUP FAILED: $*" >&2; exit 1; }\n'

FAKE_PYTHON = """#!/bin/sh
# $2 is the -c program ensure_env.sh probes with.
case "$2" in
  *sys.exit*) exit {exit_code} ;;
  *print*)    echo "{version}" ;;
esac
"""


def _selection_block(script: Path) -> str:
    """The interpreter-selection block, sliced out of the shipped script."""
    lines = script.read_text(encoding="utf-8").splitlines(keepends=True)
    start = next((i for i, l in enumerate(lines) if l.startswith("MIN_PY=")), None)
    end = next((i for i, l in enumerate(lines) if l.startswith('[ -n "$PYTHON_BIN" ]')), None)
    assert start is not None and end is not None and end > start, (
        f"{script.name} no longer has an interpreter-selection block "
        "(expected a MIN_PY= line and a `[ -n \"$PYTHON_BIN\" ]` guard)")
    return "".join(lines[start:end + 1])


def _fake_bin(tmp_path, interpreters):
    """A PATH directory holding fake pythons: {name: (version, exit_code)}."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    for name, (version, exit_code) in interpreters.items():
        f = bindir / name
        f.write_text(FAKE_PYTHON.format(version=version, exit_code=exit_code))
        f.chmod(0o755)
    return bindir


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_selection_prefers_a_versioned_311_over_an_old_bare_python3(tmp_path):
    bindir = _fake_bin(tmp_path, {
        "python3": ("3.9.6", 1),      # the trap: on PATH, below the floor
        "python3.11": ("3.11.15", 0),
    })
    result = subprocess.run(
        [BASH, "-c", FAIL_STUB + _selection_block(ENSURE_ENV_SCRIPTS[0])
         + '\necho "SELECTED=$PYTHON_BIN"'],
        capture_output=True, text=True, env={"PATH": str(bindir)})
    assert result.returncode == 0, result.stderr
    assert f"SELECTED={bindir}/python3.11" in result.stdout, (
        f"selection did not pick the 3.11 interpreter:\n{result.stdout}\n{result.stderr}")


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_selection_fails_loudly_naming_what_it_found_instead(tmp_path):
    bindir = _fake_bin(tmp_path, {"python3": ("3.9.6", 1)})
    result = subprocess.run(
        [BASH, "-c", FAIL_STUB + _selection_block(ENSURE_ENV_SCRIPTS[0])],
        capture_output=True, text=True, env={"PATH": str(bindir)})
    assert result.returncode != 0, (
        f"a 3.9-only machine was accepted:\n{result.stdout}\n{result.stderr}")
    assert "SETUP FAILED" in result.stderr, result.stderr
    assert "3.9.6" in result.stderr, (
        f"the failure never says what it found instead:\n{result.stderr}")
    assert "3.11" in result.stderr, (
        f"the failure never states the requirement:\n{result.stderr}")


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_selection_prefers_the_pinned_311_over_anything_newer(tmp_path):
    """3.11 wins over 3.14 when both are present.

    Taking the newest available would reintroduce the drift this floor exists to
    remove: a dev machine with 3.14 installed would build a 3.14 venv while
    Docker (python:3.11-slim), CI and the QM sandbox (3.11.2) all run 3.11, and
    nothing would say so. 3.11 is the version every layer agrees on.
    """
    bindir = _fake_bin(tmp_path, {
        "python3": ("3.9.6", 0),
        "python3.11": ("3.11.15", 0),
        "python3.14": ("3.14.1", 0),   # newer, and deliberately not chosen
    })
    result = subprocess.run(
        [BASH, "-c", FAIL_STUB + _selection_block(ENSURE_ENV_SCRIPTS[0])
         + '\necho "SELECTED=$PYTHON_BIN"'],
        capture_output=True, text=True, env={"PATH": str(bindir)})
    assert result.returncode == 0, result.stderr
    assert f"SELECTED={bindir}/python3.11" in result.stdout, (
        f"selection drifted off the pinned version:\n{result.stdout}")


def test_selection_falls_back_to_the_newest_when_311_is_absent(tmp_path):
    """Fallback, not failure: a hard stop would take every skill down the day
    QM's base image moves off Debian 12. Newest-above-the-floor is the right
    fallback; it is only wrong as a *preference*."""
    bindir = _fake_bin(tmp_path, {
        "python3": ("3.11.15", 0),     # adequate ...
        "python3.14": ("3.14.1", 0),   # ... but this one is newer
    })
    result = subprocess.run(
        [BASH, "-c", FAIL_STUB + _selection_block(ENSURE_ENV_SCRIPTS[0])
         + '\necho "SELECTED=$PYTHON_BIN"'],
        capture_output=True, text=True, env={"PATH": str(bindir)})
    assert result.returncode == 0, result.stderr
    assert f"SELECTED={bindir}/python3.14" in result.stdout, (
        f"selection settled for an older-but-adequate interpreter:\n{result.stdout}")
