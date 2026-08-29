"""Driving Garvi's free property search — offline, against the recorded page.

Garvi (the Gujarat registration index) is a second, independent source from
AnyRoR: AnyRoR gives the 7/12 and the 6-entry mutation register, Garvi gives the
registered-document index the encumbrance opinion actually rests on.

Two things make this module worth testing hard rather than eyeballing:

1. The page is ASP.NET WebForms. A postback that does not echo the *current*
   __VIEWSTATE back is rejected, so the dropdown you think you selected silently
   is not selected, and the search runs against whatever the server still holds.
   That failure looks like a clean result, not an error.
2. The final submit is gated on an SMS one-time code delivered to a real
   colleague's handset. Nothing here may press that button. The fake transport
   below raises if any request body so much as carries the OTP control name, so
   a regression fails the suite instead of texting a person.

Every test runs off tests/fixtures/garvi/frmPropertySearch_New.html, captured
live on 2026-08-28. No test in this file performs I/O of any kind.
"""
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from gujtsr.garvi import (
    SURVEY_NUMBER_WARNING,
    BASE_URL,
    GarviBlocked,
    GarviCaptchaUnavailable,
    GarviSession,
    OTP_CONTROL,
    P,
    captcha_url,
    options,
    parse_form,
)

FIXTURE = Path(__file__).parent / "fixtures" / "garvi" / "frmPropertySearch_New.html"
LIVE_HTML = FIXTURE.read_text(encoding="utf-8")

# Measured from the fixture; if the recorded page is ever re-captured these move.
LIVE_VIEWSTATE_LEN = 2908
LIVE_VIEWSTATEGENERATOR = "B8E69F6D"
LIVE_CAPTCHA_GUID = "6f1dbd14-bf4a-4f14-a056-10902f30bbca"


# --------------------------------------------------------------------------
# Fixture surgery. The recorded page has cmbofc and ddlindex2village EMPTY,
# because on the live site they are filled by a postback. To exercise the
# cascade we have to build the pages the server would have sent back — from
# the real page, so everything else (VIEWSTATE, control names, captcha) stays
# exactly as the portal writes it.
# --------------------------------------------------------------------------

def _with_options(html: str, control: str, opts) -> str:
    """Return `html` with <select id=MainContent_{control}> carrying `opts`."""
    body = "".join('<option value="%s">%s</option>' % (v, t) for v, t in opts)
    pat = re.compile(r'(<select[^>]*id="MainContent_%s"[^>]*>).*?(</select>)'
                     % re.escape(control), re.S)
    new, n = pat.subn(lambda m: m.group(1) + body + m.group(2), html)
    assert n == 1, f"could not find select {control} in the fixture"
    return new


def _with_viewstate(html: str, value: str) -> str:
    """Return `html` with a different __VIEWSTATE, the way a real postback does."""
    pat = re.compile(r'(name="__VIEWSTATE" id="__VIEWSTATE" value=")[^"]*(")')
    new, n = pat.subn(lambda m: m.group(1) + value + m.group(2), html)
    assert n == 1, "could not find __VIEWSTATE in the fixture"
    return new


def _with_captcha_guid(html: str, guid: str) -> str:
    """Return `html` with a different captcha guid, the way a postback does.

    ASP.NET reissues the guid on every postback and binds it to the server-side
    session, so this is not cosmetic: it is the difference between reading the
    captcha Garvi is currently asking and reading a stale one.
    """
    pat = re.compile(r'(<img src="CaptchaImage\.aspx\?guid=)[^"]*(")')
    new, n = pat.subn(lambda m: m.group(1) + guid + m.group(2), html)
    assert n == 1, "could not find the captcha image in the fixture"
    return new


OFFICES = [("1", "AHMEDABAD-1"), ("2", "AHMEDABAD-2")]
VILLAGES = [("101", "VASTRAPUR"), ("102", "BODAKDEV")]

# Page 2: what the server returns after the district postback — offices filled.
PAGE_AFTER_DISTRICT = _with_viewstate(
    _with_options(LIVE_HTML, "cmbofc", OFFICES), "VIEWSTATE-AFTER-DISTRICT")
# Page 3: after the office postback — villages filled too.
PAGE_AFTER_OFFICE = _with_viewstate(
    _with_options(PAGE_AFTER_DISTRICT, "ddlindex2village", VILLAGES),
    "VIEWSTATE-AFTER-OFFICE")

# Page 2', identical to page 2 but for the captcha: the guid the server hands
# back after a postback is a NEW one. Nothing that caches the first guid can
# pass the re-read test below.
SECOND_CAPTCHA_GUID = "0a4e77bd-2c19-4d38-9f5b-77ce41a6d902"
PAGE_AFTER_DISTRICT_NEW_CAPTCHA = _with_captcha_guid(PAGE_AFTER_DISTRICT,
                                                     SECOND_CAPTCHA_GUID)

