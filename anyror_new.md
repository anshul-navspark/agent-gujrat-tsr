# Gujarat Land Record Automation Tool

## Overview
This tool automates the process of retrieving land records from the Gujarat government's AnyRoR (Any Record of Rights) portal. It navigates through the website, fills in the required information, solves CAPTCHA using AI, and generates a PDF of the land record.

## Features
- Automated navigation through the AnyRoR website
- Selection of district, taluka, village, and survey/block number
- AI-powered CAPTCHA recognition using Google Gemini
- PDF generation of land records
- Comprehensive logging system
- Can be used as a standalone script or as an API function

## Prerequisites
- Python 3.7+
- Chrome browser installed
- Google Gemini API access (for CAPTCHA recognition)

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/gujrat_tsr_agent.git
cd gujrat_tsr_agent
```

2. Install required dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables for Google Gemini:
```bash
export GEMINI_API_KEY="your-gemini-api-key"
export GEMINI_MODEL_NAME="gemini-2.5-flash"
```

## Usage

### As a standalone script
Run the script with default parameters:
```bash
python anyror_new.py
```

### As an API function
Import and use the `fetch_land_record` function in your code:

```python
from anyror_new import fetch_land_record

result = fetch_land_record(
    district_name="પાટણ",         # District name in Gujarati
    taluka_name="પાટણ",           # Taluka name in Gujarati
    village_name="અનાવાડા - 091",  # Village name in Gujarati
    survey_block_number="0z૧",     # Survey/Block Number
    output_path="/path/to/save/land_record.pdf"
)

if result['success']:
    print(f"Land record fetched successfully: {result['pdf_path']}")
else:
    print(f"Failed to fetch land record: {result['error']}")
