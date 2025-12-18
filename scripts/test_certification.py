#!/usr/bin/env python3
"""
Test script to verify structured certification extraction.
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tsr_generator.utils.pdf_utils import extract_text_from_pdf
from tsr_generator.extractors.unified_extractor import extract_all_unified

def test_certification_extraction():
    """Test the structured certification extraction."""
    # Use the existing PDF file
    pdf_path = "/Users/anshulgoyal/work/gujrat_tsr_agent/Kutch_Abdasa_Trambo_150_Original.pdf"
    
    if not os.path.exists(pdf_path):
        print(f"Error: PDF file not found at {pdf_path}")
        return
    
    print(f"Extracting text from: {pdf_path}")
    pdf_text = extract_text_from_pdf(pdf_path)
    
    if not pdf_text:
        print("Error: Could not extract text from PDF")
        return
    
    print(f"Extracted {len(pdf_text)} characters from PDF")
    print("\n" + "="*60)
    print("Running unified extraction with structured certification fields...")
    print("="*60 + "\n")
    
    result = extract_all_unified(pdf_text)
    
    if not result.success:
        print(f"Extraction failed: {result.error}")
        return
    
    print(f"✓ Extraction successful!")
    print(f"  - Found {len(result.entry_numbers)} entry numbers")
    print(f"  - Extracted {len(result.mutation_entries)} mutation entries")
    print(f"  - Input tokens: ~{result.input_tokens}")
    print(f"  - Output tokens: ~{result.output_tokens}")
    
    print("\n" + "="*60)
    print("CERTIFICATION DETAILS FOR EACH ENTRY:")
    print("="*60)
    
    for entry in result.mutation_entries:
        entry_num = entry.get('entry_number', 'N/A')
        entry_date = entry.get('date', 'N/A')
        entry_type = entry.get('type', 'N/A')
        
        # Check for structured certification fields
        cert_status = entry.get('certification_status', '')
        cert_official = entry.get('certification_official', '')  
        cert_date = entry.get('certification_date', '')
        
        # Also check for old format
        old_cert = entry.get('certification', '')
        
        print(f"\n📋 Entry No. {entry_num} (Dated: {entry_date}) - Type: {entry_type}")
        print(f"   Description: {entry.get('description', 'N/A')[:100]}...")
        
        if cert_status or cert_official or cert_date:
            print(f"   ✅ STRUCTURED CERTIFICATION FIELDS:")
            print(f"      - Status: '{cert_status}'")
            print(f"      - Official: '{cert_official}'")
            print(f"      - Date: '{cert_date}'")
            
            # Construct the certification string
            if cert_status:
                if cert_official and cert_date:
                    constructed = f"The Entry is {cert_status} by {cert_official} on {cert_date}."
                elif cert_official:
                    constructed = f"The Entry is {cert_status} by {cert_official}."
                elif cert_date:
                    constructed = f"The Entry is {cert_status} on {cert_date}."
                else:
                    constructed = f"The Entry is {cert_status}."
                print(f"      📝 Constructed: \"{constructed}\"")
        elif old_cert:
            print(f"   ⚠️  OLD FORMAT CERTIFICATION: '{old_cert}'")
        else:
            print(f"   ❌ NO CERTIFICATION DATA")
    
    print("\n" + "="*60)
    print("Test complete!")
    print("="*60)

if __name__ == "__main__":
    test_certification_extraction()
