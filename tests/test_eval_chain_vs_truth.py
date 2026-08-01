"""Tests for the Phase 0 chain measurement harness (scripts/eval_chain_vs_truth.py).

Fixtures are verbatim excerpts of AnyRoR record text (Bhungar, Talaja, Bhavnagar,
fetched 2026-07-31), so these lock in the real layout including the trailing-'*'
index marker that originally truncated the parse.
"""
import os
import sys

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
)
import eval_chain_vs_truth as eval_chain  # noqa: E402


# Bhungar 57p1 -- index carries starred entries (470*, 644*)
INDEX_WITH_STARS = """Entry Details
117
177
290
291
470*
644*
1095
1134
1156
1184
નોંધ નંબર
નોંધની
તારીખ
"""

# Bhungar 57p3 -- plain index, no stars
INDEX_PLAIN = """Entry Details
117
290
291
309
446
454
689
760
909
1146
નોંધ નંબર
"""

DETAIL_ROWS = """1146
22/12/2023
બોજા મુક્તિ
પ્રમાણિત
760
26/02/2016
બોજા મુક્તિ
446
09/10/2006
બોજો દાખલ
"""


class TestExtractEntryIndex:
    def test_plain_index(self):
        entries, starred = eval_chain.extract_entry_index(INDEX_PLAIN)
        assert entries == ["117", "290", "291", "309", "446",
                           "454", "689", "760", "909", "1146"]
        assert starred == []

    def test_starred_entries_do_not_truncate_the_parse(self):
        """Regression: '470*' failed \\d+ and silently cut the index to 4 entries."""
        entries, starred = eval_chain.extract_entry_index(INDEX_WITH_STARS)
        assert entries == ["117", "177", "290", "291", "470",
                           "644", "1095", "1134", "1156", "1184"]
        assert starred == ["470", "644"]

    def test_missing_heading(self):
        assert eval_chain.extract_entry_index("no such section") == ([], [])


class TestExtractDetailRows:
    def test_detail_rows_and_years(self):
        detailed, years = eval_chain.extract_detail_rows(DETAIL_ROWS)
        assert detailed == ["1146", "760", "446"]
        assert years == {"1146": 2023, "760": 2016, "446": 2006}

    def test_index_only_entries_are_those_without_detail_rows(self):
        index, _ = eval_chain.extract_entry_index(INDEX_PLAIN)
        detailed, _ = eval_chain.extract_detail_rows(DETAIL_ROWS)
        assert [e for e in index if e not in detailed] == [
            "117", "290", "291", "309", "454", "689", "909",
        ]


class TestNormalizeSurvey:
    @pytest.mark.parametrize("filename,expected", [
        ("44 - complete final.docx", "44"),
        ("44-p1 - complete final.docx", "44p1"),
        ("45-4p2 - complete Final.docx", "454p2"),
        ("57p1 - complete fina;.docx", "57p1"),
        ("TSR_Bhavnagar_Talaja_Bhunagar_57p3.docx", "57p3"),
        ("Original_Bhavnagar_Talaja_Bhunagar_56.pdf", "56"),
    ])
    def test_filename_variants_map_to_survey_key(self, filename, expected):
        assert eval_chain.normalize_survey(filename) == expected

    def test_generated_pdf_and_docx_pair_up(self):
        assert (eval_chain.normalize_survey("Original_Bhavnagar_Talaja_Bhunagar_57p3.pdf")
                == eval_chain.normalize_survey("TSR_Bhavnagar_Talaja_Bhunagar_57p3.docx"))


class TestPhantomAndMissingDetection:
    def test_khata_numbers_misread_as_entries_are_flagged(self):
        """Bhungar 57p3: 106/110/116/126 are khata numbers from the bulk-loan
        lists inside entries 446/454, and 290 was dropped entirely."""
        index, _ = eval_chain.extract_entry_index(INDEX_PLAIN)
        generated = ["106", "110", "116", "117", "126", "291", "309",
                     "446", "454", "689", "760", "909", "1146"]
        assert [e for e in generated if e not in index] == ["106", "110", "116", "126"]
        assert [e for e in index if e not in generated] == ["290"]

    def test_clean_chain_has_no_diff(self):
        index, _ = eval_chain.extract_entry_index(INDEX_PLAIN)
        assert [e for e in index if e not in index] == []


class TestSummarize:
    def test_era_split_uses_the_cross_fill_cutoff(self):
        assert eval_chain.CROSS_FILL_CUTOFF_YEAR == 1993
        reports = [
            eval_chain.SurveyReport(survey="a", index_entries=["1", "2"],
                                    entry_years={"1": 1962, "2": 2006}),
        ]
        summary = eval_chain.summarize(reports)
        assert summary["pre_1993"] == 1
        assert summary["post_1993"] == 1
        assert summary["pre_1993_pct"] == 50.0
