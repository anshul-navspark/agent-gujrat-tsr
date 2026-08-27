"""Browser-free AnyRoR fetch.

AnyRoR's WAF resets the Selenium/Chrome browser (it serves a JS challenge) but
lets plain HTTP requests through. This module walks the ASP.NET WebForms
cascading-postback flow with `requests`, solves the inline base64 captcha with
CaptchaSolver (the local `claude` CLI — no API key), and returns the record
HTML. No Chrome, so the WAF never triggers.

The record HTML is rendered to a PDF with a local headless Chrome (loading a
local file only — never navigating to AnyRoR), so the WAF never triggers there
either. `fetch_record_pdf()` mirrors AnyRoRScraper.fetch_land_record()'s
contract, so it can serve as the primary fetch path with Selenium as fallback.
"""
import base64
import logging
import os
import re
import shutil
import subprocess
import time
from urllib.parse import urljoin

import requests

from anyror.captcha_solver import CaptchaSolver

URL = "https://anyror.gujarat.gov.in/LandRecordRural.aspx"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/150 Safari/537.36")
P = "ctl00$ContentPlaceHolder1$"
RECORD_TYPE_VALUE = "8"  # Integrated Survey No Details

# (connect, read). Short CONNECT so a dead IPv4-or-IPv6 family under NAT64 fails
# fast instead of eating the whole budget (journal 2026-07-31); long READ because
# AnyRoR's final "Get Detail" submit generates the record server-side and can sit
# well past 45s on larger survey histories (Pandatirath 80/1 timed out 3x at 45s
# while every dropdown postback succeeded -- slow record generation, not the WAF).
def _default_connect_timeout(env):
    """Connect timeout in seconds, given an environment mapping.

    A proxied run also pays for the CONNECT tunnel to the residential exit,
    which cold-starts well past 6s before settling (~2s thereafter), so the
    short NAT64 fast-fail budget would kill whole attempts. An explicit
    ANYROR_CONNECT_TIMEOUT always wins.
    """
    explicit = env.get("ANYROR_CONNECT_TIMEOUT", "").strip()
    if explicit:
        return float(explicit)
    return 30.0 if env.get("ANYROR_PROXY", "").strip() else 6.0


CONNECT_TIMEOUT = _default_connect_timeout(os.environ)
STEP_TIMEOUT = (CONNECT_TIMEOUT, float(os.getenv("ANYROR_STEP_TIMEOUT", "45")))
SUBMIT_TIMEOUT = (CONNECT_TIMEOUT, float(os.getenv("ANYROR_SUBMIT_TIMEOUT", "180")))

GUJ_DIGITS = {'0': '૦', '1': '૧', '2': '૨', '3': '૩', '4': '૪',
              '5': '૫', '6': '૬', '7': '૭', '8': '૮', '9': '૯'}


def _to_guj(s):
    return ''.join(GUJ_DIGITS.get(c, c) for c in s)


