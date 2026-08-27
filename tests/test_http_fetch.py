"""Tests for the browser-free AnyRoR fetch (anyror/http_fetch.py).

AnyRoR's WAF resets Selenium/Chrome but allows plain HTTP, so http_fetch walks
the ASP.NET form with `requests`. It is now the ONLY fetch path — the Selenium
scraper was removed because driving the portal with a browser is what drew the
WAF Attack ID. These tests cover the pure parsing/matching logic against static
HTML fixtures (no network) and guard the exact captcha field-name bug
(`txt_captcha_1`, with underscore) that silently rejected every submit.
"""

import inspect

from anyror.http_fetch import (
    AnyRoRHttpFetcher,
    _options,
    _match_option,
    _hiddens,
    P,
)

_fetcher = AnyRoRHttpFetcher.__new__(AnyRoRHttpFetcher)  # no __init__ (no Gemini)


# --------------------------------------------------------------- survey match
class TestSurveyCandidates:
    def test_paiki_no_slash(self):
        # AnyRoR renders "24/p1" as "24p૧" (no slash, Gujarati paiki digit)
        assert "24p૧" in _fetcher._survey_candidate_texts("24/p1")
        assert "24p૧" in _fetcher._survey_candidate_texts("24p1")

    def test_paiki_with_slash(self):
        # ...but "48/p4" as "48/p૪" (with slash) — inconsistent in AnyRoR data
        assert "48/p૪" in _fetcher._survey_candidate_texts("48/p4")

    def test_five_as_pa_letter(self):
        # digit 5 is sometimes the letter પ, not ૫
        cands = _fetcher._survey_candidate_texts("16/p5")
        assert "16/pપ" in cands or "16pપ" in cands

    def test_exact_match_not_substring(self):
        # "24p૧" must not match "24p૧/p૧" when we want survey 24 paiki 1
        opts = [("24p૧", "24p૧"), ("24p૧/p૧", "24p૧/p૧")]
        cands = _fetcher._survey_candidate_texts("24/p1")
        hit = next((t for c in cands for v, t in opts if t == c), None)
        assert hit == "24p૧"


# --------------------------------------------------------------- html parsing
DISTRICT_HTML = (
    '<select id="ContentPlaceHolder1_ddlDistrict">'
    '<option value="">Select</option>'
    '<option value="14">ભાવનગર</option>'
    '<option value="01">કચ્છ</option>'
    '</select>'
)


class TestHtmlParsing:
    def test_options(self):
        opts = _options(DISTRICT_HTML, "ddlDistrict")
        assert ("14", "ભાવનગર") in opts

    def test_match_option_gujarati(self):
        opts = _options(DISTRICT_HTML, "ddlDistrict")
        val, text = _match_option(opts, "Bhavnagar", "ભાવનગર")
        assert val == "14"

    def test_hiddens_viewstate(self):
        html = (
            '<input type="hidden" name="__VIEWSTATE" value="ABC123" />'
            '<input type="hidden" name="__EVENTVALIDATION" value="XYZ" />'
        )
        h = _hiddens(html)
        assert h["__VIEWSTATE"] == "ABC123"
        assert h["__EVENTVALIDATION"] == "XYZ"

    def test_captcha_from_data_uri(self):
        import base64
        raw = b"\x89PNG-fake-bytes"
        b64 = base64.b64encode(raw).decode()
        html = (f'<img id="ContentPlaceHolder1_i_captcha_1" '
                f'src="data:image/png;base64,{b64}">')
        assert _fetcher._captcha_from(html) == raw


# --------------------------------------------------------- regression guards
class TestCaptchaFieldRegression:
    def test_posts_to_underscore_field(self):
        """The real captcha field is `txt_captcha_1` (underscore before 1).
        Posting to `txt_captcha1` writes to a non-existent field -> AnyRoR
        rejects every submit as 'Capcha is not matched'."""
        src = inspect.getsource(AnyRoRHttpFetcher.fetch_record_html)
        assert "txt_captcha_1" in src
        assert "'txt_captcha1'" not in src and '"txt_captcha1"' not in src

    def test_record_type_is_integrated_survey(self):
        from anyror.http_fetch import RECORD_TYPE_VALUE
        assert RECORD_TYPE_VALUE == "8"  # Integrated Survey No Details


