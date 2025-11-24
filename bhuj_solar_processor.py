#!/usr/bin/env python3
"""
Bhuj Solar Land Survey Processor

This script processes the Bhuj Solar Land Survey List Excel file and generates
land record PDFs and TSR documents for each entry.

Usage:
    python bhuj_solar_processor.py [options]

Options:
    --excel-file       Path to the Excel file (default: "Bhuj Solar Land Survey List Feb 24 2025.xlsx")
    --output-dir       Base directory for output files (default: "output")
    --no-sequential    Process records in parallel instead of sequentially
    --max-workers      Maximum number of parallel workers (default: 4)
    --start-row        Start processing from this row number (default: 0, first data row)
    --end-row          Stop processing at this row number (default: process all)
    --pdf-only         Only fetch PDFs, skip TSR generation
    --verbose          Enable verbose logging
    --test-conversion  Test survey number conversion without fetching records
    --survey-numbers   List of survey numbers to test conversion (used with --test-conversion)
    --no-cleanup       Skip cleanup of chromedriver cache between runs
    --regenerate       Regenerate PDFs even if they already exist
    --headless         Run in headless mode (default: False)
"""

import os
import sys
import pandas as pd
import logging
from datetime import datetime
import time
import traceback
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import argparse
from tqdm import tqdm
import re
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager

# Import your existing modules

import anyror_refactored
from anyror_refactored import AnyRoRScraper  # Add this import
from tsr_generator import generate_tsr_from_pdf  # Import from the new package

# Add these dictionaries for English to Gujarati translation
DISTRICT_TRANSLATIONS = {
    "Patan": "પાટણ",
    "Kutch": "કચ્છ",
    "Bhuj": "ભુજ",
    "Kachchh": "કચ્છ",
    "Banaskantha": "બનાસકાંઠા",
    "Bhavnagar": "ભાવનગર",  # Added for Datha
    "Jamnagar": "જામનગર",
    # Add more districts as needed
}

TALUKA_TRANSLATIONS = {
    "Patan": "પાટણ",
    "Bhuj": "ભુજ",
    "Anjar": "અંજાર",
    "Abdasa": "અબડાસા",
    "Dhanera": "ધાનેરા",
    "Talaja": "તળાજા",  # Added for Datha
    "Jamjodhpur": "જામજોધપુર",
    "Jamkhadaba": "જામજોધપુર",  # Alternative for Jamjodhpur
    # Add more talukas as needed
}

VILLAGE_TRANSLATIONS = {
    "Anavada": "અનાવાડા - 091",
    "Trambo": "ત્રંબો - 033",
    "Trambau": "ત્રંબો - 033",

    "Edal": "એડાલ - 031",
    "Jadi": "જાડી - 029",
    "Jadiya" :"જડીયા - 018",
    "Janali": "જનાલી - 033",
    "Shiya": "શિયા - 030",
    "Malotra": "માલોત્રા - 050",
    "Datha": "દાઠા",  # Added for Datha
    
    # Hothiji Khadaba variations - the exact Gujarati text provided
    "Hothiji Khadba": "હોથીજી ખડબા - 034",
    "Hothiji Khadaba": "હોથીજી ખડબા - 034", 
    "Hothiji Khadba Abdasa": "હોથીજી ખડબા - 034",
    "Hothiji Khadaba Abdasa": "હોથીજી ખડબા - 034",
    "હોથીજી ખડબા": "હોથીજી ખડબા - 034",  # Direct Gujarati mapping
    "Hothiji": "હોથીજી ખડબા - 034",  # Shortened version
    "Khadaba": "હોથીજી ખડબા - 034",  # Alternative search
    "Nagiya": "નાંગીયા - 031",
    "RAMPAR ABDA": "રામપર(અબડા) - 034",
    "Rampar Abda": "રામપર(અબડા) - 034",
    "Rampr(Abda)": "રામપર(અબડા) - 034",
    "RamprAbda": "રામપર(અબડા) - 034",
    "Rampar (Abda)": "રામપર(અબડા) - 034",
    # Add more villages as needed
}

