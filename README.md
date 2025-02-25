# Bhuj Solar Land Survey Batch Processor

This tool automates the processing of the Bhuj Solar Land Survey List by fetching land records from anyROR (Gujarat government website) and generating Title Search Reports (TSRs) for each entry.

## Overview

The tool consists of the following components:

1. **Bhuj Solar Processor (`bhuj_solar_processor.py`)**: Main script that reads the Excel file and processes each land record entry.
2. **Runner Example (`run_bhuj_processor.py`)**: Example script showing how to use the processor with different options.
3. **Existing Scripts**:
   - `anyror_new.py`: Handles fetching land records from the AnyRoR website.
   - `anyrortoTSR.py`: Converts PDF land records to formatted TSR documents.

## Prerequisites

- Python 3.7+
- Required Python packages (install using `pip install -r requirements.txt`):
  - pandas
  - openpyxl
  - selenium
  - flask
  - easyocr
  - tqdm
  - python-dotenv
  - langchain_openai
  - python-docx
  - PyPDF2
  - Pillow

## Setup

1. Make sure ChromeDriver is installed and available in your PATH.
2. Set up your Azure OpenAI credentials in the `.env` file.
3. Ensure the Excel file `Bhuj Solar Land Survey List Feb 24 2025.xlsx` is in the same directory.

## Usage

### Basic Usage

To process the entire Excel file:

```bash
python bhuj_solar_processor.py
```

This will read the Excel file, fetch each land record from the AnyRoR website, and generate corresponding TSR documents.

### Advanced Options

The processor supports various command-line options:

```bash
python bhuj_solar_processor.py --excel-file "your_file.xlsx" --output-dir "custom_output" --sequential --verbose
```

| Option | Description |
|--------|-------------|
| `--excel-file` | Path to the Excel file (default: "Bhuj Solar Land Survey List Feb 24 2025.xlsx") |
| `--output-dir` | Base directory for output files (default: "output") |
| `--sequential` | Process records sequentially instead of in parallel |
| `--max-workers` | Maximum number of parallel workers (default: 4) |
| `--start-row` | Start processing from this row number (default: 0, first data row) |
| `--end-row` | Stop processing at this row number (default: process all) |c
| `--pdf-only` | Only fetch PDFs, skip TSR generation |
| `--verbose` | Enable verbose logging |

### Example: Processing a Subset of Records

To process only rows 5-10 from the Excel file:

```bash
python bhuj_solar_processor.py --start-row 5 --end-row 10
```

### Example: Run with the Example Script

For quick demonstration of different processing options:

```bash
python run_bhuj_processor.py
```

This will run several example scenarios showing different ways to use the processor.

## Output Files

The processor creates the following outputs:

1. **PDF Land Records**: Stored in `output/pdfs/` directory
2. **TSR Documents**: Stored in `output/tsr/` directory
3. **Summary CSV**: Contains details of processed records
4. **Logs**: Detailed logs stored in the `logs/` directory

## Troubleshooting

- Check the log files in the `logs/` directory for detailed error information.
- Ensure your Chrome browser and ChromeDriver are compatible versions.
- Verify your internet connection is stable.
- Ensure the format of the Excel file matches what the processor expects.

## Notes

- The AnyRoR website may require CAPTCHA solving. The script attempts to automate this, but may occasionally require manual input.
- Processing a large number of records can take significant time.
- The script adds a delay between requests to avoid overwhelming the server.