r"""CAPTCHA solver for Gujarat's land portals, backed by the local `claude` CLI.

Two portals, two captcha shapes, one solver:

    NUMERIC_6  AnyRoR — 6 numeric digits          (the default; unchanged)
    ALNUM_5    Garvi  — 5 alphanumeric characters

`CaptchaSolver()` with no arguments is still exactly the AnyRoR solver: same
prompt wording, same flags, same errors. Pass `shape=ALNUM_5` for Garvi, whose
answer contains letters — which is why extraction is per-shape rather than the
old `re.sub(r"\D", "", raw)` for everyone (see `_extract_alnum`).

Garvi's captcha is CASE SENSITIVE. Nothing in this module may upper- or
lower-case a reading, and the prompt must ask for the case as shown: the model
folds case if you let it, and by the time the reply reaches `_extract_alnum`
the true reading is already gone.

AnyRoR's captcha is 6 numeric digits that vary in colour, size and vertical
position. This module reads it by shelling out to the `claude` CLI in print
mode (`claude -p`), which uses the machine's logged-in Claude Code subscription
— NO API key. That is deliberate: all Gemini/Anthropic API credits are at zero,
so the subscription CLI is the only model access this repo has. The previous
LangChain/`ChatGoogleGenerativeAI` implementation is gone.

Model choice is NOT a preference — it is a measured result. Bake-off over 15
real AnyRoR captchas, first-attempt exact match:

    Sonnet 5, low effort, raw image ............ 12/15  (80.0%)
    Sonnet 5, low effort, PIL-preprocessed ..... 12/15  (80.0%)
    Opus 5,   low effort, raw .................. 14/15  (93.3%)
    Opus 5,   low effort, PIL-preprocessed ..... 14/15  (93.3%)
    Opus 5,   HIGH effort, raw ................. 15/15  (100.0%)  <-- chosen
                                                 (mean 10.1s, max 12s)

Three consequences are baked in on purpose. Please do not "optimise" them away:

1. NO FALLBACK CHAIN, no Sonnet path. A fallback would only mask a model that
   is not good enough. A missed captcha does not cost one cheap retry — it
   burns a whole fresh AnyRoR session, and session/WAF budget is the genuinely
   scarce resource here (see docs/journal.md, the 2026-07-31 and 2026-08-10 IP
   burns). Spend the extra seconds on Opus, not the session.

2. The RAW image is sent. The old PIL preprocessing (resize / contrast x1.5 /
   sharpness x2) was tuned for Gemini and scored IDENTICALLY to raw for both
   Claude models in the bake-off — it is dead weight plus an extra failure mode,
   so it is deleted.

3. ONE attempt, not three. The old `for attempt in range(max_attempts)` loop
   re-read the SAME image at temperature 0, so it faithfully reproduced the
   same wrong answer while burning wall-clock. Genuine retries belong to
   `ANYROR_FETCH_ATTEMPTS` in anyror/http_fetch.py, where a fresh session means
   a genuinely fresh captcha image. `solve()` therefore raises on failure and
   lets that loop decide.

The `runner` argument exists only so tests can inject a fake `subprocess.run`
and never spend a real model call; production leaves it at the default.
"""

import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass

# Defaults are the bake-off winner. Overridable by env for experiments only.
DEFAULT_MODEL = "claude-opus-5"
DEFAULT_EFFORT = "high"
DEFAULT_TIMEOUT = 120  # seconds; observed max was ~12s, so this is pure headroom

DIGITS = "digits"
ALNUM = "alnum"


@dataclass(frozen=True)
class CaptchaShape:
    """What a portal's captcha looks like."""

    length: int
    alphabet: str

    def __post_init__(self):
        if self.length < 1:
            raise ValueError(f"captcha length must be positive, got {self.length}")
        if self.alphabet not in (DIGITS, ALNUM):
            raise ValueError(
                f"unknown alphabet {self.alphabet!r}; expected {DIGITS!r} or {ALNUM!r}")


NUMERIC_6 = CaptchaShape(length=6, alphabet=DIGITS)
ALNUM_5 = CaptchaShape(length=5, alphabet=ALNUM)

# The `runner` default, captured at import so `solve()` can tell "nobody
# injected one" from a real injection — see the late binding there.
_DEFAULT_RUNNER = subprocess.run

# One system prompt serves both shapes, so it must not promise digits (on Garvi
# the answer contains letters) and it must not mention case at all: it is sent
# verbatim on the NUMERIC_6 call too, whose argv bytes are what the 15/15
# bake-off measured. Case is a per-shape concern, so it is stated in
# ALNUM_PROMPT_TEMPLATE and nowhere else. "the characters" is already
# case-neutral — do not "clarify" it here.
SYSTEM_PROMPT = "You are a CAPTCHA reader. Output ONLY the characters, nothing else."