def convert_survey_number(survey_number):
    """
    Convert survey numbers to the format expected by the website.
    
    The website expects survey numbers in specific formats:
    - Simple numbers (e.g., "142", "143") remain unchanged
    - Numbers with paiki (પૈકી) are formatted as "number/પૈ" (e.g., "145/પૈ")
    - Numbers with paiki paiki (પૈકી પૈકી) are formatted as "number/પૈ/પૈ" (e.g., "144/પૈ/પૈ")
    - Numbers with 'q' or 'ર' are formatted as "number/ર" (e.g., "154/ર")
    - Numbers with 'e' or 'ૈ' are formatted as "number/ૈ" (e.g., "161/ૈ")
    - Numbers with 'p1' are formatted as "number/p૧" (with Gujarati numeral ૧)
    - Numbers with 'p2' are formatted as "number/p૨" (with Gujarati numeral ૨)
    - Numbers with 'p3' are formatted as "number/p૩" (with Gujarati numeral ૩)
    - Numbers with 'p4' are formatted as "number/p૪" (with Gujarati numeral ૪)
    - Numbers with '/1' are formatted as "/૧" (with Gujarati numeral ૧)
    - Numbers with '/2' are formatted as "/૨" (with Gujarati numeral ૨)
    - Numbers with '/3' are formatted as "/૩" (with Gujarati numeral ૩)
    - Numbers with '/4' are formatted as "/૪" (with Gujarati numeral ૪)
    
    Args:
        survey_number (str): The original survey number
        
    Returns:
        str: The converted survey number
    """
    # Convert to string if not already
    survey_number = str(survey_number).strip()
    
    # Remove any spaces in the survey number
    survey_number = survey_number.replace(" ", "")
    
    # Simple conversion rules based on patterns
    if re.match(r'^\d+$', survey_number):
        # Simple number, no conversion needed
        return survey_number
    
    # Extract the base number (everything before the first slash or non-digit)
    base_match = re.match(r'^(\d+)', survey_number)
    if not base_match:
        # If no base number found, return as is
        return survey_number
    
    base_number = base_match.group(1)
    
    # Dictionary to map Latin digits to Gujarati digits
    digit_map = {
        '0': '૦',
        '1': '૧',
        '2': '૨',
        '3': '૩',
        '4': '૪',
        '5': '૫',
        '6': '૬',
        '7': '૭',
        '8': '૮',
        '9': '૯'
    }
    
    # Extract the suffix (everything after the base number)
    suffix = survey_number[len(base_number):]
    suffix_lower = suffix.lower()
    
    # Handle Datha list specific patterns first
    if re.search(r'[/\s]?p(\d)', suffix_lower):
        # Extract the number after 'p'
        p_number = re.search(r'[/\s]?p(\d)', suffix_lower).group(1)
        # Convert to Gujarati number
        guj_number = digit_map.get(p_number, p_number)
        return f"{base_number}/p{guj_number}"
    
    # Handle other patterns
    if '/paq' in suffix_lower:
        return f"{base_number}/પા૧"
    elif '/pae' in suffix_lower:
        return f"{base_number}/પાૈ"
    elif '/pac' in suffix_lower:
        return f"{base_number}/પાચ"
    elif '/pu' in suffix_lower:
        return f"{base_number}/પુ"
    elif '/pa3e' in suffix_lower:
        return f"{base_number}/પા૩ૈ"
    elif '/pax' in suffix_lower:
        return f"{base_number}/પાક્ષ"
    elif '/pax/pa' in suffix_lower:
        return f"{base_number}/પાક્ષ/પા"
    elif '/pa30' in suffix_lower:
        return f"{base_number}/પા૩૦"
    
    # Handle complex patterns with multiple components
    if '/p1/p1' in suffix_lower:
        return f"{base_number}/p૧/p૧"
    elif '/p2/p2' in suffix_lower:
        return f"{base_number}/p૨/p૨"
    elif '/p3/p3' in suffix_lower:
        return f"{base_number}/p૩/p૩"
    elif '/p4/p4' in suffix_lower:
        return f"{base_number}/p૪/p૪"
    
    # Handle direct digit patterns (convert /1 to /૧, etc.)
    suffix = re.sub(r'/(\d)', lambda m: f"/{digit_map[m.group(1)]}", suffix)
    
    # If we've modified the suffix but none of the specific patterns matched
    if suffix != survey_number[len(base_number):]:
        return f"{base_number}{suffix}"
    
    # If no pattern matches, return as is
    return survey_number

