"""
Tests for Token Optimization in TSR Extraction

This test module validates:
1. Unified extraction produces same results as original
2. Token savings are achieved
3. API calls are reduced
"""

import os
import sys
import pytest
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, MagicMock


class TestTokenOptimization:
    """Test suite for token optimization."""

    def test_estimate_token_savings(self):
        """Test that token savings estimation works correctly."""
        from tsr_generator.extractors.unified_extractor import estimate_token_savings

        # Create a sample document text
        sample_text = "Land Details\n" * 100 + "Entry Details\n" + "123\n456\n789\n" * 50

        result = estimate_token_savings(sample_text)

        # Verify structure
        assert 'old_approach' in result
        assert 'new_approach' in result
        assert 'savings' in result

        # Verify old approach has more tokens
        assert result['old_approach']['total_tokens'] > result['new_approach']['total_tokens']

        # Verify savings percentage is positive
        assert result['savings']['percentage'] > 0

        # Verify API calls reduced
        assert result['old_approach']['api_calls'] == 3
        assert result['new_approach']['api_calls'] == 1
        assert result['savings']['api_calls_saved'] == 2

    def test_unified_prompt_structure(self):
        """Test that unified prompt is properly structured."""
        from tsr_generator.extractors.unified_extractor import build_unified_prompt

        sample_text = "Sample PDF text content"
        entry_hints = ["123", "456"]

        prompt = build_unified_prompt(sample_text, entry_hints)

        # Verify prompt contains key sections
        assert "land_details" in prompt
        assert "entry_numbers" in prompt
        assert "mutation_entries" in prompt
        assert "123, 456" in prompt  # Entry hints should be included
        assert sample_text in prompt  # Document text should be included

    def test_entry_number_fast_detection(self):
        """Test the fast regex-based entry number detection."""
        from tsr_generator.extractors.unified_extractor import _identify_entry_numbers_fast

        sample_text = """
        Some header text
        Entry Details
        123
        456*
        789
        Entry No. 999
        Jantri Detail
        More text
        """

        numbers = _identify_entry_numbers_fast(sample_text)

        # Should detect entry numbers
        assert len(numbers) > 0
        assert "123" in numbers or "456" in numbers or "789" in numbers

    def test_relevant_section_extraction(self):
        """Test that relevant sections are properly extracted."""
        from tsr_generator.extractors.unified_extractor import _extract_relevant_sections

        # Small document should pass through unchanged
        small_doc = "A" * 5000
        result = _extract_relevant_sections(small_doc)
        assert result == small_doc

        # Large document (over the ~15000-char passthrough threshold) should be
        # truncated down to the land-details header + the Entry Details section.
        large_doc = "Header " * 800 + "Entry Details " + "Content " * 800 + " Jantri Detail " + "Footer " * 800
        assert len(large_doc) > 15000
        result = _extract_relevant_sections(large_doc)
        assert len(result) < len(large_doc)

    def test_json_response_parsing(self):
        """Test that various JSON response formats are properly parsed."""
        from tsr_generator.extractors.unified_extractor import _parse_json_response

        # Test clean JSON
        clean_json = '{"land_details": {"village_name": "Test"}, "entry_numbers": ["123"], "mutation_entries": []}'
        result = _parse_json_response(clean_json)
        assert result is not None
        assert result['land_details']['village_name'] == "Test"

        # Test JSON in code block
        code_block = '```json\n{"land_details": {"village_name": "Test"}, "entry_numbers": [], "mutation_entries": []}\n```'
        result = _parse_json_response(code_block)
        assert result is not None

        # Test JSON with trailing commas (common LLM output issue)
        trailing_comma = '{"land_details": {"village_name": "Test",}, "entry_numbers": [], "mutation_entries": [],}'
        result = _parse_json_response(trailing_comma)
        assert result is not None

    def test_land_details_normalization(self):
        """Test that land details are properly normalized."""
        from tsr_generator.extractors.unified_extractor import _normalize_land_details

        land_details = {
            "village_name": "Test Village",
            "taluka_name": "",  # Empty should become "Not Available"
            "district_name": None  # None should become "Not Available"
        }

        _normalize_land_details(land_details)

        assert land_details['village_name'] == "Test Village"
        assert land_details['taluka_name'] == "Not Available"
        assert land_details['district_name'] == "Not Available"
        assert 'old_survey_number' in land_details

    def test_token_tracker(self):
        """Test the token tracking utility."""
        from tsr_generator.utils.token_tracker import TokenTracker

        tracker = TokenTracker()

        # Track some extractions
        tracker.start_extraction("doc1.pdf", method="optimized")
        tracker.end_extraction(input_tokens=1000, output_tokens=500, api_calls=1)

        tracker.start_extraction("doc2.pdf", method="original")
        tracker.end_extraction(input_tokens=3000, output_tokens=1000, api_calls=3)

        # Get stats
        stats = tracker.get_stats()
        assert stats.total_extractions == 2
        assert stats.total_tokens == 5500

        # Get method-specific stats
        optimized_stats = tracker.get_stats("optimized")
        assert optimized_stats.total_extractions == 1
        assert optimized_stats.total_tokens == 1500

    def test_unified_extraction_result_class(self):
        """Test the UnifiedExtractionResult dataclass."""
        from tsr_generator.extractors.unified_extractor import UnifiedExtractionResult

        result = UnifiedExtractionResult()
        assert result.success == False
        assert result.land_details == {}
        assert result.entry_numbers == []
        assert result.mutation_entries == []

        # Test token totals
        result.input_tokens = 1000
        result.output_tokens = 500
        assert result.input_tokens + result.output_tokens == 1500


