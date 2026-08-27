"""Tests for the `claude` CLI captcha solver (anyror/captcha_solver.py).

`subprocess.run` is mocked in every test — nothing here makes a live model call.

Two of these are regression guards rather than behaviour tests, because two
flags silently break the real invocation:

* `"enabledPlugins":{}` — without it each headless `claude -p` call loads the
  session's plugins and hangs for >300s.
* `--allowedTools Read` — the captcha image is read from disk, so the CLI needs
  the Read tool. The extraction call in tsr_generator disallows Read, so it is
  easy to copy the wrong flags across.

There is also a guard that the CLI is invoked exactly ONCE: a retry loop here
would re-read the same image at temperature 0 and reproduce the same wrong
answer, while real retries (fresh session -> fresh captcha) belong to
`ANYROR_FETCH_ATTEMPTS` in anyror/http_fetch.py.
"""

import inspect
import logging
import os
import re
import subprocess

import pytest

from anyror.captcha_solver import (
    DEFAULT_EFFORT,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    CaptchaError,
    CaptchaSolver,
)

IMAGE = b"\x89PNG\r\n\x1a\n-fake-captcha-bytes"


class FakeRun:
    """Records every `subprocess.run` call and returns a canned result."""

    def __init__(self, stdout="", returncode=0, stderr="", exc=None,
                 on_call=None):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr
        self.exc = exc
        self.on_call = on_call
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        if self.on_call:
            self.on_call(cmd)
        if self.exc:
            raise self.exc
        return subprocess.CompletedProcess(
            cmd, self.returncode, stdout=self.stdout, stderr=self.stderr)

    @property
    def cmd(self):
        assert self.calls, "the CLI was never invoked"
        return self.calls[0][0]


@pytest.fixture
def solver(monkeypatch):
    # Keep the env clean so the defaults are what is under test.
    for var in ("CAPTCHA_MODEL", "CAPTCHA_EFFORT", "CAPTCHA_TIMEOUT"):
        monkeypatch.delenv(var, raising=False)
    return CaptchaSolver(logger=logging.getLogger("test.captcha"))


def _patch(monkeypatch, fake):
    monkeypatch.setattr("anyror.captcha_solver.subprocess.run", fake)
    return fake


def _image_path_from(cmd):
    """Pull the temp image path back out of the prompt argument."""
    m = re.search(r"Read the image at (\S+) ", cmd[-1])
    assert m, f"no image path in prompt: {cmd[-1]!r}"
    return m.group(1)


# ------------------------------------------------------------------ happy path
class TestSolve:
    def test_clean_response(self, solver, monkeypatch):
        _patch(monkeypatch, FakeRun(stdout="483920"))
        assert solver.solve(IMAGE) == "483920"

    def test_tolerates_whitespace(self, solver, monkeypatch):
        _patch(monkeypatch, FakeRun(stdout="\n  483920 \n"))
        assert solver.solve(IMAGE) == "483920"

    def test_tolerates_surrounding_prose(self, solver, monkeypatch):
        _patch(monkeypatch, FakeRun(
            stdout="The digits in the CAPTCHA are:\n483920\n"))
        assert solver.solve(IMAGE) == "483920"

    def test_digits_are_joined_across_separators(self, solver, monkeypatch):
        _patch(monkeypatch, FakeRun(stdout="4 8 3 9 2 0"))
        assert solver.solve(IMAGE) == "483920"

    def test_leading_zeros_preserved(self, solver, monkeypatch):
        _patch(monkeypatch, FakeRun(stdout="007123"))
        assert solver.solve(IMAGE) == "007123"


# --------------------------------------------------------------------- failures
class TestFailures:
    def test_five_digits_raises(self, solver, monkeypatch):
        _patch(monkeypatch, FakeRun(stdout="48392"))
        with pytest.raises(CaptchaError, match="5 digits"):
            solver.solve(IMAGE)

    def test_seven_digits_raises(self, solver, monkeypatch):
        # NOT truncated to the first 6: extra digits mean the read is untrusted,
        # and a wrong answer costs a whole fresh AnyRoR session.
        _patch(monkeypatch, FakeRun(stdout="4839201"))
        with pytest.raises(CaptchaError, match="7 digits"):
            solver.solve(IMAGE)

    def test_empty_output_raises(self, solver, monkeypatch):
        _patch(monkeypatch, FakeRun(stdout=""))
        with pytest.raises(CaptchaError, match="0 digits"):
            solver.solve(IMAGE)

    def test_no_digits_in_prose_raises(self, solver, monkeypatch):
        _patch(monkeypatch, FakeRun(stdout="I cannot read this image."))
        with pytest.raises(CaptchaError):
            solver.solve(IMAGE)

    def test_non_zero_return_code_raises(self, solver, monkeypatch):
        _patch(monkeypatch, FakeRun(stdout="483920", returncode=1,
                                    stderr="boom"))
        with pytest.raises(CaptchaError, match="rc=1"):
            solver.solve(IMAGE)

    def test_missing_cli_raises_clear_error(self, solver, monkeypatch):
        _patch(monkeypatch, FakeRun(exc=FileNotFoundError("claude")))
        with pytest.raises(CaptchaError, match="not on PATH"):
            solver.solve(IMAGE)

    def test_timeout_raises(self, solver, monkeypatch):
        _patch(monkeypatch, FakeRun(
            exc=subprocess.TimeoutExpired(cmd="claude", timeout=120)))
        with pytest.raises(CaptchaError, match="timed out"):
            solver.solve(IMAGE)


