"""CLI for the gujtsr core: `python -m gujtsr <command>`.

Every command prints a JSON object on stdout and returns 0 on success, 1 on a
handled failure. Logs go to stderr, so `python -m gujtsr fetch ... | jq` works.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys


def _emit(result: dict) -> int:
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if result.get("success") else 1


def main(argv=None, session_factory=None) -> int:
    p = argparse.ArgumentParser(
        prog="gujtsr",
        description="Gujarat land records: fetch, read, and render a TSR.")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging to stderr")
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="fetch a land-record PDF from AnyRoR")
    f.add_argument("--district", required=True, help="English or Gujarati")
    f.add_argument("--taluka", required=True)
    f.add_argument("--village", required=True)
    f.add_argument("--survey", required=True, help="e.g. 44, 150/p1, 1300/p1/p2")
    f.add_argument("--out-dir", default="output")
    f.add_argument("--filename", default=None)

    t = sub.add_parser("text", help="extract the text layer from a PDF")
    t.add_argument("pdf")

    g = sub.add_parser(
        "garvi",
        help="Gujarat Sub-Registrar property search: prepare it, stop at the OTP")
    g.add_argument("--district", required=True, help="Garvi district code")
    g.add_argument("--office", required=True, help="sub-registrar office code")
    g.add_argument("--village", required=True, help="Index2 village code")
    g.add_argument("--property-type", required=True, help="1=agriculture")
    g.add_argument("--search-type", required=True, help="3=survey number")
    g.add_argument("--number", required=True, help="the survey number AS REGISTERED")
    g.add_argument("--applicant-name", default="")
    g.add_argument("--mobile", default="", help="where Garvi would text the code")
    # There is deliberately no flag here that can send an OTP. Doing so texts a
    # colleague's handset, and nothing on this path can read the code back.

    r = sub.add_parser("render", help="render extraction JSON into a TSR .docx")
    r.add_argument("extraction_json", help="path, or - for stdin")
    r.add_argument("--output", required=True)
    r.add_argument("--client", default=None, help="client id from clients.json")

    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)

    if args.cmd == "fetch":
        from gujtsr.fetch import fetch_record
        return _emit(fetch_record(args.district, args.taluka, args.village,
                                  args.survey, args.out_dir, args.filename))

    if args.cmd == "text":
        from gujtsr.text import extract_text
        return _emit(extract_text(args.pdf))

    if args.cmd == "render":
        from gujtsr.render import render_tsr
        raw = sys.stdin.read() if args.extraction_json == "-" \
            else open(args.extraction_json, encoding="utf-8").read()
        try:
            extraction = json.loads(raw)
        except json.JSONDecodeError as e:
            return _emit({"success": False, "error": f"extraction JSON is not valid: {e}"})
        return _emit(render_tsr(extraction, args.output, client=args.client))

    if args.cmd == "garvi":
        return _emit(_garvi(args, session_factory))

    p.error(f"unknown command {args.cmd}")


def _garvi(args, session_factory=None) -> dict:
    """Drive the cascade, let the model read the captcha, stop before the OTP.

    The captcha is NOT asked of a human: `captcha_text` is left None, which is
    what routes the image to Opus through the solver. A captcha is a throwaway
    five characters on a public form. The OTP is the real boundary, because it
    spends an SMS on a handset nobody running this is holding.
    """
    from anyror.captcha_solver import CaptchaError
    from gujtsr.garvi import GarviBlocked, GarviCaptchaUnavailable, GarviSession

    session = (session_factory or GarviSession)()
    try:
        return session.prepare_search(
            district=args.district, office=args.office, village=args.village,
            property_type=args.property_type, search_type=args.search_type,
            search_number=args.number, captcha_text=None,
            applicant_name=args.applicant_name, mobile=args.mobile,
        )
    except GarviBlocked as e:
        return {"success": False, "prepared": False, "sent": False,
                "blocked_on": "portal", "error": str(e)}
    except CaptchaError as e:
        return {"success": False, "prepared": False, "sent": False,
                "blocked_on": "captcha",
                "error": (f"The captcha could not be read: {e} Nothing was "
                          f"submitted. Re-run to get a fresh image; do not "
                          f"guess an answer, a wrong one spends a request "
                          f"against the firm's one office IP.")}
    except GarviCaptchaUnavailable as e:
        return {"success": False, "prepared": False, "sent": False,
                "blocked_on": "captcha", "error": str(e)}


if __name__ == "__main__":
    sys.exit(main())
