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
    --sequential       Process records sequentially instead of in parallel
    --max-workers      Maximum number of parallel workers (default: 4)
    --start-row        Start processing from this row number (default: 0, first data row)
    --end-row          Stop processing at this row number (default: process all)
    --pdf-only         Only fetch PDFs, skip TSR generation
    --verbose          Enable verbose logging
    --test-conversion  Test survey number conversion without fetching records
    --survey-numbers   List of survey numbers to test conversion (used with --test-conversion)
"""

import os
import sys
import pandas as pd
import logging
from datetime import datetime
import time
import traceback
import concurrent.futures
import argparse
from tqdm import tqdm
import re

# Import your existing modules
# import anyror_new
import anyrortoTSR
import anyror_refactored

# Add these dictionaries for English to Gujarati translation
DISTRICT_TRANSLATIONS = {
    "Patan": "પાટણ",
    "Kutch": "કચ્છ",
    "Bhuj": "ભુજ",
    "Kachchh": "કચ્છ",
    # Add more districts as needed
}

TALUKA_TRANSLATIONS = {
    "Patan": "પાટણ",
    "Bhuj": "ભુજ",
    "Anjar": "અંજાર",
    "Abdasa": "અબડાસા",
    # Add more talukas as needed
}

VILLAGE_TRANSLATIONS = {
    "Anavada": "અનાવાડા - 091",
    "Trambo": "ત્રંબો - 033",
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
    - Numbers with '/1' are formatted as "/૧" (with Gujarati numeral ૧)
    - Numbers with '/2' are formatted as "/૨" (with Gujarati numeral ૨)
    - Numbers with '/3' are formatted as "/૩" (with Gujarati numeral ૩)
    - Complex patterns like 'p1/p1' are converted to 'p૧/p૧'
    - Special patterns like 'paq', 'pae', 'pac', 'pu', 'pa3e' are handled
    
    Args:
        survey_number (str): The original survey number
        
    Returns:
        str: The converted survey number
    """
    # Convert to string if not already
    survey_number = str(survey_number).strip()
    
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
    
    # Function to convert a digit to Gujarati
    def to_gujarati_digit(match):
        digit = match.group(1)
        return digit_map.get(digit, digit)
    
    # Extract the suffix (everything after the base number)
    suffix = survey_number[len(base_number):]
    suffix_lower = suffix.lower()
    
    # Handle special complex patterns from the image
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
    elif '/pae' in suffix_lower:
        return f"{base_number}/પાૈ"
    elif '/pa30' in suffix_lower:
        return f"{base_number}/પા૩૦"
    
    # Handle complex patterns with multiple components
    if '/p1/p1' in suffix_lower:
        return f"{base_number}/p૧/p૧"
    elif '/p2/p2' in suffix_lower:
        return f"{base_number}/p૨/p૨"
    elif '/p3/p3' in suffix_lower:
        return f"{base_number}/p૩/p૩"
    
    # Handle p1, p2, p3 patterns
    if '/p1' in suffix_lower:
        suffix = re.sub(r'/p1', r'/p૧', suffix.lower())
    elif '/p2' in suffix_lower:
        suffix = re.sub(r'/p2', r'/p૨', suffix.lower())
    elif '/p3' in suffix_lower:
        suffix = re.sub(r'/p3', r'/p૩', suffix.lower())
    
    # Handle direct digit patterns (convert /1 to /૧, etc.)
    suffix = re.sub(r'/(\d)', lambda m: f"/{digit_map[m.group(1)]}", suffix)
    
    # Check for paiki paiki notation (abbreviated as "pa/pa" in English)
    if re.search(r'/pa/pa', suffix.lower()) or re.search(r'/પૈ/પૈ', suffix):
        return f"{base_number}/પૈ/પૈ"
    
    # Check for paiki notation (abbreviated as "pa" in English)
    if re.search(r'/pa\b', suffix.lower()) or re.search(r'/પૈ\b', suffix):
        return f"{base_number}/પૈ"
    
    # Check for pe notation (alternative spelling of paiki)
    if re.search(r'/pe\b', suffix.lower()) or re.search(r'/પૈ\b', suffix):
        return f"{base_number}/પૈ"
    
    # Check for 'q' or 'ર' notation (Gujarati letter 'ra')
    if re.search(r'/q\b', suffix.lower()) or re.search(r'/ર\b', suffix):
        return f"{base_number}/ર"
    
    # Check for 'e' or 'ૈ' notation (Gujarati vowel sign)
    if re.search(r'/e\b', suffix.lower()) or re.search(r'/ૈ\b', suffix):
        return f"{base_number}/ૈ"
    
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
    # Replace slashes and other problematic characters with underscores
    return re.sub(r'[\\/*?:"<>|]', '_', filename)

