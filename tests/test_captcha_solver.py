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
    ALNUM_5,
    DEFAULT_EFFORT,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    NUMERIC_6,
    CaptchaError,
    CaptchaShape,
    CaptchaSolver,
)

IMAGE = b"\x89PNG\r\n\x1a\n-fake-captcha-bytes"

# Captured before any patching: once the autouse guard below is armed,
# `subprocess.run` no longer refers to the real function.
REAL_SUBPROCESS_RUN = subprocess.run


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


@pytest.fixture(autouse=True)
def never_shell_out(monkeypatch):
    """No test in this file may spawn the real `claude` CLI.

    The runner is injectable precisely so tests stay free and offline. Without
    this guard a test that forgets `runner=` does not fail — it silently spawns
    a real `claude -p`, blocks for the full 120s timeout, spends a real model
    call, and then asserts against whatever that call happened to print. This
    turns that mistake into an instant, loud failure instead.

    Tests that want a canned result either inject `runner=FakeRun(...)` or
    re-patch this same attribute; both take precedence over the guard.
    """
    def forbidden(*args, **kwargs):
        raise AssertionError(
            "a test tried to shell out to the real claude CLI; pass "
            "runner=FakeRun(...) or patch anyror.captcha_solver.subprocess.run")

    monkeypatch.setattr("anyror.captcha_solver.subprocess.run", forbidden)


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


# =====================================================================
# Shapes: the same solver has to read Garvi's 5-character alphanumeric
# captcha as well as AnyRoR's 6 digits. Everything below injects a
# `runner`, so no test here can shell out to the real CLI.
# =====================================================================

ALNUM_ANSWER = "K7Q2M"  # letters AND digits: digit-stripping would mangle it


def _solver(shape, runner):
    return CaptchaSolver(logger=logging.getLogger("test.captcha"),
                         shape=shape, runner=runner)


class TestShapes:
    def test_shape_constants(self):
        assert (NUMERIC_6.length, NUMERIC_6.alphabet) == (6, "digits")
        assert (ALNUM_5.length, ALNUM_5.alphabet) == (5, "alnum")

    def test_default_shape_is_numeric_6(self, solver):
        """`CaptchaSolver()` is still the AnyRoR solver, unchanged."""
        assert solver.shape == NUMERIC_6

    def test_default_shape_still_rejects_a_five_digit_read(self, monkeypatch):
        """A 5-character read is right for Garvi and WRONG for AnyRoR; the
        default must keep refusing it rather than padding or guessing."""
        fake = FakeRun(stdout="48392")
        s = CaptchaSolver(logger=logging.getLogger("test.captcha"), runner=fake)
        with pytest.raises(CaptchaError, match="5 digits"):
            s.solve(IMAGE)

    def test_custom_shape_is_accepted(self):
        shape = CaptchaShape(length=4, alphabet="alnum")
        s = _solver(shape, FakeRun(stdout="AB12"))
        assert s.solve(IMAGE) == "AB12"


