from docx import Document
from tsr_generator.document.docx_generator import add_chain_of_title_section
from tsr_generator.extractors.entry_schema import GenericEntry

def test_entry_to_row_map_returns_correct_mapping():
    doc = Document()
    entries = [
        GenericEntry(entry_number="100", date="01/01/2000", type="SALE",
                     formatted_description="Test sale entry", entry_status="certified"),
        GenericEntry(entry_number="200", date="02/02/2001", type="LOAN",
                     formatted_description="Test loan entry", entry_status="certified"),
    ]
    entry_table = ["100", "200"]
    result = add_chain_of_title_section(doc, entries, entry_table)
    assert isinstance(result, dict)
    assert result["100"] == 1
    assert result["200"] == 2

def test_entry_to_row_map_empty_entries():
    doc = Document()
    result = add_chain_of_title_section(doc, [], [])
    assert result == {}