# Two distinguishable image bodies. Real PNG magic, so a magic-byte check sees
# an image; different payloads, so "which one came back" is answerable.
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
CAPTCHA_PNG = PNG_MAGIC + b"first-captcha-pixels"
SECOND_CAPTCHA_PNG = PNG_MAGIC + b"second-captcha-pixels"


class FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


class FakeImageResponse(FakeResponse):
    """A binary body, the way requests exposes one: bytes on `.content`.

    Subclasses FakeResponse so FakeTransport hands it back untouched.
    """

    def __init__(self, content, status_code=200):
        super().__init__(content.decode("latin-1"), status_code)
        self.content = content


class FakeCaptchaError(RuntimeError):
    """Stands in for anyror.captcha_solver.CaptchaError.

    A local class on purpose: no test in this file may import the real solver,
    which shells out to the `claude` CLI.
    """


class FakeSolver:
    """Stands in for CaptchaSolver(shape=ALNUM_5). Reads nothing, records all.

    The default reading is deliberately not a string this module could produce
    by accident — not the fixture's captcha answer, not a substring of any page.
    """

    def __init__(self, reading="Q7ZK4", error=None):
        self.reading = reading
        self.error = error
        self.seen = []          # every image body handed to it

    def solve(self, image_data):
        self.seen.append(image_data)
        if self.error is not None:
            raise self.error
        return self.reading


class FakeTransport:
    """Stands in for requests.Session. Records calls, performs no I/O.

    The OTP tripwire is the point of this class. Garvi's
    ctl00$MainContent$BtnSendOTP sends an SMS to a colleague's phone; if any
    code path ever puts that name in a request body, the suite must fail loudly
    rather than quietly succeed.
    """

    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []          # (method, url, data)

    def get(self, url, **kw):
        self.calls.append(("GET", url, None))
        return self._next()

    def post(self, url, data=None, **kw):
        data = dict(data or {})
        offenders = [k for k in data if "BtnSendOTP" in k]
        if offenders:
            raise AssertionError(
                "the code under test tried to press Garvi's Send-OTP button "
                f"({offenders}) — that texts a real handset")
        self.calls.append(("POST", url, data))
        return self._next()

    @property
    def posts(self):
        return [c for c in self.calls if c[0] == "POST"]

    def _next(self):
        assert self.pages, "fake transport ran out of recorded pages"
        item = self.pages.pop(0)
        return item if isinstance(item, FakeResponse) else FakeResponse(item)


def _session(pages, **kw):
    """A session wired to a fake transport and a fake clock (tests stay instant)."""
    kw.setdefault("sleep", lambda seconds: None)
    return GarviSession(transport=FakeTransport(pages), **kw)


# --------------------------------------------------------------------------
# parse_form — the hidden fields a postback must echo back
# --------------------------------------------------------------------------

class TestParseForm:
    def test_carries_viewstate_and_generator(self):
        fields = parse_form(LIVE_HTML)
        assert len(fields["__VIEWSTATE"]) == LIVE_VIEWSTATE_LEN
        assert fields["__VIEWSTATEGENERATOR"] == LIVE_VIEWSTATEGENERATOR

    def test_carries_every_hidden_input_not_just_the_famous_two(self):
        """__LASTFOCUS et al are part of the form; drop one and the page drifts."""
        fields = parse_form(LIVE_HTML)
        assert set(fields) == {"__EVENTTARGET", "__EVENTARGUMENT", "__LASTFOCUS",
                               "__VIEWSTATE", "__VIEWSTATEGENERATOR"}

    def test_does_not_invent_eventvalidation(self):
        """Garvi's search page has NO __EVENTVALIDATION.

        Sending an empty one is not harmless — ASP.NET validates the field when
        it is present, so a fabricated blank value gets the postback rejected.
        """
        assert "__EVENTVALIDATION" not in LIVE_HTML
        assert "__EVENTVALIDATION" not in parse_form(LIVE_HTML)


# --------------------------------------------------------------------------
# options — reading a dropdown without ever offering the placeholder
# --------------------------------------------------------------------------

