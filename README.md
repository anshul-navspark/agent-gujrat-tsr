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
| `--end-row` | Stop processing at this row number (default: process all) |
| `--pdf-only` | Only fetch PDFs, skip TSR generation |
| `--verbose` | Enable verbose logging |
| `--test-conversion` | Test survey number conversion without fetching records |
| `--survey-numbers` | List of survey numbers to test conversion (used with --test-conversion) |

### Example: Processing a Subset of Records

To process only rows 5-10 from the Excel file:

```bash
python bhuj_solar_processor.py --start-row 5 --end-row 10
```

### Example: Testing Survey Number Conversion

To test how survey numbers are converted to match the website's format:

```bash
python bhuj_solar_processor.py --test-conversion
```

To test specific survey numbers:

```bash
python bhuj_solar_processor.py --test-conversion --survey-numbers "144/pa" "153/pe" "161/q" "150/p1" "151/p2"
```

### Example: Run with the Example Script

For quick demonstration of different processing options:

```bash
python run_bhuj_processor.py
```

This will run several example scenarios showing different ways to use the processor.

## Survey Number Conversion

The tool automatically converts survey numbers from the Excel file to the format expected by the AnyRoR website. This includes:

- Simple numbers (e.g., "142", "143") remain unchanged
- Numbers with paiki (પૈકી) are formatted as "number/પૈ" (e.g., "145/પૈ")
- Numbers with paiki paiki (પૈકી પૈકી) are formatted as "number/પૈ/પૈ" (e.g., "144/પૈ/પૈ")
- Numbers with 'q' or 'ર' are formatted as "number/ર" (e.g., "154/ર")
- Numbers with 'e' or 'ૈ' are formatted as "number/ૈ" (e.g., "161/ૈ")
- Numbers with 'p1' are formatted as "number/p૧" (with Gujarati numeral ૧) (e.g., "150/p૧")
- Numbers with 'p2' are formatted as "number/p૨" (with Gujarati numeral ૨) (e.g., "151/p૨")
- Numbers with 'p3' are formatted as "number/પ૩" (with Gujarati numeral ૩) (e.g., "153/પ૩")

If the initial conversion fails to find a match on the website, the system will automatically try alternative formats to increase the success rate.

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
- If survey numbers are not being found, use the `--test-conversion` option to see how they're being converted.

## Notes

- The AnyRoR website may require CAPTCHA solving. The script attempts to automate this, but may occasionally require manual input.
- Processing a large number of records can take significant time.
- The script adds a delay between requests to avoid overwhelming the server.