class TestAlnumExtraction:
    def test_clean_reply(self):
        assert _solver(ALNUM_5, FakeRun(stdout="AB12X")).solve(IMAGE) == "AB12X"

    def test_tolerates_whitespace(self):
        fake = FakeRun(stdout="\n  AB12X \n")
        assert _solver(ALNUM_5, fake).solve(IMAGE) == "AB12X"

    def test_lowercase_exact_reply_is_returned_verbatim(self):
        """An exact full-match reply IS the answer, whitespace aside — and it
        is returned as read, not case-normalised (ported behaviour; the
        uppercase-only rule applies to prose candidates, not to a reply that is
        nothing but the answer). Only the surrounding whitespace is stripped:
        without that strip this reply has no uppercase run to fall back on."""
        fake = FakeRun(stdout="\n ab12x \n")
        assert _solver(ALNUM_5, fake).solve(IMAGE) == "ab12x"

    def test_letters_are_not_stripped_out(self):
        """THE regression this change exists for: the AnyRoR path runs
        `re.sub(r"\\D", "", raw)`, which would turn K7Q2M into 72."""
        # The fixture must be able to fail: digit-stripping visibly changes it.
        assert re.sub(r"\D", "", ALNUM_ANSWER) != ALNUM_ANSWER
        fake = FakeRun(stdout=ALNUM_ANSWER)
        assert _solver(ALNUM_5, fake).solve(IMAGE) == ALNUM_ANSWER

    def test_prose_with_one_candidate_is_read(self):
        reply = ("I read the image carefully. The characters shown are K7Q2M, "
                 "which\nreads left to right. Tell me if you want another look.")
        # The fixture must be able to fail: case-insensitively there are
        # several 5-character runs ("image", "reads", "which", ...), so only
        # the uppercase-or-digit rule makes this unambiguous.
        loose = set(re.findall(r"(?<![A-Za-z0-9])([A-Za-z0-9]{5})(?![A-Za-z0-9])",
                               reply))
        assert len(loose) > 1
        assert _solver(ALNUM_5, FakeRun(stdout=reply)).solve(IMAGE) == ALNUM_ANSWER

    def test_prose_with_two_candidates_raises_instead_of_picking(self):
        """A guess costs a portal request on a shared office exit IP."""
        reply = "It is either K7Q2M or K7Q2N — the third glyph is smudged."
        with pytest.raises(CaptchaError, match="ambiguous"):
            _solver(ALNUM_5, FakeRun(stdout=reply)).solve(IMAGE)

    def test_bold_answer_wins_over_other_uppercase_runs(self):
        reply = ("The image also carries the watermark ABCDE in the corner; "
                 "the captcha itself is **K7Q2M**.")
        # Fixture fights: without the emphasis rule this is 2 candidates.
        assert "ABCDE" in reply
        assert _solver(ALNUM_5, FakeRun(stdout=reply)).solve(IMAGE) == ALNUM_ANSWER

    def test_backticked_answer_wins_over_other_uppercase_runs(self):
        reply = ("The image also carries the watermark ABCDE in the corner; "
                 "the captcha itself is `K7Q2M`.")
        assert "ABCDE" in reply
        assert _solver(ALNUM_5, FakeRun(stdout=reply)).solve(IMAGE) == ALNUM_ANSWER

    def test_two_different_bold_answers_raise(self):
        reply = "Could be **K7Q2M**, could be **K7Q2N**."
        with pytest.raises(CaptchaError, match="ambiguous"):
            _solver(ALNUM_5, FakeRun(stdout=reply)).solve(IMAGE)

    def test_same_candidate_twice_is_not_ambiguous(self):
        """Repetition is the model agreeing with itself, not two readings."""
        reply = "The captcha reads K7Q2M. To be clear: K7Q2M."
        assert reply.count(ALNUM_ANSWER) == 2
        assert _solver(ALNUM_5, FakeRun(stdout=reply)).solve(IMAGE) == ALNUM_ANSWER

    def test_wrong_length_raises(self):
        with pytest.raises(CaptchaError, match="5-character"):
            _solver(ALNUM_5, FakeRun(stdout="K7Q2")).solve(IMAGE)

    def test_empty_output_raises(self):
        with pytest.raises(CaptchaError):
            _solver(ALNUM_5, FakeRun(stdout="")).solve(IMAGE)

    def test_refusal_prose_raises(self):
        fake = FakeRun(stdout="I cannot make out this image, sorry.")
        with pytest.raises(CaptchaError):
            _solver(ALNUM_5, fake).solve(IMAGE)


class TestAlnumFailures:
    def test_non_zero_return_code_raises(self):
        fake = FakeRun(stdout="AB12X", returncode=1, stderr="boom")
        with pytest.raises(CaptchaError, match="rc=1"):
            _solver(ALNUM_5, fake).solve(IMAGE)

    def test_timeout_raises(self):
        fake = FakeRun(exc=subprocess.TimeoutExpired(cmd="claude", timeout=120))
        with pytest.raises(CaptchaError, match="timed out"):
            _solver(ALNUM_5, fake).solve(IMAGE)

    def test_missing_cli_raises(self):
        fake = FakeRun(exc=FileNotFoundError("claude"))
        with pytest.raises(CaptchaError, match="not on PATH"):
            _solver(ALNUM_5, fake).solve(IMAGE)


class TestPromptFollowsShape:
    def test_numeric_prompt(self):
        fake = FakeRun(stdout="483920")
        CaptchaSolver(logger=logging.getLogger("test.captcha"),
                      runner=fake).solve(IMAGE)
        prompt = fake.cmd[-1]
        assert "6-digit" in prompt
        assert "5-character" not in prompt
        assert "alphanumeric" not in prompt

    def test_numeric_prompt_is_byte_identical_to_the_anyror_original(self):
        """`CaptchaSolver()` must send the exact prompt it sent before shapes
        existed — the 15/15 bake-off measured THIS wording."""
        fake = FakeRun(stdout="483920")
        CaptchaSolver(logger=logging.getLogger("test.captcha"),
                      runner=fake).solve(IMAGE)
        path = _image_path_from(fake.cmd)
        assert fake.cmd[-1] == (
            f"Read the image at {path} . It is a 6-digit numeric CAPTCHA. The "
            "digits vary in colour, size and vertical position. Output exactly "
            "the 6 digits, left to right, no spaces and no other text."
        )

    def test_alnum_prompt(self):
        fake = FakeRun(stdout="AB12X")
        _solver(ALNUM_5, fake).solve(IMAGE)
        prompt = fake.cmd[-1]
        assert "5-character" in prompt
        assert "alphanumeric" in prompt.lower()
        assert "uppercase" in prompt.lower()
        assert "6-digit" not in prompt

    def test_system_prompt_is_honest_for_both_shapes(self):
        """One system prompt serves both shapes, so it must not promise
        digits when the answer can contain letters."""
        import anyror.captcha_solver as mod
        assert "digit" not in mod.SYSTEM_PROMPT.lower()