class TestOptions:
    def test_district_placeholder_is_dropped(self):
        """'---Select District---' (value 0) is in the page and must not survive.

        Submitting district 0 returns the whole-state index, or nothing, with no
        error — the caller has no way to tell that from a genuine empty result.
        """
        assert '<option selected="selected" value="0">---Select District---' in LIVE_HTML
        opts = options(LIVE_HTML, "cmbDistrict")
        assert ("0", "---Select District---") not in opts
        assert all(v != "0" for v, _ in opts)
        assert len(opts) == 34            # 35 <option> elements minus the placeholder

    def test_search_type_placeholder_uses_minus_one(self):
        """The other placeholder value NIC uses. Dropping only '0' misses it."""
        assert '--Select Search Type--' in LIVE_HTML
        opts = options(LIVE_HTML, "ddlsearchtype")
        assert all(v != "-1" for v, _ in opts)
        assert len(opts) == 4

    def test_placeholder_is_dropped_even_when_the_value_attribute_comes_last(self):
        """`<option selected="selected" value="0">` — attribute order is not fixed.

        A `<option value="..."` regex silently skips the selected option, which
        is exactly the one carrying the placeholder.
        """
        opts = options(LIVE_HTML, "cmbDistrict")
        assert "---Select District---" not in [t for _, t in opts]

    def test_labels_stay_attached_to_the_right_value(self):
        """The bilingual label is why this API trades in values, not names.

        Property type 1 is literally "AGRICULTURE(કૃષિ)" — a caller matching on
        "AGRICULTURE" by equality gets nothing, and a caller matching by
        substring across a greedily-parsed page gets whatever option happened to
        share the value in a *different* dropdown.
        """
        labels = dict(options(LIVE_HTML, "ddlProperty"))
        assert labels["1"] == "AGRICULTURE(કૃષિ)"
        assert dict(options(LIVE_HTML, "ddlsearchtype"))["1"].startswith("TP./FP.Number")

    def test_option_labels_are_unescaped(self):
        """Not exercised by the recorded page (it carries no entities in an
        option), but a district list that ever ships `&amp;` must not reach a
        report as literal '&amp;'."""
        page = ('<select id="MainContent_x">'
                '<option value="0">--pick--</option>'
                '<option value="7"> DAHOD &amp; ZALOD </option>'
                '</select>')
        assert options(page, "x") == [("7", "DAHOD & ZALOD")]

    def test_empty_dropdown_is_an_empty_list_not_an_error(self):
        """cmbofc is empty until a district postback. That is a state, not a fault."""
        assert options(LIVE_HTML, "cmbofc") == []
        assert options(LIVE_HTML, "ddlindex2village") == []

    def test_absent_dropdown_is_an_empty_list_not_an_error(self):
        assert options(LIVE_HTML, "cmbNoSuchControl") == []

    def test_control_may_be_named_by_id_or_by_post_name(self):
        by_id = options(LIVE_HTML, "cmbDistrict")
        assert options(LIVE_HTML, "MainContent_cmbDistrict") == by_id
        assert options(LIVE_HTML, P + "cmbDistrict") == by_id


# --------------------------------------------------------------------------
# The cascade
# --------------------------------------------------------------------------

class TestDistricts:
    def test_districts_come_from_the_initial_page_with_the_real_codes(self):
        """35 options ship in the initial HTML — no postback needed for these."""
        s = _session([LIVE_HTML])
        s.open()
        codes = dict((t, v) for v, t in s.districts())
        assert codes["AHMEDABAD"] == "12"
        assert codes["AMRELI"] == "5"
        assert codes["ANAND"] == "22"
        assert len(codes) == 34
        assert len(s.transport.posts) == 0, "districts must not cost a postback"


class TestCascade:
    def test_offices_are_empty_until_the_district_postback(self):
        s = _session([LIVE_HTML])
        s.open()
        assert options(s.html, "cmbofc") == []

    def test_offices_drive_one_postback_targeting_cmbDistrict(self):
        s = _session([LIVE_HTML, PAGE_AFTER_DISTRICT])
        s.open()
        assert s.offices("12") == OFFICES
        assert len(s.transport.posts) == 1
        _, url, data = s.transport.posts[0]
        assert url == BASE_URL
        assert data["__EVENTTARGET"] == P + "cmbDistrict"
        assert data[P + "cmbDistrict"] == "12"

    def test_villages_drive_the_district_then_office_postbacks(self):
        s = _session([LIVE_HTML, PAGE_AFTER_DISTRICT, PAGE_AFTER_OFFICE])
        s.open()
        assert s.villages("12", "1") == VILLAGES
        targets = [d["__EVENTTARGET"] for _, _, d in s.transport.posts]
        assert targets == [P + "cmbDistrict", P + "cmbofc"]
        # the office postback must still carry the district, or the server
        # rebuilds the office list empty and the village list never appears
        assert s.transport.posts[1][2][P + "cmbDistrict"] == "12"
        assert s.transport.posts[1][2][P + "cmbofc"] == "1"

    def test_office_postback_does_not_ask_the_village_dropdown_to_post_back(self):
        """ddlindex2village has NO onchange handler — it is the end of the cascade.

        Posting back on it would burn a request against a rate-limited portal
        for a page identical to the one we already hold.
        """
        assert 'id="MainContent_ddlindex2village"' in LIVE_HTML
        village_tag = re.search(r'<select[^>]*id="MainContent_ddlindex2village"[^>]*>',
                                LIVE_HTML).group(0)
        assert "onchange" not in village_tag
        s = _session([LIVE_HTML, PAGE_AFTER_DISTRICT, PAGE_AFTER_OFFICE])
        s.open()
        s.villages("12", "1")
        assert len(s.transport.posts) == 2


