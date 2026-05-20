"""Render-level tests for TSR document generation.

Covers two behaviors the lawyers asked for:
- Chain of Title rows carry Word's auto-numbering (numPr) so inserting or
  deleting a row in Word renumbers the column automatically.
- The 'Re:' line in the recipient block is data-driven, not hardcoded.
"""

import os
import pytest

from docx import Document
from docx.oxml.ns import qn

from tsr_generator.document.docx_generator import add_chain_of_title_section
from tsr_generator.document.tsr_document import create_tsr_document
from tsr_generator.extractors.entry_schema import GenericEntry


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _first_para_num_id(cell):
    """Return the w:numId value attached to the cell's first paragraph, or None."""
    pPr = cell.paragraphs[0]._p.find(qn("w:pPr"))
    if pPr is None:
        return None
    numPr = pPr.find(qn("w:numPr"))
    if numPr is None:
        return None
    numId_el = numPr.find(qn("w:numId"))
    if numId_el is None:
        return None
    return numId_el.get(qn("w:val"))


def _abstract_format_for_num_id(document, num_id):
    """Resolve numId -> abstractNum -> lvl[0]'s numFmt val."""
    numbering = document.part.numbering_part.element
    for num in numbering.findall(qn("w:num")):
        if num.get(qn("w:numId")) == num_id:
            abs_ref = num.find(qn("w:abstractNumId"))
            abs_id = abs_ref.get(qn("w:val"))
            for abstract in numbering.findall(qn("w:abstractNum")):
                if abstract.get(qn("w:abstractNumId")) == abs_id:
                    lvl = abstract.find(qn("w:lvl"))
                    if lvl is None:
                        return None
                    numFmt = lvl.find(qn("w:numFmt"))
                    return numFmt.get(qn("w:val")) if numFmt is not None else None
    return None


def _paragraph_texts(docx_path):
    doc = Document(docx_path)
    return [p.text for p in doc.paragraphs]


# ---------------------------------------------------------------------------
# Chain of Title: auto-numbering
# ---------------------------------------------------------------------------


def test_chain_of_title_data_rows_have_word_auto_numbering():
    """Each data row's first cell must carry a w:numPr so Word renders the
    serial number itself (and renumbers when a row is inserted/deleted)."""
    doc = Document()
    entries = [
        GenericEntry(entry_number="100", date="01/01/2000", type="SALE",
                     formatted_description="First entry", entry_status="certified"),
        GenericEntry(entry_number="200", date="02/02/2001", type="LOAN",
                     formatted_description="Second entry", entry_status="certified"),
        GenericEntry(entry_number="300", date="03/03/2002", type="RELEASE",
                     formatted_description="Third entry", entry_status="certified"),
    ]
    add_chain_of_title_section(doc, entries, ["100", "200", "300"])

    table = doc.tables[-1]
    # row[0] is the explanatory header; row[-1] is the Note row. Data rows are in between.
    data_rows = table.rows[1:-1]
    assert len(data_rows) == 3

    num_ids = [_first_para_num_id(row.cells[0]) for row in data_rows]
    assert all(n is not None for n in num_ids), \
        f"every data row's first cell must have w:numPr, got {num_ids}"
    assert len(set(num_ids)) == 1, \
        f"all data rows must share one numId so Word counts them together, got {num_ids}"


def test_chain_of_title_uses_decimal_numbering_format():
    """The auto-number must render as 1., 2., 3., ... (decimal), not bullets."""
    doc = Document()
    entries = [
        GenericEntry(entry_number="100", date="01/01/2000", type="SALE",
                     formatted_description="Only entry", entry_status="certified"),
    ]
    add_chain_of_title_section(doc, entries, ["100"])
    table = doc.tables[-1]
    num_id = _first_para_num_id(table.rows[1].cells[0])
    assert _abstract_format_for_num_id(doc, num_id) == "decimal"


def test_chain_of_title_header_and_note_rows_skip_auto_number():
    """Header and Note rows must NOT carry numPr — otherwise Word counts them."""
    doc = Document()
    entries = [
        GenericEntry(entry_number="100", date="01/01/2000", type="SALE",
                     formatted_description="Only entry", entry_status="certified"),
    ]
    add_chain_of_title_section(doc, entries, ["100"])
    table = doc.tables[-1]
    assert _first_para_num_id(table.rows[0].cells[0]) is None, "header row must not be numbered"
    assert _first_para_num_id(table.rows[-1].cells[0]) is None, "note row must not be numbered"


# ---------------------------------------------------------------------------
# Re: line: data-driven, no hardcoded date
# ---------------------------------------------------------------------------


def _base_land_details():
    return {
        "village_name": "Trambo",
        "taluka_name": "Bhuj",
        "district_name": "Kutch",
        "survey_number": "32",
        "nature_of_land": "new tenure",
        "total_area": "1-00-00",
        "owner": "Sample Owner",
        "old_survey_number": "",
    }


def _entries():
    return [
        GenericEntry(entry_number="100", date="01/01/2000", type="SALE",
                     formatted_description="Sample sale", entry_status="certified"),
    ]


def test_re_line_omitted_when_no_reference_email_date(tmp_path):
    """No reference_email_date and no re_line override -> Re: paragraph is dropped,
    and the hardcoded fallback date must not leak into the doc."""
    out = tmp_path / "no_re_line.docx"
    create_tsr_document(
        entry_table=["100"],
        entries=_entries(),
        land_details=_base_land_details(),
        findings=[],
        output_path=str(out),
    )
    texts = _paragraph_texts(str(out))
    assert not any("21.11.2023" in t for t in texts), \
        "hardcoded 21.11.2023 fallback must not appear in the document"
    assert not any(t.lstrip().startswith("Re:") for t in texts), \
        f"Re: paragraph must be omitted when no reference_email_date is set; got {texts}"


def test_re_line_uses_reference_email_date_from_land_details(tmp_path):
    out = tmp_path / "with_date.docx"
    land = _base_land_details()
    land["reference_email_date"] = "15.05.2026"
    create_tsr_document(
        entry_table=["100"],
        entries=_entries(),
        land_details=land,
        findings=[],
        output_path=str(out),
    )
    texts = _paragraph_texts(str(out))
    re_line = next((t for t in texts if t.lstrip().startswith("Re:")), None)
    assert re_line is not None, f"expected a Re: paragraph; got {texts}"
    assert "15.05.2026" in re_line
    assert "Trambo" in re_line and "Bhuj" in re_line and "Kutch" in re_line
    assert "21.11.2023" not in re_line


def test_re_line_uses_full_override(tmp_path):
    """A caller-supplied re_line should be used verbatim, even without a date."""
    out = tmp_path / "override.docx"
    land = _base_land_details()
    land["re_line"] = "Re:\tCustom matter — Survey 32, Trambo."
    create_tsr_document(
        entry_table=["100"],
        entries=_entries(),
        land_details=land,
        findings=[],
        output_path=str(out),
    )
    texts = _paragraph_texts(str(out))
    assert any("Custom matter" in t for t in texts), \
        f"override re_line must appear; got {texts}"
    assert not any("21.11.2023" in t for t in texts)