def translate_to_gujarati(text, translation_dict, default=None):
    """Translate English text to Gujarati using the provided dictionary"""
    if not text:
        return default or text
    
    # Try direct lookup
    if text in translation_dict:
        return translation_dict[text]
    
    # Try case-insensitive lookup
    for eng, guj in translation_dict.items():
        if eng.lower() == text.lower():
            return guj
    
    # If no match found, return original text or default
    logger = logging.getLogger(__name__)
    logger.warning(f"No Gujarati translation found for: {text}")
    return default or text

def setup_logging(verbose=False):
    """Setup logging configuration"""
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Create a timestamp for the log file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = f'logs/bhuj_solar_{timestamp}.log'

    # Configure logging
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()  # Also print to console
        ]
    )
    return logging.getLogger(__name__)

def sanitize_filename(filename):
    """Convert a string to a valid filename by replacing invalid characters"""
    # Ensure filename is a string
    filename = str(filename).strip()
    # Replace slashes and other problematic characters with underscores
    return re.sub(r'[\\/*?:"<>|]', '_', filename)

# A completely self-contained function to fetch the land record
def fetch_land_record_isolated(district, taluka, village, survey, output_path, timeout=300):
    """
    A self-contained function to fetch land records that can be run in its own process.
    This avoids issues with signals and shared resources.
    """
    result = {
        'success': False,
        'error': None,
        'pdf_path': None
    }
    
    try:
        # Set up a basic logger for this process
        log_format = '%(asctime)s - %(levelname)s - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)
        logger = logging.getLogger('fetch_process')
        
        # Import here to avoid any global import issues
        from anyror_refactored import AnyRoRScraper
        
        # Clean up any zombie processes first
        try:
            subprocess_cmd = ["pkill", "-f", "chromedriver"]
            import subprocess
            subprocess.run(subprocess_cmd, check=False)
        except Exception as e:
            logger.warning(f"Failed to kill zombie processes: {str(e)}")
        
        # Create scraper instance and fetch the land record
        scraper = AnyRoRScraper(headless=True, logger=logger)
        try:
            result_dict = scraper.fetch_land_record(
                district_name=district,
                taluka_name=taluka,
                village_name=village,
                survey_block_number=survey,
                output_path=output_path
            )
            
            # Check the result
            if result_dict.get('success', False):
                result['success'] = True
                result['pdf_path'] = output_path
            else:
                result['error'] = result_dict.get('error', 'Unknown error')
        finally:
            # Clean up the scraper
            try:
                scraper.web_driver_manager.close()
            except:
                pass
            
    except Exception as e:
        result['error'] = str(e)
    
    return result