# --------------------------------------------------------------------------
# VIEWSTATE round-trip — the whole reason this module exists
# --------------------------------------------------------------------------

class TestViewstateRoundTrip:
    def test_postback_echoes_the_viewstate_it_was_given(self):
        s = _session([LIVE_HTML, PAGE_AFTER_DISTRICT])
        s.open()
        sent_from_page_one = parse_form(LIVE_HTML)["__VIEWSTATE"]
        s.postback(P + "cmbDistrict", {P + "cmbDistrict": "12"})
        _, _, data = s.transport.posts[0]
        assert data["__VIEWSTATE"] == sent_from_page_one
        assert data["__VIEWSTATEGENERATOR"] == LIVE_VIEWSTATEGENERATOR

    def test_a_postback_before_open_fetches_the_page_first(self):
        """Otherwise the very first postback ships an empty VIEWSTATE, which
        ASP.NET answers with a reset page rather than an error."""
        s = _session([LIVE_HTML, PAGE_AFTER_DISTRICT])
        s.postback(P + "cmbDistrict", {P + "cmbDistrict": "12"})
        assert [c[0] for c in s.transport.calls] == ["GET", "POST"]
        assert s.transport.posts[0][2]["__VIEWSTATE"] == parse_form(LIVE_HTML)["__VIEWSTATE"]

    def test_the_new_viewstate_is_carried_into_the_next_postback(self):
        """The response's VIEWSTATE, not the one we opened with.

        ASP.NET rejects a stale VIEWSTATE, and Garvi's rejection is a re-rendered
        page with the dropdowns reset — which reads as 'no records', not an error.
        PAGE_AFTER_DISTRICT deliberately carries a DIFFERENT VIEWSTATE so a
        module that kept re-sending the opening one cannot pass this.
        """
        assert parse_form(PAGE_AFTER_DISTRICT)["__VIEWSTATE"] == "VIEWSTATE-AFTER-DISTRICT"
        assert parse_form(LIVE_HTML)["__VIEWSTATE"] != "VIEWSTATE-AFTER-DISTRICT"

        s = _session([LIVE_HTML, PAGE_AFTER_DISTRICT, PAGE_AFTER_OFFICE])
        s.open()
        s.villages("12", "1")
        first, second = s.transport.posts
        assert first[2]["__VIEWSTATE"] == parse_form(LIVE_HTML)["__VIEWSTATE"]
        assert second[2]["__VIEWSTATE"] == "VIEWSTATE-AFTER-DISTRICT"
        assert s.fields["__VIEWSTATE"] == "VIEWSTATE-AFTER-OFFICE"


# --------------------------------------------------------------------------
# Captcha
# --------------------------------------------------------------------------

class TestCaptchaUrl:
    def test_url_is_extracted_and_absolute(self):
        """The page writes it relative; a bare 'CaptchaImage.aspx?...' fetches nothing."""
        assert 'src="CaptchaImage.aspx?guid=' in LIVE_HTML
        url = captcha_url(LIVE_HTML)
        assert url == ("https://garvi.gujarat.gov.in/CaptchaImage.aspx?guid="
                       + LIVE_CAPTCHA_GUID)
        assert url.startswith("https://")

    def test_returns_none_when_the_image_is_absent(self):
        stripped = re.sub(r'<img src="CaptchaImage\.aspx[^>]*>', "", LIVE_HTML)
        assert "CaptchaImage.aspx" not in stripped
        assert captcha_url(stripped) is None

    def test_session_exposes_the_captcha_of_the_page_it_is_holding(self):
        s = _session([LIVE_HTML])
        s.open()
        assert LIVE_CAPTCHA_GUID in s.captcha_url()