# For NUMERIC_6 this renders the exact prompt the 15/15 bake-off measured.
NUMERIC_PROMPT_TEMPLATE = (
    "Read the image at {path} . It is a {length}-digit numeric CAPTCHA. The digits "
    "vary in colour, size and vertical position. Output exactly the {length} digits, "
    "left to right, no spaces and no other text."
)

# Garvi's captcha mixes letters and digits, and the portal checks it CASE
# SENSITIVELY: k7Qm2 and K7QM2 are different answers. This prompt therefore
# demands the case as shown and must never ask for uppercase.
#
# An earlier version did ask for uppercase, to keep prose replies easy to
# parse (see _extract_alnum). That was the wrong trade: the case-folding
# happens inside the MODEL, before any of our code runs, so a genuine k7Qm2
# came back as K7QM2 and the true reading was gone for good. Extraction can be
# made stricter after the fact; a destroyed reading cannot be recovered.
ALNUM_PROMPT_TEMPLATE = (
    "Read the image at {path} . It is a {length}-character alphanumeric CAPTCHA "
    "(letters and digits). The characters vary in colour, size and vertical "
    "position. Case is significant: reproduce each character exactly as it "
    "appears in the image, preserving upper and lower case, and never convert "
    "between them. Output exactly the {length} characters, left to right, no "
    "spaces and no other text. If you cannot read it, say so plainly and do not "
    "guess. If you add any explanation at all, put the answer in backticks like "
    "`Ab3xY`, so it can be told apart from the words around it."
)

PROMPT_TEMPLATES = {
    DIGITS: NUMERIC_PROMPT_TEMPLATE,
    ALNUM: ALNUM_PROMPT_TEMPLATE,
}


class CaptchaError(RuntimeError):
    """The captcha could not be read. Callers should retry with a FRESH session."""