def process_single_row(row, args, logger):
    """Process a single row from the Excel file."""
    # Initialize result dictionary with default values
    result = {
        'row_index': row.name,
        'district': None,
        'taluka': None,
        'village': None,
        'survey_number': None,
        'gujarati_survey': None,
        'status': 'Not Processed',
        'pdf_path': None,
        'tsr_path': None,
        'error': None
    }
    
    try:
        # Extract district, taluka, village, and survey number from row
        # Handle both old and new column names
        district = row.get('District', row.get('District ', ''))  # Note the space in 'District '
        taluka = row.get('Tehsil', row.get('Taluka', row.get('Taluka ', '')))  # Note the space in 'Taluka '
        village = row.get('Village', '')
        survey = row.get('Survey Nos', row.get('Survey No', ''))
        
        # Skip rows with missing essential data
        if not all([district, taluka, village, survey]):
            logger.warning(f"Skipping row {row.name} due to missing essential data: "
                           f"District={district}, Taluka={taluka}, Village={village}, Survey={survey}")
            result['error'] = "Missing essential data"
            result['status'] = 'Skipped'
            return result
        
        # Clean up any extra whitespace
        district = district.strip()
        taluka = taluka.strip()
        village = village.strip()
        survey = str(survey).strip()
        
        # Translate English names to Gujarati using dictionaries
        guj_district = translate_to_gujarati(district, DISTRICT_TRANSLATIONS, default=district)
        guj_taluka = translate_to_gujarati(taluka, TALUKA_TRANSLATIONS, default=taluka)
        guj_village = translate_to_gujarati(village, VILLAGE_TRANSLATIONS, default=village)
        
        # Convert survey number to Gujarati format
        guj_survey = convert_survey_number(survey)
        
        # Update result with extracted data
        result.update({
            'district': district,
            'taluka': taluka,
            'village': village,
            'survey_number': survey,
            'gujarati_survey': guj_survey
        })
        
        # Log the processing information
        logger.info(f"Processing row {row.name}: {district} ({guj_district}), {taluka} ({guj_taluka}), "
                    f"{village} ({guj_village}), Survey: {survey} (Converted: {guj_survey})")
        
        # Determine output paths
        output_dir = args.output_dir
        pdf_dir = os.path.join(output_dir, "pdfs")
        tsr_dir = os.path.join(output_dir, "tsr")
        
        # Create directories if they don't exist
        os.makedirs(pdf_dir, exist_ok=True)
        os.makedirs(tsr_dir, exist_ok=True)
        
        # Generate output filenames
        sanitized_survey = sanitize_filename(survey)
        pdf_filename = f"Survey No.{sanitized_survey}.pdf"
        tsr_filename = f"Survey No.{sanitized_survey}.docx"
        
        pdf_path = os.path.join(pdf_dir, pdf_filename)
        tsr_path = os.path.join(tsr_dir, tsr_filename)
        
        # Check if PDF already exists and skip if it does (unless regeneration is requested)
        if os.path.exists(pdf_path) and not args.regenerate:
            logger.info(f"PDF already exists for row {row.name}, skipping PDF generation")
            result['pdf_path'] = pdf_path
            result['status'] = 'PDF Already Exists'
        else:
            # Fetch the land record and save as PDF
            logger.info(f"Fetching land record for row {row.name}")
            
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    # Use the regular anyror_refactored for sequential mode
                    if not args.no_sequential:
                        # Clean up any zombie chromedriver processes first
                        try:
                            from anyror_refactored import WebDriverManager
                            wdm = WebDriverManager()
                            wdm._kill_zombie_chromedrivers()
                        except Exception as e:
                            logger.warning(f"Failed to kill zombie processes: {str(e)}")
                        
                        # Create scraper instance and fetch the land record
                        scraper = AnyRoRScraper(headless=True, logger=logger)
                        try:
                            result_dict = scraper.fetch_land_record(
                                district_name=guj_district,
                                taluka_name=guj_taluka,
                                village_name=guj_village,
                                survey_block_number=guj_survey,
                                output_path=pdf_path
                            )
                            
                            if result_dict.get('success', False):
                                result['pdf_path'] = pdf_path
                                result['status'] = 'PDF Generated'
                                break  # Success, exit the retry loop
                            else:
                                error_msg = result_dict.get('error', 'Unknown error')
                                logger.error(f"Failed to fetch land record for row {row.name}: {error_msg}")
                                if attempt < max_attempts - 1:
                                    logger.info(f"Retrying... (Attempt {attempt + 2}/{max_attempts})")
                                    # Sleep a bit before retrying
                                    time.sleep(5)
                                else:
                                    result['error'] = error_msg
                                    result['status'] = 'PDF Generation Failed'
                        finally:
                            # Clean up the scraper
                            try:
                                scraper.web_driver_manager.close()
                            except:
                                pass
                    else:
                        # For parallel mode, use our isolated function in a process pool
                        # This ensures complete isolation of the browser instances
                        with ProcessPoolExecutor(max_workers=1) as executor:
                            future = executor.submit(
                                fetch_land_record_isolated,
                                guj_district, guj_taluka, guj_village, guj_survey, pdf_path, 300  # Add timeout
                            )
                            
                            try:
                                # Wait for 5 minutes (300 seconds)
                                fetch_result = future.result(timeout=300)
                                
                                if fetch_result.get('success', False):
                                    result['pdf_path'] = pdf_path
                                    result['status'] = 'PDF Generated'
                                    break  # Success, exit the retry loop
                                else:
                                    error_msg = fetch_result.get('error', 'Unknown error')
                                    logger.error(f"Failed to fetch land record for row {row.name}: {error_msg}")
                                    if attempt < max_attempts - 1:
                                        logger.info(f"Retrying... (Attempt {attempt + 2}/{max_attempts})")
                                        time.sleep(5)
                                    else:
                                        result['error'] = error_msg
                                        result['status'] = 'PDF Generation Failed'
                            except concurrent.futures.TimeoutError:
                                future.cancel()
                                logger.error(f"Timeout while fetching land record for row {row.name}")
                                # Clean up any zombie processes
                                import subprocess
                                subprocess.run(["pkill", "-f", "chromedriver"], check=False)
                                
                                if attempt < max_attempts - 1:
                                    logger.info(f"Retrying after timeout... (Attempt {attempt + 2}/{max_attempts})")
                                    time.sleep(10)
                                else:
                                    result['error'] = "Operation timed out"
                                    result['status'] = 'PDF Generation Failed (Timeout)'
                
                except Exception as e:
                    logger.error(f"Failed to fetch land record for row {row.name}: {str(e)}")
                    logger.error(traceback.format_exc())
                    
                    # Clean up resources
                    import subprocess
                    subprocess.run(["pkill", "-f", "chromedriver"], check=False)
                    
                    if attempt < max_attempts - 1:
                        logger.info(f"Retrying after error... (Attempt {attempt + 2}/{max_attempts})")
                        time.sleep(5)
                    else:
                        result['error'] = str(e)
                        result['status'] = 'PDF Generation Failed (Error)'
        
        # If PDF was generated successfully and TSR generation is requested
        if result['pdf_path'] and not args.pdf_only:
            try:
                logger.info(f"Generating TSR for row {row.name}")
                
                generate_tsr_from_pdf(
                    pdf_path=result['pdf_path'],
                    output_path=tsr_path
                )
                
                result['tsr_path'] = tsr_path
                result['status'] = 'TSR Generated'
                logger.info(f"Report generated successfully: {tsr_path}")
                
            except Exception as e:
                logger.error(f"Failed to generate TSR for row {row.name}: {str(e)}")
                logger.error(traceback.format_exc())
                result['error'] = f"TSR Generation Error: {str(e)}"
                # Don't change status if PDF was generated successfully
        
    except Exception as e:
        logger.error(f"Error processing row {row.name}: {str(e)}")
        logger.error(traceback.format_exc())
        result['error'] = str(e)
        result['status'] = 'Processing Error'
    
    return result

