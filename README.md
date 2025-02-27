# TSR Generator

A Python package for generating Title Search Reports (TSR) from PDF land records.

## Overview

The TSR Generator package provides a modular and maintainable solution for extracting information from PDF land records and generating formatted Title Search Reports in DOCX format. The package uses AI-based extraction techniques to identify key information from the land records, including land details, entry details, and standard findings.

## Features

- Extract text from PDF land records
- AI-based extraction of land details (village, taluka, district, survey number, etc.)
- AI-based extraction of entry details (entry number, date, type, description)
- Translation of Gujarati text to English
- Generation of standard findings for TSR reports
- Creation of formatted DOCX reports with proper styling and layout

## Installation

```bash
# Clone the repository
git clone <repository-url>

# Navigate to the project directory
cd <project-directory>

# Install the package
pip install -e .
```

## Usage

### Command Line Interface

```bash
# Generate a TSR from a PDF file
python -m tsr_generator /path/to/land_record.pdf --output /path/to/output.docx

# Show help
python -m tsr_generator --help
```

### Python API

```python
from tsr_generator import generate_tsr_from_pdf

# Generate a TSR from a PDF file
result = generate_tsr_from_pdf(
    pdf_path='/path/to/land_record.pdf',
    output_path='/path/to/output.docx'
)

if result['success']:
    print(f"TSR generated successfully: {result['tsr_path']}")
else:
    print(f"Failed to generate TSR: {result['error']}")
```

## Package Structure

The package is organized into the following modules:

- `tsr_generator/`: Main package directory
  - `__init__.py`: Package initialization and exports
  - `__main__.py`: Command-line entry point
  - `api/`: API modules
    - `tsr_generator.py`: Main API for TSR generation
  - `utils/`: Utility modules
    - `logging_utils.py`: Logging utilities
    - `pdf_utils.py`: PDF processing utilities
    - `text_utils.py`: Text processing utilities
  - `extractors/`: Data extraction modules
    - `land_details.py`: Land details extraction
    - `entry_details.py`: Entry details extraction
    - `findings.py`: Findings generation
  - `document/`: Document generation modules
    - `docx_generator.py`: DOCX generation utilities
    - `tsr_document.py`: TSR document creation

## Dependencies

- `python-docx`: For creating DOCX documents
- `PyPDF2`: For extracting text from PDF files
- `langchain_openai`: For AI-based extraction
- `python-dotenv`: For loading environment variables
- `pydantic`: For data validation

## Environment Variables

The package requires the following environment variables to be set:

- `AZURE_OPENAI_ENDPOINT`: Azure OpenAI API endpoint
- `AZURE_OPENAI_KEY`: Azure OpenAI API key

These can be set in a `.env` file in the project directory.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Authors

- Your Name - Initial work 