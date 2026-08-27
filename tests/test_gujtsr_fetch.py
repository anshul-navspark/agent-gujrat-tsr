"""Input normalisation for `gujtsr fetch`.

These are the checks that stop us spending AnyRoR sessions on requests that were
never going to match. A failed fetch is not free: it burns a session against a
WAF that blocks by source IP, and there is one shared residential exit.
"""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from gujtsr.fetch import _to_gujarati, fetch_record


class TestNameResolution:
    def test_district_translates(self):
        guj, err = _to_gujarati("Bhavnagar", "district")
        assert err is None
        assert guj == "ભાવનગર"

    def test_taluka_translates_scoped_by_district(self):
        d, _ = _to_gujarati("Bhavnagar", "district")
        guj, err = _to_gujarati("Talaja", "taluka", parent_district=d)
        assert err is None
        assert guj == "તળાજા"

    def test_both_village_spellings_agree_when_scoped(self):
        """Bodki/Bodkee must land on ONE village.

        Unscoped they do not: 'Bodkee' resolves to code 040 and 'Bodki' to 094.
        Fetching 040 would return a real, valid-looking PDF for the wrong land —
        the same silent wrong-record failure we deleted with form_filler.py.
        """
        d, _ = _to_gujarati("Bhavnagar", "district")
        t, _ = _to_gujarati("Talaja", "taluka", parent_district=d)
        a, err_a = _to_gujarati("Bodkee", "village", parent_district=d, parent_taluka=t)
        b, err_b = _to_gujarati("Bodki", "village", parent_district=d, parent_taluka=t)
        assert err_a is None and err_b is None
        assert a == b, f"scoped spellings disagree: {a!r} vs {b!r}"

    def test_unknown_name_returns_actionable_error_not_an_exception(self):
        guj, err = _to_gujarati("Nonsuchville", "taluka")
        assert guj is None
        assert err["success"] is False
        assert "Nonsuchville" in err["error"]
        assert "taluka" in err["error"]


class TestFetchRecordGuards:
    """fetch_record must fail BEFORE touching the network when a name is bad."""

    def test_bad_taluka_never_reaches_anyror(self):
        with patch("anyror.http_fetch.AnyRoRHttpFetcher") as fetcher:
            out = fetch_record("Bhavnagar", "Nonsuchville", "Bodki", "44")
        assert out["success"] is False
        fetcher.assert_not_called()

    def test_names_are_translated_before_the_fetch(self):
        """The regression this file exists for.

        AnyRoR's dropdowns are Gujarati-only, and fetch_record_pdf passes the
        taluka it is given as BOTH the ascii and gujarati spelling. Handing it
        English matched nothing and burned three sessions before failing.
        """
        with patch("anyror.http_fetch.AnyRoRHttpFetcher") as cls:
            cls.return_value.fetch_record_pdf.return_value = {
                "success": True, "output_path": "/tmp/nonexistent.pdf"}
            fetch_record("Bhavnagar", "Talaja", "Bodki", "44", out_dir="/tmp")
        args = cls.return_value.fetch_record_pdf.call_args[0]
        assert args[0] == "ભાવનગર", f"district not translated: {args[0]!r}"
        assert args[1] == "તળાજા", f"taluka not translated: {args[1]!r}"
        assert "બોડકી" in args[2], f"village not translated: {args[2]!r}"
        # survey stays ASCII: _survey_candidate_texts derives the Gujarati-digit
        # and paiki spellings itself, including nested 1300/p1/p2 forms.
        assert args[3] == "44"
