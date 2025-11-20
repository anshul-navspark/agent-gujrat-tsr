#!/usr/bin/env python3
"""
Batch TSR Generator
Generates TSR DOCX files for all PDFs in a directory
"""

import os
import sys
import logging
from pathlib import Path
from tqdm import tqdm

from tsr_generator import generate_tsr_from_pdf

def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('batch_tsr_generation.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

def generate_tsr_for_pdfs(pdf_directory, output_directory=None, logger=None):
    """
    Generate TSR DOCX files for all PDFs in a directory
    
    Args:
        pdf_directory: Path to directory containing PDF files
        output_directory: Path to save TSR DOCX files (default: same as PDF directory)
        logger: Logger instance
    """
    if logger is None:
        logger = setup_logging()
    
    pdf_dir = Path(pdf_directory)
    if not pdf_dir.exists():
        logger.error(f"PDF directory does not exist: {pdf_directory}")
        return
    
    # Set output directory
    if output_directory is None:
        output_dir = pdf_dir / "tsr"
    else:
        output_dir = Path(output_directory)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output directory: {output_dir}")
    
    # Find all PDF files
    pdf_files = list(pdf_dir.glob("*.pdf"))
    total_pdfs = len(pdf_files)
    
    if total_pdfs == 0:
        logger.warning(f"No PDF files found in {pdf_directory}")
        return
    
    logger.info(f"Found {total_pdfs} PDF files to process")
    
    # Statistics
    successful = 0
    failed = 0
    skipped = 0
    
    # Process each PDF
    for pdf_file in tqdm(pdf_files, desc="Generating TSRs"):
        pdf_name = pdf_file.stem
        output_path = output_dir / f"{pdf_name}.docx"
        
        # Skip if TSR already exists
        if output_path.exists():
            logger.info(f"Skipping {pdf_name} - TSR already exists")
            skipped += 1
            continue
        
        logger.info(f"Processing: {pdf_file.name}")
        
        try:
            result = generate_tsr_from_pdf(
                str(pdf_file),
                str(output_path),
                logger=logger
            )
            
            if result.get('success'):
                successful += 1
                logger.info(f"✓ Successfully generated TSR for {pdf_name}")
            else:
                failed += 1
                error_msg = result.get('error', 'Unknown error')
                logger.error(f"✗ Failed to generate TSR for {pdf_name}: {error_msg}")
                
        except Exception as e:
            failed += 1
            logger.error(f"✗ Exception while processing {pdf_name}: {str(e)}")
    
    # Print summary
    logger.info("\n" + "="*60)
    logger.info("BATCH PROCESSING SUMMARY")
    logger.info("="*60)
    logger.info(f"Total PDFs: {total_pdfs}")
    logger.info(f"Successful: {successful}")
    logger.info(f"Failed: {failed}")
    logger.info(f"Skipped (already exists): {skipped}")
    logger.info(f"Output directory: {output_dir}")
    logger.info("="*60)

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate TSR DOCX files for all PDFs in a directory"
    )
    parser.add_argument(
        "--pdf-dir",
        type=str,
        default="/Users/anshulgoyal/Downloads/pdfs",
        help="Directory containing PDF files (default: /Users/anshulgoyal/Downloads/pdfs)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory to save TSR DOCX files (default: pdf-dir/tsr)"
    )
    
    args = parser.parse_args()
    
    logger = setup_logging()
    logger.info("Starting batch TSR generation...")
    logger.info(f"PDF directory: {args.pdf_dir}")
    
    generate_tsr_for_pdfs(args.pdf_dir, args.output_dir, logger)
    
    logger.info("Batch processing completed!")

if __name__ == "__main__":
    main()

