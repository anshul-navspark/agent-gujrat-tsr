#!/usr/bin/env python3
"""
TSR Generator - Main Entry Point

This module provides a command-line interface for the TSR generator package.
"""

import argparse
import logging
import sys
# Unified (optimized) extraction is the only path; import the package-level entry point.
# Importing the package also configures root logging (tsr_generator/__init__.py).
from tsr_generator import generate_tsr_from_pdf

def main():
    """Main function to run the script from command line"""
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Generate TSR from PDF')
    parser.add_argument('pdf_path', help='Path to the PDF file')
    parser.add_argument('--output', '-o', default='tsr_output.docx', help='Output path for the TSR document')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    args = parser.parse_args()

    # Logging is configured at package import; just grab a logger.
    logger = logging.getLogger("tsr_generator")
    logger.setLevel(logging.DEBUG if args.verbose else logging.INFO)

    # Generate TSR
    logger.info(f"Starting TSR generation for {args.pdf_path}")
    result = generate_tsr_from_pdf(args.pdf_path, args.output)
    
    if result.get('success'):
        logger.info(f"TSR generated successfully: {result['tsr_path']}")
        print(f"TSR generated successfully: {result['tsr_path']}")
        return 0
    else:
        logger.error(f"Failed to generate TSR: {result['error']}")
        print(f"Failed to generate TSR: {result['error']}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 