class TestCaptchaImage:
    """Fetching the image itself — on this session, for the page in hand."""

    def test_it_fetches_the_guid_on_the_page_currently_held(self):
        s = _session([LIVE_HTML, FakeImageResponse(CAPTCHA_PNG)])
        s.open()
        assert s.captcha_image() == CAPTCHA_PNG
        gets = [url for method, url, _ in s.transport.calls if method == "GET"]
        assert len(gets) == 2, "one GET for the page, one for its captcha"
        assert gets[1] == ("https://garvi.gujarat.gov.in/CaptchaImage.aspx?guid="
                           + LIVE_CAPTCHA_GUID), "the URL must be absolute"

    def test_it_re_reads_the_guid_after_a_postback(self):
        """The guid is session-bound and ASP.NET reissues it on every postback.

        Cache it and you fetch the image for a question Garvi has stopped
        asking; the answer is then wrong, and a wrong answer costs a request
        against the one office IP the whole firm shares.
        """
        assert SECOND_CAPTCHA_GUID != LIVE_CAPTCHA_GUID
        assert SECOND_CAPTCHA_GUID in PAGE_AFTER_DISTRICT_NEW_CAPTCHA
        assert LIVE_CAPTCHA_GUID not in PAGE_AFTER_DISTRICT_NEW_CAPTCHA

        s = _session([LIVE_HTML, FakeImageResponse(CAPTCHA_PNG),
                      PAGE_AFTER_DISTRICT_NEW_CAPTCHA,
                      FakeImageResponse(SECOND_CAPTCHA_PNG)])
        s.open()
        first = s.captcha_image()
        s.offices("12")
        second = s.captcha_image()

        gets = [url for method, url, _ in s.transport.calls if method == "GET"]
        assert LIVE_CAPTCHA_GUID in gets[1]
        assert SECOND_CAPTCHA_GUID in gets[2], "it re-used a stale guid"
        assert LIVE_CAPTCHA_GUID not in gets[2]
        assert (first, second) == (CAPTCHA_PNG, SECOND_CAPTCHA_PNG)

    def test_it_goes_through_the_injected_transport(self):
        """Cookies live on the transport. A captcha fetched on another
        connection belongs to another session and cannot be answered."""
        s = _session([LIVE_HTML, FakeImageResponse(CAPTCHA_PNG)])
        s.open()
        s.captcha_image()
        assert len(s.transport.calls) == 2, "the image was not fetched on this transport"

    def test_the_captcha_fetch_is_paced_like_every_other_request(self):
        slept = []
        s = GarviSession(
            transport=FakeTransport([LIVE_HTML, FakeImageResponse(CAPTCHA_PNG)]),
            sleep=slept.append)
        s.open()
        s.captcha_image()
        assert slept, "the captcha fetch skipped the pacing"
        assert min(slept) >= 2.0

    def test_a_block_page_in_place_of_the_image_raises(self):
        """A WAF page is not an image. Handing it to the model gets a
        confident five characters of nonsense and burns a request."""
        blocked = FakeResponse("<html><body>Web Page Blocked. Attack ID: 1</body></html>")
        s = _session([LIVE_HTML, blocked])
        s.open()
        with pytest.raises(GarviBlocked):
            s.captcha_image()

    def test_a_block_status_raises_even_when_the_body_looks_like_a_png(self):
        """Status first: neither the wording check nor the magic bytes can see this."""
        s = _session([LIVE_HTML, FakeImageResponse(CAPTCHA_PNG, status_code=403)])
        s.open()
        with pytest.raises(GarviBlocked) as e:
            s.captcha_image()
        assert "403" in str(e.value)

    def test_a_page_with_no_captcha_raises_instead_of_passing_none(self):
        stripped = re.sub(r'<img src="CaptchaImage\.aspx[^>]*>', "", LIVE_HTML)
        assert "CaptchaImage.aspx" not in stripped
        assert "__VIEWSTATE" in stripped, "still the search form, just no captcha"
        s = _session([stripped])
        s.open()
        before = len(s.transport.calls)
        with pytest.raises(GarviCaptchaUnavailable) as e:
            s.captcha_image()
        assert "captcha" in str(e.value).lower()
        assert len(s.transport.calls) == before, "it fetched something anyway"

    def test_an_empty_body_is_not_handed_to_the_model(self):
        s = _session([LIVE_HTML, FakeImageResponse(b"")])
        s.open()
        with pytest.raises(GarviCaptchaUnavailable):
            s.captcha_image()


