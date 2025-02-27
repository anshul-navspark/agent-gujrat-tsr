#!/usr/bin/env python3
"""
TSR Generator - Main Entry Point

This module provides a command-line interface for the TSR generator package.
"""

import argparse
import sys
from tsr_generator.utils.logging_utils import setup_logging
from tsr_generator.api.tsr_generator import generate_tsr_from_pdf

def main():
    """Main function to run the script from command line"""
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Generate TSR from PDF')
    parser.add_argument('pdf_path', help='Path to the PDF file')
    parser.add_argument('--output', '-o', default='tsr_output.docx', help='Output path for the TSR document')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    args = parser.parse_args()
    
    # Set up logging
    logger = setup_logging()
    
    # Generate TSR
    logger.info(f"Starting TSR generation for {args.pdf_path}")
    result = generate_tsr_from_pdf(args.pdf_path, args.output, logger)
    
    if result['success']:
        logger.info(f"TSR generated successfully: {result['tsr_path']}")
        print(f"TSR generated successfully: {result['tsr_path']}")
        return 0
    else:
        logger.error(f"Failed to generate TSR: {result['error']}")
        print(f"Failed to generate TSR: {result['error']}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 