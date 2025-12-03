"""MCP Tool: Batch process multiple land records"""

import os
import sys
import json
import logging
from typing import Optional, Dict, Any

# Add parent directory to path to import project modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import pandas as pd
from services.parallel_processing_service import ParallelProcessingService
from utils.ai_column_detector import auto_detect_columns

logger = logging.getLogger(__name__)


def execute(
    excel_path: str,
    output_dir: str = "output",
    max_workers: int = 3,
    headless: bool = True,
    regenerate_pdf: bool = False,
    auto_detect_columns: bool = True,
    column_mapping: Optional[Dict[str, str]] = None
) -> str:
    """
    Batch process multiple land records from an Excel file.

    Args:
        excel_path: Path to Excel file with land record data
        output_dir: Base output directory (default: "output")
        max_workers: Number of parallel workers (default: 3)
        headless: Run browser in headless mode (default: True)
        regenerate_pdf: Force regenerate PDFs (default: False)
        auto_detect_columns: Auto-detect columns using AI (default: True)
        column_mapping: Manual column mapping (overrides auto-detect)
                       Format: {"district": "District", "taluka": "Taluka", ...}

    Returns:
        JSON string with batch processing results
    """
    try:
        logger.info(f"Batch processing Excel file: {excel_path}")

        # Validate Excel file exists
        if not os.path.exists(excel_path):
            return json.dumps({
                "success": False,
                "error": f"Excel file not found: {excel_path}"
            }, indent=2)

        # Read Excel file
        try:
            df = pd.read_excel(excel_path)
            logger.info(f"Loaded {len(df)} records from Excel")
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Failed to read Excel file: {str(e)}"
            }, indent=2)

        # Detect or use provided column mapping
        if column_mapping:
            logger.info("Using provided column mapping")
            col_map = column_mapping
        elif auto_detect_columns:
            logger.info("Auto-detecting columns using AI...")
            try:
                col_map, detection_method = auto_detect_columns(df, logger)
                logger.info(f"Detected columns: {col_map} (method: {detection_method})")
            except Exception as e:
                return json.dumps({
                    "success": False,
                    "error": f"Column detection failed: {str(e)}",
                    "help": "Please provide column_mapping manually"
                }, indent=2)
        else:
            # Try to use standard column names
            col_map = {
                "district": "District",
                "taluka": "Taluka",
                "village": "Village",
                "survey": "Survey Number"
            }
            logger.info(f"Using default column mapping: {col_map}")

        # Validate columns exist in DataFrame
        missing_cols = []
        for key, col_name in col_map.items():
            if col_name not in df.columns:
                missing_cols.append(col_name)

        if missing_cols:
            return json.dumps({
                "success": False,
                "error": f"Required columns not found in Excel: {missing_cols}",
                "available_columns": df.columns.tolist(),
                "help": "Please provide correct column_mapping"
            }, indent=2)

        # Initialize parallel processing service
        service = ParallelProcessingService(
            output_base_dir=output_dir,
            max_workers=max_workers,
            headless=headless,
            logger=logger
        )

        # Process the batch
        logger.info(f"Starting batch processing with {max_workers} workers...")
        results = service.process_dataframe(
            df=df,
            col_map=col_map,
            regenerate_pdf=regenerate_pdf,
            generate_tsr=True
        )

        # Compile statistics
        success_count = sum(1 for r in results if r.success)
        error_count = len(results) - success_count
        errors = [
            {
                "index": i,
                "error": r.error
            }
            for i, r in enumerate(results)
            if not r.success
        ]

        # Create results summary
        result_summary = {
            "success": True,
            "total_records": len(results),
            "successful": success_count,
            "failed": error_count,
            "success_rate": round((success_count / len(results)) * 100, 2) if results else 0,
            "output_directory": output_dir,
            "column_mapping_used": col_map,
            "max_workers": max_workers
        }

        if errors:
            result_summary["errors"] = errors[:10]  # Limit to first 10 errors
            if error_count > 10:
                result_summary["additional_errors"] = error_count - 10

        # Save results to Excel
        try:
            results_df = df.copy()
            results_df['Success'] = [r.success for r in results]
            results_df['PDF_Path'] = [r.pdf_path if r.pdf_path else '' for r in results]
            results_df['TSR_Path'] = [r.tsr_path if r.tsr_path else '' for r in results]
            results_df['Error'] = [r.error if r.error else '' for r in results]

            results_excel = os.path.join(output_dir, "batch_results.xlsx")
            results_df.to_excel(results_excel, index=False)
            result_summary["results_excel"] = results_excel
            logger.info(f"Results saved to {results_excel}")
        except Exception as e:
            logger.warning(f"Could not save results Excel: {e}")

        return json.dumps(result_summary, indent=2)

    except Exception as e:
        logger.error(f"Error in batch processing: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }, indent=2)


if __name__ == "__main__":
    # Test the tool
    import argparse

    parser = argparse.ArgumentParser(description="Batch process land records")
    parser.add_argument("excel_path", help="Path to Excel file")
    parser.add_argument("--output-dir", default="output", help="Output directory")
    parser.add_argument("--workers", type=int, default=3, help="Number of parallel workers")
    parser.add_argument("--visible", action="store_true", help="Run browser in visible mode")
    parser.add_argument("--regenerate", action="store_true", help="Force regenerate PDFs")
    parser.add_argument("--no-auto-detect", action="store_true", help="Disable auto column detection")

    args = parser.parse_args()

    result = execute(
        excel_path=args.excel_path,
        output_dir=args.output_dir,
        max_workers=args.workers,
        headless=not args.visible,
        regenerate_pdf=args.regenerate,
        auto_detect_columns=not args.no_auto_detect
    )

    print(result)
