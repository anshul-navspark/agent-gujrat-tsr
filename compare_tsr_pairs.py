#!/usr/bin/env python3
"""
Compare 5 TSR document pairs (manual vs AI) across 7 specific dimensions.
"""

import re
from docx import Document
from docx.oxml.ns import qn

BASE_MANUAL = "/Users/anshulgoyal/work/gujrat_tsr_agent/Final TSR Sample"
BASE_AI = "/Users/anshulgoyal/work/gujrat_tsr_agent/Final AI TSR Sample"

PAIRS = [
    ("979", "S.No. 979 - Final.docx", "AI_S.No. 979 - Final.docx"),
    ("982", "S.No. 982 - Final.docx", "AI_S.No. 982 - Final.docx"),
    ("1043", "S.No. 1043 - Final.docx", "AI_S.No. 1043 - Final.docx"),
    ("1099", "S.No. 1099 - Complete Final.docx", "AI_S.No. 1099 - Complete Final.docx"),
    ("1259", "S.No. 1259 - Complete final.docx", "AI_S.No. 1259 - Complete final.docx"),
]

def extract_all_text(doc):
    """Extract all paragraphs with their text."""
    return [p.text.strip() for p in doc.paragraphs if p.text.strip()]

def extract_all_tables(doc):
    """Extract all tables as list of list of lists (table -> row -> cell text)."""
    tables = []
    for table in doc.tables:
        rows = []
        for row in table.rows:
            cells = []
            for cell in row.cells:
                cells.append(cell.text.strip())
            rows.append(cells)
        tables.append(rows)
    return tables

def extract_nested_tables(doc):
    """Extract tables including nested ones from XML."""
    all_tables = []
    for tbl in doc.element.body.iter(qn('w:tbl')):
        rows = []
        for tr in tbl.findall(qn('w:tr')):
            cells = []
            for tc in tr.findall(qn('w:tc')):
                text_parts = []
                for p in tc.findall(qn('w:p')):
                    run_texts = []
                    for r in p.findall(qn('w:r')):
                        t = r.find(qn('w:t'))
                        if t is not None and t.text:
                            run_texts.append(t.text)
                    text_parts.append(''.join(run_texts))
                cells.append('\n'.join(text_parts).strip())
            rows.append(cells)
        all_tables.append(rows)
    return all_tables

def find_section_headers(paragraphs):
    """Find paragraphs that look like section headers."""
    headers = []
    for p in paragraphs:
        # Look for numbered or title-like headers
        if any(kw in p.lower() for kw in ['title search report', 'chain of title',
              'observations', 'schedule of property', 'encumbrance', 'certificate',
              'details of property', 'search report']):
            headers.append(p)
        # Also catch numbered headers like "1.", "2.", etc.
        if re.match(r'^\d+[\.\)]\s', p):
            headers.append(p)
    return headers

def find_chain_of_title_table(tables):
    """Find the chain of title table (usually has columns like SN, Entry No, etc.)."""
    for i, table in enumerate(tables):
        for row in table[:3]:  # Check first 3 rows
            row_text = ' '.join(row).lower()
            if 'entry' in row_text and ('particulars' in row_text or 'details' in row_text or 'nature' in row_text):
                return i, table
            if 'sl' in row_text and 'entry' in row_text:
                return i, table
    return None, None

def find_observations_table(tables):
    """Find the observations table."""
    for i, table in enumerate(tables):
        for row in table[:3]:
            row_text = ' '.join(row).lower()
            if 'observation' in row_text or ('sr' in row_text and 'particulars' in row_text):
                return i, table
            # Also check for the specific observation patterns
            if any('encumbrance' in c.lower() for c in row):
                return i, table
    return None, None

def find_release_entries(table):
    """Find rows mentioning release/charge removal in chain of title."""
    entries = []
    for row in table:
        row_text = ' '.join(row).lower()
        if 'release' in row_text or 'charge' in row_text or 'satisfaction' in row_text or 'no due' in row_text:
            entries.append(row)
    return entries

def find_inheritance_entries(table):
    """Find rows mentioning inheritance/succession/mutation."""
    entries = []
    for row in table:
        row_text = ' '.join(row).lower()
        if any(kw in row_text for kw in ['inheritance', 'succession', 'mutation', 'death', 'heirship', 'khata', 'legal heir']):
            entries.append(row)
    return entries

def find_promulgation_entries(table):
    """Find promulgation / notification / gazette entries."""
    entries = []
    for row in table:
        row_text = ' '.join(row).lower()
        if any(kw in row_text for kw in ['promulgation', 'notification', 'gazette', 'entry 4672', '4672', 'town planning', 'layout', 'bda', 'conversion']):
            entries.append(row)
    return entries

def find_note_row(table):
    """Find the Note row at the end of chain of title."""
    notes = []
    for row in table:
        row_text = ' '.join(row).lower()
        if 'note' in row_text:
            notes.append(row)
    return notes

def analyze_formatting(text):
    """Analyze formatting patterns in text."""
    patterns = {}
    # Dash types
    if '–' in text:
        patterns['en_dash'] = True
    if '--' in text:
        patterns['double_hyphen'] = True
    if '—' in text:
        patterns['em_dash'] = True
    # Date formats
    dates_4digit = re.findall(r'\d{1,2}[./-]\d{1,2}[./-]\d{4}', text)
    dates_2digit = re.findall(r'\d{1,2}[./-]\d{1,2}[./-]\d{2}(?!\d)', text)
    if dates_4digit:
        patterns['dates_4digit'] = dates_4digit[:5]
    if dates_2digit:
        patterns['dates_2digit'] = dates_2digit[:5]
    return patterns

def get_observation_rows(table, target_sns):
    """Get specific observation rows by serial number."""
    results = {}
    for row in table:
        if row:
            # First cell might be SN
            sn_text = row[0].strip().rstrip('.')
            try:
                sn = int(sn_text)
                if sn in target_sns:
                    results[sn] = row
            except ValueError:
                pass
    return results

def print_separator():
    print("=" * 120)

def print_sub_separator():
    print("-" * 100)

# ===================== MAIN ANALYSIS =====================

for sno, manual_file, ai_file in PAIRS:
    print_separator()
    print(f"  S.No. {sno}")
    print_separator()

    manual_doc = Document(f"{BASE_MANUAL}/{manual_file}")
    ai_doc = Document(f"{BASE_AI}/{ai_file}")

    manual_paras = extract_all_text(manual_doc)
    ai_paras = extract_all_text(ai_doc)

    manual_tables = extract_all_tables(manual_doc)
    ai_tables = extract_all_tables(ai_doc)

    manual_all_text = '\n'.join(manual_paras) + '\n' + '\n'.join(
        ' | '.join(cell for cell in row) for table in manual_tables for row in table)
    ai_all_text = '\n'.join(ai_paras) + '\n' + '\n'.join(
        ' | '.join(cell for cell in row) for table in ai_tables for row in table)

    # ---- 1. SECTION HEADERS ----
    print(f"\n--- 1. SECTION HEADERS ---")
    manual_headers = find_section_headers(manual_paras)
    ai_headers = find_section_headers(ai_paras)

    # Also check table cells for headers
    for table in manual_tables:
        for row in table:
            for cell in row:
                if cell.strip():
                    for kw in ['title search report', 'chain of title', 'observations',
                              'schedule of property', 'encumbrance certificate', 'details of property']:
                        if kw in cell.lower() and len(cell) < 200:
                            manual_headers.append(cell)
    for table in ai_tables:
        for row in table:
            for cell in row:
                if cell.strip():
                    for kw in ['title search report', 'chain of title', 'observations',
                              'schedule of property', 'encumbrance certificate', 'details of property']:
                        if kw in cell.lower() and len(cell) < 200:
                            ai_headers.append(cell)

    # Deduplicate
    manual_headers = list(dict.fromkeys(manual_headers))
    ai_headers = list(dict.fromkeys(ai_headers))

    print(f"  MANUAL headers ({len(manual_headers)}):")
    for h in manual_headers:
        print(f"    >> {repr(h)}")
    print(f"  AI headers ({len(ai_headers)}):")
    for h in ai_headers:
        print(f"    >> {repr(h)}")

    # Check inline numbering
    manual_numbered = [h for h in manual_headers if re.match(r'^\d+[\.\)]\s', h)]
    ai_numbered = [h for h in ai_headers if re.match(r'^\d+[\.\)]\s', h)]
    print(f"  Manual numbered headers: {len(manual_numbered)} -> {manual_numbered[:5]}")
    print(f"  AI numbered headers: {len(ai_numbered)} -> {ai_numbered[:5]}")

    # ---- 2. RELEASE/CHARGE REMOVAL ENTRIES ----
    print(f"\n--- 2. CHAIN OF TITLE: RELEASE/CHARGE REMOVAL ---")
    _, manual_cot = find_chain_of_title_table(manual_tables)
    _, ai_cot = find_chain_of_title_table(ai_tables)

    if manual_cot:
        manual_releases = find_release_entries(manual_cot)
        print(f"  MANUAL release entries ({len(manual_releases)}):")
        for r in manual_releases:
            for i, cell in enumerate(r):
                if len(cell) > 20:
                    print(f"    Cell[{i}]: {repr(cell[:500])}")
    else:
        print("  MANUAL: Chain of title table NOT FOUND")

    if ai_cot:
        ai_releases = find_release_entries(ai_cot)
        print(f"  AI release entries ({len(ai_releases)}):")
        for r in ai_releases:
            for i, cell in enumerate(r):
                if len(cell) > 20:
                    print(f"    Cell[{i}]: {repr(cell[:500])}")
    else:
        print("  AI: Chain of title table NOT FOUND")

    # ---- 3. INHERITANCE/SUCCESSION ENTRIES ----
    print(f"\n--- 3. CHAIN OF TITLE: INHERITANCE/SUCCESSION ---")
    if manual_cot:
        manual_inherit = find_inheritance_entries(manual_cot)
        print(f"  MANUAL inheritance entries ({len(manual_inherit)}):")
        for r in manual_inherit:
            for i, cell in enumerate(r):
                if len(cell) > 15:
                    print(f"    Cell[{i}]: {repr(cell[:600])}")

    if ai_cot:
        ai_inherit = find_inheritance_entries(ai_cot)
        print(f"  AI inheritance entries ({len(ai_inherit)}):")
        for r in ai_inherit:
            for i, cell in enumerate(r):
                if len(cell) > 15:
                    print(f"    Cell[{i}]: {repr(cell[:600])}")

    # ---- 4. PROMULGATION ENTRIES ----
    print(f"\n--- 4. PROMULGATION/NOTIFICATION ENTRIES ---")
    if manual_cot:
        manual_prom = find_promulgation_entries(manual_cot)
        print(f"  MANUAL promulgation entries ({len(manual_prom)}):")
        for r in manual_prom:
            for i, cell in enumerate(r):
                if len(cell) > 15:
                    print(f"    Cell[{i}] ({len(cell)} chars): {repr(cell[:800])}")

    if ai_cot:
        ai_prom = find_promulgation_entries(ai_cot)
        print(f"  AI promulgation entries ({len(ai_prom)}):")
        for r in ai_prom:
            for i, cell in enumerate(r):
                if len(cell) > 15:
                    print(f"    Cell[{i}] ({len(cell)} chars): {repr(cell[:800])}")

    # ---- 5. OBSERVATIONS TABLE - ROWS 3, 5, 10, 18 ----
    print(f"\n--- 5. OBSERVATIONS TABLE (rows 3, 5, 10, 18) ---")
    _, manual_obs = find_observations_table(manual_tables)
    _, ai_obs = find_observations_table(ai_tables)

    # If not found by header, try finding by content patterns
    if not manual_obs:
        for table in manual_tables:
            for row in table:
                row_text = ' '.join(row).lower()
                if 'period of search' in row_text or 'encumbrance period' in row_text:
                    manual_obs = table
                    break
            if manual_obs:
                break
    if not ai_obs:
        for table in ai_tables:
            for row in table:
                row_text = ' '.join(row).lower()
                if 'period of search' in row_text or 'encumbrance period' in row_text:
                    ai_obs = table
                    break
            if ai_obs:
                break

    target_rows = [3, 5, 10, 18]
    if manual_obs:
        manual_obs_rows = get_observation_rows(manual_obs, target_rows)
        print(f"  MANUAL observations (found rows: {sorted(manual_obs_rows.keys())}):")
        for sn in target_rows:
            if sn in manual_obs_rows:
                row = manual_obs_rows[sn]
                print(f"    Row {sn}: {repr(' | '.join(row)[:400])}")
    else:
        print("  MANUAL: Observations table NOT FOUND")
        # Dump all table headers for debugging
        print(f"  Manual tables count: {len(manual_tables)}")
        for i, t in enumerate(manual_tables):
            if t:
                print(f"    Table {i} first row: {repr(' | '.join(t[0])[:200])}")

    if ai_obs:
        ai_obs_rows = get_observation_rows(ai_obs, target_rows)
        print(f"  AI observations (found rows: {sorted(ai_obs_rows.keys())}):")
        for sn in target_rows:
            if sn in ai_obs_rows:
                row = ai_obs_rows[sn]
                print(f"    Row {sn}: {repr(' | '.join(row)[:400])}")
    else:
        print("  AI: Observations table NOT FOUND")
        print(f"  AI tables count: {len(ai_tables)}")
        for i, t in enumerate(ai_tables):
            if t:
                print(f"    Table {i} first row: {repr(' | '.join(t[0])[:200])}")

    # ---- 6. NOTE ROW AT END OF CHAIN OF TITLE ----
    print(f"\n--- 6. NOTE ROW (end of chain of title) ---")
    if manual_cot:
        manual_notes = find_note_row(manual_cot)
        print(f"  MANUAL notes ({len(manual_notes)}):")
        for n in manual_notes:
            print(f"    >> {repr(' | '.join(n)[:500])}")

    if ai_cot:
        ai_notes = find_note_row(ai_cot)
        print(f"  AI notes ({len(ai_notes)}):")
        for n in ai_notes:
            print(f"    >> {repr(' | '.join(n)[:500])}")

    # Also search all tables for Note rows
    print("  Searching ALL tables for Note rows...")
    for idx, table in enumerate(manual_tables):
        for row in table:
            row_text = ' '.join(row)
            if 'Note' in row_text and ('entry' in row_text.lower() or 'khata' in row_text.lower() or 'document' in row_text.lower()):
                print(f"    MANUAL Table[{idx}]: {repr(row_text[:500])}")
    for idx, table in enumerate(ai_tables):
        for row in table:
            row_text = ' '.join(row)
            if 'Note' in row_text and ('entry' in row_text.lower() or 'khata' in row_text.lower() or 'document' in row_text.lower()):
                print(f"    AI Table[{idx}]: {repr(row_text[:500])}")

    # ---- 7. MINOR FORMATTING ----
    print(f"\n--- 7. FORMATTING ANALYSIS ---")

    # Dashes
    manual_en = manual_all_text.count('–')
    manual_dd = manual_all_text.count('--')
    manual_em = manual_all_text.count('—')
    ai_en = ai_all_text.count('–')
    ai_dd = ai_all_text.count('--')
    ai_em = ai_all_text.count('—')
    print(f"  Dashes: MANUAL: en-dash({manual_en}) double-hyphen({manual_dd}) em-dash({manual_em})")
    print(f"  Dashes: AI:     en-dash({ai_en}) double-hyphen({ai_dd}) em-dash({ai_em})")

    # Date formats
    manual_4d = re.findall(r'\d{1,2}[./-]\d{1,2}[./-](20\d{2}|19\d{2})', manual_all_text)
    manual_2d = re.findall(r'\d{1,2}[./-]\d{1,2}[./-](\d{2})(?!\d)', manual_all_text)
    ai_4d = re.findall(r'\d{1,2}[./-]\d{1,2}[./-](20\d{2}|19\d{2})', ai_all_text)
    ai_2d = re.findall(r'\d{1,2}[./-]\d{1,2}[./-](\d{2})(?!\d)', ai_all_text)
    print(f"  Dates: MANUAL: 4-digit-year({len(manual_4d)}) 2-digit-year({len(manual_2d)})")
    print(f"  Dates: AI:     4-digit-year({len(ai_4d)}) 2-digit-year({len(ai_2d)})")

    # Sample dates
    sample_manual_dates = re.findall(r'\d{1,2}[./-]\d{1,2}[./-]\d{2,4}', manual_all_text)[:8]
    sample_ai_dates = re.findall(r'\d{1,2}[./-]\d{1,2}[./-]\d{2,4}', ai_all_text)[:8]
    print(f"  Sample MANUAL dates: {sample_manual_dates}")
    print(f"  Sample AI dates:     {sample_ai_dates}")

    # Survey number format
    manual_sy = re.findall(r'(?:Sy|S[.y]|Survey)\s*(?:No|Number)?[.\s]*\d+[/\d]*', manual_all_text, re.IGNORECASE)[:5]
    ai_sy = re.findall(r'(?:Sy|S[.y]|Survey)\s*(?:No|Number)?[.\s]*\d+[/\d]*', ai_all_text, re.IGNORECASE)[:5]
    print(f"  Survey nums MANUAL: {manual_sy}")
    print(f"  Survey nums AI:     {ai_sy}")

    # Name list numbering (1), 2) vs 1. 2. etc.)
    manual_numnames = re.findall(r'(?:\d+\)|[ivx]+\)|\d+\.)\s*(?:Sri|Smt|Mr|Mrs|Shri)', manual_all_text)[:5]
    ai_numnames = re.findall(r'(?:\d+\)|[ivx]+\)|\d+\.)\s*(?:Sri|Smt|Mr|Mrs|Shri)', ai_all_text)[:5]
    print(f"  Name numbering MANUAL: {manual_numnames}")
    print(f"  Name numbering AI:     {ai_numnames}")

    # Observation SN format (with/without periods)
    if manual_obs:
        manual_sns = [row[0].strip() for row in manual_obs if row and row[0].strip() and row[0].strip()[0].isdigit()][:5]
        print(f"  Obs SN format MANUAL: {manual_sns}")
    if ai_obs:
        ai_sns = [row[0].strip() for row in ai_obs if row and row[0].strip() and row[0].strip()[0].isdigit()][:5]
        print(f"  Obs SN format AI:     {ai_sns}")

    # Bank name style
    manual_banks = re.findall(r'(?:bank|finance|housing|credit|LIC|HDFC|SBI|ICICI|Canara|Corporation)[\w\s,.]*(?:Ltd|Limited|Bank)?', manual_all_text, re.IGNORECASE)[:3]
    ai_banks = re.findall(r'(?:bank|finance|housing|credit|LIC|HDFC|SBI|ICICI|Canara|Corporation)[\w\s,.]*(?:Ltd|Limited|Bank)?', ai_all_text, re.IGNORECASE)[:3]
    print(f"  Bank names MANUAL: {[b.strip()[:80] for b in manual_banks]}")
    print(f"  Bank names AI:     {[b.strip()[:80] for b in ai_banks]}")

    print()

print_separator()
print("ANALYSIS COMPLETE")
print_separator()
