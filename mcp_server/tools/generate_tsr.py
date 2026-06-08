"""MCP Tool: Generate Title Search Report (TSR) DOCX document"""

import os
import sys
import json
import logging
from typing import Optional, List

# Add parent directory to path to import project modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Unified (optimized) extraction is the only path; import the package-level entry point.
from tsr_generator import generate_tsr_from_pdf

logger = logging.getLogger(__name__)


def execute(
    pdf_path: str,
    output_path: Optional[str] = None,
    custom_findings: Optional[List[str]] = None,
    advocate_name: Optional[str] = None,
    advocate_address: Optional[str] = None,
    use_agent: bool = False
) -> str:
    """
    Generate Title Search Report (TSR) DOCX document from PDF.

    Args:
        pdf_path: Path to the PDF land record file
        output_path: Path for output DOCX file (default: auto-generated)
        custom_findings: List of custom findings to add to the report
        advocate_name: Custom advocate name for letterhead
        advocate_address: Custom advocate address for letterhead
        use_agent: Use AI agent mode for extraction (experimental)

    Returns:
        JSON string with generation result
    """
    try:
        logger.info(f"Generating TSR from PDF: {pdf_path}")

        # Validate PDF exists
        if not os.path.exists(pdf_path):
            return json.dumps({
                "success": False,
                "error": f"PDF file not found: {pdf_path}"
            }, indent=2)

        # Auto-generate output path if not provided
        if not output_path:
            pdf_dir = os.path.dirname(pdf_path)
            pdf_name = os.path.basename(pdf_path)
            tsr_name = pdf_name.replace('.pdf', '_TSR.docx')
            output_path = os.path.join(pdf_dir, tsr_name)

        # Ensure output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        # Generate TSR
        logger.info(f"Generating TSR to: {output_path}")

        # Build kwargs for generator
        gen_kwargs = {}
        if custom_findings:
            gen_kwargs['custom_findings'] = custom_findings
        if advocate_name:
            gen_kwargs['advocate_name'] = advocate_name
        if advocate_address:
            gen_kwargs['advocate_address'] = advocate_address
        if use_agent:
            gen_kwargs['use_agent'] = use_agent

        # Call the TSR generator
        generate_tsr_from_pdf(pdf_path, output_path, **gen_kwargs)

        # Verify output was created
        if not os.path.exists(output_path):
            return json.dumps({
                "success": False,
                "error": "TSR generation completed but output file was not created"
            }, indent=2)

        # Get file size
        file_size = os.path.getsize(output_path)

        return json.dumps({
            "success": True,
            "tsr_path": output_path,
            "tsr_size_bytes": file_size,
            "tsr_size_kb": round(file_size / 1024, 2),
            "pdf_path": pdf_path,
            "custom_findings_count": len(custom_findings) if custom_findings else 0,
            "used_agent_mode": use_agent
        }, indent=2)

    except Exception as e:
        logger.error(f"Error generating TSR: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }, indent=2)


if __name__ == "__main__":
    # Test the tool
    import argparse

    parser = argparse.ArgumentParser(description="Generate TSR document")
    parser.add_argument("pdf_path", help="Path to PDF file")
    parser.add_argument("--output", help="Output DOCX path")
    parser.add_argument("--finding", action="append", dest="findings", help="Add custom finding (can be used multiple times)")
    parser.add_argument("--advocate-name", help="Custom advocate name")
    parser.add_argument("--advocate-address", help="Custom advocate address")
    parser.add_argument("--use-agent", action="store_true", help="Use AI agent mode")

    args = parser.parse_args()

    result = execute(
        pdf_path=args.pdf_path,
        output_path=args.output,
        custom_findings=args.findings,
        advocate_name=args.advocate_name,
        advocate_address=args.advocate_address,
        use_agent=args.use_agent
    )

    print(result)
