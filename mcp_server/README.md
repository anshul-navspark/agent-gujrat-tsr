# TSR Tools MCP Server

Model Context Protocol (MCP) server for Gujarat Title Search Report (TSR) generation tools.

## Overview

This MCP server exposes four specialized tools for automating land record processing and TSR generation:

1. **fetch_pdf_from_anyror** - Fetch land record PDFs from Gujarat AnyRoR website
2. **analyze_land_record** - Extract structured data from land record PDFs
3. **generate_tsr_document** - Generate professional TSR DOCX documents
4. **batch_process_records** - Process multiple records in parallel from Excel

## Installation

### 1. Install Dependencies

```bash
cd mcp_server
pip install -r requirements.txt
```

### 2. Install Parent Project Dependencies

The MCP server requires the main project dependencies:

```bash
cd ..
pip install -r requirements.txt
```

### 3. Set Up Environment Variables

Create a `.env` file in the project root with:

```env
GOOGLE_API_KEY=your_gemini_api_key_here
```

## Configuration

### For Claude Desktop

Add to your Claude Desktop config file (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "tsr-tools": {
      "command": "python",
      "args": [
        "/absolute/path/to/agent-gujrat-tsr/mcp_server/server.py"
      ],
      "env": {
        "PYTHONPATH": "/absolute/path/to/agent-gujrat-tsr"
      }
    }
  }
}
```

### For Claude Code

Add to your project's MCP settings or use the provided `config.json`.

## Tools

### 1. fetch_pdf_from_anyror

Fetch land record PDF from Gujarat government website.

**Parameters:**
- `district` (required): District name (English or Gujarati)
- `taluka` (required): Taluka name (English or Gujarati)
- `village` (required): Village name (English or Gujarati)
- `survey_number` (required): Survey number
- `output_dir` (optional): Output directory (default: "output")
- `headless` (optional): Run browser headless (default: true)
- `regenerate` (optional): Force regenerate PDF (default: false)

**Example:**
```json
{
  "district": "Kutch",
  "taluka": "Bhuj",
  "village": "Trambo",
  "survey_number": "51"
}
```

**Returns:**
```json
{
  "success": true,
  "pdf_path": "output/pdfs/Survey No.51.pdf",
  "pdf_size_mb": 2.45,
  "page_count": 15,
  "location": {...},
  "gujarati_inputs": {...}
}
```

---

### 2. analyze_land_record

Extract structured data from land record PDF.

**Parameters:**
- `pdf_path` (required): Path to PDF file
- `extract_land` (optional): Extract land details (default: true)
- `extract_entries` (optional): Extract mutation entries (default: true)
- `include_raw_text` (optional): Include raw text (default: false)

**Example:**
```json
{
  "pdf_path": "output/pdfs/Survey No.51.pdf"
}
```

**Returns:**
```json
{
  "success": true,
  "land_details": {
    "village": "Trambo",
    "survey_number": "51",
    "area": "2-00-00",
    "owner": "...",
    ...
  },
  "entries": [
    {
      "entry_type": "Sale",
      "entry_number": "123",
      "date": "2020-01-15",
      "buyer": {...},
      "seller": {...},
      ...
    }
  ],
  "entry_count": 5,
  "entry_summary": {
    "Sale": 2,
    "Mortgage": 1,
    "Inheritance": 2
  }
}
```

---

### 3. generate_tsr_document

Generate Title Search Report DOCX document.

**Parameters:**
- `pdf_path` (required): Path to PDF land record
- `output_path` (optional): Output DOCX path (auto-generated if not provided)
- `custom_findings` (optional): Array of custom findings
- `advocate_name` (optional): Custom advocate name
- `advocate_address` (optional): Custom advocate address
- `use_agent` (optional): Use AI agent mode (default: false)

**Example:**
```json
{
  "pdf_path": "output/pdfs/Survey No.51.pdf",
  "custom_findings": [
    "No encumbrances found",
    "Clear marketable title"
  ]
}
```

**Returns:**
```json
{
  "success": true,
  "tsr_path": "output/pdfs/Survey No.51_TSR.docx",
  "tsr_size_kb": 45.23,
  "custom_findings_count": 2
}
```

---

### 4. batch_process_records

Process multiple land records from Excel file.

**Parameters:**
- `excel_path` (required): Path to Excel file
- `output_dir` (optional): Output directory (default: "output")
- `max_workers` (optional): Parallel workers (default: 3, max: 10)
- `headless` (optional): Run headless (default: true)
- `regenerate_pdf` (optional): Force regenerate (default: false)
- `auto_detect_columns` (optional): Auto-detect columns (default: true)
- `column_mapping` (optional): Manual column mapping

**Example:**
```json
{
  "excel_path": "data/land_records.xlsx",
  "max_workers": 5
}
```

**Returns:**
```json
{
  "success": true,
  "total_records": 50,
  "successful": 48,
  "failed": 2,
  "success_rate": 96.0,
  "results_excel": "output/batch_results.xlsx",
  "errors": [...]
}
```

## Testing

### Manual Testing

Test individual tools from command line:

```bash
# Test fetch_pdf
python mcp_server/tools/fetch_pdf.py \
  --district "Kutch" \
  --taluka "Bhuj" \
  --village "Trambo" \
  --survey-number "51"

# Test analyze_pdf
python mcp_server/tools/analyze_pdf.py \
  output/pdfs/Survey\ No.51.pdf

# Test generate_tsr
python mcp_server/tools/generate_tsr.py \
  output/pdfs/Survey\ No.51.pdf

# Test batch_process
python mcp_server/tools/batch_process.py \
  data/test_records.xlsx --workers 3
```

### MCP Server Testing

Use the provided test script:

```bash
python mcp_server/test_mcp.py
```

## Architecture

```
mcp_server/
├── server.py              # MCP server implementation
├── tools/                 # Tool implementations
│   ├── fetch_pdf.py      # PDF fetching tool
│   ├── analyze_pdf.py    # PDF analysis tool
│   ├── generate_tsr.py   # TSR generation tool
│   └── batch_process.py  # Batch processing tool
├── config.json            # MCP configuration
├── requirements.txt       # Dependencies
└── README.md             # This file
```

## Error Handling

All tools return JSON with a `success` field:

**Success:**
```json
{
  "success": true,
  ...
}
```

**Error:**
```json
{
  "success": false,
  "error": "Error message",
  "error_type": "ExceptionType"
}
```

## Logging

The MCP server logs to stdout. View logs when running:

```bash
python mcp_server/server.py
```

## Troubleshooting

### Chrome/ChromeDriver Issues

If PDF fetching fails with WebDriver errors:

```bash
# Check Chrome is installed
google-chrome --version

# The project uses webdriver-manager which auto-downloads ChromeDriver
```

### Import Errors

Ensure PYTHONPATH includes the project root:

```bash
export PYTHONPATH=/path/to/agent-gujrat-tsr:$PYTHONPATH
```

### API Key Issues

Verify your Google Gemini API key is set:

```bash
echo $GOOGLE_API_KEY
```

Or add to `.env` file in project root.

## Development

### Adding New Tools

1. Create tool module in `tools/` directory
2. Implement `execute()` function that returns JSON string
3. Add tool to `server.py` in `list_tools()` and `call_tool()`
4. Update this README

### Testing Changes

```bash
# Test tool directly
python mcp_server/tools/your_tool.py --help

# Test MCP server
python mcp_server/test_mcp.py
```

## License

Same as parent project.

## Support

For issues, see the main project repository.
