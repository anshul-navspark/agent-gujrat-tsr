#!/usr/bin/env python3
"""
Comprehensive comparison of ALL manual vs AI TSR document pairs.
Analyzes ~58 pairs matched by survey number.
"""

import os
import re
import json
from collections import defaultdict, Counter
from docx import Document

MANUAL_DIR = "Final TSR Sample"
AI_DIR = "Final AI TSR Sample"

def extract_survey_number(filename):
    """Extract survey number from filename."""
    m = re.search(r'S\.No\.\s*(\d+)', filename)
    if m:
        return m.group(1)
    return None

def get_matched_pairs():
    """Find all matched pairs between manual and AI directories."""
    manual_files = {}
    for f in os.listdir(MANUAL_DIR):
        if f.endswith('.docx') and not f.startswith('~'):
            sn = extract_survey_number(f)
            if sn:
                # Handle duplicates (e.g. 1267p1, 1267p2, 1267-p3, 1128-p1, 1128-p2)
                key = f  # use full filename as key for uniqueness
                manual_files[f] = (sn, os.path.join(MANUAL_DIR, f))

    ai_files = {}
    for f in os.listdir(AI_DIR):
        if f.endswith('.docx') and not f.startswith('~'):
            sn = extract_survey_number(f)
            if sn:
                ai_files[f] = (sn, os.path.join(AI_DIR, f))

    # Match by: AI filename = "AI_" + manual filename
    pairs = []
    for manual_name, (sn, manual_path) in manual_files.items():
        ai_name = "AI_" + manual_name
        if ai_name in ai_files:
            pairs.append((sn, manual_name, manual_path, ai_files[ai_name][1]))
        else:
            print(f"  WARNING: No AI match for {manual_name}")

    # Check for unmatched AI files
    matched_ai = set("AI_" + m for m in manual_files.keys())
    for ai_name in ai_files:
        if ai_name not in matched_ai:
            print(f"  WARNING: No manual match for {ai_name}")

    pairs.sort(key=lambda x: x[1])
    return pairs

def extract_doc_data(filepath):
    """Extract all relevant data from a TSR document."""
    try:
        doc = Document(filepath)
    except Exception as e:
        return None, str(e)

    data = {
        'paragraphs': [p.text for p in doc.paragraphs],
        'num_tables': len(doc.tables),
        'tables': [],
    }

    for ti, table in enumerate(doc.tables):
        rows = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            rows.append(cells)
        data['tables'].append(rows)

    return data, None

def count_2digit_vs_4digit_years(text):
    """Count 2-digit vs 4-digit year dates in text."""
    # Match date patterns like DD/MM/YY or DD/MM/YYYY or DD.MM.YY etc.
    dates_4digit = re.findall(r'\d{1,2}[/.-]\d{1,2}[/.-]((?:19|20)\d{2})', text)
    dates_2digit = re.findall(r'\d{1,2}[/.-]\d{1,2}[/.-](\d{2})(?!\d)', text)
    # Filter out 4-digit matches from 2-digit
    return len(dates_2digit), len(dates_4digit)

def check_certification_details(text):
    """Check if certification includes officer name and date."""
    has_officer = bool(re.search(r'certified\s+by\s+[A-Z]', text, re.IGNORECASE))
    has_co = bool(re.search(r'C\.O\.', text))
    has_just_certified = bool(re.search(r'(The [Ee]ntry is certified|entry is certified)\.?\s*$', text, re.MULTILINE))
    return has_officer or has_co, has_just_certified

def analyze_release_phrasing(text):
    """Analyze RELEASE entry phrasing."""
    # Manual style: "upon receiving an application from X for removing the charge of Y"
    manual_style = len(re.findall(r'upon receiving an application', text, re.IGNORECASE))
    # AI style: "charge of X removed on application of Y"
    ai_style = len(re.findall(r'charge of .+? removed', text, re.IGNORECASE))
    # Also check for "exemption of burden"
    exemption_style = len(re.findall(r'exemption of burden', text, re.IGNORECASE))
    return manual_style, ai_style, exemption_style

def get_chain_of_title_table(data):
    """Get the chain of title table (usually table index 2)."""
    if data['num_tables'] >= 3:
        return data['tables'][2]
    return None

def get_observations_table(data):
    """Get the observations table (usually last table or index 3)."""
    if data['num_tables'] >= 4:
        return data['tables'][3]
    # Sometimes it's the last table
    if data['num_tables'] >= 1:
        last = data['tables'][-1]
        # Check if it looks like observations table
        if len(last) > 0 and any('Particular' in str(r) for r in last[:2]):
            return last
    return None

def get_property_table(data):
    """Get the property description table (usually table index 0)."""
    if data['num_tables'] >= 1:
        return data['tables'][0]
    return None

def get_documents_table(data):
    """Get the documents table (usually table index 1)."""
    if data['num_tables'] >= 2:
        return data['tables'][1]
    return None

def count_chain_entries(chain_table):
    """Count actual entries (non-header, non-note rows)."""
    if not chain_table:
        return 0
    count = 0
    for row in chain_table:
        text = ' '.join(row)
        if 'Brief history' in text or 'Note' in text.split(':-')[0][:10]:
            continue
        if re.search(r'Entry No\.?\s*\d+', text):
            count += 1
    return count

def extract_entry_numbers(chain_table):
    """Extract all entry numbers from chain of title."""
    entries = []
    if not chain_table:
        return entries
    for row in chain_table:
        text = ' '.join(row)
        m = re.search(r'Entry No\.?\s*(\d+)', text)
        if m:
            entries.append(int(m.group(1)))
    return entries

def get_note_row(chain_table):
    """Get the Note row from chain of title."""
    if not chain_table:
        return ""
    for row in chain_table:
        text = ' '.join(row)
        if 'Note:-' in text or 'Note:' in text or text.strip().startswith('Note'):
            return text
    # Check last row
    if chain_table:
        last_text = ' '.join(chain_table[-1])
        return last_text
    return ""

