"""Fetch a Gujarat land record as a PDF.

Thin wrapper over the tested AnyRoRHttpFetcher. Everything hard-won about talking
to AnyRoR lives there and in references/anyror-operations.md; this module owns
input normalisation and result shaping.

The normalisation is not optional. AnyRoR's dropdowns carry **Gujarati text only**,
and `fetch_record_pdf` passes the taluka/village names it is given as *both* the
ASCII and the Gujarati spelling — so handing it "Talaja" matches nothing and burns
a session per attempt. The production API path translates before it calls; so must
we. (District is the exception: `_resolve_district` has its own translator
fallback. Taluka and village do not.)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

log = logging.getLogger(__name__)


def _to_gujarati(name: str, context: str, parent_district: str | None = None,
                 parent_taluka: str | None = None) -> tuple[str | None, Dict[str, Any] | None]:
    """Translate one place name, or return an error dict a lawyer can act on.

    Always pass the parents you have. Village names are NOT unique across Gujarat
    — an unscoped "Bodki" and "Bodkee" resolve to two different villages (codes
    094 and 040). Resolving a village without its district and taluka is how you
    silently fetch the wrong land record.
    """
    from utils.json_translations import translate_to_gujarati, TranslationNotFoundError

    try:
        return translate_to_gujarati(name, context=context,
                                     parent_district=parent_district,
                                     parent_taluka=parent_taluka), None
    except TranslationNotFoundError as e:
        err: Dict[str, Any] = {
            "success": False,
            "error": f"{context} '{name}' was not found in the AnyRoR hierarchy.",
        }
        if getattr(e, "suggestions", None):
            err["did_you_mean"] = list(e.suggestions)
            err["error"] += " Closest matches: " + ", ".join(map(str, e.suggestions))
        return None, err
    except Exception as e:
        return None, {"success": False,
                      "error": f"could not translate {context} '{name}': {e}"}


def fetch_record(district: str, taluka: str, village: str, survey: str,
                 out_dir: str = "output", filename: str | None = None) -> Dict[str, Any]:
    """Fetch one land record. Returns a JSON-shaped dict; expected failures (bad
    name, WAF block, captcha miss) come back as {'success': False, 'error': ...}
    rather than raising, because the caller is a skill reporting to a lawyer.

    Place names may be given in English or Gujarati. The survey number stays ASCII:
    `_survey_candidate_texts` generates the Gujarati-digit and paiki spellings
    itself, including nested forms like 1300/p1/p2.
    """
    from anyror.http_fetch import AnyRoRHttpFetcher

    if not os.getenv("ANYROR_PROXY", "").strip():
        # Not fatal — a fresh residential IP works too — but it is nearly always
        # the reason a fetch fails, so say it up front rather than after a block.
        log.warning("ANYROR_PROXY is not set; AnyRoR blocks datacenter and "
                    "previously-burned IPs. Expect a WAF page.")

    # Resolve outermost-first: the hierarchy scopes children by their parents'
    # GUJARATI names, so each step feeds the next. Skipping this is how an
    # unscoped village name picks the wrong one of several identically-named
    # villages, and returns a valid-looking PDF for the wrong land.
    district_guj, err = _to_gujarati(district, "district")
    if err:
        return err
    taluka_guj, err = _to_gujarati(taluka, "taluka", parent_district=district_guj)
    if err:
        return err
    village_guj, err = _to_gujarati(village, "village", parent_district=district_guj,
                                    parent_taluka=taluka_guj)
    if err:
        return err

    safe = str(survey).replace("/", "_").strip()
    name = filename or f"Survey No.{safe}.pdf"
    output_path = os.path.join(out_dir, name)

    fetcher = AnyRoRHttpFetcher(logger=log)
    result = fetcher.fetch_record_pdf(district_guj, taluka_guj, village_guj,
                                      str(survey).strip(), output_path)

    if result.get("success"):
        path = result["output_path"]
        result["size_bytes"] = os.path.getsize(path) if os.path.exists(path) else 0
    result["request"] = {"district": district, "taluka": taluka,
                         "village": village, "survey": survey,
                         "resolved": {"district": district_guj, "taluka": taluka_guj,
                                      "village": village_guj}}
    return result
