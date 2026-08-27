"""CAPTCHA solver for AnyRoR, backed by the local `claude` CLI.

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
"""

import logging
import os
import re
import subprocess
import tempfile

# Defaults are the bake-off winner. Overridable by env for experiments only.
DEFAULT_MODEL = "claude-opus-5"
DEFAULT_EFFORT = "high"
DEFAULT_TIMEOUT = 120  # seconds; observed max was ~12s, so this is pure headroom

SYSTEM_PROMPT = "You are a CAPTCHA reader. Output ONLY the digits, nothing else."

PROMPT_TEMPLATE = (
    "Read the image at {path} . It is a 6-digit numeric CAPTCHA. The digits "
    "vary in colour, size and vertical position. Output exactly the 6 digits, "
    "left to right, no spaces and no other text."
)


class CaptchaError(RuntimeError):
    """The captcha could not be read. Callers should retry with a FRESH session."""


class CaptchaSolver:
    """Reads a 6-digit AnyRoR captcha via the local `claude` CLI."""

    def __init__(self, logger=None):
        """
        Args:
            logger: Logger instance for logging.
        """
        self.logger = logger or logging.getLogger(__name__)
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
            PROMPT_TEMPLATE.format(path=image_path),
        ]

    def solve(self, image_data):
        """Recognize the CAPTCHA in `image_data`.

        Args:
            image_data: Raw bytes of the captcha image (PNG from AnyRoR's
                inline base64 data URI). Sent as-is — no preprocessing.

        Returns:
            The 6-digit captcha string.

        Raises:
            CaptchaError: CLI missing, timed out, non-zero exit, or output that
                is not exactly 6 digits. One shot only — the caller retries with
                a fresh session (and therefore a fresh captcha).
        """
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(image_data)
            image_path = tmp.name

        try:
            cmd = self._command(image_path)
            self.logger.debug(
                "Solving captcha via claude CLI (model=%s, effort=%s, timeout=%ss)",
                self.model, self.effort, self.timeout)
            try:
                res = subprocess.run(cmd, capture_output=True, text=True,
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

            raw = res.stdout or ""
            digits = re.sub(r"\D", "", raw)
            if len(digits) != 6:
                raise CaptchaError(
                    f"captcha read returned {len(digits)} digits, expected 6; "
                    f"raw output: {raw.strip()[:200]!r}")

            self.logger.debug("Captcha solved: %s", digits)
            return digits
        finally:
            try:
                os.unlink(image_path)
            except OSError:
                pass