def get_obs_row_by_sn(obs_table, target_sn):
    """Get observation row by SN number (the first column)."""
    if not obs_table:
        return ""
    for row in obs_table:
        if len(row) >= 3:
            sn = row[0].strip().rstrip('.')
            if sn == str(target_sn):
                return row[2]  # Observations column
    return ""

def get_obs_row_by_question_keyword(obs_table, keyword):
    """Get observation row by keyword in the question column."""
    if not obs_table:
        return ""
    for row in obs_table:
        if len(row) >= 3:
            if keyword.lower() in row[1].lower():
                return row[2]
    return ""

def has_empty_entries(chain_table):
    """Check how many entries have only entry number but no content."""
    if not chain_table:
        return 0
    count = 0
    for row in chain_table:
        text = ' '.join(row)
        m = re.match(r'.*Entry No\.?\s*\d+\s*Dated\s*:?\s*$', text.strip())
        if m:
            count += 1
    return count

def main():
    print("=" * 80)
    print("COMPREHENSIVE TSR COMPARISON REPORT")
    print("Manual vs AI — All Matched Pairs")
    print("=" * 80)
    print()

    pairs = get_matched_pairs()
    print(f"Total matched pairs: {len(pairs)}")
    print()

    # Accumulators for all analyses
    results = {
        'chain_entry_counts': [],  # (sn, manual_count, ai_count, diff)
        'empty_ai_entries': [],  # (sn, count_of_empty_entries)
        'missing_entries_in_ai': [],  # (sn, manual_entries_not_in_ai)
        'release_phrasing': [],  # (sn, manual_app_style, ai_removed_style, ...)
        'date_format': [],  # (sn, manual_2d, manual_4d, ai_2d, ai_4d)
        'certification': [],  # (sn, manual_with_officer, manual_just_cert, ai_with_officer, ai_just_cert)
        'obs_row5': [],  # (sn, manual_text, ai_text)
        'obs_row18': [],  # (sn, manual_text, ai_text)
        'obs_row3': [],  # (sn, manual_text, ai_text)
        'note_row': [],  # (sn, manual_note, ai_note)
        'property_title_holder': [],  # (sn, manual_text, ai_text)
        'documents_table': [],  # (sn, manual_rows, ai_rows)
        'area_format': [],  # (sn, manual_area, ai_area)
        'obs_row10': [],  # charge details
        'chain_full_text': [],  # for other pattern analysis
        'paragraph_diffs': [],
    }

    errors = []

    for sn, fname, manual_path, ai_path in pairs:
        manual_data, m_err = extract_doc_data(manual_path)
        ai_data, a_err = extract_doc_data(ai_path)

        if m_err:
            errors.append((sn, f"Manual error: {m_err}"))
            continue
        if a_err:
            errors.append((sn, f"AI error: {a_err}"))
            continue

        # Get tables
        m_chain = get_chain_of_title_table(manual_data)
        a_chain = get_chain_of_title_table(ai_data)
        m_obs = get_observations_table(manual_data)
        a_obs = get_observations_table(ai_data)
        m_prop = get_property_table(manual_data)
        a_prop = get_property_table(ai_data)
        m_docs = get_documents_table(manual_data)
        a_docs = get_documents_table(ai_data)

        # A. Chain of Title — Entry count comparison
        m_count = count_chain_entries(m_chain)
        a_count = count_chain_entries(a_chain)
        results['chain_entry_counts'].append((sn, fname, m_count, a_count, m_count - a_count))

        # Check for empty entries in AI
        a_empty = has_empty_entries(a_chain)
        if a_empty > 0:
            results['empty_ai_entries'].append((sn, a_empty))

        # Check for missing entry numbers in AI
        m_entries = set(extract_entry_numbers(m_chain))
        a_entries = set(extract_entry_numbers(a_chain))
        missing = m_entries - a_entries
        extra = a_entries - m_entries
        if missing:
            results['missing_entries_in_ai'].append((sn, sorted(missing), sorted(extra)))

        # B. Release entry phrasing
        m_chain_text = '\n'.join(' '.join(r) for r in m_chain) if m_chain else ''
        a_chain_text = '\n'.join(' '.join(r) for r in a_chain) if a_chain else ''
        m_app, m_removed, m_exempt = analyze_release_phrasing(m_chain_text)
        a_app, a_removed, a_exempt = analyze_release_phrasing(a_chain_text)
        results['release_phrasing'].append((sn, m_app, m_removed, m_exempt, a_app, a_removed, a_exempt))

        # C. Date format
        m_2d, m_4d = count_2digit_vs_4digit_years(m_chain_text)
        a_2d, a_4d = count_2digit_vs_4digit_years(a_chain_text)
        results['date_format'].append((sn, m_2d, m_4d, a_2d, a_4d))

        # D. Certification details
        m_with_officer = 0
        m_just_cert = 0
        a_with_officer = 0
        a_just_cert = 0
        if m_chain:
            for row in m_chain[1:]:  # skip header
                text = ' '.join(row)
                if 'Entry No' not in text:
                    continue
                has_off, has_just = check_certification_details(text)
                if has_off:
                    m_with_officer += 1
                if has_just:
                    m_just_cert += 1
        if a_chain:
            for row in a_chain[1:]:
                text = ' '.join(row)
                if 'Entry No' not in text:
                    continue
                has_off, has_just = check_certification_details(text)
                if has_off:
                    a_with_officer += 1
                if has_just:
                    a_just_cert += 1
        results['certification'].append((sn, m_with_officer, m_just_cert, a_with_officer, a_just_cert))

        # E. Observations rows
        # Row 5 (additional suggestions)
        m_obs5 = get_obs_row_by_question_keyword(m_obs, 'Additional suggestions')
        a_obs5 = get_obs_row_by_question_keyword(a_obs, 'Additional suggestions')
        results['obs_row5'].append((sn, m_obs5, a_obs5))

        # Row 18 (title conclusion)
        m_obs18 = get_obs_row_by_question_keyword(m_obs, 'absolute, clear, and marketable')
        a_obs18 = get_obs_row_by_question_keyword(a_obs, 'absolute, clear, and marketable')
        results['obs_row18'].append((sn, m_obs18, a_obs18))

        # Row 3 (encumbrance period)
        m_obs3 = get_obs_row_by_question_keyword(m_obs, 'period covered under the Encumbrances')
        a_obs3 = get_obs_row_by_question_keyword(a_obs, 'period covered under the Encumbrances')
        results['obs_row3'].append((sn, m_obs3, a_obs3))

        # Row 10 (charge details)
        m_obs10 = get_obs_row_by_question_keyword(m_obs, 'Details of creation of charge')
        a_obs10 = get_obs_row_by_question_keyword(a_obs, 'Details of creation of charge')
        results['obs_row10'].append((sn, m_obs10, a_obs10))

        # F. Note row
        m_note = get_note_row(m_chain)
        a_note = get_note_row(a_chain)
        results['note_row'].append((sn, m_note, a_note))

        # G. Property table — title holder formatting
        if m_prop and len(m_prop) > 1:
            m_holder = m_prop[1][-1] if len(m_prop[1]) >= 5 else ''
        else:
            m_holder = ''
        if a_prop and len(a_prop) > 1:
            a_holder = a_prop[1][-1] if len(a_prop[1]) >= 5 else ''
        else:
            a_holder = ''
        results['property_title_holder'].append((sn, m_holder, a_holder))

        # Area format
        if m_prop and len(m_prop) > 1 and len(m_prop[1]) >= 3:
            m_area = m_prop[1][2]
        else:
            m_area = ''
        if a_prop and len(a_prop) > 1 and len(a_prop[1]) >= 3:
            a_area = a_prop[1][2]
        else:
            a_area = ''
        results['area_format'].append((sn, m_area, a_area))

        # H. Documents table comparison
        m_doc_rows = len(m_docs) if m_docs else 0
        a_doc_rows = len(a_docs) if a_docs else 0
        results['documents_table'].append((sn, m_doc_rows, a_doc_rows,
                                           m_docs if m_docs else [],
                                           a_docs if a_docs else []))

        # Store full chain text for pattern analysis
        results['chain_full_text'].append((sn, m_chain_text, a_chain_text))

    # ====================================================================
    # REPORT
    # ====================================================================
    print("\n" + "=" * 80)
    print("A. CHAIN OF TITLE — ENTRY COUNT COMPARISON")
    print("=" * 80)
    total_manual = 0
    total_ai = 0
    fewer_ai = 0
    same_count = 0
    more_ai = 0
    significant_fewer = []
    for sn, fname, mc, ac, diff in results['chain_entry_counts']:
        total_manual += mc
        total_ai += ac
        if diff > 0:
            fewer_ai += 1
            if diff >= 3:
                significant_fewer.append((sn, fname, mc, ac, diff))
        elif diff == 0:
            same_count += 1
        else:
            more_ai += 1

    print(f"Total entries across all manuals: {total_manual}")
    print(f"Total entries across all AIs:     {total_ai}")
    print(f"Pairs where AI has FEWER entries: {fewer_ai}")
    print(f"Pairs where counts are EQUAL:     {same_count}")
    print(f"Pairs where AI has MORE entries:  {more_ai}")
    print()

    if significant_fewer:
        print(f"Pairs where AI has 3+ fewer entries ({len(significant_fewer)}):")
        for sn, fname, mc, ac, diff in sorted(significant_fewer, key=lambda x: -x[4]):
            print(f"  S.No. {sn} ({fname}): Manual={mc}, AI={ac}, Missing={diff}")
    print()

    # Per-pair detail
    print("Full entry count table:")
    print(f"  {'S.No.':<8} {'Manual':>8} {'AI':>8} {'Diff':>8}")
    print(f"  {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for sn, fname, mc, ac, diff in results['chain_entry_counts']:
        marker = " <<<" if diff >= 3 else ""
        print(f"  {sn:<8} {mc:>8} {ac:>8} {diff:>8}{marker}")

    # Empty entries in AI
    print()
    print("AI documents with EMPTY/SKELETON entries (Entry No. X Dated: only):")
    total_empty = sum(c for _, c in results['empty_ai_entries'])
    print(f"  Total documents affected: {len(results['empty_ai_entries'])}")
    print(f"  Total empty entries: {total_empty}")
    for sn, count in results['empty_ai_entries']:
        print(f"    S.No. {sn}: {count} empty entries")

    # Missing entry numbers
    print()
    print("Entry numbers present in Manual but MISSING from AI:")
    for sn, missing, extra in results['missing_entries_in_ai']:
        print(f"  S.No. {sn}: Missing={missing}")

    # ====================================================================
    print("\n" + "=" * 80)
    print("B. CHAIN OF TITLE — RELEASE ENTRY PHRASING")
    print("=" * 80)
    total_m_app = sum(r[1] for r in results['release_phrasing'])
    total_m_removed = sum(r[2] for r in results['release_phrasing'])
    total_m_exempt = sum(r[3] for r in results['release_phrasing'])
    total_a_app = sum(r[4] for r in results['release_phrasing'])
    total_a_removed = sum(r[5] for r in results['release_phrasing'])
    total_a_exempt = sum(r[6] for r in results['release_phrasing'])

    print(f"Manual — 'upon receiving an application' style: {total_m_app}")
    print(f"Manual — 'charge of X removed' style:          {total_m_removed}")
    print(f"Manual — 'exemption of burden' style:          {total_m_exempt}")
    print()
    print(f"AI     — 'upon receiving an application' style: {total_a_app}")
    print(f"AI     — 'charge of X removed' style:          {total_a_removed}")
    print(f"AI     — 'exemption of burden' style:          {total_a_exempt}")
    print()

    # Per-pair where there's a difference
    print("Per-pair release phrasing (only showing pairs with release entries):")
    for sn, m_app, m_rem, m_ex, a_app, a_rem, a_ex in results['release_phrasing']:
        if m_app + m_rem + a_app + a_rem > 0:
            print(f"  S.No. {sn}: Manual(app={m_app},removed={m_rem},exempt={m_ex}) AI(app={a_app},removed={a_rem},exempt={a_ex})")

    # ====================================================================
    print("\n" + "=" * 80)
    print("C. CHAIN OF TITLE — DATE FORMAT (2-digit vs 4-digit years)")
    print("=" * 80)
    total_m2 = sum(r[1] for r in results['date_format'])
    total_m4 = sum(r[2] for r in results['date_format'])
    total_a2 = sum(r[3] for r in results['date_format'])
    total_a4 = sum(r[4] for r in results['date_format'])

    print(f"Manual — 2-digit year dates: {total_m2}")
    print(f"Manual — 4-digit year dates: {total_m4}")
    if total_m2 + total_m4 > 0:
        print(f"Manual — 4-digit ratio: {total_m4/(total_m2+total_m4)*100:.1f}%")
    print()
    print(f"AI     — 2-digit year dates: {total_a2}")
    print(f"AI     — 4-digit year dates: {total_a4}")
    if total_a2 + total_a4 > 0:
        print(f"AI     — 4-digit ratio: {total_a4/(total_a2+total_a4)*100:.1f}%")
    print()

    # Per-pair
    print("Per-pair date format:")
    print(f"  {'S.No.':<8} {'M-2dig':>8} {'M-4dig':>8} {'A-2dig':>8} {'A-4dig':>8}")
    for sn, m2, m4, a2, a4 in results['date_format']:
        if m2 + m4 + a2 + a4 > 0:
            print(f"  {sn:<8} {m2:>8} {m4:>8} {a2:>8} {a4:>8}")

    # ====================================================================
    print("\n" + "=" * 80)
    print("D. CHAIN OF TITLE — CERTIFICATION DETAILS")
    print("=" * 80)
    total_m_officer = sum(r[1] for r in results['certification'])
    total_m_just = sum(r[2] for r in results['certification'])
    total_a_officer = sum(r[3] for r in results['certification'])
    total_a_just = sum(r[4] for r in results['certification'])

    print(f"Manual — Entries with officer name/details: {total_m_officer}")
    print(f"Manual — Entries with just 'certified':     {total_m_just}")
    print()
    print(f"AI     — Entries with officer name/details: {total_a_officer}")
    print(f"AI     — Entries with just 'certified':     {total_a_just}")
    print()

    print("Per-pair certification details:")
    print(f"  {'S.No.':<8} {'M-officer':>10} {'M-just':>8} {'A-officer':>10} {'A-just':>8}")
    for sn, mo, mj, ao, aj in results['certification']:
        if mo + ao > 0:
            print(f"  {sn:<8} {mo:>10} {mj:>8} {ao:>10} {aj:>8}")

    # ====================================================================
    print("\n" + "=" * 80)
    print("E. OBSERVATIONS TABLE — KEY ROW COMPARISON")
    print("=" * 80)

    # Row 5 — Additional suggestions
    print("\n--- Row 5: Additional suggestions ---")
    r5_manual_has_point_ref = 0
    r5_ai_has_point_ref = 0
    r5_manual_generic = 0
    r5_ai_generic = 0
    r5_diffs = []
    for sn, m_text, a_text in results['obs_row5']:
        m_has_ref = bool(re.search(r'point\s+\d+|table\s+no\.?\s*\d+|subject to', m_text, re.IGNORECASE))
        a_has_ref = bool(re.search(r'point\s+\d+|table\s+no\.?\s*\d+|subject to', a_text, re.IGNORECASE))
        if m_has_ref:
            r5_manual_has_point_ref += 1
        else:
            r5_manual_generic += 1
        if a_has_ref:
            r5_ai_has_point_ref += 1
        else:
            r5_ai_generic += 1
        if m_text.strip() != a_text.strip():
            r5_diffs.append((sn, m_text[:200], a_text[:200]))

    print(f"Manual — with specific point/table references: {r5_manual_has_point_ref}")
    print(f"Manual — generic:                              {r5_manual_generic}")
    print(f"AI     — with specific point/table references: {r5_ai_has_point_ref}")
    print(f"AI     — generic:                              {r5_ai_generic}")
    print(f"Pairs with different text: {len(r5_diffs)}")
    if r5_diffs:
        print("\nSample differences (first 10):")
        for sn, m, a in r5_diffs[:10]:
            print(f"  S.No. {sn}:")
            print(f"    Manual: {m}")
            print(f"    AI:     {a}")
            print()

    # Row 18 — Title conclusion
    print("\n--- Row 18: Title conclusion ---")
    r18_manual_has_ref = 0
    r18_ai_has_ref = 0
    r18_diffs = []
    for sn, m_text, a_text in results['obs_row18']:
        m_has_ref = bool(re.search(r'point\s+\d+|table\s+no\.?\s*\d+|subject to', m_text, re.IGNORECASE))
        a_has_ref = bool(re.search(r'point\s+\d+|table\s+no\.?\s*\d+|subject to', a_text, re.IGNORECASE))
        if m_has_ref:
            r18_manual_has_ref += 1
        if a_has_ref:
            r18_ai_has_ref += 1
        if m_text.strip() != a_text.strip():
            r18_diffs.append((sn, m_text[:200], a_text[:200]))

    print(f"Manual — with specific references: {r18_manual_has_ref}")
    print(f"AI     — with specific references: {r18_ai_has_ref}")
    print(f"Pairs with different text: {len(r18_diffs)}")
    if r18_diffs:
        print("\nSample differences (first 10):")
        for sn, m, a in r18_diffs[:10]:
            print(f"  S.No. {sn}:")
            print(f"    Manual: {m}")
            print(f"    AI:     {a}")
            print()

    # Row 3 — Encumbrance period
    print("\n--- Row 3: Encumbrance period ---")
    r3_diffs = []
    for sn, m_text, a_text in results['obs_row3']:
        if m_text.strip() != a_text.strip():
            r3_diffs.append((sn, m_text[:200], a_text[:200]))
    print(f"Pairs with different encumbrance text: {len(r3_diffs)}")
    if r3_diffs:
        print("\nAll differences:")
        for sn, m, a in r3_diffs:
            print(f"  S.No. {sn}:")
            print(f"    Manual: {m}")
            print(f"    AI:     {a}")
            print()

    # Row 10 — charge details
    print("\n--- Row 10: Details of creation of charge ---")
    r10_diffs = []
    for sn, m_text, a_text in results['obs_row10']:
        if m_text.strip() != a_text.strip():
            r10_diffs.append((sn, m_text[:300], a_text[:300]))
    print(f"Pairs with different charge detail text: {len(r10_diffs)}")
    # Count pattern: "charge subsisting" vs "no charge subsisting"
    m_charge_sub = sum(1 for _, m, a in results['obs_row10'] if 'there is charge subsisting' in m.lower() and 'no charge' not in m.lower())
    m_no_charge = sum(1 for _, m, a in results['obs_row10'] if 'no charge' in m.lower())
    a_charge_sub = sum(1 for _, m, a in results['obs_row10'] if 'there is charge subsisting' in a.lower() and 'no charge' not in a.lower())
    a_no_charge = sum(1 for _, m, a in results['obs_row10'] if 'no charge' in a.lower())
    print(f"Manual — 'charge subsisting': {m_charge_sub}, 'no charge': {m_no_charge}")
    print(f"AI     — 'charge subsisting': {a_charge_sub}, 'no charge': {a_no_charge}")
    # Show mismatches
    charge_mismatches = []
    for sn, m, a in results['obs_row10']:
        m_has = 'charge subsisting' in m.lower() and 'no charge' not in m.lower()
        a_has = 'charge subsisting' in a.lower() and 'no charge' not in a.lower()
        m_no = 'no charge' in m.lower()
        a_no = 'no charge' in a.lower()
        if m_has != a_has or m_no != a_no:
            charge_mismatches.append((sn, m[:150], a[:150]))
    if charge_mismatches:
        print(f"\nCharge status MISMATCHES ({len(charge_mismatches)}):")
        for sn, m, a in charge_mismatches:
            print(f"  S.No. {sn}:")
            print(f"    Manual: {m}")
            print(f"    AI:     {a}")
            print()

    # ====================================================================
    print("\n" + "=" * 80)
    print("F. NOTE ROW (last row of chain of title)")
    print("=" * 80)

    note_diffs = []
    m_note_has_entry_refs = 0
    a_note_has_entry_refs = 0
    m_note_has_dilr = 0
    a_note_has_dilr = 0
    m_note_has_stamp = 0
    a_note_has_stamp = 0
    m_note_has_borewell = 0
    a_note_has_borewell = 0
    m_note_has_bank_charge = 0
    a_note_has_bank_charge = 0

    for sn, m_note, a_note in results['note_row']:
        if re.search(r'entry|Entry No|(\d{3,})', m_note) and 'Note' in m_note:
            m_note_has_entry_refs += 1
        if re.search(r'entry|Entry No|(\d{3,})', a_note) and 'Note' in a_note:
            a_note_has_entry_refs += 1
        if 'DILR' in m_note.upper():
            m_note_has_dilr += 1
        if 'DILR' in a_note.upper():
            a_note_has_dilr += 1
        if 'stamp' in m_note.lower():
            m_note_has_stamp += 1
        if 'stamp' in a_note.lower():
            a_note_has_stamp += 1
        if 'borewell' in m_note.lower() or 'bore well' in m_note.lower():
            m_note_has_borewell += 1
        if 'borewell' in a_note.lower() or 'bore well' in a_note.lower():
            a_note_has_borewell += 1
        if 'bank charge' in m_note.lower() or 'subject to bank' in m_note.lower():
            m_note_has_bank_charge += 1
        if 'bank charge' in a_note.lower() or 'subject to bank' in a_note.lower():
            a_note_has_bank_charge += 1

        if m_note.strip() != a_note.strip():
            note_diffs.append((sn, m_note[:300], a_note[:300]))

    print(f"Manual — Notes with specific entry number refs: {m_note_has_entry_refs}")
    print(f"AI     — Notes with specific entry number refs: {a_note_has_entry_refs}")
    print(f"Manual — Notes mentioning DILR:     {m_note_has_dilr}")
    print(f"AI     — Notes mentioning DILR:     {a_note_has_dilr}")
    print(f"Manual — Notes mentioning stamp:    {m_note_has_stamp}")
    print(f"AI     — Notes mentioning stamp:    {a_note_has_stamp}")
    print(f"Manual — Notes mentioning borewell: {m_note_has_borewell}")
    print(f"AI     — Notes mentioning borewell: {a_note_has_borewell}")
    print(f"Manual — Notes mentioning bank charge: {m_note_has_bank_charge}")
    print(f"AI     — Notes mentioning bank charge: {a_note_has_bank_charge}")
    print(f"Pairs with different note text: {len(note_diffs)}")
    print()

    if note_diffs:
        print("All note differences:")
        for sn, m, a in note_diffs:
            print(f"  S.No. {sn}:")
            print(f"    Manual: {m}")
            print(f"    AI:     {a}")
            print()

    # ====================================================================
    print("\n" + "=" * 80)
    print("G. PROPERTY TABLE — TITLE HOLDER FORMATTING")
    print("=" * 80)

    numbered_manual = 0
    numbered_ai = 0
    holder_diffs = []
    for sn, m_holder, a_holder in results['property_title_holder']:
        m_num = bool(re.search(r'^\s*\d+[\.\)]\s', m_holder))
        a_num = bool(re.search(r'^\s*\d+[\.\)]\s', a_holder))
        if m_num:
            numbered_manual += 1
        if a_num:
            numbered_ai += 1
        if m_holder.strip() != a_holder.strip():
            holder_diffs.append((sn, m_holder[:150], a_holder[:150]))

    print(f"Manual — Numbered names format: {numbered_manual}")
    print(f"AI     — Numbered names format: {numbered_ai}")
    print(f"Pairs with different holder text: {len(holder_diffs)}")
    if holder_diffs:
        print("\nAll holder differences:")
        for sn, m, a in holder_diffs:
            print(f"  S.No. {sn}:")
            print(f"    Manual: {m}")
            print(f"    AI:     {a}")
            print()

    # ====================================================================
    print("\n" + "=" * 80)
    print("G2. PROPERTY TABLE — AREA FORMAT")
    print("=" * 80)
    area_diffs = []
    for sn, m_area, a_area in results['area_format']:
        if m_area.strip() != a_area.strip():
            area_diffs.append((sn, m_area[:150], a_area[:150]))
    print(f"Pairs with different area format: {len(area_diffs)}")
    if area_diffs:
        print("\nArea format differences (all):")
        for sn, m, a in area_diffs:
            print(f"  S.No. {sn}:")
            print(f"    Manual: {m}")
            print(f"    AI:     {a}")
            print()

    # ====================================================================
    print("\n" + "=" * 80)
    print("G3. DOCUMENTS TABLE — ROW COUNT COMPARISON")
    print("=" * 80)
    doc_diffs = []
    for sn, m_rows, a_rows, m_table, a_table in results['documents_table']:
        if m_rows != a_rows:
            doc_diffs.append((sn, m_rows, a_rows))
    print(f"Pairs with different document row counts: {len(doc_diffs)}")
    for sn, mr, ar in doc_diffs:
        print(f"  S.No. {sn}: Manual={mr}, AI={ar}")

    # ====================================================================
    print("\n" + "=" * 80)
    print("H. OTHER SYSTEMATIC DIFFERENCES")
    print("=" * 80)

    # H1. Check for "Dated :" pattern in AI (empty dates)
    print("\n--- H1. Empty 'Dated :' entries in AI (no date filled) ---")
    ai_empty_dated = 0
    ai_docs_with_empty = 0
    for sn, m_text, a_text in results['chain_full_text']:
        empties = len(re.findall(r'Dated\s*:\s*(?:\n|$|Entry|That)', a_text))
        # Also check for "Dated :" at end of text
        empties2 = len(re.findall(r'Entry No\.?\s*\d+\s+Dated\s*:\s*$', a_text, re.MULTILINE))
        total = empties + empties2
        if total > 0:
            ai_empty_dated += total
            ai_docs_with_empty += 1
    print(f"AI documents with empty dates: {ai_docs_with_empty}")
    print(f"Total empty date entries in AI: {ai_empty_dated}")

    # H2. Check for entry descriptions — SALE type
    print("\n--- H2. SALE entry phrasing ---")
    m_sale_count = 0
    a_sale_count = 0
    for sn, m_text, a_text in results['chain_full_text']:
        m_sale_count += len(re.findall(r'[Ss]ale|[Ss]old|[Ss]elling', m_text))
        a_sale_count += len(re.findall(r'[Ss]ale|[Ss]old|[Ss]elling', a_text))
    print(f"Manual — sale-related mentions: {m_sale_count}")
    print(f"AI     — sale-related mentions: {a_sale_count}")

    # H3. LOAN entry phrasing
    print("\n--- H3. LOAN entry phrasing ---")
    m_loan_took = 0
    a_loan_took = 0
    m_loan_taken = 0
    a_loan_taken = 0
    for sn, m_text, a_text in results['chain_full_text']:
        m_loan_took += len(re.findall(r'took a loan', m_text, re.IGNORECASE))
        a_loan_took += len(re.findall(r'took a loan', a_text, re.IGNORECASE))
        m_loan_taken += len(re.findall(r'loan.{0,30}was taken|a loan of', m_text, re.IGNORECASE))
        a_loan_taken += len(re.findall(r'loan.{0,30}was taken|a loan of', a_text, re.IGNORECASE))
    print(f"Manual — 'took a loan': {m_loan_took}")
    print(f"AI     — 'took a loan': {a_loan_took}")
    print(f"Manual — 'a loan was taken' / 'a loan of': {m_loan_taken}")
    print(f"AI     — 'a loan was taken' / 'a loan of': {a_loan_taken}")

    # H4. PARTITION/distribution phrasing
    print("\n--- H4. PARTITION/Distribution phrasing ---")
    m_dist = 0
    a_dist = 0
    m_partition = 0
    a_partition = 0
    for sn, m_text, a_text in results['chain_full_text']:
        m_dist += len(re.findall(r'distributed', m_text, re.IGNORECASE))
        a_dist += len(re.findall(r'distributed', a_text, re.IGNORECASE))
        m_partition += len(re.findall(r'partition', m_text, re.IGNORECASE))
        a_partition += len(re.findall(r'partition', a_text, re.IGNORECASE))
    print(f"Manual — 'distributed': {m_dist}")
    print(f"AI     — 'distributed': {a_dist}")
    print(f"Manual — 'partition':   {m_partition}")
    print(f"AI     — 'partition':   {a_partition}")

    # H5. "The entry is certified" vs "The Entry is certified" capitalization
    print("\n--- H5. Certification text capitalization ---")
    m_cap_entry = 0
    a_cap_entry = 0
    m_lower_entry = 0
    a_lower_entry = 0
    for sn, m_text, a_text in results['chain_full_text']:
        m_cap_entry += len(re.findall(r'The Entry is certified', m_text))
        a_cap_entry += len(re.findall(r'The Entry is certified', a_text))
        m_lower_entry += len(re.findall(r'The entry is certified', m_text))
        a_lower_entry += len(re.findall(r'The entry is certified', a_text))
    print(f"Manual — 'The Entry is certified': {m_cap_entry}")
    print(f"AI     — 'The Entry is certified': {a_cap_entry}")
    print(f"Manual — 'The entry is certified': {m_lower_entry}")
    print(f"AI     — 'The entry is certified': {a_lower_entry}")

    # H6. "rejected" entries
    print("\n--- H6. Rejected entries ---")
    m_rejected = 0
    a_rejected = 0
    for sn, m_text, a_text in results['chain_full_text']:
        m_rejected += len(re.findall(r'rejected', m_text, re.IGNORECASE))
        a_rejected += len(re.findall(r'rejected', a_text, re.IGNORECASE))
    print(f"Manual — 'rejected' mentions: {m_rejected}")
    print(f"AI     — 'rejected' mentions: {a_rejected}")

    # H7. "not related to present survey" entries
    print("\n--- H7. 'Not related to present survey' entries ---")
    m_not_related = 0
    a_not_related = 0
    for sn, m_text, a_text in results['chain_full_text']:
        m_not_related += len(re.findall(r'not related to present survey', m_text, re.IGNORECASE))
        a_not_related += len(re.findall(r'not related to present survey', a_text, re.IGNORECASE))
    print(f"Manual — 'not related to present survey': {m_not_related}")
    print(f"AI     — 'not related to present survey': {a_not_related}")

    # H8. Numbering in chain of title (AI uses 1., 2., 3. in first column)
    print("\n--- H8. Chain of title row numbering ---")
    m_numbered = 0
    a_numbered = 0
    for sn, m_text, a_text in results['chain_full_text']:
        pass  # Already visible from table structure
    # Count from the actual chain tables
    m_has_numbering = 0
    a_has_numbering = 0
    for sn, fname, manual_path, ai_path in pairs:
        m_data, _ = extract_doc_data(manual_path)
        a_data, _ = extract_doc_data(ai_path)
        if m_data and a_data:
            m_chain = get_chain_of_title_table(m_data)
            a_chain = get_chain_of_title_table(a_data)
            if m_chain and len(m_chain) > 1:
                # Check if first column has sequential numbers
                if m_chain[1][0].strip() in ('1', '1.'):
                    m_has_numbering += 1
            if a_chain and len(a_chain) > 1:
                if a_chain[1][0].strip() in ('1', '1.'):
                    a_has_numbering += 1
    print(f"Manual — Chain tables with numbered first column: {m_has_numbering}")
    print(f"AI     — Chain tables with numbered first column: {a_has_numbering}")

    # H9. Check dash style ("--" vs "–" vs "-")
    print("\n--- H9. Dash style in chain text ---")
    m_double_dash = 0
    a_double_dash = 0
    m_emdash = 0
    a_emdash = 0
    for sn, m_text, a_text in results['chain_full_text']:
        m_double_dash += m_text.count('--')
        a_double_dash += a_text.count('--')
        m_emdash += m_text.count('\u2013') + m_text.count('\u2014')
        a_emdash += a_text.count('\u2013') + a_text.count('\u2014')
    print(f"Manual — double-dash '--': {m_double_dash}")
    print(f"AI     — double-dash '--': {a_double_dash}")
    print(f"Manual — em/en-dash:       {m_emdash}")
    print(f"AI     — em/en-dash:       {a_emdash}")

    # H10. Survey number format in entries
    print("\n--- H10. 'Old Survey No.' vs 'Survey No.' in chain entries ---")
    m_old_sn = 0
    a_old_sn = 0
    m_just_sn = 0
    a_just_sn = 0
    for sn, m_text, a_text in results['chain_full_text']:
        m_old_sn += len(re.findall(r'[Oo]ld [Ss]urvey [Nn]o', m_text))
        a_old_sn += len(re.findall(r'[Oo]ld [Ss]urvey [Nn]o', a_text))
        m_just_sn += len(re.findall(r'(?<![Oo]ld )[Ss]urvey [Nn]o', m_text))
        a_just_sn += len(re.findall(r'(?<![Oo]ld )[Ss]urvey [Nn]o', a_text))
    print(f"Manual — 'Old Survey No': {m_old_sn}")
    print(f"AI     — 'Old Survey No': {a_old_sn}")
    print(f"Manual — just 'Survey No': {m_just_sn}")
    print(f"AI     — just 'Survey No': {a_just_sn}")

    # H11. Check for "demise" / death entries
    print("\n--- H11. Demise/death/mutation entries ---")
    m_demise = 0
    a_demise = 0
    for sn, m_text, a_text in results['chain_full_text']:
        m_demise += len(re.findall(r'demise|death', m_text, re.IGNORECASE))
        a_demise += len(re.findall(r'demise|death', a_text, re.IGNORECASE))
    print(f"Manual — 'demise/death' mentions: {m_demise}")
    print(f"AI     — 'demise/death' mentions: {a_demise}")

    # H12. Content length comparison
    print("\n--- H12. Chain of title text length comparison ---")
    m_lengths = []
    a_lengths = []
    length_ratios = []
    for sn, m_text, a_text in results['chain_full_text']:
        ml = len(m_text)
        al = len(a_text)
        m_lengths.append(ml)
        a_lengths.append(al)
        if ml > 0:
            length_ratios.append((sn, al / ml))
    print(f"Manual — avg chain text length: {sum(m_lengths)/len(m_lengths):.0f} chars")
    print(f"AI     — avg chain text length: {sum(a_lengths)/len(a_lengths):.0f} chars")
    print(f"Average AI/Manual length ratio: {sum(r for _, r in length_ratios)/len(length_ratios):.2f}")
    print()
    print("Per-pair length ratios (AI/Manual):")
    for sn, ratio in sorted(length_ratios, key=lambda x: x[1]):
        marker = " <<<" if ratio < 0.7 else (" >>>" if ratio > 1.3 else "")
        print(f"  S.No. {sn}: {ratio:.2f}{marker}")

    # H13. Check for consistent text patterns manual has but AI lacks
    print("\n--- H13. Text patterns in manual missing from AI ---")
    patterns_to_check = [
        ('exemption of burden', r'exemption of burden'),
        ('upon receiving an application', r'upon receiving an application'),
        ('Family members distributed', r'[Ff]amily members distributed'),
        ('during his lifetime', r'during his lifetime'),
        ('in family distribution', r'in family distribution'),
        ('Government allotted', r'[Gg]overnment allotted'),
        ('was conducted by Government', r'was conducted by Government'),
        ('not completely scanned', r'not completely scanned'),
        ('correction order from DILR', r'[Cc]orrection.{0,20}DILR'),
        ('stamp duty', r'[Ss]tamp [Dd]uty'),
        ('Borewell', r'[Bb]orewell'),
        ('area was reduced', r'area was reduced'),
        ('Prant Officer', r'[Pp]rant [Oo]fficer'),
        ('Province Officer', r'[Pp]rovince [Oo]fficer'),
        ('Re-survey promulgation', r'[Rr]e-?survey promulgation'),
    ]

    for label, pattern in patterns_to_check:
        m_count = sum(1 for _, m, a in results['chain_full_text'] if re.search(pattern, m))
        a_count = sum(1 for _, m, a in results['chain_full_text'] if re.search(pattern, a))
        if m_count > 0 or a_count > 0:
            diff_marker = " ***" if abs(m_count - a_count) >= 3 else ""
            print(f"  '{label}': Manual={m_count}, AI={a_count}{diff_marker}")

    # H14. Check note row for specific content patterns
    print("\n--- H14. Note row content patterns ---")
    note_patterns = [
        ('clear and marketable', r'clear and marketable'),
        ('subject to bank charge', r'subject to.{0,30}bank.{0,10}charge'),
        ('subject to point', r'subject to point'),
        ('DILR', r'DILR'),
        ('correction order', r'[Cc]orrection.{0,10}order'),
        ('area reduced', r'area.{0,20}reduced'),
        ('borewell', r'[Bb]ore\s*well'),
        ('stamp duty', r'[Ss]tamp'),
        ('entry numbers in note', r'\(\s*\d{3,}'),
        ('revenue records', r'revenue records'),
    ]
    for label, pattern in note_patterns:
        m_count = sum(1 for _, m, a in results['note_row'] if re.search(pattern, m))
        a_count = sum(1 for _, m, a in results['note_row'] if re.search(pattern, a))
        if m_count > 0 or a_count > 0:
            diff_marker = " ***" if abs(m_count - a_count) >= 3 else ""
            print(f"  '{label}': Manual={m_count}, AI={a_count}{diff_marker}")

    # ====================================================================
    print("\n" + "=" * 80)
    print("SUMMARY OF KEY FINDINGS")
    print("=" * 80)

    print(f"""
1. MATCHED PAIRS: {len(pairs)} total

2. CHAIN ENTRY COUNTS:
   - Total manual entries: {total_manual}, Total AI entries: {total_ai}
   - AI has fewer in {fewer_ai} pairs, same in {same_count}, more in {more_ai}
   - {len(significant_fewer)} pairs have 3+ fewer AI entries
   - {len(results['empty_ai_entries'])} AI docs have empty/skeleton entries (total: {total_empty})

3. RELEASE PHRASING:
   - Manual uses 'upon receiving an application' style: {total_m_app} times
   - AI uses 'charge of X removed' style: {total_a_removed} times
   - AI uses 'upon receiving' style: {total_a_app} times

4. DATE FORMAT:
   - Manual: {total_m4} four-digit, {total_m2} two-digit ({total_m4/(total_m2+total_m4)*100:.1f}% four-digit)
   - AI:     {total_a4} four-digit, {total_a2} two-digit ({total_a4/(total_a2+total_a4)*100:.1f}% four-digit)

5. CERTIFICATION:
   - Manual entries with officer details: {total_m_officer}
   - AI entries with officer details: {total_a_officer}

6. OBSERVATIONS ROW 5 (suggestions):
   - Manual with point/table refs: {r5_manual_has_point_ref}, AI: {r5_ai_has_point_ref}
   - {len(r5_diffs)} pairs differ

7. OBSERVATIONS ROW 18 (title conclusion):
   - Manual with refs: {r18_manual_has_ref}, AI: {r18_ai_has_ref}
   - {len(r18_diffs)} pairs differ

8. NOTE ROW:
   - {len(note_diffs)} pairs have different notes
   - Manual notes with DILR: {m_note_has_dilr}, AI: {a_note_has_dilr}
   - Manual notes with entry refs: {m_note_has_entry_refs}, AI: {a_note_has_entry_refs}

9. PROPERTY HOLDER FORMATTING:
   - {len(holder_diffs)} pairs have different holder text
""")

    if errors:
        print(f"\nERRORS ({len(errors)}):")
        for sn, err in errors:
            print(f"  S.No. {sn}: {err}")

if __name__ == '__main__':
    main()