def process_bhuj_solar_data(args):
    """Process the Bhuj Solar Land Survey List Excel file"""
    logger = logging.getLogger(__name__)
    
    # Create output directories
    pdf_dir = os.path.join(args.output_dir, "pdfs")
    tsr_dir = os.path.join(args.output_dir, "tsr")
    
    os.makedirs(pdf_dir, exist_ok=True)
    logger.info(f"Created directory: {pdf_dir}")
    
    os.makedirs(tsr_dir, exist_ok=True)
    logger.info(f"Created directory: {tsr_dir}")
    
    # Read the Excel file
    excel_path = args.excel_file
    logger.info(f"Reading Excel file: {excel_path}")
    
    try:
        data_df = pd.read_excel(excel_path)
        data_df = data_df.fillna('')
        
        # Print column names for debugging
        logger.info(f"Excel columns: {list(data_df.columns)}")
        
        logger.info(f"Successfully read data with {len(data_df)} records")
    except Exception as e:
        logger.error(f"Error reading Excel file: {str(e)}")
        return []

    # Filter rows if specific survey numbers are requested
    if args.process_survey_numbers and args.survey_numbers:
        logger.info(f"Filtering by specific survey numbers: {args.survey_numbers}")
        # Convert survey numbers to strings to avoid type matching issues
        survey_numbers = [str(s).strip() for s in args.survey_numbers]
        # Get the column name that contains survey numbers
        survey_col = 'Survey Nos'
        
        # Filter rows where Survey Nos column matches any of the specified survey numbers
        filtered_rows = []
        for _, row in data_df.iterrows():
            if str(row.get(survey_col, '')).strip() in survey_numbers:
                filtered_rows.append(row)
        
        if filtered_rows:
            data_df = pd.DataFrame(filtered_rows)
            logger.info(f"Filtered to {len(data_df)} rows matching the specified survey numbers")
        else:
            logger.warning(f"No rows found matching the specified survey numbers")
            return []
    # Otherwise filter rows by row index if specified
    else:
        start_row = args.start_row
        end_row = args.end_row if args.end_row is not None else len(data_df)
        
        data_df = data_df.iloc[start_row:end_row].copy()
        logger.info(f"Starting to process {len(data_df)} rows from the Bhuj Solar Land Survey List")
    
    # Prepare summary DataFrame for results
    summary_columns = [
        'row', 'district', 'taluka', 'village', 'survey', 'converted_survey',
        'pdf_success', 'pdf_path', 'tsr_success', 'tsr_path', 
        'error', 'processing_time'
    ]
    summary_df = pd.DataFrame(columns=summary_columns)
    
    # Create a timestamp for the summary file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    summary_path = os.path.join(args.output_dir, f"summary_{timestamp}.csv")
    
    # Process rows
    results = []
    
    if args.no_sequential:
        logger.info("Processing in parallel")
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            futures = {executor.submit(process_single_row, row, args, logger): idx for idx, row in data_df.iterrows()}
            
            for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc="Processing"):
                row_idx = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    # Update summary DataFrame using concat instead of append
                    summary_df = pd.concat([summary_df, pd.DataFrame([result])], ignore_index=True)
                    
                    # Save intermediate results
                    summary_df.to_csv(summary_path, index=False)
                except Exception as e:
                    logger.error(f"Error processing row {row_idx}: {str(e)}")
    else:
        logger.info("Processing sequentially")
        for idx, row in tqdm(data_df.iterrows(), total=len(data_df), desc="Processing"):
            result = process_single_row(row, args, logger)
            results.append(result)
            
            # Update summary DataFrame using concat instead of append
            summary_df = pd.concat([summary_df, pd.DataFrame([result])], ignore_index=True)
            
            # Save intermediate results
            summary_df.to_csv(summary_path, index=False)

    
    # Final save of summary file
    summary_df.to_csv(summary_path, index=False)
    
    return results

