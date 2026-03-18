#!/usr/bin/env python3
"""
Find "not related to present survey" entries in manual TSR documents
and check whether they are missing from the corresponding AI versions.
"""

import os
import re
import sys
from docx import Document
from collections import defaultdict

MANUAL_DIR = "/Users/anshulgoyal/work/gujrat_tsr_agent/Final TSR Sample/"
AI_DIR = "/Users/anshulgoyal/work/gujrat_tsr_agent/Final AI TSR Sample/"

# Patterns to match "not related" style entries (case-insensitive)
PATTERNS = [
    re.compile(r"not\s+related\s+to\s+present\s+survey", re.IGNORECASE),
    re.compile(r"not\s+related\s+to\s+the\s+present\s+survey", re.IGNORECASE),
    re.compile(r"not\s+concern", re.IGNORECASE),
    re.compile(r"does\s+not\s+relate", re.IGNORECASE),
    re.compile(r"does\s+not\s+concern", re.IGNORECASE),
    re.compile(r"not\s+pertaining", re.IGNORECASE),
    re.compile(r"not\s+relevant\s+to", re.IGNORECASE),
    re.compile(r"no\s+concern\s+with", re.IGNORECASE),
    re.compile(r"is\s+not\s+related", re.IGNORECASE),
    re.compile(r"are\s+not\s+related", re.IGNORECASE),
    re.compile(r"entry.*not.*present\s+survey", re.IGNORECASE),
    re.compile(r"entry.*not.*survey\s+number", re.IGNORECASE),
    re.compile(r"entry.*not.*survey\s+no", re.IGNORECASE),
]


def get_chain_of_title_table(doc):
    """Get Table 2 (0-indexed) which is the chain of title table."""
    if len(doc.tables) < 3:
        return None
    return doc.tables[2]


def get_full_row_text(row):
    """Combine all cell texts in a row."""
    return " ".join(cell.text.strip() for cell in row.cells).strip()


def matches_pattern(text):
    """Check if text matches any 'not related' pattern. Return the matched pattern."""
    for pat in PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(0)
    return None


def extract_entry_number(text):
    """Extract entry number from text like 'Entry No. 448 ...'"""
    m = re.search(r"Entry\s+No\.?\s*(\d+)", text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def check_ai_version(ai_filepath, entry_number, entry_text_snippet):
    """Check if the entry exists in the AI version."""
    if not os.path.exists(ai_filepath):
        return "AI FILE NOT FOUND"

    try:
        doc = Document(ai_filepath)
        table = get_chain_of_title_table(doc)
        if table is None:
            return "NO CHAIN-OF-TITLE TABLE IN AI"

        for row in table.rows:
            row_text = get_full_row_text(row)
            if entry_number and f"Entry No. {entry_number}" in row_text:
                return f"FOUND IN AI: {row_text[:120]}..."
            if entry_number and re.search(rf"Entry\s+No\.?\s*{entry_number}\b", row_text):
                return f"FOUND IN AI: {row_text[:120]}..."

        return "MISSING FROM AI (confirmed)"
    except Exception as e:
        return f"AI CHECK ERROR: {e}"


def main():
    manual_files = sorted([
        f for f in os.listdir(MANUAL_DIR) if f.endswith(".docx") and not f.startswith("~")
    ])

    print(f"Scanning {len(manual_files)} manual TSR files...\n")

    # Collect all matches grouped by pattern
    results_by_pattern = defaultdict(list)
    all_results = []
    errors = []

    for filename in manual_files:
        filepath = os.path.join(MANUAL_DIR, filename)
        try:
            doc = Document(filepath)
            table = get_chain_of_title_table(doc)
            if table is None:
                continue

            for row_idx, row in enumerate(table.rows):
                text = get_full_row_text(row)
                matched = matches_pattern(text)
                if matched:
                    entry_num = extract_entry_number(text)

                    # Build AI filename
                    ai_filename = "AI_" + filename
                    ai_filepath = os.path.join(AI_DIR, ai_filename)
                    ai_status = check_ai_version(ai_filepath, entry_num, text)

                    result = {
                        "filename": filename,
                        "row": row_idx,
                        "entry_num": entry_num,
                        "text": text,
                        "matched_phrase": matched.lower(),
                        "ai_status": ai_status,
                    }
                    pattern_key = matched.lower().strip()
                    results_by_pattern[pattern_key].append(result)
                    all_results.append(result)
        except Exception as e:
            errors.append((filename, str(e)))

    # Print results
    print("=" * 100)
    print(f"TOTAL MATCHES FOUND: {len(all_results)}")
    print(f"FILES WITH ERRORS: {len(errors)}")
    print("=" * 100)

    if errors:
        print("\nERRORS:")
        for fn, err in errors:
            print(f"  {fn}: {err}")

    # Group by pattern
    print(f"\n{'=' * 100}")
    print("RESULTS GROUPED BY PATTERN")
    print("=" * 100)

    count = 0
    for pattern, entries in sorted(results_by_pattern.items(), key=lambda x: -len(x[1])):
        print(f"\n{'─' * 100}")
        print(f"PATTERN: \"{pattern}\" ({len(entries)} matches)")
        print("─" * 100)

        for entry in entries:
            if count >= 30:
                print("\n... (truncated at 30 examples)")
                break
            count += 1

            print(f"\n  [{count}] File: {entry['filename']}")
            print(f"      Survey No: {entry['filename'].split('S.No.')[1].split('-')[0].strip() if 'S.No.' in entry['filename'] else '?'}")
            print(f"      Row: {entry['row']}")
            print(f"      Entry No: {entry['entry_num'] or 'N/A'}")
            print(f"      Full Text:")
            # Word-wrap the text for readability
            text = entry["text"]
            for i in range(0, len(text), 120):
                prefix = "        " if i > 0 else "        "
                print(f"{prefix}{text[i:i+120]}")
            print(f"      AI Status: {entry['ai_status']}")

        if count >= 30:
            break

    # Summary
    print(f"\n{'=' * 100}")
    print("SUMMARY")
    print("=" * 100)
    missing_count = sum(1 for r in all_results if "MISSING" in r["ai_status"])
    found_count = sum(1 for r in all_results if "FOUND IN AI" in r["ai_status"])
    print(f"  Total 'not related' entries in manual TSRs: {len(all_results)}")
    print(f"  Confirmed MISSING from AI versions: {missing_count}")
    print(f"  Found in AI versions: {found_count}")
    print(f"  Other (file not found, errors): {len(all_results) - missing_count - found_count}")

    # List unique survey numbers with these entries
    survey_nums = sorted(set(r["filename"] for r in all_results))
    print(f"\n  Files containing 'not related' entries ({len(survey_nums)}):")
    for sn in survey_nums:
        count_in_file = sum(1 for r in all_results if r["filename"] == sn)
        print(f"    - {sn} ({count_in_file} entries)")


if __name__ == "__main__":
    main()
