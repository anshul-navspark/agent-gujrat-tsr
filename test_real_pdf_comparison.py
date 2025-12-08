#!/usr/bin/env python3
"""
Real PDF comparison test - compares original vs optimized extraction on actual document.
"""

import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set to use original extraction first
os.environ['USE_OPTIMIZED_EXTRACTION'] = 'false'

print("=" * 70)
print("REAL PDF COMPARISON TEST")
print("=" * 70)

PDF_PATH = "Kutch_Abdasa_Trambo_150_Original.pdf"

# ============================================================================
# Step 1: Extract PDF text
# ============================================================================
print("\n[Step 1] Extracting text from PDF...")

# Use pdfplumber for PDF extraction (avoids cryptography dependency issue)
import pdfplumber

def extract_text_from_pdf_local(pdf_path):
    """Extract text using pdfplumber"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text
    except Exception as e:
        print(f"Error extracting PDF: {e}")
        return None

pdf_text = extract_text_from_pdf_local(PDF_PATH)

if not pdf_text:
    print("  ERROR: Failed to extract PDF text")
    sys.exit(1)

print(f"  Extracted {len(pdf_text)} characters from PDF")
print(f"  First 500 chars: {pdf_text[:500]}...")

# ============================================================================
# Step 2: Run ORIGINAL extraction (3 API calls)
# ============================================================================
print("\n[Step 2] Running ORIGINAL extraction (3 separate API calls)...")
print("-" * 50)

from tsr_generator.extractors.land_details import extract_land_details as original_land_details
from tsr_generator.extractors.entry_details import extract_entry_table as original_entry_table
from tsr_generator.extractors.entry_details import extract_entry_details as original_entry_details

original_results = {}
original_api_calls = 0

try:
    start_time = time.time()

    print("  Calling extract_land_details (API call 1)...")
    original_results['land_details'] = original_land_details(pdf_text)
    original_api_calls += 1
    print(f"    Land: {original_results['land_details'].get('village_name', 'N/A')}, {original_results['land_details'].get('district_name', 'N/A')}")

    print("  Calling extract_entry_table (API call 2)...")
    original_results['entry_numbers'] = original_entry_table(pdf_text)
    original_api_calls += 1
    print(f"    Entry numbers: {original_results['entry_numbers']}")

    print("  Calling extract_entry_details (API call 3)...")
    original_results['entries'] = original_entry_details(pdf_text)
    original_api_calls += 1
    print(f"    Entries extracted: {len(original_results['entries'])}")

    original_time = time.time() - start_time
    print(f"\n  Original extraction completed in {original_time:.2f}s with {original_api_calls} API calls")

except Exception as e:
    print(f"  ERROR in original extraction: {e}")
    import traceback
    traceback.print_exc()
    original_results = None

# ============================================================================
# Step 3: Run OPTIMIZED extraction (1 API call)
# ============================================================================
print("\n[Step 3] Running OPTIMIZED extraction (1 unified API call)...")
print("-" * 50)

from tsr_generator.extractors.unified_extractor import extract_all_unified

optimized_results = {}

try:
    start_time = time.time()

    print("  Calling extract_all_unified (single API call)...")
    unified_result = extract_all_unified(pdf_text)

    if unified_result.success:
        optimized_results['land_details'] = unified_result.land_details
        optimized_results['entry_numbers'] = unified_result.entry_numbers
        optimized_results['mutation_entries'] = unified_result.mutation_entries

        print(f"    Land: {unified_result.land_details.get('village_name', 'N/A')}, {unified_result.land_details.get('district_name', 'N/A')}")
        print(f"    Entry numbers: {unified_result.entry_numbers}")
        print(f"    Mutation entries: {len(unified_result.mutation_entries)}")
        print(f"    Input tokens: ~{unified_result.input_tokens}")
        print(f"    Output tokens: ~{unified_result.output_tokens}")
    else:
        print(f"  ERROR: {unified_result.error}")

    optimized_time = time.time() - start_time
    print(f"\n  Optimized extraction completed in {optimized_time:.2f}s with 1 API call")

except Exception as e:
    print(f"  ERROR in optimized extraction: {e}")
    import traceback
    traceback.print_exc()
    optimized_results = None

# ============================================================================
# Step 4: Compare results
# ============================================================================
print("\n[Step 4] Comparing Results...")
print("-" * 50)

if original_results and optimized_results:
    print("\n  LAND DETAILS COMPARISON:")
    land_fields = ['village_name', 'taluka_name', 'district_name', 'survey_number', 'total_area', 'owner']
    matches = 0
    for field in land_fields:
        orig_val = original_results.get('land_details', {}).get(field, 'N/A')
        opt_val = optimized_results.get('land_details', {}).get(field, 'N/A')
        match = "✓" if orig_val == opt_val else "≈" if orig_val.lower() == opt_val.lower() else "✗"
        if match in ["✓", "≈"]:
            matches += 1
        print(f"    {field}:")
        print(f"      Original:  {orig_val}")
        print(f"      Optimized: {opt_val} {match}")

    print(f"\n  ENTRY NUMBERS COMPARISON:")
    orig_entries = set(str(x) for x in original_results.get('entry_numbers', []))
    opt_entries = set(optimized_results.get('entry_numbers', []))
    common = orig_entries & opt_entries
    only_orig = orig_entries - opt_entries
    only_opt = opt_entries - orig_entries

    print(f"    Original found: {len(orig_entries)} entries - {sorted(orig_entries)}")
    print(f"    Optimized found: {len(opt_entries)} entries - {sorted(opt_entries)}")
    print(f"    Common: {len(common)}, Only in original: {len(only_orig)}, Only in optimized: {len(only_opt)}")

    print(f"\n  MUTATION ENTRIES COMPARISON:")
    orig_mutation_count = len(original_results.get('entries', []))
    opt_mutation_count = len(optimized_results.get('mutation_entries', []))
    print(f"    Original: {orig_mutation_count} detailed entries")
    print(f"    Optimized: {opt_mutation_count} detailed entries")

    # ============================================================================
    # Summary
    # ============================================================================
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    print(f"""
  ORIGINAL METHOD:
    - API Calls: {original_api_calls}
    - Time: {original_time:.2f}s
    - Land details: {len(original_results.get('land_details', {}))} fields
    - Entry numbers: {len(orig_entries)}
    - Detailed entries: {orig_mutation_count}

  OPTIMIZED METHOD:
    - API Calls: 1
    - Time: {optimized_time:.2f}s
    - Land details: {len(optimized_results.get('land_details', {}))} fields
    - Entry numbers: {len(opt_entries)}
    - Detailed entries: {opt_mutation_count}
    - Tokens used: ~{unified_result.input_tokens + unified_result.output_tokens}

  COMPARISON:
    - API calls reduced: {original_api_calls} → 1 ({(original_api_calls-1)/original_api_calls*100:.0f}% reduction)
    - Time: {original_time:.2f}s → {optimized_time:.2f}s
    - Land details match: {matches}/{len(land_fields)} fields
    - Entry numbers overlap: {len(common)}/{max(len(orig_entries), len(opt_entries))}
""")

    if matches >= 4 and len(common) >= len(orig_entries) * 0.8:
        print("  ✓ RESULTS ARE FUNCTIONALLY EQUIVALENT")
        print("  The optimized extraction produces comparable results with fewer API calls.")
    else:
        print("  ⚠ RESULTS HAVE SOME DIFFERENCES")
        print("  Review the comparison above to determine if differences are acceptable.")

else:
    print("  Cannot compare - one or both extractions failed")

print("\n" + "=" * 70)
