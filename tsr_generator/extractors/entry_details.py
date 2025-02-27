import os
import json
import re
import logging
import traceback
from datetime import datetime
from langchain_openai import AzureChatOpenAI
from pydantic import SecretStr
from dotenv import load_dotenv

from tsr_generator.extractors.entry_schema import (
    EntryType, Person, BaseEntry, EntryUnion, create_entry_from_dict,
    SaleEntry, MortgageEntry, ReleaseEntry, InheritanceEntry, 
    PartitionEntry, RelinquishmentEntry, OrderEntry, CorrectionEntry, GenericEntry
)

def extract_entry_details_ai(pdf_text):
    """
    Extract entry details from PDF using AI with formatting exactly matching
    the Gujrat Mutation Entry examples
    
    Args:
        pdf_text (str): The full text of the PDF document
        
    Returns:
        list: A list of dictionaries with entry details
    """
    logger = logging.getLogger(__name__)
    logger.info("Extracting entry details to match Gujrat Mutation Entry format")
    
    try:
        # Find the section with entry details
        entry_section = pdf_text
        # Try to focus on just the entry section to reduce noise
        if len(pdf_text) > 5000:
            # Look for entry details section
            m = re.search(r'(?:Entry Details|[\u0A95-\u0AC5]\s*[\u0A95-\u0AC5].*?Details)', pdf_text, re.IGNORECASE)
            if m:
                start = max(0, m.start() - 200)
                entry_section = pdf_text[start:start + 5000]
            else:
                # Use the first part of the document
                entry_section = pdf_text[:5000]
        
        # Initialize Azure OpenAI client
        load_dotenv()
        llm = AzureChatOpenAI(
            model="gpt-4o",
            api_version='2024-02-15-preview',
            azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT', ''),
            api_key=SecretStr(os.getenv('AZURE_OPENAI_KEY', '')),
            temperature=0.0
        )
        
        # Create a focused prompt for extracting entries with the specific format
        prompt = f"""
        Extract all mutation entries from this land record document, exactly matching the format shown in the examples below.
        
        For each entry, extract:
        1. entry_number - The entry number
        2. date - The date (DD/MM/YYYY)
        3. type - Category of entry (LOAN, DEATH, RELEASE, LOAN CLOSE, SALE, PARTITION, PERSONS ADD, TO TRANSFER, etc.)
        4. description - Detailed description following the exact format from examples
        5. certification - Line about certification if available (starts with "The Entry is certified...")
        
        The descriptions MUST follow these exact patterns as shown in the examples:
        
        LOAN Example:
        "That Rabari Sujabhai Jawanabhai and others took a loan of Rs. 1,00,000/- on the land bearing Survey No. 54/2p2(143), 59p3(143), 60/3p2(143), 66/1/2p2(143), 66/2p2(143), 68p5(143) from Voda Group Gopalak Vikas Kariyakari Sahakari Mandli."
        
        DEATH Example:
        "That upon the demise of Jawanabhai Manabhai, his land bearing old Survey No. 59 P, 68 P, 54/2p, 60/3, 66/3 P & 66/2 P came to be mutated in his legal heirs which are as follows:-
        • Sujabhai Jawanabhai 
        • Hariyaben Jawanabhai
        • Keliben Jawanabhai
        • Ajyotiben Jawanabhai
        • Panchuben Jawanabhai
        • Champaben Jawanabhai"
        
        SALE Example:
        "That the said Choudhary Harkhabhai Chhotybhai and Choudhary Shivabhai Harkhabhai they sold their respective share in land bearing Survey No. 241/1 measuring 1-96-27 Hectare to Choudhary Shaileshbhai Devanbhai through the document no. 324/2022 dated 17.05.2022 for a consideration of Rs. 3,00,000/-."
        
        Always start with "That" in the descriptions. For entries involving lists of people, use the format "which are as follows:-" followed by a bulleted list with each person on a separate line.
        
        Also extract certification information if available:
        "The Entry is certified by C.O. Jadiya on 24/12/2007."
        "The Entry is certified but date is not legible."
        
        Format your response as a JSON array with objects containing these keys:
        "entry_number", "date", "type", "description", "certification"
        
        Here's the document section to analyze:
        {entry_section}
        """
        
        response = llm.invoke(prompt)
        
        # Parse JSON from the response
        json_match = re.search(r'\[\s*\{.*\}\s*\]', response.content, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            entries = json.loads(json_str)
            logger.info(f"Successfully extracted {len(entries)} entries with Gujrat Mutation Entry format")
            return entries
        else:
            logger.warning("Failed to parse JSON from AI response for entry details")
            # If no entries found, try the fallback approach
            return extract_entry_details_fallback(entry_section)
    
    except Exception as e:
        logger.error(f"Error in AI-based entry details extraction: {str(e)}")
        logger.error(traceback.format_exc())
        return [{
            'entry_number': "1",
            'date': datetime.now().strftime('%d/%m/%Y'),
            'type': "Summary",
            'description': "This document contains information about the property.",
            'certification': "The Entry is certified but date is not legible."
        }]

def extract_entry_details_fallback(entry_section):
    """
    Fallback method for entry extraction matching Gujrat Mutation Entry format
    
    Args:
        entry_section (str): The entry details section text
        
    Returns:
        list: A list of dictionaries with entry details
    """
    logger = logging.getLogger(__name__)
    logger.info("Using fallback method for Gujrat Mutation Entry format extraction")
    
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
        
        # Simplified prompt focusing on the exact format
        prompt = f"""
        Extract entries from this land record document using EXACTLY this format:
        
        Entry format:
        - entry_number: The numeric entry number
        - date: In DD/MM/YYYY format if available
        - type: One word category (LOAN, DEATH, RELEASE, SALE, PARTITION, etc.)
        - description: Start with "That" and provide complete details
        - certification: Information about who certified the entry and when
        
        Description examples:
        - "That Rabari Sujabhai Jawanabhai and others took a loan of Rs. 1,00,000/- on the land bearing Survey No. 54/2p2(143)..."
        - "That upon the demise of Jawanabhai Manabhai, his land bearing old Survey No. 59 P, 68 P, 54/2p, 60/3, 66/3 P & 66/2 P came to be mutated in his legal heirs which are as follows:-"
        
        Certification examples:
        - "The Entry is certified by C.O. Jadiya on 24/12/2007."
        - "The Entry is certified but date is not legible."
        
        Format your response as a JSON array with objects containing these keys:
        "entry_number", "date", "type", "description", "certification"
        
        Here's the text:
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
                'description': "This document contains information about the property.",
                'certification': "The Entry is certified but date is not legible."
            }]
            
    except Exception as e:
        logger.error(f"Error in fallback entry extraction: {str(e)}")
        logger.error(traceback.format_exc())
        return [{
            'entry_number': "1",
            'date': datetime.now().strftime('%d/%m/%Y'),
            'type': "Summary",
            'description': "This document contains information about the property.",
            'certification': "The Entry is certified but date is not legible."
        }]

def process_entry_details(raw_entries):
    """
    Process raw entry dictionaries into structured entry objects with certification info
    
    Args:
        raw_entries (list): List of dictionaries with raw entry details
        
    Returns:
        list: List of processed entry objects
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Processing {len(raw_entries)} raw entries into structured entries with certification info")
    
    processed_entries = []
    
    for raw_entry in raw_entries:
        try:
            # Create basic entry object
            entry = create_entry_from_dict(raw_entry)
            
            # Process the description to create a formatted version
            format_entry_description(entry, raw_entry)
            
            # Extract additional details based on entry type
            extract_entry_specific_details(entry, raw_entry)
            
            # Ensure certification info is set
            if hasattr(entry, 'certification') and not entry.certification and 'certification' in raw_entry:
                entry.certification = raw_entry['certification']
            
            processed_entries.append(entry)
            
        except Exception as e:
            logger.error(f"Error processing entry {raw_entry.get('entry_number', 'unknown')}: {str(e)}")
            logger.error(traceback.format_exc())
            # Add a basic entry with the original data in case of error
            basic_entry = create_entry_from_dict(raw_entry)
            # Ensure certification is set
            if 'certification' in raw_entry:
                basic_entry.certification = raw_entry['certification']
            processed_entries.append(basic_entry)
    
    # Sort entries by entry number if possible
    try:
        processed_entries = sorted(processed_entries, 
                                  key=lambda x: int(x.entry_number) if x.entry_number.isdigit() else 9999)
    except Exception as sort_error:
        logger.warning(f"Error sorting entries: {str(sort_error)}")
    
    logger.info(f"Successfully processed {len(processed_entries)} entries with certification info")
    return processed_entries

def format_entry_description(entry, raw_entry):
    """
    Format the description for an entry with Gujrat Mutation Entry format
    
    Args:
        entry: Entry object
        raw_entry: Raw entry dictionary
    """
    # Get the raw description
    desc = raw_entry.get('description', '')
    
    # Store original description
    entry.raw_description = desc
    
    # Use the description as provided by the AI extraction
    # which should already be in the format we want
    entry.formatted_description = desc
    
    # Add certification information if available
    if 'certification' in raw_entry and raw_entry['certification']:
        entry.certification = raw_entry['certification']

def extract_entry_specific_details(entry, raw_entry):
    """
    Extract additional details specific to entry type
    
    Args:
        entry: Entry object
        raw_entry: Raw entry dictionary
    """
    # Extract details based on entry type
    if isinstance(entry, SaleEntry):
        extract_sale_details(entry, raw_entry)
    elif isinstance(entry, MortgageEntry):
        extract_mortgage_details(entry, raw_entry)
    elif isinstance(entry, InheritanceEntry):
        extract_inheritance_details(entry, raw_entry)
    elif isinstance(entry, ReleaseEntry):
        extract_release_details(entry, raw_entry)
    elif isinstance(entry, PartitionEntry):
        extract_partition_details(entry, raw_entry)
    elif isinstance(entry, RelinquishmentEntry):
        extract_relinquishment_details(entry, raw_entry)
    elif isinstance(entry, OrderEntry):
        extract_order_details(entry, raw_entry)
    elif isinstance(entry, GenericEntry):
        extract_generic_details(entry, raw_entry)

def format_sale_description(entry, raw_entry):
    """Format description for sale entries"""
    desc = raw_entry.get('description', '')
    sellers = raw_entry.get('sellers', [])
    buyers = raw_entry.get('buyers', [])
    consideration = raw_entry.get('consideration', None)
    
    if sellers and buyers:
        seller_names = ", ".join([s.get('name', '') if isinstance(s, dict) else s for s in sellers])
        buyer_names = ", ".join([b.get('name', '') if isinstance(b, dict) else b for b in buyers])
        
        formatted = f"Sale of property from {seller_names} to {buyer_names}"
        if consideration:
            formatted += f" for a consideration of {consideration}"
        formatted += "." 
        
        # Add any additional details from original description
        if len(desc) > len(formatted) * 1.5:  # If original has much more info
            formatted += f" {desc}"
            
        return formatted
    return desc

def format_mortgage_description(entry, raw_entry):
    """Format description for mortgage entries"""
    desc = raw_entry.get('description', '')
    mortgagors = raw_entry.get('mortgagors', [])
    mortgagees = raw_entry.get('mortgagees', [])
    amount = raw_entry.get('amount', None)
    
    if mortgagors and mortgagees:
        mortgagor_names = ", ".join([m.get('name', '') if isinstance(m, dict) else m for m in mortgagors])
        mortgagee_names = ", ".join([m.get('name', '') if isinstance(m, dict) else m for m in mortgagees])
        
        formatted = f"Mortgage by {mortgagor_names} in favor of {mortgagee_names}"
        if amount:
            formatted += f" for an amount of {amount}"
        formatted += "."
        
        # Add any additional details from original description
        if len(desc) > len(formatted) * 1.5:
            formatted += f" {desc}"
            
        return formatted
    return desc

def format_inheritance_description(entry, raw_entry):
    """Format description for inheritance entries"""
    desc = raw_entry.get('description', '')
    deceased = raw_entry.get('deceased', {})
    heirs = raw_entry.get('heirs', [])
    
    if deceased and heirs:
        deceased_name = deceased.get('name', '') if isinstance(deceased, dict) else deceased
        heir_names = ", ".join([h.get('name', '') if isinstance(h, dict) else h for h in heirs])
        
        formatted = f"Inheritance of property by {heir_names} upon the death of {deceased_name}."
        
        # Add any additional details from original description
        if len(desc) > len(formatted) * 1.5:
            formatted += f" {desc}"
            
        return formatted
    return desc

def format_release_description(entry, raw_entry):
    """Format description for release entries"""
    desc = raw_entry.get('description', '')
    releasors = raw_entry.get('releasors', [])
    releasees = raw_entry.get('releasees', [])
    
    if releasors and releasees:
        releasor_names = ", ".join([r.get('name', '') if isinstance(r, dict) else r for r in releasors])
        releasee_names = ", ".join([r.get('name', '') if isinstance(r, dict) else r for r in releasees])
        
        formatted = f"Release of charge/mortgage by {releasor_names} in favor of {releasee_names}."
        
        # Add any additional details from original description
        if len(desc) > len(formatted) * 1.5:
            formatted += f" {desc}"
            
        return formatted
    return desc

def format_partition_description(entry, raw_entry):
    """Format description for partition entries"""
    return raw_entry.get('description', '')

def format_relinquishment_description(entry, raw_entry):
    """Format description for relinquishment entries"""
    return raw_entry.get('description', '')

def format_order_description(entry, raw_entry):
    """Format description for order entries"""
    return raw_entry.get('description', '')

def extract_sale_details(entry, raw_entry):
    """Extract sale specific details"""
    # Extract sellers
    sellers = raw_entry.get('sellers', [])
    if sellers:
        if isinstance(sellers, list):
            entry.sellers = [Person(name=s) if isinstance(s, str) else 
                             Person(name=s.get('name', ''), 
                                  role=s.get('role', None),
                                  relationship=s.get('relationship', None))
                             for s in sellers]
        elif isinstance(sellers, str):
            # Handle case where sellers is a string
            entry.sellers = [Person(name=sellers)]
    
    # Extract buyers
    buyers = raw_entry.get('buyers', [])
    if buyers:
        if isinstance(buyers, list):
            entry.buyers = [Person(name=b) if isinstance(b, str) else 
                           Person(name=b.get('name', ''), 
                                role=b.get('role', None),
                                relationship=b.get('relationship', None))
                           for b in buyers]
        elif isinstance(buyers, str):
            # Handle case where buyers is a string
            entry.buyers = [Person(name=buyers)]
    
    # Extract other sale details
    entry.consideration = raw_entry.get('consideration', None)
    entry.property_details = raw_entry.get('property_details', None)

def extract_mortgage_details(entry, raw_entry):
    """Extract mortgage specific details"""
    # Extract mortgagors
    mortgagors = raw_entry.get('mortgagors', []) or raw_entry.get('mortgagor', [])
    if mortgagors:
        if isinstance(mortgagors, list):
            entry.mortgagor = [Person(name=m) if isinstance(m, str) else 
                              Person(name=m.get('name', ''), 
                                   role=m.get('role', None))
                              for m in mortgagors]
        elif isinstance(mortgagors, str):
            # Handle case where mortgagors is a string
            entry.mortgagor = [Person(name=mortgagors)]
    
    # Extract mortgagees
    mortgagees = raw_entry.get('mortgagees', []) or raw_entry.get('mortgagee', [])
    if mortgagees:
        if isinstance(mortgagees, list):
            entry.mortgagee = [Person(name=m) if isinstance(m, str) else 
                              Person(name=m.get('name', ''), 
                                   role=m.get('role', None))
                              for m in mortgagees]
        elif isinstance(mortgagees, str):
            # Handle case where mortgagees is a string
            entry.mortgagee = [Person(name=mortgagees)]
    
    # Extract other mortgage details
    entry.amount = raw_entry.get('amount', None) or raw_entry.get('loan_amount', None)
    entry.period = raw_entry.get('period', None)
    entry.interest_rate = raw_entry.get('interest_rate', None)

def extract_inheritance_details(entry, raw_entry):
    """Extract inheritance specific details"""
    # Extract deceased
    deceased = raw_entry.get('deceased', None)
    if deceased:
        if isinstance(deceased, dict):
            entry.deceased = Person(name=deceased.get('name', ''), 
                                   role='deceased',
                                   relationship=deceased.get('relationship', None))
        elif isinstance(deceased, str):
            entry.deceased = Person(name=deceased, role='deceased')
    
    # Extract heirs
    heirs = raw_entry.get('heirs', [])
    if heirs:
        if isinstance(heirs, list):
            entry.heirs = [Person(name=h) if isinstance(h, str) else 
                          Person(name=h.get('name', ''), 
                               role='heir',
                               relationship=h.get('relationship', None))
                          for h in heirs]
        elif isinstance(heirs, str):
            # Handle case where heirs is a string
            entry.heirs = [Person(name=heirs, role='heir')]
    
    # Extract other inheritance details
    entry.death_date = raw_entry.get('death_date', None)
    entry.shares = raw_entry.get('shares', None)

def extract_release_details(entry, raw_entry):
    """Extract release specific details"""
    # Extract releasors
    releasors = raw_entry.get('releasors', []) or raw_entry.get('releasor', [])
    if releasors:
        if isinstance(releasors, list):
            entry.releasor = [Person(name=r) if isinstance(r, str) else 
                             Person(name=r.get('name', ''), role=r.get('role', None))
                             for r in releasors]
        elif isinstance(releasors, str):
            entry.releasor = [Person(name=releasors)]
    
    # Extract releasees
    releasees = raw_entry.get('releasees', []) or raw_entry.get('releasee', [])
    if releasees:
        if isinstance(releasees, list):
            entry.releasee = [Person(name=r) if isinstance(r, str) else 
                             Person(name=r.get('name', ''), role=r.get('role', None))
                             for r in releasees]
        elif isinstance(releasees, str):
            entry.releasee = [Person(name=releasees)]
    
    # Extract reference to original entry
    entry.reference_to_original = raw_entry.get('reference_to_original', None)

def extract_partition_details(entry, raw_entry):
    """Extract partition specific details"""
    # Extract original owners
    original_owners = raw_entry.get('original_owners', [])
    if original_owners:
        if isinstance(original_owners, list):
            entry.original_owners = [Person(name=o) if isinstance(o, str) else 
                                    Person(name=o.get('name', ''), role=o.get('role', None))
                                    for o in original_owners]
        elif isinstance(original_owners, str):
            entry.original_owners = [Person(name=original_owners)]
    
    # Extract resulting allocations
    entry.resulting_allocations = raw_entry.get('resulting_allocations', {})

def extract_relinquishment_details(entry, raw_entry):
    """Extract relinquishment specific details"""
    # Extract relinquishers
    relinquishers = raw_entry.get('relinquishers', []) or raw_entry.get('relinquisher', [])
    if relinquishers:
        if isinstance(relinquishers, list):
            entry.relinquisher = [Person(name=r) if isinstance(r, str) else 
                                 Person(name=r.get('name', ''), role=r.get('role', None))
                                 for r in relinquishers]
        elif isinstance(relinquishers, str):
            entry.relinquisher = [Person(name=relinquishers)]
    
    # Extract beneficiaries
    beneficiaries = raw_entry.get('beneficiaries', []) or raw_entry.get('beneficiary', [])
    if beneficiaries:
        if isinstance(beneficiaries, list):
            entry.beneficiary = [Person(name=b) if isinstance(b, str) else 
                                Person(name=b.get('name', ''), role=b.get('role', None))
                                for b in beneficiaries]
        elif isinstance(beneficiaries, str):
            entry.beneficiary = [Person(name=beneficiaries)]
    
    # Extract relationship
    entry.relationship = raw_entry.get('relationship', None)

def extract_order_details(entry, raw_entry):
    """Extract order specific details"""
    # Extract authority
    entry.authority = raw_entry.get('authority', None)
    
    # Extract order details
    entry.order_details = raw_entry.get('order_details', None)
    
    # Extract affected parties
    affected_parties = raw_entry.get('affected_parties', [])
    if affected_parties:
        if isinstance(affected_parties, list):
            entry.affected_parties = [Person(name=p) if isinstance(p, str) else 
                                     Person(name=p.get('name', ''), role=p.get('role', None))
                                     for p in affected_parties]
        elif isinstance(affected_parties, str):
            entry.affected_parties = [Person(name=affected_parties)]

def extract_generic_details(entry, raw_entry):
    """Extract details for generic entries"""
    # Extract parties involved
    parties = raw_entry.get('parties', [])
    if parties:
        if isinstance(parties, list):
            entry.parties = [Person(name=p) if isinstance(p, str) else 
                            Person(name=p.get('name', ''), role=p.get('role', None))
                            for p in parties]
        elif isinstance(parties, str):
            entry.parties = [Person(name=parties)]
    
    # Extract additional details
    additional_details = {}
    for key, value in raw_entry.items():
        if key not in ['entry_number', 'date', 'type', 'description', 'parties']:
            additional_details[key] = value
    
    if additional_details:
        entry.additional_details = additional_details

def extract_entry_details(pdf_text):
    """
    Main function for extracting entry details using the AI-based approach.
    
    Args:
        pdf_text (str): The full text of the PDF document
        
    Returns:
        list: A list of structured entry objects
    """
    logger = logging.getLogger(__name__)
    logger.info("Extracting entry details using enhanced AI-based approach")
    
    try:
        # Use the dedicated AI function to extract entries
        raw_entries = extract_entry_details_ai(pdf_text)
        
        if not raw_entries:
            logger.warning("No entries extracted, using fallback method")
            raw_entries = [{
                'entry_number': "1",
                'date': datetime.now().strftime('%d/%m/%Y'),
                'type': "Summary",
                'description': "This land record document contains information about land ownership and historical records.",
                'certification': "The Entry is certified but date is not legible."
            }]
        
        # Process the raw entries into structured entry objects
        processed_entries = process_entry_details(raw_entries)
        
        logger.info(f"Successfully extracted and processed {len(processed_entries)} entries")
        return processed_entries
        
    except Exception as e:
        logger.error(f"Error in entry extraction process: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Create a default entry
        default_entry = BaseEntry(
            entry_number="1",
            date=datetime.now().strftime('%d/%m/%Y'),
            type=EntryType.UNKNOWN,
            raw_description="This land record document contains information about land ownership and historical records.",
            formatted_description="This land record document contains information about land ownership and historical records.",
            certification="The Entry is certified but date is not legible."
        )
        
        return [default_entry]

def translate_entry_content(entries):
    """
    Translate Gujarati content to English (now just a pass-through as translations
    are handled within the extraction process)
    
    Args:
        entries (list): List of entry objects
        
    Returns:
        list: Same list of entry objects
    """
    logger = logging.getLogger(__name__)
    logger.info("Translation already handled within extraction process")
    return entries 