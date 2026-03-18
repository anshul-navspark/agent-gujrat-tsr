#!/usr/bin/env python3
"""
Deep comparison of chain-of-title tables (release, inheritance, promulgation entries).
Dumps all tables to identify the right one, then extracts specific entry types.
"""

from docx import Document
import re

BASE_MANUAL = "/Users/anshulgoyal/work/gujrat_tsr_agent/Final TSR Sample"
BASE_AI = "/Users/anshulgoyal/work/gujrat_tsr_agent/Final AI TSR Sample"

PAIRS = [
    ("979", "S.No. 979 - Final.docx", "AI_S.No. 979 - Final.docx"),
    ("982", "S.No. 982 - Final.docx", "AI_S.No. 982 - Final.docx"),
    ("1043", "S.No. 1043 - Final.docx", "AI_S.No. 1043 - Final.docx"),
    ("1099", "S.No. 1099 - Complete Final.docx", "AI_S.No. 1099 - Complete Final.docx"),
    ("1259", "S.No. 1259 - Complete final.docx", "AI_S.No. 1259 - Complete final.docx"),
]

def extract_all_tables(doc):
    tables = []
    for table in doc.tables:
        rows = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            rows.append(cells)
        tables.append(rows)
    return tables

def identify_chain_of_title_table(tables):
    """Find the chain of title table - it's usually the largest table with entry numbers."""
    best_idx = -1
    best_score = 0
    for i, table in enumerate(tables):
        score = 0
        for row in table:
            row_text = ' '.join(row).lower()
            if re.search(r'entry\s*no', row_text):
                score += 2
            if 'khata' in row_text:
                score += 1
            if 'certified' in row_text:
                score += 1
            if re.search(r'\d{2,4}\s', row_text) and len(row) >= 3:
                score += 0.5
        if score > best_score:
            best_score = score
            best_idx = i
    return best_idx if best_score > 3 else -1

def classify_entry(row_text):
    """Classify an entry row by type."""
    lower = row_text.lower()
    types = []
    if any(kw in lower for kw in ['release', 'satisfaction', 'no due', 'no-due', 'noc', 'discharge']):
        types.append('RELEASE')
    if any(kw in lower for kw in ['charge', 'mortgage', 'loan', 'hypothecation', 'equitable']):
        types.append('CHARGE')
    if any(kw in lower for kw in ['inheritance', 'death', 'heir', 'succession', 'died', 'expire', 'demise']):
        types.append('INHERITANCE')
    if any(kw in lower for kw in ['mutation', 'khata', 'family distribution', 'partition']):
        types.append('MUTATION')
    if any(kw in lower for kw in ['promulgation', 'notification', 'gazette', 'layout', 'town planning', 'bda', 'conversion', 'bbmp', 'dc rate']):
        types.append('PROMULGATION')
    if any(kw in lower for kw in ['sale deed', 'sale', 'purchase', 'conveyance']):
        types.append('SALE')
    if 'note' in lower and len(row_text) > 30:
        types.append('NOTE')
    return types if types else ['OTHER']

for sno, manual_file, ai_file in PAIRS:
    print("=" * 130)
    print(f"  S.No. {sno} -- CHAIN OF TITLE DEEP DIVE")
    print("=" * 130)

    manual_doc = Document(f"{BASE_MANUAL}/{manual_file}")
    ai_doc = Document(f"{BASE_AI}/{ai_file}")

    manual_tables = extract_all_tables(manual_doc)
    ai_tables = extract_all_tables(ai_doc)

    # Find chain of title tables
    m_idx = identify_chain_of_title_table(manual_tables)
    a_idx = identify_chain_of_title_table(ai_tables)

    print(f"\n  Manual: {len(manual_tables)} tables total, CoT at index {m_idx}")
    print(f"  AI:     {len(ai_tables)} tables total, CoT at index {a_idx}")

    # Dump table summaries for context
    for label, tables in [("MANUAL", manual_tables), ("AI", ai_tables)]:
        print(f"\n  {label} table sizes: {[len(t) for t in tables]}")
        for i, t in enumerate(tables):
            if t:
                first_row = ' | '.join(t[0])[:120]
                print(f"    T[{i}] ({len(t)} rows): {repr(first_row)}")

    for label, tables, idx in [("MANUAL", manual_tables, m_idx), ("AI", ai_tables, a_idx)]:
        if idx < 0:
            print(f"\n  {label}: CoT table NOT FOUND")
            continue

        cot = tables[idx]
        print(f"\n  {label} Chain of Title ({len(cot)} rows):")
        print(f"  {'='*120}")

        # Categorize and print entries
        release_entries = []
        inheritance_entries = []
        promulgation_entries = []
        note_entries = []

        for row_num, row in enumerate(cot):
            row_text = ' '.join(row)
            types = classify_entry(row_text)

            if 'RELEASE' in types or 'CHARGE' in types:
                release_entries.append((row_num, row))
            if 'INHERITANCE' in types or 'MUTATION' in types:
                inheritance_entries.append((row_num, row))
            if 'PROMULGATION' in types:
                promulgation_entries.append((row_num, row))
            if 'NOTE' in types:
                note_entries.append((row_num, row))

        # --- RELEASE/CHARGE entries ---
        print(f"\n  >> {label} RELEASE/CHARGE entries ({len(release_entries)}):")
        for row_num, row in release_entries[:5]:  # limit to 5
            print(f"    Row {row_num}:")
            for ci, cell in enumerate(row):
                if len(cell) > 5:
                    print(f"      Cell[{ci}]: {repr(cell[:400])}")

        # --- INHERITANCE/MUTATION entries ---
        print(f"\n  >> {label} INHERITANCE/MUTATION entries ({len(inheritance_entries)}):")
        for row_num, row in inheritance_entries[:5]:
            print(f"    Row {row_num}:")
            for ci, cell in enumerate(row):
                if len(cell) > 5:
                    print(f"      Cell[{ci}]: {repr(cell[:600])}")

        # --- PROMULGATION entries ---
        print(f"\n  >> {label} PROMULGATION entries ({len(promulgation_entries)}):")
        for row_num, row in promulgation_entries[:3]:
            print(f"    Row {row_num}:")
            for ci, cell in enumerate(row):
                if len(cell) > 5:
                    print(f"      Cell[{ci}] ({len(cell)} chars): {repr(cell[:800])}")

        # --- NOTE entries ---
        print(f"\n  >> {label} NOTE entries ({len(note_entries)}):")
        for row_num, row in note_entries:
            print(f"    Row {row_num}:")
            for ci, cell in enumerate(row):
                if len(cell) > 5:
                    print(f"      Cell[{ci}]: {repr(cell[:600])}")

    print("\n")

print("DEEP ANALYSIS COMPLETE")
