#!/usr/bin/env python3
"""
MCP Server for TSR Generation Tools

This server exposes tools for:
- Fetching PDFs from Gujarat AnyRoR website
- Analyzing land record PDFs
- Generating Title Search Report documents
- Batch processing multiple records
"""

import asyncio
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# Import our tools
from tools import fetch_pdf, analyze_pdf, generate_tsr, batch_process

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create MCP server
server = Server("tsr-tools")

logger.info("Initializing TSR Tools MCP Server")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """List all available tools."""
    return [
        types.Tool(
            name="fetch_pdf_from_anyror",
            description=(
                "Fetch land record PDF from Gujarat AnyRoR website. "
                "Accepts district, taluka, village, and survey number. "
                "Automatically translates English names to Gujarati if needed. "
                "Returns PDF path and metadata."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "district": {
                        "type": "string",
                        "description": "District name (English or Gujarati), e.g., 'Kutch' or 'કચ્છ'"
                    },
                    "taluka": {
                        "type": "string",
                        "description": "Taluka name (English or Gujarati), e.g., 'Bhuj' or 'ભુજ'"
                    },
                    "village": {
                        "type": "string",
                        "description": "Village name (English or Gujarati), e.g., 'Trambo' or 'ટ્રાંબો'"
                    },
                    "survey_number": {
                        "type": "string",
                        "description": "Survey number in any format, e.g., '51', '51/1', 'પાટ નં ૫૧'"
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory (default: 'output')",
                        "default": "output"
                    },
                    "headless": {
                        "type": "boolean",
                        "description": "Run browser in headless mode (default: true)",
                        "default": True
                    },
                    "regenerate": {
                        "type": "boolean",
                        "description": "Force regenerate PDF even if it exists (default: false)",
                        "default": False
                    }
                },
                "required": ["district", "taluka", "village", "survey_number"]
            }
        ),
        types.Tool(
            name="analyze_land_record",
            description=(
                "Analyze land record PDF and extract structured data. "
                "Extracts land details (owner, area, survey numbers) and "
                "mutation entries (sales, mortgages, inheritances, etc.). "
                "Returns structured JSON with all extracted information."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pdf_path": {
                        "type": "string",
                        "description": "Path to the PDF file to analyze"
                    },
                    "extract_land": {
                        "type": "boolean",
                        "description": "Extract land details (default: true)",
                        "default": True
                    },
                    "extract_entries": {
                        "type": "boolean",
                        "description": "Extract mutation entries (default: true)",
                        "default": True
                    },
                    "include_raw_text": {
                        "type": "boolean",
                        "description": "Include raw extracted text in output (default: false)",
                        "default": False
                    }
                },
                "required": ["pdf_path"]
            }
        ),
        types.Tool(
            name="generate_tsr_document",
            description=(
                "Generate Title Search Report (TSR) DOCX document from land record PDF. "
                "Creates professional legal document with letterhead, land details, "
                "chain of title analysis, and standard findings. "
                "Supports custom findings and advocate information."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pdf_path": {
                        "type": "string",
                        "description": "Path to the PDF land record file"
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Path for output DOCX file (default: auto-generated)"
                    },
                    "custom_findings": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of custom findings to add to the report"
                    },
                    "advocate_name": {
                        "type": "string",
                        "description": "Custom advocate name for letterhead"
                    },
                    "advocate_address": {
                        "type": "string",
                        "description": "Custom advocate address for letterhead"
                    },
                    "use_agent": {
                        "type": "boolean",
                        "description": "Use AI agent mode for extraction (experimental, default: false)",
                        "default": False
                    }
                },
                "required": ["pdf_path"]
            }
        ),
        types.Tool(
            name="batch_process_records",
            description=(
                "Batch process multiple land records from an Excel file. "
                "Processes records in parallel, fetching PDFs and generating TSRs. "
                "Auto-detects Excel columns using AI or accepts manual column mapping. "
                "Returns processing statistics and creates results Excel file."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "excel_path": {
                        "type": "string",
                        "description": "Path to Excel file with land record data"
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory (default: 'output')",
                        "default": "output"
                    },
                    "max_workers": {
                        "type": "integer",
                        "description": "Number of parallel workers (default: 3)",
                        "default": 3,
                        "minimum": 1,
                        "maximum": 10
                    },
                    "headless": {
                        "type": "boolean",
                        "description": "Run browser in headless mode (default: true)",
                        "default": True
                    },
                    "regenerate_pdf": {
                        "type": "boolean",
                        "description": "Force regenerate PDFs (default: false)",
                        "default": False
                    },
                    "auto_detect_columns": {
                        "type": "boolean",
                        "description": "Auto-detect columns using AI (default: true)",
                        "default": True
                    },
                    "column_mapping": {
                        "type": "object",
                        "description": "Manual column mapping (overrides auto-detect). Keys: district, taluka, village, survey",
                        "properties": {
                            "district": {"type": "string"},
                            "taluka": {"type": "string"},
                            "village": {"type": "string"},
                            "survey": {"type": "string"}
                        }
                    }
                },
                "required": ["excel_path"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Any) -> list[types.TextContent]:
    """Execute a tool and return the result."""
    logger.info(f"Tool called: {name} with arguments: {arguments}")

    try:
        if name == "fetch_pdf_from_anyror":
            result = fetch_pdf.execute(**arguments)
        elif name == "analyze_land_record":
            result = analyze_pdf.execute(**arguments)
        elif name == "generate_tsr_document":
            result = generate_tsr.execute(**arguments)
        elif name == "batch_process_records":
            result = batch_process.execute(**arguments)
        else:
            error_msg = f"Unknown tool: {name}"
            logger.error(error_msg)
            result = json.dumps({"success": False, "error": error_msg})

        logger.info(f"Tool {name} completed successfully")
        return [types.TextContent(type="text", text=result)]

    except Exception as e:
        logger.error(f"Error executing tool {name}: {e}", exc_info=True)
        error_result = json.dumps({
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        })
        return [types.TextContent(type="text", text=error_result)]


async def main():
    """Run the MCP server."""
    logger.info("Starting TSR Tools MCP Server...")
    async with stdio_server() as (read_stream, write_stream):
        logger.info("MCP Server running on stdio")
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise
