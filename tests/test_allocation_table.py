"""Partition / distribution allocations must render as a table, not prose.

The lawyer rebuilt this table by hand on both the Bodki 44 and 44/p1 reports
(2026-07-28 review), so the generator emits it directly.
"""
import pytest

from tsr_generator.document.docx_generator import _parse_allocation_table

DESC = (
    "That the said Lachhiben Rukhadbhai Bhadarka, Nathiben Rukhadbhai Bhadarka, "
    "Najubhai Hamabhai Bhammar and Hiteshbhai Hamabhai Bhammar distributed their "
    "joint land bearing Survey No. 44(125), 208p2(125) measuring 3-68-27 Hectare "
    "among themselves as follows:-\n"
    "Lachhiben Rukhadbhai Bhadarka, Najubhai Hamabhai Bhammar and Hiteshbhai "
    "Hamabhai Bhammar (joint account) - Survey No. 208/p2 - 1-70-98\n"
    "Nathiben Rukhadbhai Bhadarka (independent account) - Survey No. 44 - 1-29-46\n"
    "Najubhai Hamabhai Bhammar and Hiteshbhai Hamabhai Bhammar (joint account) "
    "- Survey No. 44 - 0-67-83\n"
    "\n"
    "The distribution/Partition of the shares as mentioned above was recorded "
    "based on their application, deed of partition and affidavits before the Notary."
)


def test_parses_three_allocation_rows():
    parsed = _parse_allocation_table(DESC)
    assert parsed is not None
    _, rows, _ = parsed
    assert len(rows) == 3
    assert rows[1]["name"] == "Nathiben Rukhadbhai Bhadarka (independent account)"
    assert rows[1]["survey"] == "44"
    assert rows[1]["area"] == "1-29-46"


def test_areas_match_the_source_record():
    """Areas must sum to the stated joint total 3-68-27."""
    _, rows, _ = _parse_allocation_table(DESC)
    assert [r["area"] for r in rows] == ["1-70-98", "1-29-46", "0-67-83"]


def test_lead_in_and_closing_are_preserved():
    pre, _, post = _parse_allocation_table(DESC)
    assert pre.startswith("That the said")
    assert pre.rstrip().endswith("as follows:-")
    assert "affidavits before the Notary" in post


def test_numbered_rows_are_accepted():
    """_number_names_after_follows may prefix rows with '1.' before we parse."""
    numbered = DESC.replace("Lachhiben Rukhadbhai Bhadarka, Najubhai",
                            "1. Lachhiben Rukhadbhai Bhadarka, Najubhai")
    parsed = _parse_allocation_table(numbered)
    assert parsed is not None
    assert not parsed[1][0]["name"].startswith("1.")


def test_single_allocation_stays_prose():
    """One beneficiary is a sentence, not a table - matches the prompt rule."""
    one = ("That X distributed his land as follows:-\n"
           "Nathiben Rukhadbhai Bhadarka - Survey No. 44 - 1-29-46")
    assert _parse_allocation_table(one) is None


def test_non_allocation_description_is_untouched():
    assert _parse_allocation_table(
        "That Rukhadbhai Lakhabhai Bhadarka took a loan of Rs. 2,25,000/- on land "
        "bearing Survey No. 44(125) from Bank of India, Talaja Branch."
    ) is None
