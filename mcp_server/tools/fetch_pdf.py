"""MCP Tool: Fetch PDF from Gujarat AnyRoR website"""

import os
import sys
import json
import logging
from typing import Dict, Any

# Add parent directory to path to import project modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from services.processing_service import LandRecordProcessor
from utils.json_translations import translate_to_gujarati, TranslationNotFoundError
from utils.survey_utils import convert_survey_number

logger = logging.getLogger(__name__)


def execute(
    district: str,
    taluka: str,
    village: str,
    survey_number: str,
    output_dir: str = "output",
    headless: bool = True,
    regenerate: bool = False
) -> str:
    """
    Fetch land record PDF from Gujarat AnyRoR website.

    Args:
        district: District name (English or Gujarati)
        taluka: Taluka name (English or Gujarati)
        village: Village name (English or Gujarati)
        survey_number: Survey number (can be in various formats)
        output_dir: Base output directory (default: "output")
        headless: Run browser in headless mode (default: True)
        regenerate: Force regenerate PDF even if it exists (default: False)

    Returns:
        JSON string with result details
    """
    try:
        logger.info(f"Fetching PDF for {district}/{taluka}/{village}/{survey_number}")

        # Translate to Gujarati if needed
        try:
            district_guj = translate_to_gujarati(district, context='district')
            taluka_guj = translate_to_gujarati(taluka, context='taluka')
            village_guj = translate_to_gujarati(village, context='village')
            survey_guj = convert_survey_number(survey_number)
        except TranslationNotFoundError as e:
            return json.dumps({
                "success": False,
                "error": f"Translation error: {str(e)}",
                "help": "Please provide valid Gujarat district/taluka/village names"
            }, indent=2)

        # Initialize processor
        processor = LandRecordProcessor(
            output_base_dir=output_dir,
            headless=headless,
            logger=logger
        )

        # Fetch PDF (without generating TSR)
        result = processor.fetch_pdf_and_tsr(
            district_guj=district_guj,
            taluka_guj=taluka_guj,
            village_guj=village_guj,
            survey_number_guj=survey_guj,
            regenerate_pdf=regenerate,
            generate_tsr=False
        )

        if not result.success:
            return json.dumps({
                "success": False,
                "error": result.error
            }, indent=2)

        # Get PDF metadata
        pdf_path = result.pdf_path
        pdf_size = os.path.getsize(pdf_path) if pdf_path and os.path.exists(pdf_path) else 0

        # Try to get page count
        page_count = None
        try:
            from PyPDF2 import PdfReader
            if pdf_path and os.path.exists(pdf_path):
                with open(pdf_path, 'rb') as f:
                    reader = PdfReader(f)
                    page_count = len(reader.pages)
        except Exception as e:
            logger.warning(f"Could not get PDF page count: {e}")

        return json.dumps({
            "success": True,
            "pdf_path": pdf_path,
            "pdf_size_bytes": pdf_size,
            "pdf_size_mb": round(pdf_size / (1024 * 1024), 2),
            "page_count": page_count,
            "location": {
                "district": district,
                "taluka": taluka,
                "village": village,
                "survey_number": survey_number
            },
            "gujarati_inputs": {
                "district": district_guj,
                "taluka": taluka_guj,
                "village": village_guj,
                "survey_number": survey_guj
            }
        }, indent=2)

    except Exception as e:
        logger.error(f"Error fetching PDF: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }, indent=2)


if __name__ == "__main__":
    # Test the tool
    import argparse

    parser = argparse.ArgumentParser(description="Fetch PDF from AnyRoR")
    parser.add_argument("--district", required=True, help="District name")
    parser.add_argument("--taluka", required=True, help="Taluka name")
    parser.add_argument("--village", required=True, help="Village name")
    parser.add_argument("--survey-number", required=True, help="Survey number")
    parser.add_argument("--output-dir", default="output", help="Output directory")
    parser.add_argument("--visible", action="store_true", help="Run browser in visible mode")
    parser.add_argument("--regenerate", action="store_true", help="Force regenerate PDF")

    args = parser.parse_args()

    result = execute(
        district=args.district,
        taluka=args.taluka,
        village=args.village,
        survey_number=args.survey_number,
        output_dir=args.output_dir,
        headless=not args.visible,
        regenerate=args.regenerate
    )

    print(result)