def process_single_row(row, args, logger):
    """Process a single row from the Excel data"""
    # Get English values from the Excel - use correct column names
    district_eng = row.get('District', '')
    taluka_eng = row.get('Tehsil', '')
    village_eng = row.get('Village', '')
    survey = str(row.get('Survey Nos', ''))
    
    # Skip rows with empty essential fields
    if not district_eng or not taluka_eng or not village_eng or not survey:
        logger.warning(f"Skipping row {row.name} due to missing essential data: District={district_eng}, Taluka={taluka_eng}, Village={village_eng}, Survey={survey}")
        return {
            'row': row.name,
            'district': district_eng,
            'taluka': taluka_eng,
            'village': village_eng,
            'survey': survey,
            'pdf_success': False,
            'pdf_path': '',
            'tsr_success': False,
            'tsr_path': '',
            'error': 'Missing essential data',
            'processing_time': 0
        }
    
    # Translate to Gujarati
    district = translate_to_gujarati(district_eng, DISTRICT_TRANSLATIONS, district_eng)
    taluka = translate_to_gujarati(taluka_eng, TALUKA_TRANSLATIONS, taluka_eng)
    village = translate_to_gujarati(village_eng, VILLAGE_TRANSLATIONS, village_eng)
    
    # Convert survey number to the format expected by the website
    converted_survey = convert_survey_number(survey)
    
    logger.info(f"Processing row {row.name}: {district_eng} ({district}), {taluka_eng} ({taluka}), {village_eng} ({village}), Survey: {survey} (Converted: {converted_survey})")
    
    # Create sanitized file names - ensure survey is not empty
    sanitized_survey = sanitize_filename(survey) if survey else "unknown"
    pdf_dir = os.path.join(args.output_dir, "pdfs")
    tsr_dir = os.path.join(args.output_dir, "tsr")
    
    pdf_path = os.path.join(pdf_dir, f"land_record_row{row.name}_survey{sanitized_survey}.pdf")
    tsr_path = os.path.join(tsr_dir, f"tsr_row{row.name}_survey{sanitized_survey}.docx")
    
    # Ensure directories exist
    os.makedirs(pdf_dir, exist_ok=True)
    os.makedirs(tsr_dir, exist_ok=True)
    
    result = {
        'row': row.name,
        'district': district_eng,
        'taluka': taluka_eng,
        'village': village_eng,
        'survey': survey,
        'converted_survey': converted_survey,  # Add the converted survey number to the result
        'pdf_success': False,
        'pdf_path': '',
        'tsr_success': False,
        'tsr_path': '',
        'error': '',
        'processing_time': 0
    }
    
    start_time = time.time()
    
    try:
        # Step 1: Fetch land record PDF using Gujarati names and converted survey number
        logger.info(f"Fetching land record for row {row.name}")
        pdf_result = anyror_refactored.fetch_land_record(
            district_name=district,  # Gujarati name
            taluka_name=taluka,      # Gujarati name
            village_name=village,    # Gujarati name
            survey_block_number=converted_survey,  # Use the converted survey number
            output_path=pdf_path,
            logger=logger
        )
        
        # If first attempt fails, try alternative formats
        if not pdf_result['success'] and "Survey/Block Number not found" in pdf_result.get('error', ''):
            logger.warning(f"First attempt failed for survey {converted_survey}, trying alternative formats")
            
            # Try alternative formats
            alternative_formats = get_alternative_survey_formats(survey)
            
            # Try each alternative format
            for alt_format in alternative_formats:
                logger.info(f"Trying alternative format: {alt_format}")
                alt_pdf_result = anyror_refactored.fetch_land_record(
                    district_name=district,
                    taluka_name=taluka,
                    village_name=village,
                    survey_block_number=alt_format,
                    output_path=pdf_path,
                    logger=logger
                )
                
                if alt_pdf_result['success']:
                    logger.info(f"Alternative format {alt_format} succeeded")
                    pdf_result = alt_pdf_result
                    result['converted_survey'] = alt_format  # Update the successful format
                    break
        
        if pdf_result['success']:
            # Verify the PDF file actually exists
            if os.path.exists(pdf_path):
                result['pdf_success'] = True
                result['pdf_path'] = pdf_path
                
                # Step 2: Generate TSR if PDF was successful and not in pdf-only mode
                if not args.pdf_only:
                    logger.info(f"Generating TSR for row {row.name}")
                    tsr_result = anyrortoTSR.generate_tsr_from_pdf(
                        pdf_path=pdf_path,
                        output_path=tsr_path,
                        logger=logger
                    )
                    
                    if tsr_result['success']:
                        result['tsr_success'] = True
                        result['tsr_path'] = tsr_path
                    else:
                        error_msg = f"Failed to generate TSR for row {row.name}: {tsr_result.get('error', 'Unknown error')}"
                        logger.error(error_msg)
                        result['error'] = error_msg
                else:
                    result['tsr_success'] = None  # Not attempted
            else:
                error_msg = f"PDF file not found at {pdf_path} despite successful fetch"
                logger.error(error_msg)
                result['error'] = error_msg
        else:
            error_msg = f"Failed to fetch land record for row {row.name}: {pdf_result.get('error', 'Unknown error')}"
            logger.error(error_msg)
            result['error'] = error_msg
    
    except Exception as e:
        error_msg = f"Error processing row {row.name}: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        result['error'] = error_msg
    
    result['processing_time'] = time.time() - start_time
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

    # Filter rows if specified
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
    
    if args.sequential:
        logger.info("Processing sequentially")
        for idx, row in tqdm(data_df.iterrows(), total=len(data_df), desc="Processing"):
            result = process_single_row(row, args, logger)
            results.append(result)
            
            # Update summary DataFrame using concat instead of append
            summary_df = pd.concat([summary_df, pd.DataFrame([result])], ignore_index=True)
            
            # Save intermediate results
            summary_df.to_csv(summary_path, index=False)
    else:
        logger.info(f"Processing in parallel with {args.max_workers} workers")
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
    """Main entry point"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Process Bhuj Solar Land Survey List')
    
    parser.add_argument('--excel-file', default="Bhuj Solar Land Survey List Feb 24 2025.xlsx",
                        help='Path to the Excel file (default: "Bhuj Solar Land Survey List Feb 24 2025.xlsx")')
    
    parser.add_argument('--output-dir', default="output",
                        help='Base directory for output files (default: "output")')
    
    parser.add_argument('--sequential', action='store_true',
                        help='Process records sequentially instead of in parallel')
    
    parser.add_argument('--max-workers', type=int, default=4,
                        help='Maximum number of parallel workers (default: 4)')
    
    parser.add_argument('--start-row', type=int, default=0,
                        help='Start processing from this row number (default: 0, first data row)')
    
    parser.add_argument('--end-row', type=int, default=None,
                        help='Stop processing at this row number (default: process all)')
    
    parser.add_argument('--pdf-only', action='store_true',
                        help='Only fetch PDFs, skip TSR generation')
    
    parser.add_argument('--verbose', action='store_true',
                        help='Enable verbose logging')
    
    parser.add_argument('--test-conversion', action='store_true',
                        help='Test survey number conversion without fetching records')
    
    parser.add_argument('--survey-numbers', nargs='+',
                        help='List of survey numbers to test conversion (used with --test-conversion)')
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(args.verbose)
    
    try:
        # Test mode for survey number conversion
        if args.test_conversion:
            logger.info("Running in survey number conversion test mode")
            
            # Use provided survey numbers or a set of test cases
            survey_numbers = args.survey_numbers if args.survey_numbers else [
                "142", "143", "144/pa/pa", "144/pa", "145", "145/pa", "146", 
                "147", "147/pa", "148/pa", "148/pe", "149", "150/pa", "150/pa/pa",
                "150/pa/pe", "150/pe", "151", "151/pa", "152", "152/pa", "153/pa",
                "153/pe", "153/p3", "154/q", "154/e", "155", "156", "157", "157/pa",
                "158", "159", "160/pa", "160/pe", "161/q", "161/e", "162", "163",
                "164", "165/q", "165/e"
            ]
            
            # Print header
            print("\nSurvey Number Conversion Test Results:")
            print("-" * 80)
            print(f"{'Original Survey Number':<25} | {'Converted Format':<25} | {'Alternative Formats'}")
            print("-" * 80)
            
            # Test each survey number
            for survey in survey_numbers:
                converted = convert_survey_number(survey)
                alternatives = get_alternative_survey_formats(survey)
                
                # Format alternatives for display (excluding the first one which is usually just the base number)
                alt_display = ", ".join(alternatives[1:4]) if len(alternatives) > 1 else "None"
                if len(alternatives) > 4:
                    alt_display += f" (+ {len(alternatives) - 4} more)"
                
                print(f"{survey:<25} | {converted:<25} | {alt_display}")
            
            print("-" * 80)
            return 0
        
        # Process the data
        logger.info("Starting Bhuj Solar Land Survey processing")
        results = process_bhuj_solar_data(args)
        return 0
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}")
        logger.error(traceback.format_exc())
        return 1

if __name__ == "__main__":
    sys.exit(main())