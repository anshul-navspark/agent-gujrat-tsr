"""A WAF block must stop the walk, not restart it.

`fetch_record_html` retries the WHOLE walk on failure, which is right for a
rejected captcha and catastrophic for a block: each attempt is seven requests,
so a block that should have cost one walk costs three, from the one office IP
that is already blocked. The documentation has always said "stop, do not
retry"; the code caught its own block exception in the generic retry handler
and did the opposite.
"""
import re
from pathlib import Path

import pytest

from anyror import http_fetch


def test_a_block_has_its_own_exception_type():
    """A bare RuntimeError is indistinguishable from a captcha rejection, which
    is exactly why the retry loop swallowed it."""
    assert issubclass(http_fetch.WAFBlocked, Exception)
    assert not issubclass(http_fetch.WAFBlocked, http_fetch.CaptchaRejected)


def test_the_retry_loop_re_raises_a_block_before_the_catch_all():
    """Order matters: `except WAFBlocked: raise` must come BEFORE the generic
    handler, or the generic one swallows it and the walk restarts."""
    source = Path(http_fetch.__file__).read_text()
    body = source[source.index("def fetch_record_html"):]
    block_at = body.find("except WAFBlocked")
    generic_at = body.find("except Exception")
    assert block_at != -1, "a block is not distinguished from any other failure"
    assert block_at < generic_at, "the catch-all comes first and swallows the block"
    # The block handler's body must re-raise, comments notwithstanding.
    handler_body = body[block_at:generic_at]
    assert re.search(r"^\s*raise\s*$", handler_body, re.M), (
        "a block must be re-raised out of the retry loop, not retried"
    )


def test_every_block_detection_raises_the_block_type():
    """Both places that recognise a WAF page must raise the type the retry loop
    lets through — one of them still raising RuntimeError would be retried."""
    source = Path(http_fetch.__file__).read_text()
    detections = source.count("'Web Page Blocked' in")
    raises = source.count("raise WAFBlocked(")
    assert detections >= 2
    assert raises == detections, (
        f"{detections} block detections but {raises} raise WAFBlocked — one still "
        f"raises something the retry loop will catch"
    )


def test_a_rejected_captcha_is_still_retried():
    """The distinction that matters: a spent captcha SHOULD get a fresh walk."""
    source = Path(http_fetch.__file__).read_text()
    assert "CaptchaRejected" in source
    body = source[source.index("def fetch_record_html"):]
    assert "except WAFBlocked" in body


def test_the_stale_captcha_field_name_is_gone_from_config():
    """CONFIG['CAPTCHA_INPUT_ID'] was 'txt_captcha1'; the real field is
    'txt_captcha_1' with an underscore, and posting the wrong one silently
    yields "Capcha is not matched".

    It was referenced by no code and documented as wrong in two places. A
    documented trap is still a trap -- the next person to "wire up the config"
    reintroduces the bug.
    """
    from anyror import config
    assert "CAPTCHA_INPUT_ID" not in config.CONFIG


def test_the_real_field_name_is_still_the_one_posted():
    source = Path(http_fetch.__file__).read_text()
    assert "txt_captcha_1" in source
    assert "'txt_captcha1'" not in source