```

## Configuration
You can modify the default parameters in the `main()` function:
- `district_name`: Name of the district in Gujarati
- `taluka_name`: Name of the taluka in Gujarati
- `village_name`: Name of the village in Gujarati
- `survey_block_number`: Survey or Block number
- `output_path`: Path where the PDF will be saved

## Logging
The script creates detailed logs in the `logs` directory with timestamps. Each run generates a new log file.

## Error Handling
The script includes comprehensive error handling for:
- Selection failures (district, taluka, village, survey number)
- CAPTCHA recognition failures
- PDF generation issues

## Performance Optimizations

The latest version includes several performance improvements:

1. **Reduced Wait Times**
   - Decreased default timeout from 30 to 20 seconds
   - Reduced dropdown staleness check timeout from 5 to 3 seconds
   - Shortened wait times between operations (0.5 seconds instead of 1 second)
   - Optimized page load wait time before PDF generation (3 seconds instead of 5)

2. **Improved Logging**
   - Minimized console output (only warnings and errors by default)
   - Detailed logs still saved to file for troubleshooting
   - Simplified console output format for better readability
   - Added configuration options for log levels

3. **Browser Optimizations**
   - Added additional Chrome options to improve performance
   - Disabled browser logging and notifications
   - Suppressed WebDriver Manager output
   - Increased LRU cache size for dropdown options

4. **Reduced External Library Logging**
   - Suppressed verbose logging from Selenium
   - Disabled WebDriver Manager logs
   - Reduced LangChain/Gemini logging level

5. **Configurable Settings**
   - Added configuration constants for all timeouts and wait periods
   - Separate log levels for console and file output
   - Easy to adjust settings based on network conditions

## Recent Fixes

The latest version includes fixes for the following issues:

1. **Unicode Encoding in Logs**
   - Fixed Unicode encoding errors when logging Gujarati text
   - Added UTF-8 encoding for log files
   - Improved console output handling for non-ASCII characters

2. **Dropdown Selection Timeouts**
   - Added fallback mechanisms for survey number selection
   - Implemented shorter timeouts for dropdown staleness checks
   - Added graceful handling of StaleElementReferenceException

3. **JavaScript Escape Sequence**
   - Fixed invalid escape sequence in JavaScript code for CAPTCHA image extraction

4. **Browser Stability**
   - Added additional Chrome options to improve stability
   - Implemented better error handling and recovery mechanisms
   - Added appropriate waiting periods for page loading

5. **PDF Generation**
   - Added additional wait time before PDF generation to ensure page is fully loaded

6. **ChromeDriverManager Initialization**
   - Fixed ChromeDriverManager initialization by removing invalid log_level parameter
   - Used environment variables to control WebDriver Manager logging

7. **Gemini Client Configuration**
   - Removed problematic logging_level parameter from prior Azure client initialization
   - Simplified LLM client configuration

## Key Improvements in Refactored Version

The refactored version (`anyror_refactored.py`) includes several significant improvements:

1. **Object-Oriented Design**
   - Organized code into logical classes with clear responsibilities
   - Improved code readability and maintainability
   - Easier to extend with new features

2. **Configuration Management**
   - Moved hardcoded values to a central CONFIG dictionary
   - Added support for environment variables via dotenv
   - Easier to update and maintain configuration values

3. **Enhanced Error Handling**
   - Added proper exception handling throughout the code
   - Implemented retry mechanism for CAPTCHA recognition
   - Better error reporting with specific error messages

4. **Performance Optimizations**
   - Replaced arbitrary time.sleep() calls with explicit waits
   - Added caching for dropdown options with lru_cache
   - Improved form navigation with staleness checks

5. **Code Reusability**
   - Created reusable components for common operations
   - Implemented helper methods to reduce code duplication
   - Better separation of concerns between components

6. **Type Hints and Documentation**
   - Added type hints for better IDE support and code clarity
   - Comprehensive docstrings for all classes and methods
   - Clear parameter and return value documentation

7. **Resource Management**
   - Proper cleanup of resources in finally blocks
   - Better handling of temporary files
   - Explicit WebDriver closing

## Improvement Suggestions

### Code Efficiency and Best Practices

1. **Configuration Management**
   - Move hardcoded values (URLs, element IDs, etc.) to a configuration file
   - Use environment variables or a `.env` file for sensitive information

2. **Modular Structure**
   - Split the script into multiple modules (e.g., `captcha.py`, `webdriver.py`, `pdf_generator.py`)
   - Create a class-based structure for better organization

3. **Error Handling and Retries**
   - Implement a retry mechanism for CAPTCHA recognition failures
   - Add exponential backoff for website navigation issues
   - Create custom exceptions for different error types

4. **Performance Optimization**
   - Replace `time.sleep()` with explicit waits
   - Optimize the CAPTCHA recognition process
   - Implement caching for frequently accessed data

5. **Testing**
   - Add unit tests for individual components
   - Create integration tests for the entire workflow
   - Implement mock objects for external dependencies

### Refactoring Strategies

1. **Class-Based Architecture**
```python
# Example structure
class AnyRoRScraper:
    def __init__(self, config=None, logger=None):
        self.config = config or self._default_config()
        self.logger = logger or setup_logging()
        self.driver = None
        
    def setup_driver(self):
        # Initialize WebDriver
        
    def navigate_to_form(self):
        # Navigate to the form page
        
    def select_options(self, district, taluka, village, survey):
        # Select all dropdown options
        
    def solve_captcha(self):
        # Handle CAPTCHA recognition
        
    def submit_form(self):
        # Submit the form and handle alerts
        
    def generate_pdf(self, output_path):
        # Generate and save PDF
        
    def fetch_record(self, district, taluka, village, survey, output_path):
        # Main method that orchestrates the entire process
```

2. **Dependency Injection**
```python
# Example of dependency injection
class CaptchaSolver:
    def __init__(self, llm_client, logger):
        self.llm_client = llm_client
        self.logger = logger
        
    def solve(self, image_data):
        # Solve CAPTCHA using the provided LLM client
        
# Usage
llm_client = create_llm_client()
logger = setup_logging()
captcha_solver = CaptchaSolver(llm_client, logger)
scraper = AnyRoRScraper(captcha_solver=captcha_solver, logger=logger)
```

3. **Command Pattern for Form Filling**
```python
# Example of command pattern
class FormCommand:
    def execute(self, driver, wait):
        pass
        
class SelectDistrictCommand(FormCommand):
    def __init__(self, district_name):
        self.district_name = district_name
        
    def execute(self, driver, wait):
        # Select district logic
        
# Usage
commands = [
    SelectDistrictCommand(district_name),
    SelectTalukaCommand(taluka_name),
    # ...
]

for command in commands:
    command.execute(driver, wait)
```

4. **Async Implementation**
```python
# Example of async implementation
async def fetch_land_record_async(district_name, taluka_name, village_name, survey_block_number, output_path):
    # Async implementation for better performance
    # Especially useful for batch processing multiple records
```

5. **Implement Caching**
```python
# Example of caching implementation
from functools import lru_cache

@lru_cache(maxsize=128)
def get_district_options(driver):
    # Fetch and cache district options
```

## License
[MIT License](LICENSE)

## Disclaimer
This tool is for educational and personal use only. Please ensure you comply with the terms of service of the AnyRoR website.
