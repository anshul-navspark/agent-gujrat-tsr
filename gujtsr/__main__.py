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


def main(argv=None) -> int:
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

    p.error(f"unknown command {args.cmd}")


if __name__ == "__main__":
    sys.exit(main())