class TestSolveCaptcha:
    """Reading it with the model — the only reader this module has."""

    def test_it_returns_the_solver_reading_for_the_fetched_image(self):
        solver = FakeSolver("Q7ZK4")
        s = _session([LIVE_HTML, FakeImageResponse(CAPTCHA_PNG)],
                     captcha_solver=solver)
        s.open()
        assert s.solve_captcha() == "Q7ZK4"
        assert solver.seen == [CAPTCHA_PNG], \
            "the solver must be given the bytes this session just fetched"

    def test_a_captcha_error_propagates_and_is_never_guessed_around(self):
        """A wrong answer burns a request against the firm's single office IP.

        Swallowing the error and submitting something is worse than stopping.
        """
        solver = FakeSolver(error=FakeCaptchaError("could not read it"))
        s = _session([LIVE_HTML, FakeImageResponse(CAPTCHA_PNG)],
                     captcha_solver=solver)
        s.open()
        with pytest.raises(FakeCaptchaError):
            s.solve_captcha()

    def test_the_solver_is_injectable_and_never_built_until_it_is_needed(self):
        """Constructing the real one imports a module that shells out to the
        `claude` CLI. Nothing may build it just by making a session."""
        s = GarviSession(transport=FakeTransport([]), sleep=lambda seconds: None)
        assert s.captcha_solver is None
        s2 = _session([LIVE_HTML], captcha_solver=FakeSolver())
        assert isinstance(s2.captcha_solver, FakeSolver)


# --------------------------------------------------------------------------
# The search builder — prepared, unsent, stopped at the OTP
# --------------------------------------------------------------------------

def _prepared_session():
    s = _session([LIVE_HTML, PAGE_AFTER_DISTRICT, PAGE_AFTER_OFFICE])
    s.open()
    s.villages("12", "1")
    return s


def _prepare(s, **over):
    kw = dict(district="12", office="1", village="101", property_type="1",
              search_type="3", search_number="122", captcha_text="A1B2C",
              applicant_name="Nav Law Associates LLP", mobile="9876543210")
    kw.update(over)
    return s.prepare_search(**kw)


class TestPrepareSearch:
    def test_stops_at_the_otp_and_says_so(self):
        out = _prepare(_prepared_session())
        assert out["success"] is False
        assert out["blocked_on"] == "otp"
        assert out["prepared"] is True
        assert out["sent"] is False
        assert "OTP" in out["error"] or "verification code" in out["error"].lower()

    def test_sends_nothing_at_all(self):
        """'Prepared' means prepared. Not one extra request leaves the process."""
        s = _prepared_session()
        before = len(s.transport.calls)
        _prepare(s)
        assert len(s.transport.calls) == before

    def test_the_prepared_body_is_complete_and_carries_the_live_viewstate(self):
        out = _prepare(_prepared_session())
        f = out["fields"]
        assert f["__VIEWSTATE"] == "VIEWSTATE-AFTER-OFFICE"
        assert f[P + "cmbDistrict"] == "12"
        assert f[P + "cmbofc"] == "1"
        assert f[P + "ddlindex2village"] == "101"
        assert f[P + "ddlProperty"] == "1"
        assert f[P + "ddlsearchtype"] == "3"
        assert f[P + "txtsearchtypeno"] == "122"
        assert f[P + "CaptchaControl1"] == "A1B2C"
        assert f[P + "txtappName"] == "Nav Law Associates LLP"
        assert f[P + "txtmbNo"] == "9876543210"

    def test_the_prepared_body_selects_the_property_search_radio(self):
        """All five search modes POST under one name, ctl00$MainContent$rb.

        Omit it and Garvi keeps whatever mode the session was last in.
        """
        f = _prepare(_prepared_session())["fields"]
        assert f[P + "rb"] == "rbproperty"

    def test_the_prepared_body_does_not_contain_the_otp_button(self):
        f = _prepare(_prepared_session())["fields"]
        assert not any("BtnSendOTP" in k for k in f)
        assert OTP_CONTROL not in f

    def test_it_warns_that_the_index_is_keyed_on_the_survey_number_at_registration(self):
        """A renumbered parcel searched under its CURRENT number returns a short,
        clean, wrong result. The warning has to travel with the request."""
        out = _prepare(_prepared_session())
        assert "warning" in out
        w = out["warning"].lower()
        assert "renumber" in w or "as written" in w or "at registration" in w
        assert "no encumbrance" in w or "clean" in w or "absence" in w

    def test_a_district_that_is_not_on_the_page_is_refused_not_guessed(self):
        """ISSUES.md #1: a scraper that guesses returns the wrong land, silently."""
        out = _prepare(_prepared_session(), district="999")
        assert out["success"] is False
        assert out["blocked_on"] != "otp"
        assert "999" in out["error"]

    def test_a_village_that_is_not_on_the_page_is_refused_not_guessed(self):
        out = _prepare(_prepared_session(), village="999")
        assert out["success"] is False
        assert out["blocked_on"] != "otp"
        assert "999" in out["error"]

    def test_refuses_before_the_cascade_has_been_driven(self):
        """With cmbofc still empty, nothing the caller names can be verified."""
        s = _session([LIVE_HTML])
        s.open()
        out = _prepare(s)
        assert out["success"] is False
        assert out["blocked_on"] != "otp"

    def test_refuses_without_a_survey_number(self):
        out = _prepare(_prepared_session(), search_number="   ")
        assert out["success"] is False
        assert out["blocked_on"] != "otp"

    def test_refuses_without_a_captcha_answer(self):
        out = _prepare(_prepared_session(), captcha_text="")
        assert out["success"] is False
        assert out["blocked_on"] != "otp"
        assert "captcha" in out["error"].lower()