class CaptchaSolver:
    """Reads a portal captcha via the local `claude` CLI.

    Defaults to AnyRoR's 6 digits (`NUMERIC_6`); pass `shape=ALNUM_5` for
    Garvi's 5 alphanumeric characters.
    """

    def __init__(self, logger=None, shape=NUMERIC_6, runner=subprocess.run):
        """
        Args:
            logger: Logger instance for logging.
            shape: Which captcha this portal shows.
            runner: `subprocess.run`-compatible callable (injected by tests).
        """
        self.logger = logger or logging.getLogger(__name__)
        self.shape = shape
        self.runner = runner
        self.model = os.getenv("CAPTCHA_MODEL", "").strip() or DEFAULT_MODEL
        self.effort = os.getenv("CAPTCHA_EFFORT", "").strip() or DEFAULT_EFFORT
        try:
            self.timeout = int(os.getenv("CAPTCHA_TIMEOUT", "").strip()
                               or DEFAULT_TIMEOUT)
        except ValueError:
            self.logger.warning(
                "CAPTCHA_TIMEOUT is not an integer; using %ss", DEFAULT_TIMEOUT)
            self.timeout = DEFAULT_TIMEOUT

    def _command(self, image_path):
        """Build the `claude -p` argv.

        Two flags here are load-bearing and silently break the call if dropped:

        * `"enabledPlugins":{}` in --settings — without it every headless call
          loads the session's plugins (the superpowers SessionStart hook) and
          HANGS for >300s. The rest of the settings blob (auto-memory, dream,
          prompt suggestions off) keeps the one-shot call free of interactive
          machinery.
        * `--allowedTools Read` — the image is read from DISK, so the CLI needs
          the Read tool. NOTE: the extraction call in
          tsr_generator/extractors/unified_extractor.py *disallows* Read (it
          passes its payload on stdin and must not touch the filesystem). Do not
          copy those flags wholesale in either direction.
        """
        return [
            "claude", "-p",
            "--model", self.model,
            "--strict-mcp-config",  # don't spawn the session's MCP servers
            "--settings",
            ('{"effortLevel":"%s","enabledPlugins":{},"autoMemoryEnabled":false,'
             '"autoDreamEnabled":false,"promptSuggestionEnabled":false}'
             % self.effort),
            "--allowedTools", "Read",
            "--system-prompt", SYSTEM_PROMPT,
            self._prompt(image_path),
        ]

    def _prompt(self, image_path):
        """The user prompt, worded for this solver's shape."""
        return PROMPT_TEMPLATES[self.shape.alphabet].format(
            path=image_path, length=self.shape.length)

    def _extract(self, raw):
        """Pull the reading out of `raw`, or raise. Never guesses."""
        if self.shape.alphabet == DIGITS:
            return self._extract_digits(raw)
        return self._extract_alnum(raw)

    def _extract_digits(self, raw):
        """Digits-only: strip everything else and demand the exact count.

        Safe here precisely because the alphabet has no letters — see
        _extract_alnum for the shape where this would destroy the answer.
        """
        n = self.shape.length
        digits = re.sub(r"\D", "", raw)
        if len(digits) != n:
            raise CaptchaError(
                f"captcha read returned {len(digits)} digits, expected {n}; "
                f"raw output: {raw.strip()[:200]!r}")
        return digits

    def _extract_alnum(self, raw):
        r"""Alphanumeric: parse the reply, never strip it.

        `re.sub(r"\D", "", raw)` would turn K7Q2M into "72", so the digit path
        cannot be reused. Ported from mp_fetch/captcha_reader.py::_extract in
        the sibling agent-mp repo, where it was written after a real `claude -p`
        call answered with a paragraph instead of bare characters:

        * an exact full-match reply is the answer;
        * an answer the model emphasised (**ABC12** or `ABC12`) is the model
          pointing at its own conclusion, and counts when it is unambiguous;
        * otherwise, standalone letter-or-digit runs of the right length, in
          EITHER case.

        Every branch returns the reply VERBATIM. The captcha is case
        sensitive, so `.upper()` here would be the same data loss the prompt
        used to cause — see ALNUM_PROMPT_TEMPLATE.

        The standalone rule used to be uppercase-only, which conveniently
        excluded ordinary English words of the right length ("reads",
        "image", "which"). Now that case carries meaning that filter is no
        longer available: a real lowercase or mixed-case answer sitting in a
        prose reply has to be visible to this rule, or the reader raises "no
        candidate" on an answer it read correctly. The price is that more
        prose replies are AMBIGUOUS.

        Ambiguity raises; it never picks. That is deliberate and must stay.
        A refusal costs one re-read of a fresh image. A wrong answer costs a
        request against the firm's single office exit IP, on AnyRoR a whole
        fresh session, and can put a wrong reading into a search. Do not add
        a tie-breaker that "resolves" ambiguity — preferring the candidate
        containing a digit, or filtering out dictionary words — those trade a
        cheap failure for an expensive one.
        """
        n = self.shape.length
        reply = (raw or "").strip()

        if re.fullmatch(r"[A-Za-z0-9]{%d}" % n, reply):
            return reply

        for pattern in (r"\*\*([A-Za-z0-9]{%d})\*\*" % n,
                        r"`([A-Za-z0-9]{%d})`" % n):
            marked = re.findall(pattern, reply)
            if len(set(marked)) == 1:
                return marked[0]

        raise CaptchaError(
            f"the reply is not a bare {n}-character reading and does not mark "
            f"one in backticks, so there is nothing here that can be trusted "
            f"as the answer: {reply[:200]!r}. Re-read a fresh image."
        )

    def solve(self, image_data):
        """Recognize the CAPTCHA in `image_data`.

        Args:
            image_data: Raw bytes of the captcha image (e.g. the PNG from
                AnyRoR's inline base64 data URI). Sent as-is — no preprocessing.

        Returns:
            The captcha string, `self.shape.length` characters long.

        Raises:
            CaptchaError: CLI missing, timed out, non-zero exit, or a read that
                does not yield exactly one candidate of the right shape. One
                shot only — the caller retries with a fresh session (and
                therefore a fresh captcha).
        """
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(image_data)
            image_path = tmp.name

        try:
            cmd = self._command(image_path)
            self.logger.debug(
                "Solving captcha via claude CLI (model=%s, effort=%s, timeout=%ss)",
                self.model, self.effort, self.timeout)
            runner = self.runner
            if runner is _DEFAULT_RUNNER:
                # Late-bound on purpose: an un-injected runner resolves
                # `subprocess.run` at call time, so patching it on this
                # module (as the pre-existing tests do) still takes effect.
                runner = subprocess.run
            try:
                res = runner(cmd, capture_output=True, text=True,
                             timeout=self.timeout)
            except FileNotFoundError:
                raise CaptchaError(
                    "`claude` CLI not on PATH; the captcha solver needs a local "
                    "Claude Code subscription (there is no API-key fallback)")
            except subprocess.TimeoutExpired:
                raise CaptchaError(
                    f"`claude` CLI timed out after {self.timeout}s solving the captcha")

            if res.returncode != 0:
                raise CaptchaError(
                    f"`claude` CLI failed (rc={res.returncode}): "
                    f"{(res.stderr or '')[:500]}")

            answer = self._extract(res.stdout or "")
            self.logger.debug("Captcha solved: %s", answer)
            return answer
        finally:
            try:
                os.unlink(image_path)
            except OSError:
                pass