def _hiddens(html):
    d = {}
    for name, val in re.findall(
            r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', html):
        d[name] = val
    for name in ['__VIEWSTATE', '__VIEWSTATEGENERATOR', '__EVENTVALIDATION',
                 '__VIEWSTATEENCRYPTED', '__LASTFOCUS',
                 'ContentPlaceHolder1_ToolkitScriptManager1_HiddenField']:
        if name not in d:
            m = re.search(r'(?:id|name)="%s"[^>]*value="([^"]*)"' % re.escape(name), html)
            d[name] = m.group(1) if m else ''
    return d


def _options(html, ctl):
    m = re.search(r'id="ContentPlaceHolder1_%s".*?</select>' % ctl, html, re.S)
    if not m:
        return None
    return re.findall(r'<option value="([^"]*)"[^>]*>([^<]*)</option>', m.group(0))


def _match_option(opts, wanted_ascii, wanted_guj=None):
    """Find the option value whose text best matches the wanted name/number."""
    if opts is None:
        return None, None
    needles = [wanted_ascii]
    if wanted_guj:
        needles.append(wanted_guj)
    for value, text in opts:
        if value in ('', '0', '-1'):
            continue
        for n in needles:
            if n and n in text:
                return value, text
    return None, None


class AnyRoRHttpFetcher:
    def __init__(self, logger=None):
        self.log = logger or logging.getLogger("anyror.http_fetch")
        self.captcha = CaptchaSolver(logger=self.log)

    def _session(self):
        s = requests.Session()
        s.headers.update({'User-Agent': UA, 'Referer': URL,
                          'Origin': 'https://anyror.gujarat.gov.in'})
        # Optional egress proxy. AnyRoR's WAF blocks by source IP, so routing the
        # walk through an Indian *residential* proxy survives a local IP burn
        # (journal 2026-08-21). Credentials live in the env, never in the repo.
        # Applies to AnyRoR traffic only -- the captcha solver shells out to a
        # local CLI and makes no HTTP request of its own.
        proxy = os.getenv('ANYROR_PROXY', '').strip()
        if proxy:
            s.proxies.update({'http': proxy, 'https': proxy})
            self.log.info("[http_fetch] routing via ANYROR_PROXY "
                          f"({proxy.rsplit('@', 1)[-1]})")
        return s

    def _postback(self, s, html, target, fields):
        data = dict(_hiddens(html))
        data['__EVENTTARGET'] = target
        data['__EVENTARGUMENT'] = ''
        data.update(fields)
        r = s.post(URL, data=data, timeout=STEP_TIMEOUT,
                   headers={'Content-Type': 'application/x-www-form-urlencoded'})
        if 'Web Page Blocked' in r.text or 'Attack ID' in r.text:
            raise RuntimeError("WAF block page returned on postback")
        return r.text

    def _captcha_from(self, html):
        m = re.search(
            r'id="ContentPlaceHolder1_i_captcha_1"[^>]*src="data:image/[a-z]+;base64,([^"]+)"',
            html)
        if not m:
            return None
        return base64.b64decode(m.group(1))

    def _survey_candidate_texts(self, survey_ascii):
        """Gujarati-digit / paiki variants a survey option text may use.

        AnyRoR keeps the BASE number in Latin digits and renders paiki digits in
        Gujarati, keeping the Latin 'p'. The '/' before 'p' is inconsistent in
        the data itself: survey 24 paiki 1 is "24p૧" (no slash) while 48 paiki 4
        is "48/p૪" (slash) — so try both. The digit 5 is sometimes the letter પ.
        """
        G = str.maketrans("0123456789", "૦૧૨૩૪૫૬૭૮૯")
        GP = str.maketrans("0123456789", "૦૧૨૩૪પ૬૭૮૯")  # 5 rendered as પ
        s = survey_ascii.strip()
        cands = []

        def add(v):
            if v and v not in cands:
                cands.append(v)

        add(s)
        add(s.translate(G))
        add(s.translate(GP))
        # Paiki, one or more levels deep: Miyani 1300 is subdivided twice and
        # the dropdown spells it "1300/p૧/p૧" (journal 2026-08-21). A one-level
        # regex generated no correct candidate for those, so the fetch failed.
        m = re.match(r'^(\d+)((?:\s*/?\s*p(?:k)?\s*\d+)+)$', s, re.I)
        if m:
            base = m.group(1)
            parts = re.findall(r'\d+', m.group(2))
            for sep in ['p', '/p']:                 # both slash + no-slash
                for tr in (G, GP, None):            # ૧ / પ / plain-ASCII digits
                    add(base + ''.join(
                        f"{sep}{p.translate(tr) if tr else p}" for p in parts))
            if len(parts) == 1:                     # spelled-out forms, 1 level
                part = parts[0]
                for sep in [' પૈકી ', ' પેકી ', ' paiki ', '/']:
                    add(f"{base}{sep}{part.translate(G)}")
                    add(f"{base}{sep}{part}")
        m2 = re.match(r'^(\d+)\s*/\s*(\d+)$', s)     # plain N/M subdivision
        if m2:
            b, p = m2.group(1), m2.group(2)
            add(f"{b}/{p.translate(G)}")
            add(f"{b}/{p.translate(GP)}")
        return cands

    def _resolve_district(self, dopts, district):
        """District code for an AnyRoR code, Gujarati name, or ASCII name.

        `ddlDistrict` carries Gujarati text only. Taluka and village get their
        ASCII fallback from the caller passing both spellings, but the district
        has no such pair, so an ASCII name is translated via the hierarchy.
        Returns None when nothing matches.
        """
        wanted = str(district or '').strip()
        if not wanted:
            return None
        live = [(v, t) for v, t in (dopts or []) if v not in ('', '0', '-1')]
        for value, text in live:
            if value == wanted or wanted in text:
                return value
        try:
            from utils.json_translations import translate_to_gujarati
            guj = translate_to_gujarati(wanted, context='district')
        except Exception as e:
            log = getattr(self, 'log', None) or logging.getLogger(__name__)
            log.debug(f"[http_fetch] district translate failed: {e}")
            return None
        for value, text in live:
            if guj and guj in text:
                return value
        return None

    def fetch_record_html(self, district, taluka_ascii, taluka_guj,
                          village_ascii, village_guj, survey_ascii, attempts=None):
        """`district` may be the numeric AnyRoR code (e.g. "14") or a district
        name (ASCII or Gujarati, e.g. "ભાવનગર"); it is resolved against the live
        dropdown. taluka/village accept ASCII and/or Gujarati names."""
        # Default 3, not 10: each attempt is a full 7-request walk, so the old
        # default could fire ~70 requests at 2s spacing and trip AnyRoR's WAF
        # (journal 2026-07-28 and 2026-08-10 both lost an IP that way).
        if attempts is None:
            attempts = int(os.getenv("ANYROR_FETCH_ATTEMPTS", "3"))
        last_err = None
        for attempt in range(1, attempts + 1):
            try:
                self.log.info(f"[http_fetch] attempt {attempt}: "
                              f"{taluka_ascii}/{village_ascii}/{survey_ascii}")
                s = self._session()
                html = s.get(URL, timeout=STEP_TIMEOUT).text
                # resolve district -> code (accept code or ASCII/Gujarati name)
                dopts = _options(html, 'ddlDistrict') or []
                district_code = self._resolve_district(dopts, district)
                if not district_code:
                    raise RuntimeError(f"district '{district}' not found")
                # 1. record type
                html = self._postback(s, html, P + 'drpLandRecord',
                                      {P + 'drpLandRecord': RECORD_TYPE_VALUE})
                # 2. district
                html = self._postback(s, html, P + 'ddlDistrict',
                                      {P + 'drpLandRecord': RECORD_TYPE_VALUE,
                                       P + 'ddlDistrict': district_code})
                # 3. taluka
                tval, ttext = _match_option(_options(html, 'ddlTaluka'),
                                            taluka_ascii, taluka_guj)
                if not tval:
                    raise RuntimeError(f"taluka '{taluka_ascii}' not found")
                base = {P + 'drpLandRecord': RECORD_TYPE_VALUE,
                        P + 'ddlDistrict': district_code, P + 'ddlTaluka': tval}
                html = self._postback(s, html, P + 'ddlTaluka', dict(base))
                # 4. village
                vval, vtext = _match_option(_options(html, 'ddlVillage'),
                                            village_ascii, village_guj)
                if not vval:
                    raise RuntimeError(f"village '{village_ascii}' not found")
                base[P + 'ddlVillage'] = vval
                html = self._postback(s, html, P + 'ddlVillage', dict(base))
                # 5. survey
                sopts = _options(html, 'ddlSurveyNo') or []
                cands = self._survey_candidate_texts(survey_ascii)
                sval = stext = None
                # exact match first
                for cand in cands:
                    for value, text in sopts:
                        if text.strip() == cand:
                            sval, stext = value, text
                            break
                    if sval:
                        break
                # slash-insensitive fallback (AnyRoR's '/p' vs 'p' inconsistency)
                if not sval:
                    norm = lambda x: x.replace('/', '').replace(' ', '')
                    ncands = {norm(c) for c in cands}
                    for value, text in sopts:
                        if norm(text.strip()) in ncands:
                            sval, stext = value, text
                            break
                if not sval:
                    raise RuntimeError(
                        f"survey '{survey_ascii}' not found; options="
                        f"{[t for _, t in (sopts or [])][:20]}")
                base[P + 'ddlSurveyNo'] = sval
                # survey dropdown auto-posts back -> refresh page + captcha
                if 'ddlSurveyNo' in html and '__doPostBack' in html:
                    html = self._postback(s, html, P + 'ddlSurveyNo', dict(base))
                self.log.info(f"[http_fetch] selected taluka={ttext} village={vtext} "
                              f"survey={stext}")
                # 6. captcha (inline) -> claude CLI. solve() RAISES on a bad
                # read (one shot, no internal retry) -- that lands in the
                # except below and retries the whole walk with a fresh
                # session, i.e. a genuinely fresh captcha image.
                cap = self._captcha_from(html)
                if not cap:
                    raise RuntimeError("captcha image not found on final page")
                answer = self.captcha.solve(cap)
                self.log.info(f"[http_fetch] captcha solved -> {answer}")
                # 7. final submit
                data = dict(_hiddens(html))
                data['__EVENTTARGET'] = ''
                data['__EVENTARGUMENT'] = ''
                data.update(base)
                data[P + 'txt_captcha_1'] = answer  # real field name has underscore
                btn = re.search(
                    r'name="(ctl00\$ContentPlaceHolder1\$btnGo)"[^>]*value="([^"]*)"', html)
                if btn:
                    data[btn.group(1)] = btn.group(2)
                else:
                    data[P + 'btnGo'] = 'Get Detail'
                r = s.post(URL, data=data, timeout=SUBMIT_TIMEOUT,
                           headers={'Content-Type': 'application/x-www-form-urlencoded'})
                out = r.text
                if 'Web Page Blocked' in out or 'Attack ID' in out:
                    raise RuntimeError("WAF block on final submit")
                # AnyRoR's wrong-captcha alert: "Capcha is not matched. કેપ્ચા
                # બરાબર નથી ફરીથી ટાઇપ કરો." -> retry with a fresh captcha.
                if ('Capcha is not matched' in out or 'બરાબર નથી' in out
                        or 'not matched' in out.lower()):
                    raise RuntimeError("captcha rejected by AnyRoR (fresh retry)")
                # Captcha accepted -> this is the record response.
                return out, {'taluka': ttext, 'village': vtext, 'survey': stext,
                             'captcha': answer}
            except Exception as e:
                last_err = e
                self.log.warning(f"[http_fetch] attempt {attempt} failed: {e}")
                time.sleep(2)
        raise RuntimeError(f"fetch failed after {attempts} attempts: {last_err}")

    # ------------------------------------------------------------------ PDF ---
    def _find_chrome(self):
        """Locate a Chrome/Chromium binary for local file -> PDF rendering."""
        env = os.getenv('CHROME_BIN')
        if env and os.path.exists(env):
            return env
        for name in ('google-chrome', 'google-chrome-stable', 'chromium',
                     'chromium-browser', 'chrome'):
            p = shutil.which(name)
            if p:
                return p
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/opt/google/chrome/chrome",
        ]
        # Playwright-managed chromium, if present
        pw = os.path.expanduser("~/Library/Caches/ms-playwright")
        if os.path.isdir(pw):
            for root, _dirs, files in os.walk(pw):
                for f in files:
                    if f in ("Google Chrome for Testing", "chrome", "chromium"):
                        candidates.append(os.path.join(root, f))
        for c in candidates:
            if os.path.exists(c):
                return c
        return None

    def _render_pdf(self, record_html, output_path):
        """Inline CSS (fetched via requests), strip scripts, print via Chrome."""
        s = self._session()

        def inline_css(m):
            href = m.group(1)
            try:
                css = s.get(urljoin(URL, href), timeout=20).text
                return f"<style>\n{css}\n</style>"
            except Exception:
                return ""
        html = re.sub(r'<link[^>]*href="([^"]+)"[^>]*rel="stylesheet"[^>]*>',
                      inline_css, record_html)
        html = re.sub(r'<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"[^>]*>',
                      inline_css, html)
        html = re.sub(r'<script.*?</script>', '', html, flags=re.S)
        html = (html.replace('src="../', 'src="https://anyror.gujarat.gov.in/')
                    .replace("src='../", "src='https://anyror.gujarat.gov.in/"))

        chrome = self._find_chrome()
        if not chrome:
            raise RuntimeError("no Chrome/Chromium binary found for PDF rendering "
                               "(set CHROME_BIN)")
        tmp_html = output_path + ".src.html"
        with open(tmp_html, 'w', encoding='utf-8') as fh:
            fh.write(html)
        try:
            subprocess.run(
                [chrome, '--headless=new', '--disable-gpu', '--no-sandbox',
                 '--run-all-compositor-stages-before-draw',
                 '--virtual-time-budget=8000', '--no-pdf-header-footer',
                 f'--print-to-pdf={output_path}', f'file://{tmp_html}'],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=120)
        finally:
            try:
                os.remove(tmp_html)
            except OSError:
                pass
        if not os.path.exists(output_path) or os.path.getsize(output_path) < 1000:
            raise RuntimeError("Chrome produced no/empty PDF")

    def fetch_record_pdf(self, district_name, taluka_name, village_name,
                         survey_block_number, output_path):
        """Browser-free equivalent of AnyRoRScraper.fetch_land_record().

        Names may be Gujarati (as the scraper passes them) or ASCII. Returns
        {'success': True, 'output_path': ...} or {'success': False, 'error': ...}.
        """
        try:
            out_dir = os.path.dirname(output_path)
            if out_dir and not os.path.exists(out_dir):
                os.makedirs(out_dir, exist_ok=True)
            record_html, meta = self.fetch_record_html(
                district_name, taluka_name, taluka_name,
                village_name, village_name, str(survey_block_number).strip())
            self._render_pdf(record_html, output_path)
            self.log.info(f"[http_fetch] saved PDF -> {output_path} ({meta})")
            return {'success': True, 'output_path': output_path,
                    'message': 'Land record fetched via http_fetch'}
        except Exception as e:
            return {'success': False, 'error': f"http_fetch failed: {e}"}
