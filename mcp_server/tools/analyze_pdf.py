"""MCP Tool: Analyze PDF land record and extract structured data"""

import os
import sys
import json
import logging
from typing import Dict, Any, Optional

# Add parent directory to path to import project modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from tsr_generator.utils.pdf_utils import extract_text_from_pdf
from tsr_generator.extractors.land_details import extract_land_details
from tsr_generator.extractors.entry_details import extract_entry_details

logger = logging.getLogger(__name__)


def execute(
    pdf_path: str,
    extract_land: bool = True,
    extract_entries: bool = True,
    include_raw_text: bool = False
) -> str:
    """
    Analyze land record PDF and extract structured data.

    Args:
        pdf_path: Path to the PDF file to analyze
        extract_land: Extract land details (default: True)
        extract_entries: Extract mutation entries (default: True)
        include_raw_text: Include raw extracted text in output (default: False)

    Returns:
        JSON string with extracted data
    """
    try:
        logger.info(f"Analyzing PDF: {pdf_path}")

        # Validate PDF exists
        if not os.path.exists(pdf_path):
            return json.dumps({
                "success": False,
                "error": f"PDF file not found: {pdf_path}"
            }, indent=2)

        # Extract text from PDF
        logger.info("Extracting text from PDF...")
        pdf_text = extract_text_from_pdf(pdf_path)

        if not pdf_text or not pdf_text.strip():
            return json.dumps({
                "success": False,
                "error": "Could not extract text from PDF. File may be corrupted or empty."
            }, indent=2)

        result = {
            "success": True,
            "pdf_path": pdf_path,
            "pdf_size_bytes": os.path.getsize(pdf_path),
            "text_length": len(pdf_text)
        }

        # Extract land details if requested
        if extract_land:
            logger.info("Extracting land details...")
            try:
                land_details = extract_land_details(pdf_text)
                # Convert to dict if it's a Pydantic model
                if hasattr(land_details, 'model_dump'):
                    land_details = land_details.model_dump()
                elif hasattr(land_details, 'dict'):
                    land_details = land_details.dict()
                result["land_details"] = land_details
            except Exception as e:
                logger.error(f"Error extracting land details: {e}", exc_info=True)
                result["land_details_error"] = str(e)

        # Extract entries if requested
        if extract_entries:
            logger.info("Extracting mutation entries...")
            try:
                entries = extract_entry_details(pdf_text)
                # Convert entries to dict format
                entries_list = []
                for entry in entries:
                    if hasattr(entry, 'model_dump'):
                        entries_list.append(entry.model_dump())
                    elif hasattr(entry, 'dict'):
                        entries_list.append(entry.dict())
                    elif isinstance(entry, dict):
                        entries_list.append(entry)
                    else:
                        entries_list.append(str(entry))

                result["entries"] = entries_list
                result["entry_count"] = len(entries_list)

                # Create summary by entry type
                entry_types = {}
                for entry in entries_list:
                    entry_type = entry.get('entry_type', 'Unknown')
                    entry_types[entry_type] = entry_types.get(entry_type, 0) + 1

                result["entry_summary"] = entry_types

            except Exception as e:
                logger.error(f"Error extracting entries: {e}", exc_info=True)
                result["entries_error"] = str(e)

        # Include raw text if requested
        if include_raw_text:
            result["raw_text"] = pdf_text

        return json.dumps(result, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Error analyzing PDF: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }, indent=2)


if __name__ == "__main__":
    # Test the tool
    import argparse

    parser = argparse.ArgumentParser(description="Analyze PDF land record")
    parser.add_argument("pdf_path", help="Path to PDF file")
    parser.add_argument("--no-land", action="store_true", help="Skip land details extraction")
    parser.add_argument("--no-entries", action="store_true", help="Skip entries extraction")
    parser.add_argument("--include-text", action="store_true", help="Include raw text in output")

    args = parser.parse_args()

    result = execute(
        pdf_path=args.pdf_path,
        extract_land=not args.no_land,
        extract_entries=not args.no_entries,
        include_raw_text=args.include_text
    )

    print(result)