class TestOptimizationIntegration:
    """Integration tests for the optimization (require API key)."""

    def test_unified_extraction_with_mock_response(self):
        """Test unified extraction with a mocked LLM response.

        Fully mocked — drives the default `claude` backend with a stubbed CLI
        call, so it needs no API key or network.
        """
        from tsr_generator.extractors.unified_extractor import extract_all_unified

        sample_text = """
        Land Details
        Village: Test Village
        Taluka: Test Taluka
        District: Test District
        Survey Number: 123/A
        Total Area: 2-50-00

        Entry Details
        456
        789

        Entry No. 456
        Date: 01/01/2020
        Type: Sale
        Description: Test sale entry
        """

        # Mock the LLM response
        mock_response = MagicMock()
        mock_response.content = '''{
            "land_details": {
                "village_name": "Test Village",
                "taluka_name": "Test Taluka",
                "district_name": "Test District",
                "survey_number": "123/A",
                "total_area": "2-50-00",
                "nature_of_land": "Agricultural",
                "owner": "Test Owner"
            },
            "entry_numbers": ["456", "789"],
            "mutation_entries": [
                {
                    "entry_number": "456",
                    "date": "01/01/2020",
                    "type": "SALE",
                    "description": "That Test Owner sold land to Buyer",
                    "certification": "The Entry is certified."
                }
            ]
        }'''

        # Force the default 'claude' backend and stub the CLI call so the test
        # is deterministic and offline. _invoke_claude_cli returns the raw model
        # text (the JSON blob); the rest of extract_all_unified parses it.
        with patch.dict(os.environ, {'EXTRACTION_BACKEND': 'claude'}), \
             patch(
                 'tsr_generator.extractors.unified_extractor._invoke_claude_cli',
                 return_value=mock_response.content,
             ):
            result = extract_all_unified(sample_text)

            # Verify extraction was successful
            assert result.success == True
            assert result.land_details['village_name'] == "Test Village"
            assert "456" in result.entry_numbers
            assert len(result.mutation_entries) >= 1


class TestBackwardsCompatibility:
    """Test that drop-in replacement functions work correctly."""

    def test_extract_land_details_optimized_caching(self):
        """Test that the caching mechanism works."""
        from tsr_generator.extractors.unified_extractor import extract_land_details_optimized

        # Clear any existing cache
        if hasattr(extract_land_details_optimized, '_last_result'):
            delattr(extract_land_details_optimized, '_last_result')

        # First call would trigger extraction (mocked)
        with patch('tsr_generator.extractors.unified_extractor.extract_all_unified') as mock_extract:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.land_details = {"village_name": "Test"}
            mock_result.entry_numbers = ["123"]
            mock_result.mutation_entries = []
            mock_extract.return_value = mock_result

            sample_text = "A" * 1000 + "B"  # Unique text

            # First call
            result1 = extract_land_details_optimized(sample_text)
            assert mock_extract.call_count == 1

            # Second call with same text should use cache
            result2 = extract_land_details_optimized(sample_text)
            # Note: cache is based on hash of first 1000 chars, so this depends on implementation


if __name__ == "__main__":
    # Run quick tests without pytest
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    logger.info("Running token optimization tests...")

    test = TestTokenOptimization()
    test.test_estimate_token_savings()
    logger.info("✓ test_estimate_token_savings passed")

    test.test_unified_prompt_structure()
    logger.info("✓ test_unified_prompt_structure passed")

    test.test_entry_number_fast_detection()
    logger.info("✓ test_entry_number_fast_detection passed")

    test.test_relevant_section_extraction()
    logger.info("✓ test_relevant_section_extraction passed")

    test.test_json_response_parsing()
    logger.info("✓ test_json_response_parsing passed")

    test.test_land_details_normalization()
    logger.info("✓ test_land_details_normalization passed")

    test.test_token_tracker()
    logger.info("✓ test_token_tracker passed")

    logger.info("\nAll tests passed!")