class TestPrepareSearchReadsTheCaptchaItself:
    def test_no_captcha_text_means_the_model_reads_the_image(self):
        solver = FakeSolver("Q7ZK4")
        s = _session([LIVE_HTML, PAGE_AFTER_DISTRICT, PAGE_AFTER_OFFICE,
                      FakeImageResponse(CAPTCHA_PNG)], captcha_solver=solver)
        s.open()
        s.villages("12", "1")
        out = _prepare(s, captcha_text=None)
        assert out["blocked_on"] == "otp", out["error"]
        assert out["fields"][P + "CaptchaControl1"] == "Q7ZK4"
        assert solver.seen == [CAPTCHA_PNG]

    def test_an_explicit_answer_is_used_unchanged_and_the_solver_is_left_alone(self):
        solver = FakeSolver("Q7ZK4")
        s = _session([LIVE_HTML, PAGE_AFTER_DISTRICT, PAGE_AFTER_OFFICE],
                     captcha_solver=solver)
        s.open()
        s.villages("12", "1")
        before = len(s.transport.calls)
        out = _prepare(s, captcha_text="AB12X")
        assert out["fields"][P + "CaptchaControl1"] == "AB12X"
        assert solver.seen == [], "it re-read a captcha the caller had already given"
        assert len(s.transport.calls) == before, "an explicit answer must cost no request"

    def test_a_refused_search_never_burns_a_captcha_read(self):
        """The dropdown checks come first. A refusal must not cost a request."""
        solver = FakeSolver("Q7ZK4")
        s = _session([LIVE_HTML, PAGE_AFTER_DISTRICT, PAGE_AFTER_OFFICE],
                     captcha_solver=solver)
        s.open()
        s.villages("12", "1")
        before = len(s.transport.calls)
        out = _prepare(s, district="999", captcha_text=None)
        assert out["success"] is False
        assert out["blocked_on"] != "otp"
        assert solver.seen == []
        assert len(s.transport.calls) == before

    def test_an_empty_string_is_still_refused_not_solved(self):
        """None means 'read it for me'. "" means the caller sent nothing."""
        solver = FakeSolver("Q7ZK4")
        s = _session([LIVE_HTML, PAGE_AFTER_DISTRICT, PAGE_AFTER_OFFICE],
                     captcha_solver=solver)
        s.open()
        s.villages("12", "1")
        out = _prepare(s, captcha_text="")
        assert out["success"] is False
        assert "captcha" in out["error"].lower()
        assert solver.seen == []


# --------------------------------------------------------------------------
# The OTP seam — a human drives this, never the code
# --------------------------------------------------------------------------

class TestOtpIsUnreachableByDefault:
    def test_send_otp_refuses_without_the_explicit_opt_in(self):
        s = _prepared_session()
        prepared = _prepare(s)
        before = len(s.transport.calls)
        out = s.send_otp(prepared)
        assert out["success"] is False
        assert len(s.transport.calls) == before, "a refusal must not hit the network"

    def test_the_refusal_names_the_handset_and_the_reason(self):
        """The message is read by a lawyer deciding what to do next."""
        s = _prepared_session()
        out = s.send_otp(_prepare(s))
        msg = out["error"]
        assert "9876543210" in msg, "the refusal must name the number that would be texted"
        low = msg.lower()
        assert "sms" in low or "text" in low
        assert "i_have_the_handset" in msg, "say how a person opts in"

    def test_the_opt_in_is_keyword_only_and_defaults_to_false(self):
        """No positional argument may ever land on it by accident."""
        import inspect
        sig = inspect.signature(GarviSession.send_otp)
        p = sig.parameters["i_have_the_handset"]
        assert p.default is False
        assert p.kind is inspect.Parameter.KEYWORD_ONLY

    def test_a_truthy_string_is_not_an_opt_in(self):
        """`i_have_the_handset="no"` is truthy. It must not press the button."""
        s = _prepared_session()
        out = s.send_otp(_prepare(s), i_have_the_handset="no")
        assert out["success"] is False

    def test_an_unprepared_request_is_refused_even_with_the_opt_in(self):
        s = _prepared_session()
        bad = _prepare(s, district="999")      # never reached the otp stage
        out = s.send_otp(bad, i_have_the_handset=True)
        assert out["success"] is False