class TestScraperWiring:
    """AnyRoRScraper.fetch_land_record delegates to http_fetch and nothing else.
    There is no browser fallback: driving AnyRoR with Selenium is what drew the
    WAF Attack ID that burned the source IP (journal 2026-07-31)."""

    def _bare_scraper(self):
        import logging
        from anyror.scraper import AnyRoRScraper
        s = AnyRoRScraper.__new__(AnyRoRScraper)  # skip __init__ (no Gemini key)
        s.logger = logging.getLogger("test")
        s.captcha_solver = None
        s.headless = True
        return s

    def test_http_fetch_success_is_returned(self, monkeypatch, tmp_path):
        class FakeFetcher:
            def __init__(self, logger=None):
                pass
            def fetch_record_pdf(self, d, t, v, survey, out):
                return {"success": True, "output_path": out, "message": "ok"}
        monkeypatch.setattr("anyror.http_fetch.AnyRoRHttpFetcher", FakeFetcher)
        s = self._bare_scraper()
        out = str(tmp_path / "x.pdf")
        res = s.fetch_land_record("ભાવનગર", "તળાજા", "બેલડા", "24/p1", out)
        assert res["success"] is True
        assert res["output_path"] == out

    def test_fails_loudly_when_http_fails(self, monkeypatch, tmp_path):
        """No silent browser retry — the http_fetch error is surfaced as-is."""
        class FailFetcher:
            def __init__(self, logger=None):
                pass
            def fetch_record_pdf(self, *a):
                return {"success": False, "error": "boom"}
        monkeypatch.setattr("anyror.http_fetch.AnyRoRHttpFetcher", FailFetcher)
        s = self._bare_scraper()
        res = s.fetch_land_record("ભાવનગર", "તળાજા", "બેલડા", "24/p1",
                                  str(tmp_path / "x.pdf"))
        assert res["success"] is False
        assert "boom" in res["error"]

    def test_raising_fetcher_returns_error_dict(self, monkeypatch, tmp_path):
        """fetch_land_record never raises; a fetcher blow-up becomes a dict."""
        class BoomFetcher:
            def __init__(self, logger=None):
                raise RuntimeError("kaboom")
        monkeypatch.setattr("anyror.http_fetch.AnyRoRHttpFetcher", BoomFetcher)
        s = self._bare_scraper()
        res = s.fetch_land_record("ભાવનગર", "તળાજા", "બેલડા", "24/p1",
                                  str(tmp_path / "x.pdf"))
        assert res["success"] is False
        assert "kaboom" in res["error"]

    def test_scraper_imports_no_browser_driver(self):
        """Regression guard: the scraper must stay browser-free on AnyRoR.

        Checks imports via the AST rather than raw text, so the module
        docstring may keep explaining why Selenium was removed.
        """
        import ast
        import anyror.scraper as scraper_mod
        tree = ast.parse(inspect.getsource(scraper_mod))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
                imported.update(a.name for a in node.names)
        for banned in ("selenium", "webdriver_manager", "WebDriverManager",
                       "form_filler", "FormFiller"):
            assert not any(banned in name for name in imported), (
                f"{banned} is imported again by anyror/scraper.py")

    def test_selenium_fallback_env_var_is_gone(self):
        """ANYROR_SELENIUM_FALLBACK was retired; nothing may read it."""
        import anyror.scraper as scraper_mod
        assert "ANYROR_SELENIUM_FALLBACK" not in inspect.getsource(scraper_mod)


class TestFetchRecordPdfContract:
    def test_returns_error_dict_on_failure(self, monkeypatch, tmp_path):
        """fetch_record_pdf mirrors AnyRoRScraper.fetch_land_record()'s dict
        contract: {'success': False, 'error': ...} on failure (never raises)."""
        def boom(*a, **k):
            raise RuntimeError("network down")
        monkeypatch.setattr(_fetcher, "fetch_record_html", boom, raising=False)
        res = _fetcher.fetch_record_pdf("ભાવનગર", "તળાજા", "બેલડા", "24/p1",
                                        str(tmp_path / "out.pdf"))
        assert res["success"] is False
        assert "error" in res


