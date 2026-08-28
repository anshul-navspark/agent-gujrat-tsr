"""Drive Garvi's free public property search — up to, and stopping at, the OTP.

Garvi (https://garvi.gujarat.gov.in) is the Gujarat registration department's
index of registered documents. It is the other half of a title search: AnyRoR
gives the 7/12 and the village mutation register, Garvi gives the registered
sale deeds, mortgages and charges an encumbrance opinion actually rests on.
The free `frmPropertySearch_New.aspx` search is the one this module drives.

Three things shape every design choice here.

**It is ASP.NET WebForms, so state lives in __VIEWSTATE, not in a URL.** Each
dropdown is filled by a postback, and a postback that does not echo the page's
*current* __VIEWSTATE back is rejected. Garvi does not say so: it re-renders the
page with the selections cleared, and the search then runs against whatever the
server still believes is selected. That is why `parse_form` is the core of the
module and why the session re-reads the hidden fields from every response.

**The final submit is gated on an SMS one-time code delivered to a real
handset.** Nothing in this module presses that button on its own. `prepare_search`
assembles the complete request body and hands it back *unsent*, marked
`blocked_on: "otp"`. `send_otp` refuses unless the caller passes
`i_have_the_handset=True`, which only a person standing at that phone can
truthfully do. The defaults make the unattended path impossible, on purpose.

**One office IP serves the whole firm.** Requests are serial and paced (>=2s),
and a block page raises `GarviBlocked` instead of being retried — a retry loop
against a WAF that bans by source address takes the portal away from every
lawyer in the office at once, not just this process.

The seam that makes all of the above testable is the injected transport: pass a
`requests.Session`-shaped object to `GarviSession(transport=...)` and nothing
here touches a network.
"""
from __future__ import annotations

import html as html_module
import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin

log = logging.getLogger(__name__)

BASE_URL = "https://garvi.gujarat.gov.in/frmPropertySearch_New.aspx"
ORIGIN = "https://garvi.gujarat.gov.in"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/150 Safari/537.36")

# Every control on the search panel is a child of the MainContent placeholder,
# so it POSTs as `ctl00$MainContent$<id>` and renders as `id="MainContent_<id>"`.
P = "ctl00$MainContent$"
_ID_PREFIX = "MainContent_"

DISTRICT = "cmbDistrict"
OFFICE = "cmbofc"                 # sub-registrar office
VILLAGE = "ddlindex2village"
PROPERTY_TYPE = "ddlProperty"
SEARCH_TYPE = "ddlsearchtype"
SEARCH_NUMBER = "txtsearchtypeno"
CAPTCHA_ANSWER = "CaptchaControl1"
APPLICANT_NAME = "txtappName"
MOBILE_NUMBER = "txtmbNo"

# All five search modes POST under one radio-group name. Omit it and Garvi keeps
# whichever mode the server-side session was last left in.
SEARCH_MODE = "rb"
PROPERTY_SEARCH_MODE = "rbproperty"

OTP_CONTROL = P + "BtnSendOTP"
OTP_BUTTON_LABEL = "Send Verification Code(ચકાસણી કોડ મોકલો)"

MIN_INTERVAL_SECONDS = 2.0
DEFAULT_TIMEOUT = (10.0, 60.0)          # (connect, read)

# NIC's two placeholder conventions on this page: value "0" for the district
# list, value "-1" for the property/search-type lists. Submitting either is not
# an error to Garvi — it is an empty answer, which is the dangerous kind.
PLACEHOLDER_VALUES = frozenset({"", "0", "-1"})

_BLOCK_MARKERS = ("web page blocked", "attack id", "access denied",
                  "request rejected")
_BLOCK_STATUSES = frozenset({403, 406, 429, 503})

SURVEY_NUMBER_WARNING = (
    "Garvi's index is keyed on the survey number AS WRITTEN ON THE DEED AT "
    "REGISTRATION, not the number the parcel carries today. A renumbered or "
    "reconstituted parcel searched under its present number comes back short and "
    "clean with no error at all — an absence that reads exactly like 'no "
    "encumbrance'. Confirm the historical number from the 7/12 and the mutation "
    "register before treating any Garvi result as a clear title."
)

OTP_STOP_MESSAGE = (
    "The search request is fully prepared but has NOT been sent. Garvi will not "
    "run a property search until a one-time verification code, sent by SMS to the "
    "mobile number on the form, is read off that handset and typed back into the "
    "page. No code has been requested and nothing has been submitted. A person "
    "holding the handset must complete this step."
)