# --------------------------------------------------------------------------
# Pacing and block pages
# --------------------------------------------------------------------------

class TestPacingAndBlocks:
    def test_requests_are_paced_through_the_injected_sleep(self):
        """Serial, >=2s apart. Injected so the suite stays instant."""
        slept = []
        s = GarviSession(transport=FakeTransport([LIVE_HTML, PAGE_AFTER_DISTRICT]),
                         sleep=slept.append)
        s.open()
        s.offices("12")
        assert slept, "no pacing between requests"
        assert min(slept) >= 2.0

    def test_the_first_request_is_not_delayed(self):
        slept = []
        s = GarviSession(transport=FakeTransport([LIVE_HTML]), sleep=slept.append)
        s.open()
        assert slept == []

    def test_a_block_page_stops_the_walk_instead_of_retrying(self):
        """One office IP serves the whole firm. A retry loop loses it for everyone.

        The message has to name the block, not just say something went wrong:
        the structural 'not the form' check below would also stop this page, and
        a human deciding whether to wait or to switch connections needs to know
        which of the two happened.
        """
        blocked = "<html><body>Web Page Blocked. Attack ID: 100000</body></html>"
        s = _session([LIVE_HTML, blocked, PAGE_AFTER_DISTRICT])
        s.open()
        with pytest.raises(GarviBlocked) as e:
            s.offices("12")
        assert "block page" in str(e.value)
        assert "web page blocked" in str(e.value).lower(), \
            "the message must name the marker it matched"
        assert len(s.transport.posts) == 1, "it retried a block page"

    def test_a_response_that_is_not_the_form_is_treated_as_a_block(self):
        """Garvi's WAF has never fired here, so there is no known block-page
        signature to match on — unlike AnyRoR's 'Attack ID' page. The reliable
        tell is structural: a 200 with no __VIEWSTATE is not the search form,
        whatever it says, and posting into it sends a blank VIEWSTATE.
        """
        not_the_form = "<html><body><h1>Service temporarily unavailable</h1></body></html>"
        assert "__VIEWSTATE" not in not_the_form
        assert not any(m in not_the_form.lower() for m in
                       ("web page blocked", "attack id", "access denied",
                        "request rejected"))
        s = _session([LIVE_HTML, not_the_form])
        s.open()
        with pytest.raises(GarviBlocked):
            s.offices("12")
        assert len(s.transport.posts) == 1

    def test_an_http_block_status_is_a_block_too(self):
        """A perfectly good-looking form body behind a 403 is still a block.

        The page here is the real one, VIEWSTATE and all, so neither the wording
        check nor the structural check can account for this — only the status.
        """
        s = _session([LIVE_HTML, FakeResponse(LIVE_HTML, status_code=403)])
        s.open()
        with pytest.raises(GarviBlocked) as e:
            s.offices("12")
        assert "403" in str(e.value)


# --------------------------------------------------------------------------
# Wiring
# --------------------------------------------------------------------------

class TestTransportIsInjectable:
    def test_no_requests_session_is_created_when_a_transport_is_given(self):
        """The reason every test above is offline."""
        s = GarviSession(transport=FakeTransport([LIVE_HTML]), sleep=lambda s: None)
        assert isinstance(s.transport, FakeTransport)

    def test_the_default_transport_is_a_requests_session(self):
        import requests
        s = GarviSession()
        assert isinstance(s.transport, requests.Session)
        assert s.transport.headers.get("Referer") == BASE_URL


# --------------------------------------------------------------------------
# The renumbering trap. Every return a caller might act on has to carry it,
# because this is the failure that looks like success: search a renumbered
# parcel under its current number and Garvi answers short, clean and wrong.
# --------------------------------------------------------------------------

class TestTheRenumberingWarningTravelsWithEveryResult:
    def test_a_prepared_search_carries_it(self):
        prepared = _prepare(_prepared_session())
        assert prepared["blocked_on"] == "otp"
        assert prepared["warning"] == SURVEY_NUMBER_WARNING

    def test_a_refusal_carries_it_too(self):
        """A caller who gets refused still has to know the trap exists —
        they will fix the refusal and search again."""
        refused = _prepare(_prepared_session(), village="does-not-exist")
        assert refused["prepared"] is False
        assert refused["warning"] == SURVEY_NUMBER_WARNING

    def test_the_warning_names_the_registration_date_rule(self):
        """Not just any text: the specific, load-bearing sentence."""
        w = SURVEY_NUMBER_WARNING.lower()
        assert "as written on the deed at" in w and "registration" in w
        assert "no encumbrance" in w