# --------------------------------------------------------- invocation guards
class TestInvocation:
    def test_enabled_plugins_is_disabled(self, solver, monkeypatch):
        """Without `"enabledPlugins":{}` each headless call hangs >300s."""
        fake = _patch(monkeypatch, FakeRun(stdout="483920"))
        solver.solve(IMAGE)
        settings = fake.cmd[fake.cmd.index("--settings") + 1]
        assert '"enabledPlugins":{}' in settings

    def test_read_tool_is_allowed(self, solver, monkeypatch):
        """The image is read from disk, so Read must be ALLOWED (the
        extraction call in tsr_generator disallows it — different call)."""
        fake = _patch(monkeypatch, FakeRun(stdout="483920"))
        solver.solve(IMAGE)
        cmd = fake.cmd
        assert cmd[cmd.index("--allowedTools") + 1] == "Read"
        assert "--disallowed-tools" not in cmd

    def test_model_and_effort_defaults(self, solver, monkeypatch):
        """Opus 5 at high effort scored 15/15 in the bake-off; Sonnet 12/15."""
        fake = _patch(monkeypatch, FakeRun(stdout="483920"))
        solver.solve(IMAGE)
        cmd = fake.cmd
        assert DEFAULT_MODEL == "claude-opus-5"
        assert DEFAULT_EFFORT == "high"
        assert cmd[cmd.index("--model") + 1] == "claude-opus-5"
        settings = cmd[cmd.index("--settings") + 1]
        assert '"effortLevel":"high"' in settings
        assert fake.calls[0][1]["timeout"] == DEFAULT_TIMEOUT

    def test_env_overrides(self, monkeypatch):
        monkeypatch.setenv("CAPTCHA_MODEL", "claude-sonnet-5")
        monkeypatch.setenv("CAPTCHA_EFFORT", "low")
        monkeypatch.setenv("CAPTCHA_TIMEOUT", "45")
        fake = _patch(monkeypatch, FakeRun(stdout="483920"))
        CaptchaSolver(logger=logging.getLogger("test.captcha")).solve(IMAGE)
        cmd = fake.cmd
        assert cmd[cmd.index("--model") + 1] == "claude-sonnet-5"
        assert '"effortLevel":"low"' in cmd[cmd.index("--settings") + 1]
        assert fake.calls[0][1]["timeout"] == 45

    def test_calls_cli_exactly_once(self, solver, monkeypatch):
        """No retry loop: re-reading the same image at temperature 0 reproduces
        the same wrong answer. Real retries live in ANYROR_FETCH_ATTEMPTS,
        where a fresh session means a genuinely fresh captcha."""
        fake = _patch(monkeypatch, FakeRun(stdout="not a captcha"))
        with pytest.raises(CaptchaError):
            solver.solve(IMAGE)
        assert len(fake.calls) == 1

    def test_solve_takes_only_image_data(self):
        """http_fetch.py calls `self.captcha.solve(cap)` — keep that signature."""
        params = list(inspect.signature(CaptchaSolver.solve).parameters)
        assert params == ["self", "image_data"]

    def test_no_gemini_or_pil_imports(self):
        """Gemini credits are at zero, and the raw image is sent unmodified, so
        the solver must import neither LangChain nor Pillow."""
        import ast
        import anyror.captcha_solver as mod

        tree = ast.parse(open(mod.__file__).read())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not {"PIL", "langchain", "langchain_core",
                    "langchain_google_genai", "pydantic"} & imported
        assert "GEMINI_API_KEY" not in inspect.getsource(mod.CaptchaSolver)


# ------------------------------------------------------------------ temp file
class TestTempFile:
    def test_raw_image_bytes_are_written(self, solver, monkeypatch):
        seen = {}

        def capture(cmd):
            path = _image_path_from(cmd)
            seen["exists"] = os.path.exists(path)
            with open(path, "rb") as fh:
                seen["bytes"] = fh.read()

        fake = _patch(monkeypatch, FakeRun(stdout="483920", on_call=capture))
        solver.solve(IMAGE)
        assert seen["exists"] is True
        # Raw, not PIL-preprocessed: preprocessing scored identically and is gone.
        assert seen["bytes"] == IMAGE
        assert not os.path.exists(_image_path_from(fake.cmd))

    def test_temp_file_deleted_on_success(self, solver, monkeypatch):
        fake = _patch(monkeypatch, FakeRun(stdout="483920"))
        solver.solve(IMAGE)
        assert not os.path.exists(_image_path_from(fake.cmd))

    def test_temp_file_deleted_on_failure(self, solver, monkeypatch):
        fake = _patch(monkeypatch, FakeRun(stdout="nope"))
        with pytest.raises(CaptchaError):
            solver.solve(IMAGE)
        assert not os.path.exists(_image_path_from(fake.cmd))

    def test_temp_file_deleted_when_cli_missing(self, solver, monkeypatch):
        fake = _patch(monkeypatch, FakeRun(exc=FileNotFoundError("claude")))
        with pytest.raises(CaptchaError):
            solver.solve(IMAGE)
        assert not os.path.exists(_image_path_from(fake.cmd))