def get_alternative_survey_formats(survey):
    """
    Generate alternative formats for a survey number to increase the chances of finding a match.
    
    Args:
        survey (str): The original survey number
        
    Returns:
        list: A list of alternative formats for the survey number
    """
    # Convert to string if not already
    survey = str(survey).strip()
    
    # Start with the original survey as the first alternative
    alternative_formats = [survey]
    
    # Extract the base number (everything before the first slash or non-digit)
    base_match = re.match(r'^(\d+)', survey)
    if not base_match:
        # If no base number found, return just the original
        return alternative_formats
    
    base_number = base_match.group(1)
    
    # Extract the suffix (everything after the base number)
    suffix = survey[len(base_number):]
    suffix_lower = suffix.lower()
    
    # Dictionary to map Latin digits to Gujarati digits
    digit_map = {
        '0': '૦',
        '1': '૧',
        '2': '૨',
        '3': '૩',
        '4': '૪',
        '5': '૫',
        '6': '૬',
        '7': '૭',
        '8': '૮',
        '9': '૯'
    }
    
    # Handle special complex patterns
    if '/paq' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/પા૧",
            f"{base_number}/પૈ",
            f"{base_number}/પૈકી",
            f"{base_number}/પૈ/પૈ"
        ])
    elif '/pae' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/પાૈ",
            f"{base_number}/પૈ",
            f"{base_number}/પૈકી",
            f"{base_number}/પૈ/પૈ"
        ])
    elif '/pac' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/પાચ",
            f"{base_number}/પૈ",
            f"{base_number}/પૈકી",
            f"{base_number}/પૈ/પૈ"
        ])
    elif '/pu' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/પુ",
            f"{base_number}/પૈ",
            f"{base_number}/ર",
            f"{base_number}/ૈ",
            f"{base_number}/પૈકી",
            f"{base_number}/પૈ/પૈ",
            f"{base_number}/pa",
            f"{base_number}/pe",
            f"{base_number}/q",
            f"{base_number}/e"
        ])
    elif '/pa3e' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/પા૩ૈ",
            f"{base_number}/પૈ",
            f"{base_number}/પૈકી",
            f"{base_number}/પૈ/પૈ"
        ])
    elif '/pax' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/પાક્ષ",
            f"{base_number}/પૈ",
            f"{base_number}/પૈકી",
            f"{base_number}/પૈ/પૈ"
        ])
    elif '/pax/pa' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/પાક્ષ/પા",
            f"{base_number}/પૈ/પૈ",
            f"{base_number}/પૈકી/પૈકી"
        ])
    elif '/pa30' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/પા૩૦",
            f"{base_number}/પૈ",
            f"{base_number}/પૈકી"
        ])
    # Handle complex patterns with multiple components
    elif '/p1/p1' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/p૧/p૧",
            f"{base_number}/પ૧/પ૧",
            f"{base_number}/p1/p1",
            f"{base_number}/પૈ/પૈ",
            f"{base_number}/પૈકી/પૈકી"
        ])
    elif '/p2/p2' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/p૨/p૨",
            f"{base_number}/પ૨/પ૨",
            f"{base_number}/p2/p2",
            f"{base_number}/પૈ/પૈ",
            f"{base_number}/પૈકી/પૈકી"
        ])
    elif '/p3/p3' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/p૩/p૩",
            f"{base_number}/પ૩/પ૩",
            f"{base_number}/p3/p3",
            f"{base_number}/પૈ/પૈ",
            f"{base_number}/પૈકી/પૈકી"
        ])
    # Handle p1, p2, p3 patterns
    elif '/p1' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/p૧",
            f"{base_number}/પ૧",
            f"{base_number}/p1",
            f"{base_number}/૧"
        ])
    elif '/p2' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/p૨",
            f"{base_number}/પ૨",
            f"{base_number}/p2",
            f"{base_number}/૨"
        ])
    elif '/p3' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/p૩",
            f"{base_number}/પ૩",
            f"{base_number}/p3",
            f"{base_number}/૩"
        ])
    # Handle direct digit patterns
    elif re.search(r'/\d', suffix):
        digit = re.search(r'/(\d)', suffix).group(1)
        gujarati_digit = digit_map.get(digit, digit)
        alternative_formats.extend([
            f"{base_number}/{gujarati_digit}",
            f"{base_number}/p{gujarati_digit}",
            f"{base_number}/{digit}"
        ])
    # Check for paiki paiki notation (abbreviated as "pa/pa" in English)
    elif re.search(r'/pa/pa', suffix_lower) or re.search(r'/પૈ/પૈ', suffix):
        alternative_formats.extend([
            f"{base_number}/પૈ/પૈ",
            f"{base_number}/પૈકી/પૈકી",
            f"{base_number}/pa/pa",
            f"{base_number}/pe/pe"
        ])
    # Check for paiki notation (abbreviated as "pa" in English)
    elif re.search(r'/pa\b', suffix_lower) or re.search(r'/પૈ\b', suffix):
        alternative_formats.extend([
            f"{base_number}/પૈ",
            f"{base_number}/પૈકી",
            f"{base_number}/pa",
            f"{base_number}/pe"
        ])
    # Check for pe notation (alternative spelling of paiki)
    elif re.search(r'/pe\b', suffix_lower) or re.search(r'/પૈ\b', suffix):
        alternative_formats.extend([
            f"{base_number}/પૈ",
            f"{base_number}/પૈકી",
            f"{base_number}/pa",
            f"{base_number}/pe"
        ])
    # Check for 'q' or 'ર' notation (Gujarati letter 'ra')
    elif re.search(r'/q\b', suffix_lower) or re.search(r'/ર\b', suffix):
        alternative_formats.extend([
            f"{base_number}/ર",
            f"{base_number}/ર્",
            f"{base_number}/q"
        ])
    # Check for 'e' or 'ૈ' notation (Gujarati vowel sign)
    elif re.search(r'/e\b', suffix_lower) or re.search(r'/ૈ\b', suffix):
        alternative_formats.extend([
            f"{base_number}/ૈ",
            f"{base_number}/પૈ",
            f"{base_number}/e"
        ])
    
    # Remove duplicates while preserving order
    seen = set()
    unique_alternatives = []
    for alt in alternative_formats:
        if alt not in seen:
            seen.add(alt)
            unique_alternatives.append(alt)
    
    return unique_alternatives