class GarviBlocked(RuntimeError):
    """Garvi returned a block page or a blocking status.

    Raised, not returned, and never retried. The firm reaches this portal from a
    single office IP; the correct response to a block is to stop and tell a human,
    because a retry loop costs everyone in the office their access, not just this
    run. The dict-returning entry points (`prepare_search`, `send_otp`) catch it
    and turn it into a `{"success": False, ...}` a lawyer can read.
    """


# --------------------------------------------------------------------------
# HTML reading. Plain `re`, matching anyror/http_fetch.py, so `gujtsr` keeps
# depending on nothing a lean skill sandbox would not already have.
# --------------------------------------------------------------------------

def _attr(tag: str, name: str) -> Optional[str]:
    """Read one attribute out of a start tag, quoted or not.

    Garvi mixes styles inside one page: the hidden inputs are fully quoted while
    the captcha answer box is written `<input name=ctl00$MainContent$CaptchaControl1
    type=text ...>` with no quotes at all. A quote-only regex reads half the form.
    """
    m = re.search(r'\b%s\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))'
                  % re.escape(name), tag, re.I)
    if not m:
        return None
    for group in m.groups():
        if group is not None:
            return html_module.unescape(group)
    return None


def _element_id(control: str) -> str:
    """`cmbDistrict` / `MainContent_cmbDistrict` / `ctl00$MainContent$cmbDistrict`
    all name the same control. Accept whichever the caller has to hand."""
    name = str(control).strip()
    if name.startswith(P):
        name = name[len(P):]
    if name.startswith(_ID_PREFIX):
        name = name[len(_ID_PREFIX):]
    return _ID_PREFIX + name


def _control_name(control: str) -> str:
    """The POST field name for a control, i.e. what __EVENTTARGET wants."""
    return P + _element_id(control)[len(_ID_PREFIX):]


def parse_form(html: str) -> Dict[str, str]:
    """Every hidden input on the page, as the field dict a postback must echo.

    This is the whole module in one function. ASP.NET rejects a postback that
    does not return the current __VIEWSTATE, and Garvi's rejection is not an
    error page — it is the same page with the dropdowns reset. So the hidden
    fields are read back out of *every* response rather than remembered once.

    Only what the page actually carries is returned. Notably this page has NO
    __EVENTVALIDATION, and fabricating an empty one is worse than omitting it:
    ASP.NET validates the field whenever it is present.
    """
    fields: Dict[str, str] = {}
    for tag in re.findall(r"<input\b[^>]*>", html or "", re.I):
        if (_attr(tag, "type") or "").lower() != "hidden":
            continue
        name = _attr(tag, "name")
        if name:
            fields[name] = _attr(tag, "value") or ""
    return fields


def options(html: str, control: str) -> List[Tuple[str, str]]:
    """A `<select>`'s real options as (value, label), placeholder removed.

    The placeholder is dropped because a caller must never be able to submit it.
    "---Select District---" posts as district 0 and "--Select Search Type--" as
    -1; Garvi answers both with an empty result and no error, which is
    indistinguishable from a genuinely unencumbered parcel.

    An empty or absent dropdown is `[]`, not a failure: `cmbofc` and
    `ddlindex2village` ship empty in the initial HTML by design and are filled
    by a postback, so "empty" is a normal state of the cascade.
    """
    m = re.search(r'<select\b[^>]*\bid="%s"[^>]*>(.*?)</select>'
                  % re.escape(_element_id(control)), html or "", re.S | re.I)
    if not m:
        return []
    out: List[Tuple[str, str]] = []
    for attrs, label in re.findall(r"<option\b([^>]*)>(.*?)</option>",
                                   m.group(1), re.S | re.I):
        # `value` is read by name, not by position: the placeholder is written
        # `<option selected="selected" value="0">`, so an `<option value="` regex
        # skips exactly the one option that most needs dropping.
        value = _attr(attrs, "value")
        if value is None or value in PLACEHOLDER_VALUES:
            continue
        text = html_module.unescape(re.sub(r"<[^>]+>", "", label)).strip()
        out.append((value, text))
    return out


def captcha_url(html: str, base: str = BASE_URL) -> Optional[str]:
    """Absolute URL of the session-bound captcha image, or None if it is absent.

    The page writes it relative (`CaptchaImage.aspx?guid=...`), and the guid is
    tied to the server-side session — so it must be fetched on the same transport
    that is walking the form, or the answer will not match. Returns None rather
    than raising: a page without a captcha is usually a block page or an expired
    session, and the caller should be free to inspect it.
    """
    m = re.search(
        r'<img\b[^>]*\bsrc\s*=\s*(?:"([^"]*CaptchaImage\.aspx[^"]*)"'
        r"|'([^']*CaptchaImage\.aspx[^']*)'"
        r'|([^\s>]*CaptchaImage\.aspx[^\s>]*))',
        html or "", re.I)
    if not m:
        return None
    for group in m.groups():
        if group is not None:
            return urljoin(base, html_module.unescape(group))
    return None


