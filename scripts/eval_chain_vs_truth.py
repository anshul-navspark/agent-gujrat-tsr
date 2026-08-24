#!/usr/bin/env python3
"""Phase 0 measurement harness for the old-entry (pre-digital) chain project.

Compares, per survey:

  * the AUTHORITATIVE entry set  -- AnyRoR's "Entry Details" index in the source
    record PDF. This is the checksum: every entry that must appear in the chain,
    and nothing else.
  * the DELIVERED chain          -- the lawyer's hand-finished TSR .docx.

and reports:

  * phantom entries   (in the TSR, absent from AnyRoR's index)
  * missing entries   (in AnyRoR's index, absent from the TSR)
  * index-only ratio  (entries AnyRoR lists but publishes no narrative for --
                       the ones transcribed by hand today)
  * pre/post-1993 mix (external cross-fill via the Sub-Registrar's Index-2 only
                       reaches back to 1993, so this split bounds how much of
                       the manual work is actually automatable)

No LLM calls and no network: this is pure parsing, so it is cheap to re-run as a
regression gate after every later phase.

Usage:
    python scripts/eval_chain_vs_truth.py --pdf-dir DIR --docx-dir DIR [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field, asdict

try:
    import fitz  # PyMuPDF
    from docx import Document
except ImportError as exc:  # pragma: no cover - environment guard
    sys.exit(f"missing dependency: {exc}. Run inside the project venv.")


# The Sub-Registrar's Index-2 search (the only cross-source with an independent
# chain of custody) covers ~31 years. Entries older than this have no external
# corroboration available -- see docs/journal.md, 2026-08-01.
CROSS_FILL_CUTOFF_YEAR = 1993


def normalize_survey(name: str) -> str:
    """Map a filename to a comparable survey key.

    'Form' filenames vary a lot by hand: '44-p1 - complete final.docx',
    '45-4p2 - complete Final.docx', '57p1 - complete fina;.docx'.
    """
    stem = os.path.splitext(os.path.basename(name))[0]
    # drop a trailing ' - complete final' / ' - Final' / ' -TSR' style suffix
    stem = re.split(r"\s+-\s*(?:complete|final|tsr)\b", stem, flags=re.I)[0]
    # generated files are 'Original_<district>_<taluka>_<village>_<survey>' /
    # 'TSR_<...>_<survey>'; the survey is the last underscore-separated token
    if "_" in stem:
        stem = stem.rsplit("_", 1)[-1]
    stem = re.sub(r"[-\s.,;]+", "", stem)
    return stem.lower()


@dataclass
class SurveyReport:
    survey: str
    pdf: str = ""
    docx: str = ""
    index_entries: list = field(default_factory=list)      # authoritative
    detailed_entries: list = field(default_factory=list)   # have a narrative
    index_only_entries: list = field(default_factory=list) # hand-typed today
    tsr_entries: list = field(default_factory=list)
    phantom: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    starred: list = field(default_factory=list)
    entry_years: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)


def extract_entry_index(text: str) -> tuple[list, list]:
    """Parse AnyRoR's authoritative 'Entry Details' index -> (entries, starred).

    The index is a run of bare numbers immediately after the heading, ending at
    the Gujarati column headers. AnyRoR marks some entries with a trailing '*';
    keep the number and record the flag separately.
    """
    marker = text.find("Entry Details")
    if marker < 0:
        return [], []
    entries: list = []
    starred: list = []
    for line in text[marker + len("Entry Details"):].splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.fullmatch(r"(\d+)(\*?)", line)
        if not match:
            break
        entries.append(match.group(1))
        if match.group(2):
            starred.append(match.group(1))
    return entries, starred


def extract_detail_rows(text: str) -> tuple[list, dict]:
    """Entries that carry a narrative -> (entry_numbers, {entry: year}).

    A detail row starts with the entry number followed by its date, e.g.
    '446\\n09/10/2006'.
    """
    detailed, years = [], {}
    for num, date in re.findall(r"^(\d+)\n(\d{2}/\d{2}/\d{4})", text, re.M):
        if num not in detailed:
            detailed.append(num)
            years[num] = int(date.split("/")[-1])
    return detailed, years


def parse_source_pdf(path: str) -> tuple[list, list, dict, list]:
    """Return (index_entries, detailed_entries, {entry: year}, starred)."""
    with fitz.open(path) as doc:
        text = "\n".join(page.get_text() for page in doc)
    index_entries, starred = extract_entry_index(text)
    detailed, years = extract_detail_rows(text)
    return index_entries, detailed, years, starred


def parse_delivered_docx(path: str) -> tuple[list, dict]:
    """Return (entry_numbers, {entry: year}) from the chain-of-title table."""
    doc = Document(path)
    entries, years = [], {}
    for table in doc.tables:
        cells = [r.cells[-1].text for r in table.rows]
        if not any("Entry No." in c for c in cells):
            continue
        for cell in cells:
            for match in re.finditer(r"Entry No\.\s*(\d+)", cell):
                num = match.group(1)
                if num not in entries:
                    entries.append(num)
                date = re.search(
                    r"Entry No\.\s*%s\b.{0,40}?(\d{2}/\d{2}/(\d{4}))" % num, cell, re.S
                )
                if date:
                    years.setdefault(num, int(date.group(2)))
        break  # chain of title is the first table containing entries
    return entries, years


def build_report(pdf_dir: str, docx_dir: str) -> list:
    pdfs, docxs = {}, {}
    for f in sorted(os.listdir(pdf_dir)):
        if f.lower().endswith(".pdf"):
            pdfs[normalize_survey(f)] = os.path.join(pdf_dir, f)
    for f in sorted(os.listdir(docx_dir)):
        if f.lower().endswith(".docx") and not f.startswith("~$"):
            docxs.setdefault(normalize_survey(f), os.path.join(docx_dir, f))

    reports = []
    for key in sorted(set(pdfs) & set(docxs)):
        rep = SurveyReport(survey=key, pdf=pdfs[key], docx=docxs[key])
        idx, detailed, pdf_years, starred = parse_source_pdf(pdfs[key])
        tsr_entries, docx_years = parse_delivered_docx(docxs[key])

        rep.index_entries = idx
        rep.detailed_entries = detailed
        rep.index_only_entries = [e for e in idx if e not in detailed]
        rep.tsr_entries = tsr_entries
        rep.phantom = [e for e in tsr_entries if e not in idx]
        rep.missing = [e for e in idx if e not in tsr_entries]
        rep.starred = starred
        rep.entry_years = {**docx_years, **pdf_years}
        if starred:
            rep.notes.append("starred in index: " + ",".join(starred))
        if not idx:
            rep.notes.append("no Entry Details index found in source PDF")
        reports.append(rep)

    for key in sorted(set(docxs) - set(pdfs)):
        rep = SurveyReport(survey=key, docx=docxs[key])
        rep.tsr_entries, rep.entry_years = parse_delivered_docx(docxs[key])
        rep.notes.append("no source PDF available - not checkable")
        reports.append(rep)
    return reports


def summarize(reports: list) -> dict:
    checkable = [r for r in reports if r.index_entries]
    tot_index = sum(len(r.index_entries) for r in checkable)
    tot_detail = sum(len(r.detailed_entries) for r in checkable)
    tot_only = sum(len(r.index_only_entries) for r in checkable)
    phantom = sum(len(r.phantom) for r in checkable)
    missing = sum(len(r.missing) for r in checkable)

    era = Counter()
    for r in reports:
        for entry, year in r.entry_years.items():
            era["pre_1993" if year < CROSS_FILL_CUTOFF_YEAR else "post_1993"] += 1
    dated = era["pre_1993"] + era["post_1993"]
    return {
        "surveys_checkable": len(checkable),
        "surveys_total": len(reports),
        "entries_authoritative": tot_index,
        "entries_with_narrative": tot_detail,
        "entries_index_only": tot_only,
        "index_only_pct": round(100 * tot_only / tot_index, 1) if tot_index else 0.0,
        "phantom_entries": phantom,
        "missing_entries": missing,
        "dated_entries": dated,
        "pre_1993": era["pre_1993"],
        "post_1993": era["post_1993"],
        "pre_1993_pct": round(100 * era["pre_1993"] / dated, 1) if dated else 0.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf-dir", required=True, help="dir of source AnyRoR record PDFs")
    ap.add_argument("--docx-dir", required=True, help="dir of delivered TSR .docx files")
    ap.add_argument("--json", help="also write the full report as JSON here")
    args = ap.parse_args()

    reports = build_report(args.pdf_dir, args.docx_dir)
    if not reports:
        print("no matching survey pairs found", file=sys.stderr)
        return 1

    print(f"{'survey':10s} {'idx':>4s} {'narr':>5s} {'only':>5s} {'tsr':>4s}  "
          f"{'phantom':<18s} {'missing':<12s} note")
    print("-" * 92)
    for r in reports:
        print(f"{r.survey:10s} {len(r.index_entries):4d} {len(r.detailed_entries):5d} "
              f"{len(r.index_only_entries):5d} {len(r.tsr_entries):4d}  "
              f"{','.join(r.phantom) or '-':<18s} {','.join(r.missing) or '-':<12s} "
              f"{'; '.join(r.notes)}")

    s = summarize(reports)
    print()
    print("=" * 92)
    print(f"surveys checked            : {s['surveys_checkable']} of {s['surveys_total']}")
    print(f"authoritative entries      : {s['entries_authoritative']}")
    print(f"  with narrative on AnyRoR : {s['entries_with_narrative']}")
    print(f"  INDEX-ONLY (hand-typed)  : {s['entries_index_only']}  ({s['index_only_pct']}%)")
    print(f"phantom entries in TSRs    : {s['phantom_entries']}")
    print(f"missing entries in TSRs    : {s['missing_entries']}")
    print()
    print(f"dated entries              : {s['dated_entries']}")
    print(f"  pre-{CROSS_FILL_CUTOFF_YEAR} (no cross-fill)   : {s['pre_1993']}  ({s['pre_1993_pct']}%)")
    print(f"  post-{CROSS_FILL_CUTOFF_YEAR} (cross-fillable) : {s['post_1993']}")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump({"summary": s, "surveys": [asdict(r) for r in reports]},
                      fh, indent=2, ensure_ascii=False)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
