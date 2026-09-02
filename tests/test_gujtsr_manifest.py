"""What was fetched, from where, and how it may be described.

Gujarat wrote a PDF and checked it was over 1000 bytes. Nothing recorded where
it came from, nothing detected the portal serving the same document twice, and
nothing stopped an error page saved with a .pdf name sitting in a matter folder
looking like a record. MP and Rajasthan both have this; Gujarat did not.
"""
import json

import pytest

from gujtsr.manifest import (
    LANE_PROVENANCE,
    DuplicateDocument,
    Manifest,
    NotAPdf,
    UnknownLane,
)

PDF = b"%PDF-1.4\nbody\n"


def a_manifest(tmp_path):
    return Manifest(tmp_path / "manifest.json", survey="44",
                    village={"district": "Bhavnagar", "taluka": "Talaja", "village": "Bodki"})


def a_pdf(tmp_path, name="rec.pdf", body=PDF):
    p = tmp_path / name
    p.write_bytes(body)
    return p


def test_a_fetched_record_is_checksummed(tmp_path):
    m = a_manifest(tmp_path)
    entry = m.record("7/12", a_pdf(tmp_path), portal="anyror", lane="anyror_record")
    assert len(entry["sha256"]) == 64
    assert entry["pdf_header_ok"] is True
    assert entry["fetched_at"]


def test_nothing_from_these_portals_is_certified(tmp_path):
    """AnyRoR's record is an uncertified online copy and Garvi returns unsealed
    index data, not an Encumbrance Certificate. Neither is annexable as a
    certified document, and the manifest must not imply otherwise."""
    assert all(not v["certified"] for v in LANE_PROVENANCE.values())


def test_a_caller_cannot_assert_its_own_provenance(tmp_path):
    m = a_manifest(tmp_path)
    entry = m.record("7/12", a_pdf(tmp_path), portal="anyror",
                     lane="anyror_record", certified=True, provenance="Certified")
    assert entry["certified"] is False
    assert entry["provenance"] == LANE_PROVENANCE["anyror_record"]["provenance"]


def test_an_unknown_lane_is_refused(tmp_path):
    m = a_manifest(tmp_path)
    with pytest.raises(UnknownLane) as raised:
        m.record("7/12", a_pdf(tmp_path), portal="anyror", lane="invented")
    assert "anyror_record" in str(raised.value)


def test_an_error_page_saved_as_pdf_is_refused(tmp_path):
    m = a_manifest(tmp_path)
    bad = tmp_path / "blocked.pdf"
    bad.write_bytes(b"<html>Web Page Blocked</html>")
    with pytest.raises(NotAPdf):
        m.record("7/12", bad, portal="anyror", lane="anyror_record")


def test_the_same_bytes_under_two_kinds_is_the_portal_repeating_itself(tmp_path):
    """AnyRoR after a failed postback serves the previous survey's record with a
    fresh header. Byte-identical documents under different kinds is the only
    signal that happened."""
    m = a_manifest(tmp_path)
    m.record("7/12", a_pdf(tmp_path, "a.pdf"), portal="anyror", lane="anyror_record")
    with pytest.raises(DuplicateDocument):
        m.record("8-A", a_pdf(tmp_path, "b.pdf"), portal="anyror", lane="anyror_record")


def test_a_refusal_is_recorded_with_its_stage(tmp_path):
    """Garvi stops at the OTP by design. That is not a failure to hide: it is
    what the requisition list is built from."""
    m = a_manifest(tmp_path)
    entry = m.record_absent("encumbrance", query={"survey": "44"},
                            blocked_on="otp", reason="Garvi needs a handset")
    assert entry["blocked_on"] == "otp"
    assert m.save().exists()


def test_saving_round_trips(tmp_path):
    m = a_manifest(tmp_path)
    m.record("7/12", a_pdf(tmp_path), portal="anyror", lane="anyror_record")
    data = json.loads(m.save().read_text())
    assert data["survey"] == "44"
    assert data["village"]["village"] == "Bodki"
    assert len(data["fetched"]) == 1


# --------------------------------------------------------------------------
# the fetch path reports WHY it stopped
# --------------------------------------------------------------------------


def test_a_waf_block_is_distinguishable_from_an_ordinary_failure():
    """The caller's correct response differs: a block means stop fetching
    entirely, an ordinary failure means this survey did not work."""
    from anyror.http_fetch import AnyRoRHttpFetcher, WAFBlocked

    fetcher = AnyRoRHttpFetcher.__new__(AnyRoRHttpFetcher)
    import logging
    fetcher.log = logging.getLogger("test")

    def boom(*a, **kw):
        raise WAFBlocked("blocked")

    fetcher.fetch_record_html = boom
    result = fetcher.fetch_record_pdf("D", "T", "V", "44", "/tmp/x.pdf")
    assert result["success"] is False
    assert result["blocked_on"] == "waf"


def test_an_ordinary_failure_is_labelled_portal():
    from anyror.http_fetch import AnyRoRHttpFetcher

    fetcher = AnyRoRHttpFetcher.__new__(AnyRoRHttpFetcher)
    import logging
    fetcher.log = logging.getLogger("test")

    def boom(*a, **kw):
        raise ValueError("something else")

    fetcher.fetch_record_html = boom
    assert fetcher.fetch_record_pdf("D", "T", "V", "44",
                                    "/tmp/x.pdf")["blocked_on"] == "portal"
