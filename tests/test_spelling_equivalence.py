"""Regression guards for the ee/i romanization equivalence.

AnyRoR transliterates ઈ as 'ee' ('Bodkee'), while the lawyer's reports use the
conventional 'i' ('Bodki'). Before 2026-07-28 passing "Bodki" was rejected with
HTTP 400: the consonant skeletons matched ('bdk') and the candidate was unique,
but the character ratio was 0.727, under the 0.80 guard. The equivalence makes
both spellings canonicalize identically WITHOUT weakening that guard.
"""
import pytest

from utils.json_translations import _canon_alpha, _consonant_skeleton


def test_ee_and_i_canonicalize_identically():
    assert _canon_alpha("Bodki") == _canon_alpha("Bodkee")
    assert _canon_alpha("Bodki") == _canon_alpha("Bodkee - 094")


def test_existing_equivalences_still_hold():
    assert _canon_alpha("Badargarh") == _canon_alpha("Badargadh")
    assert _canon_alpha("Wadala") == _canon_alpha("Vadala")


def test_dropdown_code_is_stripped():
    assert _canon_alpha("Bodkee - 094") == "bodki"


def test_consonant_skeleton_unaffected():
    # skeleton drops vowels anyway, so ee/i cannot change it
    assert _consonant_skeleton("Bodki") == _consonant_skeleton("Bodkee") == "bdk"


def test_distinct_villages_do_not_collide():
    """ee/i must not merge genuinely different names."""
    assert _canon_alpha("Borda") != _canon_alpha("Bodki")
    assert _canon_alpha("Borda") != _canon_alpha("Bordee")


@pytest.mark.parametrize("spelling", ["Bodki", "Bodkee", "BODKI", "bodki"])
def test_village_resolves_either_spelling(spelling):
    from services.translation_service import get_translation_service
    tr = get_translation_service()
    d = tr.translate_to_gujarati("Bhavnagar", context="district")
    t = tr.translate_to_gujarati("Talaja", context="taluka", parent_district=d)
    guj = tr.translate_to_gujarati(
        spelling, context="village", parent_district=d, parent_taluka=t
    )
    assert guj.startswith("બોડકી")


def test_ambiguous_spelling_is_still_refused():
    """'Bordi' shares skeleton 'brd' with BOTH બોરડા and બોરડી - must refuse,
    never guess. A wrong village is far worse than no match."""
    from services.translation_service import get_translation_service
    from core.exceptions import TranslationException
    tr = get_translation_service()
    d = tr.translate_to_gujarati("Bhavnagar", context="district")
    t = tr.translate_to_gujarati("Talaja", context="taluka", parent_district=d)
    with pytest.raises(TranslationException):
        tr.translate_to_gujarati(
            "Bordi", context="village", parent_district=d, parent_taluka=t
        )


def test_report_uses_gujarat_not_gujrat():
    """The DOCX template said '(Gujrat)'; reports must read '(Gujarat)'."""
    from pathlib import Path
    src = Path("tsr_generator/document/tsr_document.py").read_text()
    assert "(Gujrat)" not in src
    assert "(Gujarat)" in src
