import os
import json
import re
import logging
import traceback
from datetime import datetime
from langchain_openai import AzureChatOpenAI
from pydantic import SecretStr
from dotenv import load_dotenv

def extract_entry_details_ai(pdf_text):
    """
    Extract entry details using dedicated AI call - focusing on the section between
    "Entry Details" and "Jantri Detail" sections.
    
    Args:
        pdf_text (str): The full text of the PDF document
        
    Returns:
        list: A list of dictionaries with entry details
    """
    logger = logging.getLogger(__name__)
    logger.info("Extracting entry details using dedicated AI call")
    
    try:
        # Try to isolate the Entry Details section for more focused extraction
        entry_section = ""
        entry_section_start = pdf_text.find("Entry Details")
        jantri_section_start = pdf_text.find("Jantri Detail")
        
        if entry_section_start > -1 and jantri_section_start > entry_section_start:
            entry_section = pdf_text[entry_section_start:jantri_section_start]
            logger.info("Successfully isolated Entry Details section")
        else:
            # Fallback to using a portion of the document if we can't isolate the section
            entry_section = pdf_text
            logger.warning("Could not isolate Entry Details section, using full document")
        
        # Initialize Azure OpenAI client
        load_dotenv()
        llm = AzureChatOpenAI(
            model="gpt-4o",
            api_version='2024-02-15-preview',
            azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT', ''),
            api_key=SecretStr(os.getenv('AZURE_OPENAI_KEY', '')),
            temperature=0.0
        )
        
        # Create a focused prompt for extracting entries
        prompt = f"""
        Extract all mutation entries from this land record document. 
        In this document, entries are identified by a number (e.g., 1009, 897, 839, 825) and typically include:
        
        1. entry_number - The entry/record number
        2. date - The date of the entry (like DD/MM/YYYY)
        3. type - The type of entry (e.g., LOAN, DEATH, RELEASE, PARTITION)
        4. description - Detailed description of what the entry is about
        
        Look for sections that might be labeled "Entry Details", "નોંધ નંબર", or similar.
        Entries might be in Gujarati, so please translate all content to English.
        
        Important types of entries to identify:
        - Loan entries (when someone takes a loan against the land)
        - Death/inheritance entries (when land is transferred to heirs)
        - Release/relinquishment entries (when rights are given up in favor of someone)
        - Sale entries (when land is sold)
        - Partition entries (when land is distributed among family members)
        
        Format your response as a JSON array of objects with the keys: entry_number, date, type, description
        
        Here's the relevant document section:
        {entry_section}
        """
        
        response = llm.invoke(prompt)
        
        # Parse JSON from the response
        json_match = re.search(r'\[\s*\{.*\}\s*\]', response.content, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            entries = json.loads(json_str)
            logger.info(f"Successfully extracted {len(entries)} entries")
            return entries
        else:
            logger.warning("Failed to parse JSON from AI response for entry details")
            # If no entries found, try another approach with a different prompt
            return extract_entry_details_fallback(entry_section)
    
    except Exception as e:
        logger.error(f"Error in AI-based entry details extraction: {str(e)}")
        return [{
            'entry_number': "1",
            'date': datetime.now().strftime('%d/%m/%Y'),
            'type': "Summary",
            'description': "This land record document contains information about land ownership and historical records."
        }]

def extract_entry_details_fallback(entry_section):
    """
    Fallback method for entry extraction if the main method fails.
    Uses a different prompt approach.
    
    Args:
        entry_section (str): The entry details section text
        
    Returns:
        list: A list of dictionaries with entry details
    """
    logger = logging.getLogger(__name__)
    logger.info("Using fallback method for entry extraction")
    
    try:
        # Initialize Azure OpenAI client
        load_dotenv()
        llm = AzureChatOpenAI(
            model="gpt-4o",
            api_version='2024-02-15-preview',
            azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT', ''),
            api_key=SecretStr(os.getenv('AZURE_OPENAI_KEY', '')),
            temperature=0.0
        )
        
        # Alternative prompt focusing on direct extraction
        prompt = f"""
        Look at this land record document text and find all numbered entries. 
        
        Here's what I need:
        1. Find entry numbers (like 1009, 897, 839, 825)
        2. Find dates associated with each entry
        3. Determine the type of each entry (LOAN, INHERITANCE, RELEASE, etc.)
        4. Extract a description of what each entry is about
        
        Translate any Gujarati text to English.
        
        Format your response as a JSON array with objects containing these exact keys:
        "entry_number", "date", "type", "description"
        
        Here's the text to analyze:
        {entry_section}
        """
        
        response = llm.invoke(prompt)
        
        # Parse JSON from the response
        json_match = re.search(r'\[\s*\{.*\}\s*\]', response.content, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            entries = json.loads(json_str)
            logger.info(f"Successfully extracted {len(entries)} entries using fallback method")
            return entries
        else:
            logger.warning("Failed to parse JSON from fallback approach")
            return [{
                'entry_number': "1",
                'date': datetime.now().strftime('%d/%m/%Y'),
                'type': "Summary",
                'description': "This land record document contains information about land ownership and historical records."
            }]
            
    except Exception as e:
        logger.error(f"Error in fallback entry extraction: {str(e)}")
        return [{
            'entry_number': "1",
            'date': datetime.now().strftime('%d/%m/%Y'),
            'type': "Summary",
            'description': "This land record document contains information about land ownership and historical records."
        }]

def extract_entry_details(pdf_text):
    """
    Main function for extracting entry details using the AI-based approach.
    This replaces the previous two-stage approach with a focused AI extraction.
    
    Args:
        pdf_text (str): The full text of the PDF document
        
    Returns:
        list: A list of dictionaries with fully processed entries
    """
    logger = logging.getLogger(__name__)
    logger.info("Extracting entry details using AI-based approach")
    
    try:
        # Use the dedicated AI function to extract entries
        entries = extract_entry_details_ai(pdf_text)
        
        if not entries:
            logger.warning("No entries extracted, using fallback method")
            entries = [{
                'entry_number': "1",
                'date': datetime.now().strftime('%d/%m/%Y'),
                'type': "Summary",
                'description': "This land record document contains information about land ownership and historical records."
            }]
        
        # Validate entries
        validated_entries = []
        for entry in entries:
            validated_entry = {
                'entry_number': str(entry.get('entry_number', '')).strip(),
                'date': str(entry.get('date', '')).strip(),
                'type': str(entry.get('type', '')).strip(),
                'description': str(entry.get('description', 'Not Available')).strip()
            }
            
            # Only include entries with valid entry numbers
            if validated_entry['entry_number']:
                validated_entries.append(validated_entry)
        
        # Sort entries by entry number if possible
        try:
            validated_entries = sorted(validated_entries, 
                                       key=lambda x: int(x['entry_number']) if x['entry_number'].isdigit() else 9999)
        except Exception as sort_error:
            logger.warning(f"Error sorting entries: {str(sort_error)}")
        
        logger.info(f"Successfully processed {len(validated_entries)} entries")
        return validated_entries
        
    except Exception as e:
        logger.error(f"Error in entry extraction process: {str(e)}")
        logger.error("Stack trace:", exc_info=True)
        return [{
            'entry_number': "1",
            'date': datetime.now().strftime('%d/%m/%Y'),
            'type': "Summary",
            'description': "This land record document contains information about land ownership and historical records."
        }]

def translate_entry_content(entries):
    """
    Translate Gujarati content to English
    
    Args:
        entries (list): List of entry dictionaries
        
    Returns:
        list: List of entries with translated content
    """
    logger = logging.getLogger(__name__)
    
    translated_entries = []
    for entry in entries:
        # Create a new entry with translated content
        translated_entry = {
            'entry_number': entry['entry_number'],
            'date': entry.get('date', ''),
            'description': entry.get('description', 'Not Available')
        }
        
        # Translate type if present
        if 'type' in entry and entry['type']:
            if entry['type'] == 'મોલગેશન':
                translated_entry['type'] = 'Promulgation'
            elif entry['type'] == 'હુકમથી':
                translated_entry['type'] = 'Order'
            else:
                translated_entry['type'] = entry['type']
        
        translated_entries.append(translated_entry)
    
    logger.info(f"Translated {len(translated_entries)} entries")
    return translated_entries 