# ------------------------------------------------------- nested paiki surveys
class TestNestedPaikiSurveys:
    """Miyani (Porbandar) 1300 is subdivided twice: the live dropdown spells the
    options "1300/p૧/p૧", "1300/p૧/p૨", "1300/p૨" — Latin base, Latin 'p',
    Gujarati paiki digits. The single-level paiki regex never matched these, so
    the fetch failed and (pre-guard) fell through to Selenium (journal 2026-08-21).
    """

    def test_two_level_paiki(self):
        cands = _fetcher._survey_candidate_texts("1300/p1/p1")
        assert "1300/p૧/p૧" in cands

    def test_two_level_paiki_second_part(self):
        assert "1300/p૧/p૨" in _fetcher._survey_candidate_texts("1300/p1/p2")

    def test_two_level_paiki_no_slash_variant(self):
        # the slash before 'p' is inconsistent in AnyRoR's data, so offer both
        assert "1300p૧p૧" in _fetcher._survey_candidate_texts("1300/p1/p1")

    def test_single_level_paiki_still_works(self):
        # regression guard: generalising to N levels must not break one level
        assert "24p૧" in _fetcher._survey_candidate_texts("24/p1")
        assert "48/p૪" in _fetcher._survey_candidate_texts("48/p4")


# ------------------------------------------------------ ascii district lookup
DISTRICT_OPTS = [("", "Select"), ("14", "ભાવનગર"), ("01", "કચ્છ")]


class TestDistrictResolution:
    """`ddlDistrict` carries Gujarati text only — unlike taluka/village there is
    no ASCII fallback, so a direct caller passing "Bhavnagar" got
    "district 'Bhavnagar' not found" (observed 2026-08-24).
    """

    def test_resolves_numeric_code(self):
        assert _fetcher._resolve_district(DISTRICT_OPTS, "14") == "14"

    def test_resolves_gujarati_name(self):
        assert _fetcher._resolve_district(DISTRICT_OPTS, "ભાવનગર") == "14"

    def test_resolves_ascii_name(self):
        assert _fetcher._resolve_district(DISTRICT_OPTS, "Bhavnagar") == "14"

    def test_resolves_ascii_name_case_insensitively(self):
        assert _fetcher._resolve_district(DISTRICT_OPTS, "bhavnagar") == "14"

    def test_unknown_district_returns_none(self):
        assert _fetcher._resolve_district(DISTRICT_OPTS, "Nowhere") is None

    def test_placeholder_option_never_matches(self):
        # the blank "Select" option must never be chosen as a district
        assert _fetcher._resolve_district(DISTRICT_OPTS, "") is None


# --------------------------------------------------------- proxied timeouts
class TestConnectTimeoutDefault:
    """A proxied run pays for the CONNECT tunnel to the residential exit on top
    of the request; that cold-starts past 6s (observed 2026-08-24), which failed
    whole attempts. Direct runs keep the short 6s NAT64 fast-fail.
    """

    def test_direct_default_is_short(self):
        from anyror.http_fetch import _default_connect_timeout
        assert _default_connect_timeout({}) == 6.0

    def test_proxied_default_is_long(self):
        from anyror.http_fetch import _default_connect_timeout
        assert _default_connect_timeout({"ANYROR_PROXY": "http://u:p@host:443"}) == 30.0

    def test_explicit_env_wins_over_proxy_default(self):
        from anyror.http_fetch import _default_connect_timeout
        env = {"ANYROR_PROXY": "http://u:p@host:443", "ANYROR_CONNECT_TIMEOUT": "12"}
        assert _default_connect_timeout(env) == 12.0

    def test_blank_proxy_is_treated_as_absent(self):
        from anyror.http_fetch import _default_connect_timeout
        assert _default_connect_timeout({"ANYROR_PROXY": "   "}) == 6.0
