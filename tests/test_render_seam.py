"""The render seam: extraction JSON -> .docx, with no model call.

These tests pin the two things that make the seam worth having:
  1. `gujtsr.render.render_tsr` refuses bad input with a sentence a lawyer can
     act on, instead of leaking a KeyError/TypeError traceback.
  2. There is exactly ONE render implementation — the PDF pipeline and the
     JSON-in path produce the same document. If someone copy-pastes the
     drafting logic, `test_pdf_pipeline_and_render_seam_agree` goes red.

No network, no LLM: the extraction step is mocked.
"""

import copy
import json
import re
import zipfile

import pytest

from gujtsr.render import render_tsr
from tsr_generator.api.tsr_generator_optimized import render_tsr_from_extraction
from tests.utils.compare_docx import get_docx_text


# ---------------------------------------------------------------------------
# Fixture: the shape build_unified_prompt() asks the model for. Documented in
# references/extraction-rules.md.
# ---------------------------------------------------------------------------

def _extraction():
    return {
        "land_details": {
            "village_name": "Trambo",
            "taluka_name": "Abdasa",
            "district_name": "Kutch",
            "survey_number": "150/p1",
            "old_survey_number": "",
            "total_area": "1-88-48",
            "nature_of_land": "Old Tenure, Agricultural",
            "owner": "Mer Deva Depa",
        },
        "entry_numbers": ["44", "607"],
        "mutation_entries": [
            {
                "entry_number": "44",
                "date": "14/05/2005",
                "type": "LOAN",
                "description": (
                    "That Mer Deva Depa took a loan of Rs. 20,000/- on land "
                    "bearing Survey No. 150/p1(215) from Bank of India, "
                    "Modhvada Branch."
                ),
                "entry_status": "certified",
                "certification_status": "certified",
                "certification_official": "C.O. Abdasa",
                "certification_date": "21/06/2005",
            },
            {
                "entry_number": "607",
                "date": "03/09/2011",
                "type": "SALE",
                "description": (
                    "That Mer Deva Depa sold Survey No. 150/p1 measuring "
                    "1-88-48 Hectare to Bhagubhai Ghohabhai for a "
                    "consideration of Rs. 200000/- (market value Rs. "
                    "295020/-) vide document no. 1421 dated 03/09/2011."
                ),
                "entry_status": "certified",
                "certification_status": "certified",
                "certification_official": "C.O. Abdasa",
                "certification_date": "12/09/2011",
            },
        ],
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_render_tsr_writes_a_docx(tmp_path):
    out = tmp_path / "TSR_Kutch_Abdasa_Trambo_150p1.docx"
    result = render_tsr(_extraction(), str(out))

    assert result["success"] is True, result
    assert result["output_path"] == str(out)
    assert result["entries"] == 2
    assert result["size_bytes"] > 0
    assert out.exists()

    text = "\n".join(get_docx_text(str(out)))
    assert "Trambo" in text
    assert "150/p1" in text
    # Both entries reached the chain of title
    assert "Bank of India" in text
    assert "Bhagubhai Ghohabhai" in text


def test_render_tsr_creates_missing_output_directory(tmp_path):
    out = tmp_path / "nested" / "deeper" / "t.docx"
    result = render_tsr(_extraction(), str(out))
    assert result["success"] is True, result
    assert out.exists()


def test_render_keeps_the_live_word_cross_references(tmp_path):
    """The findings must cite the charge with a Word REF field, not a static
    number. That regeneration pass lives inside create_tsr_document and only
    fires when mutation_entries are forwarded — dropping them silently
    de-links the delivered report."""
    out = tmp_path / "t.docx"
    assert render_tsr(_extraction(), str(out))["success"] is True

    xml = zipfile.ZipFile(out).read("word/document.xml").decode()
    assert "{{XREF" not in xml, "marker leaked into the document as literal text"
    # Entry 44 is a certified LOAN with no release -> an active encumbrance.
    assert re.search(r"REF\s+chainEntry44\s+\\r", xml), \
        "findings lost the live cross-reference to the charge entry"


# ---------------------------------------------------------------------------
# Bad input: an actionable sentence, never a traceback
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mutate, must_mention", [
    # missing top-level keys
    (lambda e: e.pop("land_details"), "land_details"),
    (lambda e: e.pop("mutation_entries"), "mutation_entries"),
    # wrong types
    (lambda e: e.__setitem__("land_details", []), "land_details"),
    (lambda e: e.__setitem__("mutation_entries", {}), "mutation_entries"),
    (lambda e: e.__setitem__("mutation_entries", "44, 607"), "mutation_entries"),
    (lambda e: e.__setitem__("entry_numbers", "44"), "entry_numbers"),
    # a malformed entry inside an otherwise fine list
    (lambda e: e["mutation_entries"].__setitem__(1, "607"), "mutation_entries[1]"),
    (lambda e: e["mutation_entries"][0].pop("entry_number"), "mutation_entries[0]"),
    # nothing to report on
    (lambda e: (e.__setitem__("mutation_entries", []),
                e.__setitem__("entry_numbers", [])), "entry"),
])
def test_bad_input_returns_a_named_error(tmp_path, mutate, must_mention):
    extraction = _extraction()
    mutate(extraction)

    out = tmp_path / "t.docx"
    result = render_tsr(extraction, str(out))  # must not raise

    assert result["success"] is False
    assert must_mention in result["error"], result["error"]
    assert not out.exists(), "a rejected extraction must not leave a half-written file"


