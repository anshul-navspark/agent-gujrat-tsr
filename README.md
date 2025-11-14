## Agentic Mode (beta)

A new Agentic workflow can generate TSRs via an AI agent that orchestrates extraction tools.

- In the Streamlit sidebar, toggle "Agentic Mode (beta)" to enable.
- Preference is persisted locally and used across sessions.
- On failures, it falls back to the legacy generator automatically.

# Bhuj Solar Land Survey Processor

A comprehensive Python tool for processing land records from Gujarat government website, generating PDFs and Title Search Reports (TSR) for solar land surveys.

## Overview

The Bhuj Solar Land Survey Processor automates the process of fetching land records from the Gujarat government's database and generating Title Search Reports. It processes an Excel file containing land survey details (district, taluka, village, and survey numbers), translates these details to Gujarati, and fetches the corresponding land records, saving them as PDFs. It can then generate Title Search Reports (TSR) from these PDFs.

## Features

- **Excel Processing**: Reads and processes land survey data from Excel files
- **Language Translation**: Automatically translates district, taluka, village names from English to Gujarati
- **Survey Number Conversion**: Converts survey numbers to the specific format required by the government website
- **PDF Generation**: Fetches land records from the government website and saves them as PDFs
- **TSR Generation**: Creates Title Search Reports in DOCX format from the fetched PDFs
- **Parallel Processing**: Supports both sequential and parallel processing of records
- **Robust Error Handling**: Implements retry mechanisms and comprehensive error reporting
- **Detailed Logging**: Provides detailed logs of all operations
- **Summary Reports**: Generates CSV summary files of processed records

## Installation

### Prerequisites

- Python 3.8 or higher
- Chrome browser installed (for web scraping)
- Required Python packages:
  - pandas
  - selenium
  - webdriver_manager
  - tqdm
  - PyPDF2
  - python-docx

### Setup

```bash
# Clone the repository
git clone <repository-url>

# Navigate to the project directory
cd gujrat_tsr_agent

# Install dependencies
pip install -r requirements.txt
```

### Streamlit Frontend (non-technical usage)

You can run a simple web UI locally:

```bash
streamlit run app/streamlit_app.py
```

- Single Record tab: enter Gujarati District, Taluka, Village, Survey and click Fetch Record
- Batch (Excel) tab: upload an Excel file, map columns, and process all rows
- Outputs are saved to `output/pdfs` and `output/tsr` and downloadable from the UI

## Usage

### AnyRoR Dropdown Hierarchy Export

Use `anyror_hierarchy_scraper.py` to crawl the AnyRoR dropdowns and persist a nested dictionary of districts → talukas → villages (Gujarati + transliterated English variants):

```bash
python anyror_hierarchy_scraper.py --headless --output anyror_hierarchy.json
```

Flags:
- `--district-limit` / `--taluka-limit`: Optional caps for test runs.
- Omit `--headless` to watch the browser while debugging.

The generated JSON uses Gujarati names as keys:

```
{
  "પાટણ": {
    "english_names": ["Patan"],
    "talukas": {
      "પાટણ": {
        "english_names": ["Patan"],
        "villages": {
          "અનાવાડા - 091": ["Anavada", "Anawada"]
        }
      }
    }
  }
}
```

### Basic Usage

```bash
python bhuj_solar_processor.py --excel-file "Bhuj Solar Land Survey List.xlsx" --output-dir "output"
```

### Command-Line Options

```
--excel-file       Path to the Excel file (default: "Bhuj Solar Land Survey List Feb 24 2025.xlsx")
--output-dir       Base directory for output files (default: "output")
--no-sequential    Process records in parallel instead of sequentially
--max-workers      Maximum number of parallel workers (default: 4)
--start-row        Start processing from this row number (default: 0, first data row)
--end-row          Stop processing at this row number (default: process all)
--pdf-only         Only fetch PDFs, skip TSR generation
--verbose          Enable verbose logging
--test-conversion  Test survey number conversion without fetching records
--survey-numbers   List of survey numbers to test conversion or to process specifically
--process-survey-numbers  Process only specific survey numbers provided in --survey-numbers
--no-cleanup       Skip cleanup of chromedriver cache between runs
--regenerate       Regenerate PDFs even if they already exist
```

### Examples

Process specific rows from the Excel file:
```bash
python bhuj_solar_processor.py --start-row 10 --end-row 20
```

Process only specific survey numbers:
```bash
python bhuj_solar_processor.py --process-survey-numbers --survey-numbers "142" "143/પૈ" "145/1"
```

Process in parallel with 8 workers:
```bash
python bhuj_solar_processor.py --no-sequential --max-workers 8
```

Only generate PDFs without TSR reports:
```bash
python bhuj_solar_processor.py --pdf-only
```

Test survey number conversion:
```bash
python bhuj_solar_processor.py --test-conversion --survey-numbers "145/1" "143/pa" "142/p1"
```

## Excel File Format

The Excel file should contain the following columns:
- `District`: The district name in English (e.g., "Kutch", "Bhuj")
- `Tehsil` or `Taluka`: The taluka/tehsil name in English (e.g., "Bhuj", "Anjar")
- `Village`: The village name in English (e.g., "Trambo", "Edal")
- `Survey Nos`: The survey number, which may include special notations (e.g., "142", "143/p1", "145/pa")

## Output

The script generates the following outputs in the specified output directory:
- `pdfs/`: Directory containing the fetched land record PDFs
- `tsr/`: Directory containing the generated Title Search Reports (DOCX)
- `summary_TIMESTAMP.csv`: CSV file summarizing the processed records
- `logs/bhuj_solar_TIMESTAMP.log`: Detailed log file of the processing

## Survey Number Conversion

The script handles various formats of survey numbers and converts them to the format required by the government website:
- Simple numbers (e.g., "142", "143") remain unchanged
- Numbers with paiki (પૈકી) are formatted as "number/પૈ" (e.g., "145/પૈ")
- Numbers with paiki paiki (પૈકી પૈકી) are formatted as "number/પૈ/પૈ" (e.g., "144/પૈ/પૈ")
- Numbers with special characters like 'q', 'r', 'e', etc. are properly converted to Gujarati

## Notes

- The script uses Chrome browser automation to fetch land records, so Chrome must be installed on the system.
- Processing might take time depending on the number of records and network conditions.
- The script includes retry mechanisms for handling network issues and timeouts.
- All processing is logged in detail for troubleshooting purposes.

## Dependencies

- `pandas`: For Excel file reading and data manipulation
- `selenium`: For web browsing automation
- `webdriver_manager`: For Chrome driver management
- `tqdm`: For progress bar display
- `PyPDF2`: For PDF processing
- `python-docx`: For TSR document generation

## TSR Generator

The package includes a TSR Generator module for creating Title Search Reports from PDF land records. See the documentation in the `tsr_generator` package for more details.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Troubleshooting

1. **ChromeDriver Issues**: If you encounter issues with ChromeDriver, try using the `--no-cleanup` option to preserve the ChromeDriver cache.
2. **Timeouts**: The script includes retry mechanisms for timeouts. If timeouts persist, consider increasing the timeout value in the code.
3. **Missing Translations**: If the script warns about missing translations, add the missing entries to the translation dictionaries in the code. 