class TestAlnumInvocationGuards:
    """The two load-bearing flags must survive on the Garvi path too."""

    def test_enabled_plugins_is_disabled(self):
        fake = FakeRun(stdout="AB12X")
        _solver(ALNUM_5, fake).solve(IMAGE)
        assert '"enabledPlugins":{}' in fake.cmd[fake.cmd.index("--settings") + 1]

    def test_read_tool_is_allowed(self):
        fake = FakeRun(stdout="AB12X")
        _solver(ALNUM_5, fake).solve(IMAGE)
        cmd = fake.cmd
        assert cmd[cmd.index("--allowedTools") + 1] == "Read"
        assert "--disallowed-tools" not in cmd

    def test_model_is_still_opus_high(self):
        """No Sonnet path, on either shape: Opus/high scored 15/15."""
        fake = FakeRun(stdout="AB12X")
        _solver(ALNUM_5, fake).solve(IMAGE)
        cmd = fake.cmd
        assert cmd[cmd.index("--model") + 1] == DEFAULT_MODEL == "claude-opus-5"
        assert '"effortLevel":"high"' in cmd[cmd.index("--settings") + 1]

    def test_calls_cli_exactly_once(self):
        fake = FakeRun(stdout="not a captcha at all")
        with pytest.raises(CaptchaError):
            _solver(ALNUM_5, fake).solve(IMAGE)
        assert len(fake.calls) == 1

    def test_temp_file_deleted(self):
        fake = FakeRun(stdout="AB12X")
        _solver(ALNUM_5, fake).solve(IMAGE)
        assert not os.path.exists(_image_path_from(fake.cmd))


class TestRunnerInjection:
    def test_init_signature_matches_the_contract(self):
        sig = inspect.signature(CaptchaSolver.__init__)
        assert list(sig.parameters) == ["self", "logger", "shape", "runner"]
        assert sig.parameters["logger"].default is None
        assert sig.parameters["shape"].default is NUMERIC_6
        assert sig.parameters["runner"].default is REAL_SUBPROCESS_RUN

    def test_guard_catches_a_test_that_forgets_to_inject_a_runner(self):
        """Meta-test for the `never_shell_out` fixture. If this stops raising,
        the guard is gone and forgotten-`runner=` tests are silently making
        real 120s `claude -p` calls again."""
        s = CaptchaSolver(logger=logging.getLogger("test.captcha"))
        with pytest.raises(AssertionError, match="real claude CLI"):
            s.solve(IMAGE)

    def test_injected_runner_replaces_subprocess_run(self, monkeypatch):
        def boom(*a, **k):
            raise AssertionError("subprocess.run must not be called when a "
                                 "runner is injected")

        monkeypatch.setattr("anyror.captcha_solver.subprocess.run", boom)
        fake = FakeRun(stdout="483920")
        s = CaptchaSolver(logger=logging.getLogger("test.captcha"), runner=fake)
        assert s.solve(IMAGE) == "483920"
        assert len(fake.calls) == 1

    def test_default_runner_is_still_late_bound_subprocess_run(self, monkeypatch):
        """The pre-existing tests patch `subprocess.run` on the module, so the
        default must be resolved at call time, not frozen at import."""
        fake = _patch(monkeypatch, FakeRun(stdout="483920"))
        CaptchaSolver(logger=logging.getLogger("test.captcha")).solve(IMAGE)
        assert len(fake.calls) == 1

    def test_runner_receives_the_same_kwargs_as_subprocess_run(self):
        fake = FakeRun(stdout="483920")
        CaptchaSolver(logger=logging.getLogger("test.captcha"),
                      runner=fake).solve(IMAGE)
        kwargs = fake.calls[0][1]
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["timeout"] == DEFAULT_TIMEOUT
