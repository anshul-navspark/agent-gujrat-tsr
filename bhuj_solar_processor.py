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
    --parallel         Process records in parallel instead of sequentially
    --max-workers      Maximum number of parallel workers (default: 4)
    --start-row        Start processing from this row number (default: 0, first data row)
    --end-row          Stop processing at this row number (default: process all)
    --pdf-only         Only fetch PDFs, skip TSR generation
    --verbose          Enable verbose logging
    --survey-numbers   List of survey numbers to process (filters Excel to only these survey numbers)
    --regenerate       Regenerate PDFs even if they already exist
    --no-headless      Run in visible mode (default: run headless)
"""

import os
import sys
import subprocess
import pandas as pd
import logging
from datetime import datetime
import time
import traceback
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import argparse
from tqdm import tqdm

from anyror import AnyRoRScraper, WebDriverManager
from tsr_generator import generate_tsr_from_pdf
from utils.json_translations import translate_to_gujarati, TranslationNotFoundError
from utils.survey_utils import convert_survey_number, sanitize_filename

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
            sys.stdout  # Also print to console
        ]
    )
    return logging.getLogger(__name__)

# A completely self-contained function to fetch the land record
def fetch_land_record_isolated(district, taluka, village, survey, output_path, headless_mode, timeout=300):
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
        
        # AnyRoRScraper already imported at top of file
        
        # Clean up any zombie processes first
        try:
            subprocess_cmd = ["pkill", "-f", "chromedriver"]
            subprocess.run(subprocess_cmd, check=False)
        except Exception as e:
            logger.warning(f"Failed to kill zombie processes: {str(e)}")
        
        # Create scraper instance and fetch the land record
        scraper = AnyRoRScraper(headless=headless_mode, logger=logger)
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
        try:
            guj_district = translate_to_gujarati(district, context='district')
            guj_taluka = translate_to_gujarati(taluka, context='taluka')
            guj_village = translate_to_gujarati(village, context='village')
        except TranslationNotFoundError as e:
            logger.error(f"Skipping row {row.name}: {e}")
            result['error'] = str(e)
            result['status'] = 'Skipped'
            return result
        
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
        
        # Log the processing information (debug level - too verbose for INFO)
        logger.debug(f"Processing row {row.name}: {district} ({guj_district}), {taluka} ({guj_taluka}), "
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
            result['pdf_path'] = pdf_path
            result['status'] = 'PDF Already Exists'
        else:
            # Fetch the land record and save as PDF
            logger.debug(f"Fetching land record for row {row.name}")
            
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    # Use the regular anyror_refactored for sequential mode
                    if not args.parallel:
                        # Clean up any zombie chromedriver processes first
                        try:
                            # WebDriverManager already imported at top
                            wdm = WebDriverManager()
                            wdm._kill_zombie_chromedrivers()
                        except Exception as e:
                            logger.warning(f"Failed to kill zombie processes: {str(e)}")
                        
                        # Create scraper instance and fetch the land record
                        is_headless = not args.no_headless
                        scraper = AnyRoRScraper(headless=is_headless, logger=logger)
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
                    else:  # parallel mode
                        # For parallel mode, use our isolated function in a process pool
                        # This ensures complete isolation of the browser instances
                        with ProcessPoolExecutor(max_workers=1) as executor:
                            future = executor.submit(
                                fetch_land_record_isolated,
                                guj_district, guj_taluka, guj_village, guj_survey, pdf_path, not args.no_headless, 300  # Add timeout
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
                logger.debug(f"Generating TSR for row {row.name}")
                
                generate_tsr_from_pdf(
                    pdf_path=result['pdf_path'],
                    output_path=tsr_path
                )
                
                result['tsr_path'] = tsr_path
                result['status'] = 'TSR Generated'
                logger.debug(f"Report generated successfully: {tsr_path}")
                
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
    os.makedirs(tsr_dir, exist_ok=True)
    
    # Read the Excel file
    excel_path = args.excel_file
    logger.info(f"Reading Excel file: {excel_path}")
    
    try:
        data_df = pd.read_excel(excel_path)
        data_df = data_df.fillna('')
        
        logger.info(f"Successfully read data with {len(data_df)} records")
    except Exception as e:
        logger.error(f"Error reading Excel file: {str(e)}")
        return []

    # Filter rows if specific survey numbers are requested
    if args.survey_numbers:
        logger.debug(f"Filtering by specific survey numbers: {args.survey_numbers}")
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
            logger.debug(f"Filtered to {len(data_df)} rows matching the specified survey numbers")
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
    
    if args.parallel:
        logger.info("Processing in parallel")
        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
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



def main():
    """Main function to run the program."""
    parser = argparse.ArgumentParser(description="Process Bhuj Solar Land Survey List")
    parser.add_argument('--excel-file', default="Bhuj Solar Land Survey List Feb 24 2025.xlsx",
                        help="Path to the Excel file")
    parser.add_argument('--output-dir', default="output",
                        help="Base directory for output files")
    parser.add_argument('--parallel', action='store_true',
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
    parser.add_argument('--survey-numbers', nargs='+',
                        help="List of survey numbers to process (filters Excel to only these survey numbers)")
    parser.add_argument('--regenerate', action='store_true',
                        help="Regenerate PDFs even if they already exist")
    parser.add_argument('--no-headless', action='store_true',
                        help="Run in visible mode (disable headless mode)")
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(args.verbose)
    
    # Clean up ChromeDriver cache
    try:
        # WebDriverManager already imported at top
        wdm = WebDriverManager()
        logger.info("Cleaning ChromeDriver cache before starting")
        wdm._clean_chromedriver_cache()
    except Exception as e:
        logger.warning(f"Failed to clean ChromeDriver cache: {str(e)}")
    
    # Process the data
    process_bhuj_solar_data(args)

if __name__ == "__main__":
    main()