def test_non_object_extraction_is_rejected(tmp_path):
    for junk in ([], "land_details", 7, None):
        result = render_tsr(junk, str(tmp_path / "t.docx"))
        assert result["success"] is False
        assert "land_details" in result["error"]


def test_missing_output_path_is_rejected():
    result = render_tsr(_extraction(), "")
    assert result["success"] is False
    assert "output" in result["error"]


# ---------------------------------------------------------------------------
# Client resolution
# ---------------------------------------------------------------------------

def test_unknown_client_lists_the_valid_ids(tmp_path):
    from core.clients import get_client_library

    result = render_tsr(_extraction(), str(tmp_path / "t.docx"), client="acme_solar")

    assert result["success"] is False
    assert "acme_solar" in result["error"]
    for known in get_client_library().clients:
        assert known in result["error"], result["error"]


def test_known_client_renders(tmp_path):
    from core.clients import get_client_library

    known = next(iter(get_client_library().clients), None)
    if known is None:
        pytest.skip("clients.json defines no clients in this checkout")

    out = tmp_path / "t.docx"
    result = render_tsr(_extraction(), str(out), client=known)
    assert result["success"] is True, result
    assert out.exists()


# ---------------------------------------------------------------------------
# The regression that pins "one implementation"
# ---------------------------------------------------------------------------

def test_pdf_pipeline_and_render_seam_agree(tmp_path, monkeypatch):
    """generate_tsr_from_pdf_optimized must produce byte-for-text the same
    document as render_tsr_from_extraction for the same extraction.

    This is the whole point of the seam. If the drafting logic is ever
    copy-pasted back into the PDF pipeline, the two will drift and this fails.
    """
    from tsr_generator.api import tsr_generator_optimized as opt
    from tsr_generator.extractors.unified_extractor import UnifiedExtractionResult

    extraction = _extraction()

    fake = UnifiedExtractionResult()
    fake.success = True
    fake.land_details = copy.deepcopy(extraction["land_details"])
    fake.entry_numbers = list(extraction["entry_numbers"])
    fake.mutation_entries = copy.deepcopy(extraction["mutation_entries"])

    monkeypatch.setattr(opt, "extract_text_from_pdf", lambda _p: "irrelevant text")
    monkeypatch.setattr(opt, "extract_all_unified", lambda _t: fake)

    via_pdf = tmp_path / "via_pdf.docx"
    pdf_result = opt.generate_tsr_from_pdf_optimized(
        "does-not-exist.pdf", str(via_pdf), log_tokens=False)
    assert pdf_result["success"] is True, pdf_result

    via_json = tmp_path / "via_json.docx"
    json_result = render_tsr_from_extraction(copy.deepcopy(extraction), str(via_json))
    assert json_result["success"] is True, json_result

    assert get_docx_text(str(via_pdf)) == get_docx_text(str(via_json))
    assert pdf_result["entries_count"] == json_result["entries_count"]
    assert pdf_result["entry_types"] == json_result["entry_types"]
    assert pdf_result["land_details"] == json_result["land_details"]


