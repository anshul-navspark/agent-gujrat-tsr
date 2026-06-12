#!/usr/bin/env python3
"""
Generate a human-readable ledger of locally-cached (generated) TSRs.

Scans the local cache directory that ``services.cache_service.LocalCacheService``
writes to and emits a markdown table: survey, location, cached date, freshness,
DOCX path/size, and a manual "Diff vs truth / Notes" column.

The facts (survey / location / date / path / size) are auto-filled from each
entry's ``metadata.json`` on every run. Manual notes live in a sidecar JSON
(``docs/tsr_ledger_notes.json``), keyed by the short cache key, and are preserved
across refreshes — so you can record diff-vs-handtyped-truth outcomes once and
not lose them when the ledger is regenerated.

Usage:
    python scripts/tsr_ledger.py            # (re)write docs/tsr_ledger.md
    python scripts/tsr_ledger.py --out -    # print to stdout instead
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_CACHE_DIR = os.path.join(Path.home(), ".cache", "gujrat_tsr_agent", "cache")
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "docs" / "tsr_ledger.md"
DEFAULT_NOTES = REPO_ROOT / "docs" / "tsr_ledger_notes.json"


def _fmt_size(n: int) -> str:
    if not n:
        return "-"
    kb = n / 1024
    return f"{kb:.0f} KB" if kb < 1024 else f"{kb / 1024:.1f} MB"


def _display_path(path: str) -> str:
    home = str(Path.home())
    return "~" + path[len(home):] if path.startswith(home) else path


def load_entries(cache_dir: str):
    entries = []
    if not os.path.isdir(cache_dir):
        return entries
    for key in os.listdir(cache_dir):
        meta_path = os.path.join(cache_dir, key, "metadata.json")
        if not os.path.isfile(meta_path):
            continue
        try:
            with open(meta_path, encoding="utf-8") as f:
                m = json.load(f)
        except Exception:
            continue
        docx = os.path.join(cache_dir, key, "tsr.docx")
        has_docx = os.path.isfile(docx)
        entries.append({
            "key": key,
            "survey": m.get("survey_number", "?"),
            "district": m.get("original_district") or m.get("district") or m.get("translated_district") or "?",
            "taluka": m.get("original_taluka") or m.get("taluka") or m.get("translated_taluka") or "?",
            "village": m.get("original_village") or m.get("village") or m.get("translated_village") or "?",
            "timestamp": m.get("timestamp", ""),
            "docx_path": docx if has_docx else None,
            "docx_size": os.path.getsize(docx) if has_docx else 0,
        })
    return entries


def render(entries, notes, cache_dir, ttl_days):
    now = datetime.now(timezone.utc)
    entries.sort(key=lambda e: e["timestamp"], reverse=True)

    rows, fresh = [], 0
    for i, e in enumerate(entries, 1):
        date_str, status = "?", "?"
        try:
            t = datetime.fromisoformat(e["timestamp"])
            date_str = t.date().isoformat()
            if now < t + timedelta(days=ttl_days):
                status, fresh = "✅ fresh", fresh + 1
            else:
                status = "⏳ expired"
        except Exception:
            pass
        loc = f"{e['district']} / {e['taluka']} / {e['village']}"
        if e["docx_path"]:
            docx = f"`{_display_path(e['docx_path'])}` ({_fmt_size(e['docx_size'])})"
        else:
            docx = "_(missing)_"
        note = notes.get(e["key"][:8]) or notes.get(e["key"], "")
        rows.append((i, e["survey"], loc, date_str, status, e["key"][:8], docx, note))

    out = [
        "# TSR Ledger — locally generated TSRs",
        "",
        f"_Auto-generated from the local cache (`{_display_path(cache_dir)}`) by "
        f"`scripts/tsr_ledger.py`. Refresh with `python scripts/tsr_ledger.py`._",
        "",
        f"**{len(entries)} cached TSR(s)** — {fresh} fresh, {len(entries) - fresh} expired "
        f"(TTL {ttl_days}d). Generated {now.date().isoformat()}.",
        "",
        "Notes in the last column survive refreshes via `docs/tsr_ledger_notes.json` "
        "(map of short cache key → note). Record diff-vs-handtyped-truth outcomes there.",
        "",
        "| # | Survey | District / Taluka / Village | Cached | Status | Key | DOCX | Diff vs truth / Notes |",
        "|---|--------|------------------------------|--------|--------|-----|------|------------------------|",
    ]
    for r in rows:
        out.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | `{r[5]}` | {r[6]} | {r[7]} |")
    out.append("")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Generate the local TSR cache ledger.")
    ap.add_argument("--cache-dir", default=os.getenv("LOCAL_CACHE_DIR", DEFAULT_CACHE_DIR))
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output markdown path, or - for stdout")
    ap.add_argument("--notes", default=str(DEFAULT_NOTES), help="sidecar JSON of manual notes")
    ap.add_argument("--ttl-days", type=int, default=int(os.getenv("LOCAL_CACHE_TTL_DAYS", "36500")),
                    help="TTL used only to label fresh/expired in the table")
    args = ap.parse_args()

    notes = {}
    if os.path.isfile(args.notes):
        try:
            with open(args.notes, encoding="utf-8") as f:
                notes = json.load(f)
        except Exception:
            print(f"warning: could not parse {args.notes}; ignoring notes", file=sys.stderr)

    entries = load_entries(args.cache_dir)
    md = render(entries, notes, args.cache_dir, args.ttl_days)

    if args.out == "-":
        sys.stdout.write(md)
    else:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md)
        fresh = md.count("✅")
        print(f"Wrote {args.out}: {len(entries)} entries ({fresh} fresh).")


if __name__ == "__main__":
    main()
