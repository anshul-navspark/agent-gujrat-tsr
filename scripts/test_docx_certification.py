
import sys
import os
from docx import Document

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tsr_generator.extractors.entry_schema import SaleEntry, EntryType
from tsr_generator.document.docx_generator import add_chain_of_title_section

def test_docx_certification():
    print("Testing DOCX certification generation...")
    
    # Create a mock entry with structured certification data
    entry = SaleEntry(
        entry_number="123",
        date="01/01/2023",
        raw_description="Sale of land",
        formatted_description="Sale of land",
        certification="Old broken string", # This should be IGNORED
        entry_status="certified",
        certification_official="C.O. Test",
        certification_date="02/01/2023"
    )
    
    doc = Document()
    
    # We need to mock entry_table as well since the function expects it
    add_chain_of_title_section(doc, [entry], ["123"])
    
    # Inspect the document content
    # The structure is: 
    # Table -> Row -> Cell[1] (Description column) -> Paragraphs
    # We expect the last paragraph in the cell to be the certification
    
    found = False
    for table in doc.tables:
        for row in table.rows:
            # Check the second cell (index 1) which contains the description
            if len(row.cells) > 1:
                cell = row.cells[1]
                for para in cell.paragraphs:
                    text = para.text.strip()
                    if "C.O. Test" in text:
                        print(f"FAILED: Found certification in text: '{text}'")
                        print("Wait, actually - if it matches 'C.O. Test' then it used the structured data!")
                        if "02/01/2023" in text:
                             print("SUCCESS: Found correct certification official and date!")
                             found = True
                        else:
                             print("PARTIAL SUCCESS: Found official but missing date?")
                    elif "Old broken string" in text:
                        print(f"FAILURE: Used the old certification string: '{text}'")
    
    if found:
        print("\nTest PASSED: The generator used the structured certification fields.")
    else:
        print("\nTest FAILED: Could not find the expected certification text.")

if __name__ == "__main__":
    test_docx_certification()