def test_request_metadata_overrides_survive_the_split(tmp_path):
    """The client/layout key injection and the survey override moved into
    render_tsr_from_extraction with the rest of steps 3-5."""
    extraction = _extraction()
    out = tmp_path / "t.docx"

    result = render_tsr_from_extraction(extraction, str(out), request_metadata={
        "survey_number": "150/p2",
        "village": "Vayor",
        "client_name": "Acme Solar Private Limited",
        # "" means "omit this line" — a missing key would re-insert the default
        "client_cin": "",
        "tsr_profile": "final_sample_v1",
    })

    assert result["success"] is True, result
    land = result["land_details"]
    assert land["survey_number"] == "150/p2"
    assert land["village_name"] == "Vayor"
    assert land["client_name"] == "Acme Solar Private Limited"
    assert land["client_cin"] == ""
    assert land["tsr_profile"] == "final_sample_v1"

    text = "\n".join(get_docx_text(str(out)))
    assert "Acme Solar Private Limited" in text
    # Descriptions were rewired onto the overridden survey number
    assert "Survey No. 150/p2" in text


def test_render_from_extraction_reports_errors_instead_of_raising(tmp_path):
    """A failure inside the document build comes back as a dict, so the CLI
    prints JSON rather than a traceback."""
    extraction = _extraction()
    # A directory where the .docx should be -> docx.save() cannot write
    (tmp_path / "t.docx").mkdir()

    result = render_tsr_from_extraction(extraction, str(tmp_path / "t.docx"))
    assert result["success"] is False
    assert result["error"]


# ---------------------------------------------------------------------------
# The documented contract must stay in the repo
# ---------------------------------------------------------------------------

def test_extraction_rules_reference_matches_the_prompt_constants():
    """references/extraction-rules.md exists so an agent doing the extraction
    follows the same drafting conventions as the CLI. If the Python constants
    move and the file does not, the two paths start drafting differently."""
    from pathlib import Path
    from tsr_generator.extractors import unified_extractor as ux

    doc = Path(ux.__file__).resolve().parents[2] / "references" / "extraction-rules.md"
    assert doc.exists(), f"missing {doc}"
    body = doc.read_text(encoding="utf-8")

    for name in ("ENTRY_TYPE_RULES", "FORMATTING_RULES",
                 "DESCRIPTION_EXAMPLES", "CERTIFICATION_PATTERNS"):
        constant = getattr(ux, name).strip()
        assert constant in body, f"{name} in unified_extractor.py has drifted from {doc.name}"


def test_extraction_rules_reference_documents_the_json_contract():
    from pathlib import Path
    from tsr_generator.extractors import unified_extractor as ux

    doc = Path(ux.__file__).resolve().parents[2] / "references" / "extraction-rules.md"
    body = doc.read_text(encoding="utf-8")
    for key in ("land_details", "entry_numbers", "mutation_entries",
                "certification_official"):
        assert key in body, f"the JSON contract in {doc.name} does not mention {key}"
    # the documented example must itself be valid JSON
    block = re.search(r"```json\n(.*?)```", body, re.S)
    assert block, "no ```json contract block in extraction-rules.md"
    parsed = json.loads(block.group(1))
    assert set(parsed) >= {"land_details", "entry_numbers", "mutation_entries"}