def _requests_session(base_url: str):
    """A real HTTP transport. Imported lazily so `import gujtsr.garvi` works for
    parsing alone, in a sandbox that has no `requests` installed."""
    import requests

    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Referer": base_url, "Origin": ORIGIN})
    return s


# --------------------------------------------------------------------------
# The session
# --------------------------------------------------------------------------

class GarviSession:
    """One walk through the property-search form, holding the current page state.

    A class rather than a closure because the state is genuinely a thing the
    caller inspects between steps — `.html`, `.fields`, `.captcha_url()` — and
    because it mirrors `AnyRoRHttpFetcher`, which is the shape anyone reading
    this repo already has in their head.

    `transport` is any object with `requests.Session`-shaped `.get()`/`.post()`.
    It defaults to a real session; every test passes a fake, which is the only
    reason this module can be covered without texting anyone or touching NIC.

    `sleep` is injected for the same reason: pacing is real in production and
    free in tests.
    """

    def __init__(self, transport: Any = None, base_url: str = BASE_URL,
                 min_interval: float = MIN_INTERVAL_SECONDS,
                 sleep: Callable[[float], Any] = time.sleep,
                 timeout: Any = DEFAULT_TIMEOUT) -> None:
        self.transport = transport if transport is not None else _requests_session(base_url)
        self.base_url = base_url
        self.min_interval = float(min_interval)
        self.timeout = timeout
        self._sleep = sleep
        self._has_requested = False
        self.html: Optional[str] = None
        self.fields: Dict[str, str] = {}

    # -- plumbing ---------------------------------------------------------

    def _pace(self) -> None:
        """Serial requests, >=2s apart — but never a delay before the first one."""
        if self._has_requested and self.min_interval > 0:
            self._sleep(self.min_interval)
        self._has_requested = True

    def _absorb(self, response: Any) -> str:
        """Adopt a response as the current page, after checking it is not a block."""
        html = getattr(response, "text", "") or ""
        status = getattr(response, "status_code", 200)
        if status in _BLOCK_STATUSES:
            raise GarviBlocked(
                f"Garvi answered HTTP {status}. This office IP looks rate-limited "
                "or blocked. Stop — do not retry — and try again later or from "
                "another connection.")
        low = html.lower()
        for marker in _BLOCK_MARKERS:
            if marker in low:
                raise GarviBlocked(
                    f"Garvi returned a block page (matched {marker!r}). The firm "
                    "reaches this portal from one office IP, so retrying would "
                    "lose it for everyone. Stopped.")
        # Garvi's WAF has never fired here, so unlike AnyRoR there is no known
        # block-page wording to match on. The structural tell is the dependable
        # one: no __VIEWSTATE means this is not the search form, whatever it
        # says, and posting into it would ship a blank VIEWSTATE — which the
        # server answers with a reset page that reads like an empty result.
        fields = parse_form(html)
        if "__VIEWSTATE" not in fields:
            raise GarviBlocked(
                "Garvi returned a page that is not the search form (no "
                "__VIEWSTATE). That is how a block, an outage or an expired "
                "session look here. Stopped without retrying — one office IP "
                "serves the whole firm.")
        self.html = html
        self.fields = fields
        return html

    def open(self) -> str:
        """GET the search page and adopt its hidden fields."""
        self._pace()
        r = self.transport.get(self.base_url, timeout=self.timeout)
        return self._absorb(r)

    def _page(self) -> str:
        if self.html is None:
            self.open()
        return self.html or ""

    def postback(self, target: str, extra_fields: Optional[Dict[str, str]] = None) -> str:
        """Fire one __doPostBack, echoing the page's current hidden fields.

        `target` is the control's POST name (`ctl00$MainContent$cmbDistrict`),
        which is what the page's own `__doPostBack` passes. The response replaces
        the current page, so the *next* postback carries the *new* __VIEWSTATE —
        re-sending the opening one gets silently rejected.
        """
        self._page()
        data = dict(self.fields)
        data["__EVENTTARGET"] = target
        data["__EVENTARGUMENT"] = ""
        data.update(extra_fields or {})
        self._pace()
        r = self.transport.post(
            self.base_url, data=data, timeout=self.timeout,
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        return self._absorb(r)

    def captcha_url(self) -> Optional[str]:
        """The captcha image on the page currently held, resolved absolute."""
        return captcha_url(self._page(), self.base_url)

    # -- the cascade ------------------------------------------------------

    def districts(self) -> List[Tuple[str, str]]:
        """All 34 districts. These ship in the initial HTML — no postback needed."""
        return options(self._page(), DISTRICT)

    def offices(self, district: str) -> List[Tuple[str, str]]:
        """Sub-registrar offices in a district, via one postback on cmbDistrict.

        Takes the district *value* (e.g. "12"), not its label. The values are the
        stable key: labels are bilingual, and the ones on the property/search-type
        lists carry a Gujarati gloss in brackets that a caller will not reproduce
        by hand. Use `districts()` to turn a name into a value.
        """
        self.postback(_control_name(DISTRICT), {P + DISTRICT: str(district)})
        return options(self.html or "", OFFICE)

    def villages(self, district: str, office: str) -> List[Tuple[str, str]]:
        """Villages under one office: postback on cmbDistrict, then on cmbofc.

        Two requests, not three — `ddlindex2village` has no onchange handler, so
        selecting a village posts nothing back; it is the end of the cascade.

        This re-drives the district step even if `offices()` was just called.
        That costs one extra request (about 2s at our pacing) and buys the
        guarantee that the page in hand is the page these values were read from.
        Submitting against a stale server-side selection is the failure mode that
        returns a real, valid-looking record for the wrong land.
        """
        self.offices(district)
        self.postback(_control_name(OFFICE),
                      {P + DISTRICT: str(district), P + OFFICE: str(office)})
        return options(self.html or "", VILLAGE)

    # -- the search request, prepared and unsent --------------------------

    @staticmethod
    def _refused(stage: str, message: str) -> Dict[str, Any]:
        return {"success": False, "prepared": False, "sent": False,
                "blocked_on": stage, "error": message,
                "warning": SURVEY_NUMBER_WARNING}

    def _check_selection(self, control: str, value: str,
                         label: str) -> Optional[Dict[str, Any]]:
        """Refuse a code the page in hand does not offer. Never guess.

        ISSUES.md #1 is the history here: a scraper that fell back to "the first
        option" fetched a different owner's record for the same survey number, and
        nothing in the output said so.
        """
        available = options(self.html or "", control)
        if not available:
            return self._refused(
                "cascade",
                f"The {label} dropdown is empty on the page in hand, so '{value}' "
                f"cannot be checked against it. Drive the cascade first — "
                f"districts(), offices(district), villages(district, office) — and "
                f"prepare the search against the page those calls leave behind.")
        offered = [v for v, _ in available]
        if str(value) not in offered:
            return self._refused(
                "selection",
                f"The {label} code '{value}' is not offered by the page in hand, so "
                f"the search was not built. Garvi does not report a wrong code as "
                f"an error — it returns an empty result that reads like a clean "
                f"title. Codes offered: {', '.join(offered[:8])}"
                f"{' ...' if len(offered) > 8 else ''}.")
        return None

    def prepare_search(self, district: str, office: str, village: str,
                       property_type: str, search_type: str, search_number: str,
                       captcha_text: str, applicant_name: str = "",
                       mobile: str = "") -> Dict[str, Any]:
        """Assemble the complete property-search POST body — and stop, unsent.

        Returns `{"success": False, "prepared": True, "sent": False,
        "blocked_on": "otp", "fields": {...}}`. `success: False` is honest: no
        search has run. `prepared: True` says the failure is not a fault — the
        request is built and correct, and the next step belongs to a person,
        because Garvi will not search until a one-time code is SMSed to a real
        handset and typed back in. See `send_otp`.

        Every dropdown code is checked against the page in hand before the body
        is built; an unoffered code is refused rather than submitted.

        WARNING, and it is the one that matters most in a title opinion:
        Garvi's index is keyed on the survey number **as written on the deed at
        registration**, not the number the parcel carries today. Search a
        renumbered parcel under its present number and you get a short, clean,
        WRONG result — no error, just an absence that reads as "no encumbrance".
        The same warning rides back in the returned dict so it cannot be lost on
        the way to whoever reads the result.
        """
        self._page()
        for control, value, label in ((DISTRICT, district, "district"),
                                      (OFFICE, office, "sub-registrar office"),
                                      (VILLAGE, village, "village"),
                                      (PROPERTY_TYPE, property_type, "property type"),
                                      (SEARCH_TYPE, search_type, "search type")):
            refusal = self._check_selection(control, value, label)
            if refusal:
                return refusal

        if not str(search_number).strip():
            return self._refused(
                "input", "No survey / property number was given, so there is "
                         "nothing to search for.")

        if not str(captcha_text).strip():
            return self._refused(
                "captcha",
                "No captcha answer was supplied. Garvi rejects the search without "
                "the code shown in the image; read the image from captcha_url() on "
                "this same session — the guid is tied to the server-side session, "
                "so an answer fetched anywhere else will not match.")

        fields = dict(self.fields)
        fields["__EVENTTARGET"] = ""
        fields["__EVENTARGUMENT"] = ""
        fields[P + SEARCH_MODE] = PROPERTY_SEARCH_MODE
        fields[P + DISTRICT] = str(district)
        fields[P + OFFICE] = str(office)
        fields[P + VILLAGE] = str(village)
        fields[P + PROPERTY_TYPE] = str(property_type)
        fields[P + SEARCH_TYPE] = str(search_type)
        fields[P + SEARCH_NUMBER] = str(search_number).strip()
        fields[P + CAPTCHA_ANSWER] = str(captcha_text).strip()
        fields[P + APPLICANT_NAME] = str(applicant_name)
        fields[P + MOBILE_NUMBER] = str(mobile)
        # The OTP button is deliberately absent from this body. Adding its name
        # is precisely what makes Garvi send the SMS.

        log.info("[garvi] search prepared but NOT sent: district=%s office=%s "
                 "village=%s number=%s", district, office, village, search_number)
        return {
            "success": False,
            "prepared": True,
            "sent": False,
            "blocked_on": "otp",
            "url": self.base_url,
            "fields": fields,
            "otp_control": OTP_CONTROL,
            "captcha_url": self.captcha_url(),
            "error": OTP_STOP_MESSAGE,
            "warning": SURVEY_NUMBER_WARNING,
        }

    # -- the OTP seam -----------------------------------------------------

    def send_otp(self, prepared: Dict[str, Any], *,
                 i_have_the_handset: bool = False) -> Dict[str, Any]:
        """Ask Garvi to SMS a verification code. Refuses unless a person opts in.

        Pressing `ctl00$MainContent$BtnSendOTP` sends a text message to a real
        phone belonging to a real colleague. There is no way to read that code
        from here, so an automated press is not merely useless — it wakes someone
        up for nothing, and repeats of it look like abuse to the portal.

        `i_have_the_handset` is keyword-only and defaults to False, so no
        positional argument can land on it and no default path can reach the
        button. It must be exactly `True`: a truthy string such as "no" is
        rejected, because the whole value of the flag is that a human typed it
        meaning what it says.
        """
        fields = dict((prepared or {}).get("fields") or {})
        mobile = (fields.get(P + MOBILE_NUMBER) or "").strip()
        recipient = mobile or "the mobile number on the form"

        if i_have_the_handset is not True:
            return {
                "success": False, "sent": False, "blocked_on": "otp",
                "error": (
                    f"Refusing to ask Garvi for a verification code. Pressing "
                    f"'{OTP_BUTTON_LABEL}' makes the portal send an SMS one-time "
                    f"code to {recipient} — a real handset belonging to a "
                    f"colleague, which nobody in this process is holding, and the "
                    f"code can only be read off that phone. Nothing has been sent. "
                    f"Pass i_have_the_handset=True only when a person is at that "
                    f"phone, right now, and can read the code back."),
            }

        if (not (prepared or {}).get("prepared")
                or (prepared or {}).get("blocked_on") != "otp"):
            return {
                "success": False, "sent": False, "blocked_on": "validation",
                "error": ("There is no prepared search to attach a verification "
                          "code to. Call prepare_search() first and pass back what "
                          "it returns; its own error says what stopped it."),
            }

        fields["__EVENTTARGET"] = ""
        fields["__EVENTARGUMENT"] = ""
        fields[OTP_CONTROL] = OTP_BUTTON_LABEL

        log.warning("[garvi] sending a one-time code by SMS to %s at the caller's "
                    "explicit request", recipient)
        try:
            self._pace()
            r = self.transport.post(
                self.base_url, data=fields, timeout=self.timeout,
                headers={"Content-Type": "application/x-www-form-urlencoded"})
            self._absorb(r)
        except GarviBlocked as e:
            return {"success": False, "sent": True, "blocked_on": "block",
                    "error": str(e)}

        return {
            "success": True, "sent": True, "blocked_on": "otp-entry",
            "url": self.base_url,
            "captcha_url": self.captcha_url(),
            "message": (f"A one-time code has been sent by SMS to {recipient}. "
                        f"Read it off that handset and complete the search in the "
                        f"page this session is now holding."),
            "warning": SURVEY_NUMBER_WARNING,
        }