def main():
    """Main function to run the program."""
    parser = argparse.ArgumentParser(description="Process Bhuj Solar Land Survey List")
    parser.add_argument('--excel-file', default="Bhuj Solar Land Survey List Feb 24 2025.xlsx",
                        help="Path to the Excel file")
    parser.add_argument('--output-dir', default="output",
                        help="Base directory for output files")
    parser.add_argument('--no-sequential', action='store_true',
                        help="Process records in parallel instead of sequentially")
    parser.add_argument('--max-workers', type=int, default=4,
                        help="Maximum number of parallel workers")
    parser.add_argument('--start-row', type=int, default=0,
                        help="Start processing from this row number")
    parser.add_argument('--end-row', type=int, default=None,
                        help="Stop processing at this row number")
    parser.add_argument('--pdf-only', action='store_true',
                        help="Only fetch PDFs, skip TSR generation")
    parser.add_argument('--verbose', action='store_true',
                        help="Enable verbose logging")
    parser.add_argument('--test-conversion', action='store_true',
                        help="Test survey number conversion without fetching records")
    parser.add_argument('--survey-numbers', nargs='+',
                        help="List of survey numbers to test conversion or to process specifically")
    parser.add_argument('--process-survey-numbers', action='store_true',
                        help="Process only specific survey numbers provided in --survey-numbers")
    parser.add_argument('--no-cleanup', action='store_true',
                        help="Skip cleanup of chromedriver cache between runs")
    parser.add_argument('--regenerate', action='store_true',
                        help="Regenerate PDFs even if they already exist")
    parser.add_argument('--headless', action='store_true',
                        help="Run in headless mode (default: False)")
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(args.verbose)
    if args.test_conversion:
        if not args.survey_numbers:
            logger.error("Please provide survey numbers to test with --survey-numbers")
            return
        
        for survey in args.survey_numbers:
            converted = convert_survey_number(survey)
            print(f"Original: {survey} -> Converted: {converted}")
        return
    
    # Clean up ChromeDriver cache if not disabled
    if not args.no_cleanup:
        try:
            # Import WebDriverManager and clean the cache
            from anyror_refactored import WebDriverManager
            wdm = WebDriverManager()
            logger.info("Cleaning ChromeDriver cache before starting")
            wdm._clean_chromedriver_cache()
        except Exception as e:
            logger.warning(f"Failed to clean ChromeDriver cache: {str(e)}")
    
    # Update the AnyRoRScraper initialization in process_single_row
    try:
        # Initialize scraper with non-headless mode by default
        scraper = AnyRoRScraper(headless=args.headless, logger=logger)
        
        # Add additional debugging for land record type selection
        if scraper.driver:
            try:
                # Try to select land record type directly using JavaScript
                js_script = """
                    var select = document.getElementById('ContentPlaceHolder1_drpLandRecord');
                    if(select) {
                        select.value = '8';
                        var event = new Event('change', { bubbles: true });
                        select.dispatchEvent(event);
                        if(typeof jQuery !== 'undefined') {
                            jQuery(select).trigger('change');
                        }
                        return true;
                    }
                    return false;
                """
                result = scraper.driver.execute_script(js_script)
                logger.info(f"Direct JavaScript selection result: {result}")
            except Exception as e:
                logger.warning(f"JavaScript selection attempt failed: {str(e)}")
        
        process_bhuj_solar_data(args)
    finally:
        if scraper and scraper.driver:
            try:
                scraper.driver.quit()
            except:
                pass

if __name__ == "__main__":
    main()