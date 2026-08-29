"""The `gujtsr garvi` subcommand: drive the search up to the OTP, and stop.

The command exists so a skill can document something real. Until it did, the
Gujarat skill deliberately documented no commands at all — a skill whose command
fails invites the model to improvise against an API it is guessing at, and on
this portal improvising means a wrong-parcel search or a script that reaches
Send-OTP and rings a colleague's handset.

Nothing here touches the network or the `claude` CLI: the session is injected.
"""
import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from gujtsr.__main__ import main

FIXTURE = Path(__file__).parent / "fixtures" / "garvi" / "frmPropertySearch_New.html"


class FakeSession:
    """Stands in for GarviSession. Records what the CLI asked it to do."""

    def __init__(self, *, prepared=None, raises=None):
        self.calls = []
        self._prepared = prepared or {
            "success": False, "prepared": True, "sent": False,
            "blocked_on": "otp", "error": "stopped at the OTP",
            "warning": "renumbering warning",
            "fields": {"ctl00$MainContent$CaptchaControl1": "K7QM2"},
            "captcha_url": "https://garvi.gujarat.gov.in/CaptchaImage.aspx?guid=x",
        }
        self._raises = raises

    def prepare_search(self, **kw):
        self.calls.append(kw)
        if self._raises:
            raise self._raises
        return self._prepared


def _run(argv, session):
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(argv, session_factory=lambda: session)
    return code, out.getvalue()


ARGV = ["garvi", "--district", "12", "--office", "1", "--village", "7",
        "--property-type", "1", "--search-type", "3", "--number", "44"]


def test_it_emits_json_and_returns_nonzero_because_no_search_ran():
    """blocked_on=otp is not success: nothing was searched. The exit code has to
    say so, or a caller's `&&` chain treats a stop as a result."""
    session = FakeSession()
    code, out = _run(ARGV, session)
    payload = json.loads(out)
    assert code == 1
    assert payload["blocked_on"] == "otp"
    assert payload["prepared"] is True
    assert payload["sent"] is False


def test_it_passes_every_selection_through_unchanged():
    session = FakeSession()
    _run(ARGV, session)
    assert session.calls[0]["district"] == "12"
    assert session.calls[0]["office"] == "1"
    assert session.calls[0]["village"] == "7"
    assert session.calls[0]["search_number"] == "44"


def test_it_does_not_pass_a_captcha_so_the_model_reads_it():
    """The user's instruction: solve the captcha with Opus, never ask a human.
    Passing captcha_text=None is what routes it to the model."""
    session = FakeSession()
    _run(ARGV, session)
    assert session.calls[0].get("captcha_text") is None


def test_the_renumbering_warning_reaches_stdout():
    """The trap that makes an empty result look like a clean one."""
    session = FakeSession()
    _, out = _run(ARGV, session)
    assert json.loads(out)["warning"] == "renumbering warning"


def test_it_never_offers_a_flag_that_would_send_an_otp():
    """There must be no way to reach Send-OTP from the command line."""
    session = FakeSession()
    with pytest.raises(SystemExit):
        _run(ARGV + ["--send-otp"], session)
    assert "--otp" not in _help_text()
    assert "handset" not in _help_text().lower()


def _help_text() -> str:
    out = io.StringIO()
    with redirect_stdout(out):
        with pytest.raises(SystemExit):
            main(["garvi", "--help"])
    return out.getvalue()


def test_a_portal_block_is_reported_not_raised():
    from gujtsr.garvi import GarviBlocked
    session = FakeSession(raises=GarviBlocked("blocked from this IP"))
    code, out = _run(ARGV, session)
    payload = json.loads(out)
    assert code == 1
    assert payload["success"] is False
    assert "blocked" in payload["error"].lower()
    assert "Traceback" not in out


def test_a_captcha_failure_is_reported_not_raised():
    from anyror.captcha_solver import CaptchaError
    session = FakeSession(raises=CaptchaError("ambiguous reply"))
    code, out = _run(ARGV, session)
    payload = json.loads(out)
    assert code == 1
    assert "captcha" in payload["error"].lower()
    assert "Traceback" not in out
