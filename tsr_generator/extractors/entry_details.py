import os
import json
import re
import logging
import traceback
from datetime import datetime
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

from tsr_generator.extractors.entry_schema import (
    EntryType, Person, BaseEntry, EntryUnion, create_entry_from_dict,
    SaleEntry, MortgageEntry, ReleaseEntry, InheritanceEntry, 
    PartitionEntry, RelinquishmentEntry, OrderEntry, CorrectionEntry, GenericEntry
)
model_name = os.getenv('GEMINI_MODEL_NAME', 'gemini-3-pro-preview')

def extract_entry_table(pdf_text):
    llm = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=os.getenv('GEMINI_API_KEY', ''),
        temperature=0.0,
        convert_system_message_to_human=True,
    )
    prompt = f"""Extract the "Entry Details" table from the following land record document text.

        Requirements (MANDATORY):

        Locate the header "Entry Details" (case-insensitive). Extract the numeric entries that belong to that table in the same order.
        For each extracted entry, remove any asterisk (*) and remove any trailing non-digit characters (including Gujarati text). Keep only digits.
        Output must be a single line of plain text containing only digits separated by single spaces, e.g.:
        176 506 748 797 1013 1046
        Do NOT output JSON, lists, punctuation, code fences, explanation, or any other text. Only one line with numbers and single spaces. If no entries found, output an empty line.
        Example input:
        ...some lines...
        Entry Details
        176
        506
        748*
        797
        1013
        1046નાધ નંબર
        ...more...

        Desired output (exact):
        176 506 748 797 1013 1046
        """
    import time
    max_retries = 3
    retry_delay = 5
    response = None
    
    for attempt in range(max_retries):
        try:
            response = llm.invoke(prompt + "\n" + pdf_text)
            break
        except Exception as e:
            if "429" in str(e) or "resource" in str(e).lower() and attempt < max_retries - 1:
                print(f"Rate limit hit in table extraction. Sleeping for {retry_delay}s...")
                time.sleep(retry_delay)
                continue
            raise e    
    # Extract only numeric tokens from the response, filtering out non-digit characters
    # Handle various LLM output formats including code blocks, markdown, etc.
    content = response.content
    
    # Extract all sequences of digits (1-4 digits long, typical for entry numbers)
    # This handles both space-separated and newline-separated numbers
    entry_numbers = re.findall(r'\b(\d{1,4})\b', content)
    
    # Convert to integers and remove duplicates
    entry_table = sorted(list(set(int(num) for num in entry_numbers)))
    
    # If no numbers found, return empty list
    if not entry_table:
        print("Warning: No entry numbers found in LLM response")
    return entry_table

def extract_entry_details_ai(pdf_text):
    """
    Extract entry details from PDF using AI with formatting exactly matching
    the Gujrat Mutation Entry examples
    
    Args:
        pdf_text (str): The text of the entry details section
        
    Returns:
        list: A list of dictionaries with entry details
    """
    logger = logging.getLogger(__name__)
    logger.debug("Extracting entry details to match Gujrat Mutation Entry format")
    
    try:
        # The entry section is already extracted in the main function and passed in
        entry_section = pdf_text
        
        # First identify entry numbers to ensure all are captured
        all_entry_numbers = identify_all_entry_numbers(entry_section)
        logger.debug(f"Identified {len(all_entry_numbers)} entry numbers for AI processing")
        
        # Initialize Gemini client with the specified model
        load_dotenv()
        llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=os.getenv('GEMINI_API_KEY', ''),
            temperature=0.0,
            convert_system_message_to_human=True,
        )
        
        # Create a focused prompt for extracting entries with the specific format
        prompt = f"""
        Extract all mutation entries from this land record document, exactly matching the format shown in the examples below.

        Candidate entry numbers detected from the Entry Details section: {', '.join(all_entry_numbers)}
        Use them only if they are confirmed as actual mutation entries (e.g., appear as "Entry No." or in the Entry Details table). Do NOT treat Khata/Survey/Form numbers as entries. Do NOT fabricate entries that are not present.

        For each entry, extract:
        1. entry_number - The entry number
        2. date - The date (DD/MM/YYYY)
        3. type - Category of entry (LOAN, DEATH, RELEASE, LOAN CLOSE, SALE, PARTITION, PERSONS ADD, TO TRANSFER, EXCHANGE, LIFETIME DISTRIBUTION, NOT RELATED, ORDER, RELINQUISHMENT, etc.)
        4. description - Detailed description following the exact format from examples. MUST BE IN ENGLISH. Translate any Gujarati text. Do NOT include any Gujarati characters.
        5. certification - Line about certification if available (starts with "The Entry is certified..." or "The Entry is rejected"). MUST BE IN ENGLISH. Do NOT include any Gujarati characters.
        6. certification_status - One of: "certified", "rejected", "not_approved"
        7. certification_official - The official's POST/DESIGNATION and PLACE (e.g., "C.O. Porbandar", "Deputy Mamlatdar Super, Porbandar"). Abbreviate "Circle Officer" as "C.O.". Do NOT include personal names. 
        8. certification_date - The certification date in DD/MM/YYYY format. This is DIFFERENT from the entry date - look for when the entry was certified/rejected. 
        
        IMPORTANT: Extract certification_official and certification_date whenever they are present in the document, even if certification_status is not explicitly stated. If certification_official or certification_date are present, include them in the response.

        Many entries will only have an entry number listed in a table format without any other details, under the table heading "Entry Details". For these entries:
        - entry_number: Use the number from the table
        - date: ""
        - type: ""
        - description: ""
        - certification: ""
        - certification_status: ""
        - certification_official: ""
        - certification_date: ""

        CRITICAL Formatting Rules:
        1. ALL substantive descriptions MUST start with "That" (except for NOT RELATED and PROMULGATION types)
        2. Use proper name formatting with full titles (Thakor, Patel, Kanbi, Choudhary, Rabari, Vadher, Solanki, etc.)
        3. Preserve measurement units exactly: "Acre/Guntha" or "Hectare". REPLACE "H.Are.SqMt." with "Hectare".
           Example: "1-88-48 H.Are.SqMt. i.e.(18848 Sq. Mts)" -> "1-88-48 Hectare (i.e. 18848 Sq. Mts)"
        4. Format amounts as "Rs. X/-" or "Rs. X,XXX/-"
        5. For lists of heirs/parties, use "which are as follows:-" followed by bullet points
        6. Document references: "document no. X dated DD/MM/YYYY" or "document no. X dated DD.MM.YYYY"
        7. Survey numbers: Preserve exact format including "old Survey No." vs "Survey No."
        8. For entries with tables (PARTITION, EXCHANGE), preserve table structure with bullet points
        9. ALWAYS use "Survey No." instead of "Khata No." or "Account No." even if the text says Khata/Account.
        10. For ORDER entries, ALWAYS specify the Survey Number in the description. If the order applies to the current land, explicitly mention "land bearing Survey No. [Number]".

        Entry Type Classification Rules:
        - LOAN: Contains "took a loan" or "loan of Rs."
        - RELEASE/LOAN CLOSE: Contains "removing the charge" or "exemption of burden"
        - SALE: Contains "sold" and "consideration of Rs."
        - INHERITANCE/DEATH: Contains "upon the demise" or "came to be mutated in his legal heirs"
        - PARTITION: Contains "distribution took place" or "distributed his land" or "Family distribution"
        - EXCHANGE: Contains "exchanged their respective lands"
        - RELINQUISHMENT: Contains "relinquished their respective share"
        - ORDER: Contains "Taluka Circular" or "was allotted" or "given in old tenure"
        - LIFETIME DISTRIBUTION: Contains "life time distribution"
        - NOT RELATED: Contains "not related to present survey" or "not completely Scanned"
        - PROMULGATION: Contains "re-survey" or "promulgation"

        The descriptions MUST follow these exact patterns as shown in the examples:

        LOAN Example:
        "That Rabari Sujabhai Jawanabhai and others took a loan of Rs. 1,00,000/- on the land bearing Survey No. 54/2p2(143), 59p3(143), 60/3p2(143), 66/1/2p2(143), 66/2p2(143), 68p5(143) from Voda Group Gopalak Vikas Kariyakari Sahakari Mandli."

        DEATH/INHERITANCE Example:
        "That upon the demise of Jawanabhai Manabhai, his land bearing old Survey No. 59 P, 68 P, 54/2p, 60/3, 66/3 P & 66/2 P came to be mutated in his legal heirs which are as follows:-
        • Sujabhai Jawanabhai
        • Hariyaben Jawanabhai"

        RELINQUISHMENT Example:
        "That Sonbai Jetji and Heenabai Jetji relinquished their respective share in favour of Madansingh Jetji and Ishwarsingh Jetji."

        RELEASE/LOAN CLOSE Example:
        "That upon receiving an application from said Rabari Amarabhai Chamnabhai for removing the charge of Dena Gujrat Gramin Bank, Dhanera Branch. Entry No. 1341. The said exemption of burden has been recorded."

        SALE Example:
        "That the said Choudhary Harkhabhai Chhotybhai and Choudhary Shivabhai Harkhabhai they sold their respective share in land bearing Survey No. 241/1 measuring 1-96-27 Hectare to Choudhary Shaileshbhai Devanbhai through the document no. 324/2022 dated 17.05.2022 for a consideration of Rs. 3,00,000/-."

        PARTITION Example:
        "That the said Vadher Sankarbhai Ramabhai distributed his land as follows:-
        • Vadher Hamirbhai Shankarbhai - Survey No. 122 - 3-12 Acre/Guntha
        • Vadher Nanubhai Shankarbhai - Survey No. 213 - 4-28 Acre/Guntha
        • Vadher Vajjubhai Shankarbhai - Survey No. 38/1 - 11-06 Acre/Guntha, Survey No. 379 - 6-13 Acre/Guntha

        The distribution/Partition of the shares as mentioned above was recorded based on their application and their consent as per their respective rights and physical possession."

        EXCHANGE Example:
        "That Thakor Mulji Gagji and Gagji Maldevji and Thakor Chaganbhai Khushalsinghji exchanged their respective lands through a registered document no. 2472 dated 26/06/2000 and got land as follows:-
        • Thakor Mulji Gagji got Survey No. 104/1 - 13-31 Acre/Guntha
        • Thakor Chaganbhai Khushalsinghji got Survey No. 98/3 - 6-30 Acre/Guntha"

        ORDER/ALLOTMENT Example:
        "That as per the Taluka Circular No. Vatan/10 dated 18/07/1955 old Survey no. 83/4, 104/6, 119/6, 134/2 & 5/2 was allotted to Thakor Dhukhji Chamnaji in old tenure."

        LIFETIME DISTRIBUTION Example:
        "That the said Kanbi Rama Nanji made an application of life time distribution in his land bearing old Survey No. 117/4p measuring 0-37 Acre/Guntha, old Survey No. 117/6p measuring 4-30 Acre/Guntha and old Survey No. 104p measuring 2-00 Acre/Guntha to transfer to his son i.e. Kanbi Narshi Rama."

        PERSONS ADD Example:
        "That the said Choudhary Virambhai Bhemabhai made an application of life time distribution in his land bearing Survey No. 46(205), 65/2p1(205), 551/2(205) to add his legal heirs which are as follows:-
        • Choudhary Hiraben Virambhai
        • Choudhary Jayantibhai Virambhai"

        TO TRANSFER Example:
        "That the said Choudhary Virambhai Bhemabhai made an application of life time distribution in his land bearing Survey No. 46(205), 65/2p1(205), 551/2(205) to transfer to his legal heirs which are as follows:-
        • Choudhary Hiraben Virambhai
        • Choudhary Jayantibhai Virambhai"

        NOT RELATED Example:
        "This entry is not related to present survey no."
        OR
        "This entry is regarding area measurement but it is not completely Scanned."

        Also extract certification information if available. Certification examples:
        - "The Entry is certified."
        - "The Entry is certified by C.O. Jadiya on DD/MM/YYYY."
        - "The Entry is certified on DD/MM/YYYY."
        - "The Entry is rejected."
        - "The entry is Rejected."
        - "The Entry is certified but date is not legible."

        CRITICAL: When extracting certification information, look for:
        - The certifier/official name and designation (e.g., "C.O. Porbandar", "Deputy Mamlatdar Super, Porbandar")
        - The certification date (which may be different from the entry date)
        - Extract these as separate fields (certification_official and certification_date) even if they appear in the certification text

        Format your response as a JSON array with objects containing these keys:
        "entry_number", "date", "type", "description", "certification", "certification_status", "certification_official", "certification_date"

        Here's the document section to analyze:
        {entry_section}
        """
        
        import time
        max_retries = 3
        retry_delay = 5
        response = None
        
        for attempt in range(max_retries):
            try:
                response = llm.invoke(prompt)
                break
            except Exception as e:
                is_rate_limit = "429" in str(e) or "resource" in str(e).lower() or "quota" in str(e).lower()
                if is_rate_limit and attempt < max_retries - 1:
                    logger.warning(f"Rate limit hit in extract_entry_details_ai. Sleeping for {retry_delay}s before retry {attempt+1}/{max_retries}...")
                    time.sleep(retry_delay)
                    continue
                raise e
        
        # Parse JSON from the response with robust cleaning of control characters
        content = response.content if hasattr(response, 'content') else str(response)
        # Remove NULL and other control chars that break JSON
        content = ''.join(ch for ch in content if ch == '\t' or ch == '\n' or ch == '\r' or ord(ch) >= 32)
        json_match = re.search(r'\[\s*\{[\s\S]*?\}\s*\]', content)
        if json_match:
            json_str = json_match.group(0)
            # Second pass: strip stray trailing commas
            json_str = re.sub(r',\s*([\]\}])', r'\1', json_str)
            entries = json.loads(json_str)
            logger.debug(f"Successfully extracted {len(entries)} entries with Gujrat Mutation Entry format")
            
            # Do not auto-add placeholders here; trust the parsed list
            return entries
        else:
            logger.warning("Failed to parse JSON from AI response for entry details")
            # If no entries found, fall back to heuristic extractor rather than fabricating placeholders
            return extract_entry_details_fallback(entry_section)
    
    except Exception as e:
        logger.error(f"Error in AI-based entry details extraction: {str(e)}")
        logger.error(traceback.format_exc())
        # Defer to fallback rather than fabricate a summary entry
        return extract_entry_details_fallback(entry_section)

def extract_entry_details_fallback(entry_section):
    """
    Fallback method for entry extraction matching Gujrat Mutation Entry format
    
    Args:
        entry_section (str): The entry details section text
        
    Returns:
        list: A list of dictionaries with entry details
    """
    logger = logging.getLogger(__name__)
    logger.debug("Using fallback method for Gujrat Mutation Entry format extraction")

    # First identify entry numbers to ensure all are captured
    all_entry_numbers = identify_all_entry_numbers(entry_section)
    logger.debug(f"Identified {len(all_entry_numbers)} entry numbers for fallback processing")

    try:
        # Initialize Gemini client
        load_dotenv()
        llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=os.getenv('GEMINI_API_KEY', ''),
            temperature=0.0,
            convert_system_message_to_human=True,
        )
        
        # Simplified prompt focusing on the exact format
        prompt = f"""
        Extract entries from this land record document using EXACTLY this format.

        IMPORTANT: The document contains the following entry numbers that MUST be included in your extraction, even if you can't find detailed descriptions for them: {', '.join(all_entry_numbers)}

        Entry format:
        - entry_number: The numeric entry number
        - date: In DD/MM/YYYY format if available
        - type: Category (LOAN, DEATH, RELEASE, SALE, PARTITION, EXCHANGE, LIFETIME DISTRIBUTION, NOT RELATED, ORDER, RELINQUISHMENT, etc.)
        - description: Start with "That" and provide complete details (except for NOT RELATED and PROMULGATION types). MUST BE IN ENGLISH. Translate all Gujarati text. Do NOT include any Gujarati characters.
        - certification: Information about who certified the entry and when. MUST BE IN ENGLISH. Do NOT include any Gujarati characters.
        
        - certification_status: One of: "certified", "rejected", "not_approved"
        - certification_official: The official's POST/DESIGNATION and PLACE (e.g., "C.O. Porbandar", "Deputy Mamlatdar Super, Porbandar"). Abbreviate "Circle Officer" as "C.O.". Do NOT include personal names.
        - certification_date: The certification date in DD/MM/YYYY format. This is DIFFERENT from the entry date - look for when the entry was certified/rejected.
        
        IMPORTANT: Extract certification_official and certification_date whenever they are present in the document, even if certification_status is not explicitly stated.

        For entries where you can identify the entry number but not the description or other details, you may include them with empty fields. Only do this if the number clearly appears under the "Entry Details" heading or next to "Entry No.". Do not create entries from Khata/Survey numbers.

        CRITICAL Formatting Rules:
        1. Start descriptions with "That" (except NOT RELATED and PROMULGATION)
        2. Use proper titles: Thakor, Patel, Kanbi, Choudhary, Rabari, Vadher, Solanki
        3. Preserve measurement units: "Acre/Guntha" or "Hectare". REPLACE "H.Are.SqMt." with "Hectare".
           Example: "1-88-48 H.Are.SqMt. i.e.(18848 Sq. Mts)" -> "1-88-48 Hectare (i.e. 18848 Sq. Mts)"
        4. Format amounts: "Rs. X/-" or "Rs. X,XXX/-"
        5. Lists: "which are as follows:-" followed by bullet points
        6. ALWAYS use "Survey No." instead of "Khata No." or "Account No."
        7. For ORDER entries, ALWAYS specify the Survey Number.

        Description examples:
        - LOAN: "That Rabari Sujabhai Jawanabhai and others took a loan of Rs. 1,00,000/- on the land bearing Survey No. 54/2p2(143) from Voda Group Gopalak Vikas Kariyakari Sahakari Mandli."
        - DEATH: "That upon the demise of Jawanabhai Manabhai, his land bearing old Survey No. 59 P came to be mutated in his legal heirs which are as follows:-"
        - EXCHANGE: "That Thakor Mulji Gagji and Thakor Chaganbhai Khushalsinghji exchanged their respective lands through a registered document no. 2472 dated 26/06/2000 and got land as follows:-"
        - NOT RELATED: "This entry is not related to present survey no."

        Certification examples:
        - "The Entry is certified."
        - "The Entry is certified by C.O. Jadiya on DD/MM/YYYY."
        - "The Entry is rejected."
        - "The Entry is certified but date is not legible."

        CRITICAL: When extracting certification information, look for:
        - The certifier/official name and designation (e.g., "C.O. Porbandar", "Deputy Mamlatdar Super, Porbandar")
        - The certification date (which may be different from the entry date)
        - Extract these as separate fields (certification_official and certification_date) even if they appear in the certification text

        Format your response as a JSON array with objects containing these keys:
        "entry_number", "date", "type", "description", "certification", "certification_status", "certification_official", "certification_date"

        Here's the text:
        {entry_section}
        """
        
        import time
        max_retries = 3
        retry_delay = 5
        response = None
        
        for attempt in range(max_retries):
            try:
                response = llm.invoke(prompt)
                break
            except Exception as e:
                is_rate_limit = "429" in str(e) or "resource" in str(e).lower() or "quota" in str(e).lower()
                if is_rate_limit and attempt < max_retries - 1:
                    logger.warning(f"Rate limit hit in fallback extraction. Sleeping for {retry_delay}s before retry {attempt+1}/{max_retries}...")
                    time.sleep(retry_delay)
                    continue
                raise e
        
        # Parse JSON from the response
        content = response.content if hasattr(response, 'content') else str(response)
        content = ''.join(ch for ch in content if ch == '\t' or ch == '\n' or ch == '\r' or ord(ch) >= 32)
        json_match = re.search(r'\[\s*\{[\s\S]*?\}\s*\]', content)
        if json_match:
            json_str = json_match.group(0)
            json_str = re.sub(r',\s*([\]\}])', r'\1', json_str)
            entries = json.loads(json_str)
            logger.debug(f"Successfully extracted {len(entries)} entries using fallback method")
            
            # Check if all identified entry numbers are in the extracted entries
            extracted_numbers = [entry.get('entry_number') for entry in entries]
            missing_entries = [num for num in all_entry_numbers if num not in extracted_numbers]
            
            # Add placeholder entries for missing entry numbers
            for entry_num in missing_entries:
                logger.debug(f"Adding placeholder for missing entry in fallback response: {entry_num}")
                entries.append({
                    'entry_number': entry_num,
                    'date': "",
                    'type': "",
                    'description': "",
                    'certification': ""
                })
                
            return entries
        else:
            logger.warning("Failed to parse JSON from fallback approach")
            # If still nothing parsable, as a last resort return a single note entry
            if not all_entry_numbers:
                # If no entry numbers were found, create a single default entry
                return [{
                    'entry_number': "1",
                    'date': datetime.now().strftime('%d/%m/%Y'),
                    'type': "Summary",
                    'description': "This document contains information about the property.",
                    'certification': "The Entry is certified but details are not available."
                }]
            return []
            
    except Exception as e:
        logger.error(f"Error in fallback entry extraction: {str(e)}")
        logger.error(traceback.format_exc())
        
        # On error, avoid fabricating entries
        if not all_entry_numbers:
            # If no entry numbers were found, create a single default entry
            return [{
                'entry_number': "1",
                'date': datetime.now().strftime('%d/%m/%Y'),
                'type': "Summary", 
                'description': "This document contains information about the property.",
                'certification': "The Entry is certified but date is not legible."
            }]
        return []

def process_entry_details(raw_entries):
    """
    Process raw entry dictionaries into structured entry objects with certification info
    
    Args:
        raw_entries (list): List of dictionaries with raw entry details
        
    Returns:
        list: List of processed entry objects
    """
    logger = logging.getLogger(__name__)
    logger.debug(f"Processing {len(raw_entries)} raw entries into structured entries with certification info")
    
    processed_entries = []
    
    for raw_entry in raw_entries:
        try:
            # Create basic entry object
            entry = create_entry_from_dict(raw_entry)
            
            # Process the description to create a formatted version
            # Check if this is a placeholder entry
            if raw_entry.get('description') == "Entry mentioned in the document but details not available.":
                entry.formatted_description = raw_entry.get('description')
            else:
                format_entry_description(entry, raw_entry)
            
            # Extract additional details based on entry type
            extract_entry_specific_details(entry, raw_entry)
            
            # Ensure certification info is set
            # First check if we have structured certification fields that weren't used
            if hasattr(entry, 'certification') and not entry.certification:
                # Check for structured fields (certification_official, certification_date)
                if 'certification_official' in raw_entry or 'certification_date' in raw_entry:
                    from .entry_schema import _build_certification_string
                    built_cert = _build_certification_string(raw_entry)
                    if built_cert:
                        entry.certification = built_cert
                # Fall back to direct certification field if present
                elif 'certification' in raw_entry and raw_entry['certification']:
                    entry.certification = raw_entry['certification']
            
            # Set entry_status from raw entry (certified, rejected, not_accepted)
            if hasattr(entry, 'entry_status') and 'entry_status' in raw_entry:
                entry.entry_status = raw_entry.get('entry_status', '')
            # Also set entry_status from certification_status if available
            elif hasattr(entry, 'entry_status') and 'certification_status' in raw_entry:
                cert_status = raw_entry.get('certification_status', '').strip()
                if cert_status:
                    entry.entry_status = cert_status
            
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
    
    logger.debug(f"Successfully processed {len(processed_entries)} entries with certification info")
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
    
    # Replace "Part" or "part" with "p" in survey numbers
    # Pattern matches: "Part 1", "Part 2", "part 1", "Part1", "part1", etc.
    # This handles survey number patterns like "150 / Part 1" -> "150 / p1"
    desc = re.sub(r'\b([Pp]art)\s*(\d+)', r'p\2', desc)
    
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

def identify_all_entry_numbers(pdf_text):
    """
    Extract all entry numbers mentioned in the PDF, even those without detailed descriptions
    
    Args:
        pdf_text (str): The full text of the PDF document
        
    Returns:
        list: A list of all entry numbers found
    """
    logger = logging.getLogger(__name__)
    
    # Set to store unique entry numbers
    entry_numbers = set()
    
    # Extract the section between "Entry Details" and "Jantri Detail"
    entry_start_match = re.search(r'(?:Entry Details|[\u0A95-\u0AC5]\s*[\u0A95-\u0AC5].*?Details)', pdf_text, re.IGNORECASE)
    entry_end_match = re.search(r'(?:Jantri Detail|Jantri Details|જાન્ત્રી\s*વિગત)', pdf_text, re.IGNORECASE)
    
    if entry_start_match:
        start_position = entry_start_match.start()
        
        # If both start and end markers are found, extract the section between them
        if entry_end_match and entry_end_match.start() > start_position:
            entry_section = pdf_text[start_position:entry_end_match.start()]
            logger.debug(f"Analyzing entry details section between 'Entry Details' and 'Jantri Detail' for entry numbers ({len(entry_section)} characters)")
        else:
            # If only start marker is found, take all text from that point to the end
            entry_section = pdf_text[start_position:]
            logger.debug(f"Analyzing entry details section from 'Entry Details' to end of document for entry numbers ({len(entry_section)} characters)")
    else:
        logger.warning("Entry Details section not found for entry number extraction. Using full document text.")
        entry_section = pdf_text
    
    # Helper: filter out obvious false positives (Khata/Survey/Form numbers etc.)
    def is_valid_entry_mention(text: str, span: tuple, number: str) -> bool:
        window = 40
        start, end = span
        context = text[max(0, start - window): min(len(text), end + window)]
        context_lower = context.lower()
        noise_keywords = [
            'khata', 'khatta', 'survey', 'old survey', 'form no', 'vf no', 'vf-7', 'vf-6',
            'village form', 'page', 'sr no', 'sr.', 'plot', 'area', 'hectare', 'guntha',
            'sq. mts', 'sq mts', 'schedule', 'section', 'article'
        ]
        # If nearby context contains these words, it's likely not an entry number
        if any(kw in context_lower for kw in noise_keywords):
            return False
        return True

    # Pattern 0: standalone numbers under Entry Details table.
    # Be conservative: require 3-4 digits and pass context filter.
    for match in re.finditer(r'(?:^|\n|\r|\|)[\s\t]*(\d{3,4})\*?[\s\t]*(?:$|\n|\r|\|)', entry_section):
        num = match.group(1).strip()
        # Exclude obviously invalid large numbers like concatenated '923923'
        if num.isdigit() and 1 <= len(num) <= 4 and is_valid_entry_mention(entry_section, match.span(1), num):
            entry_numbers.add(num)
    
    # Pattern 1: Look for entry numbers in a list format (comma-separated)
    for entries_list in re.finditer(r'(?:Entry(?:\s+No\.?|\s+Number)?s?|نوئدہ)\s*(?::|\s)\s*(\d+(?:[\s,]+\d+)*)', entry_section, re.IGNORECASE):
        entries_text = entries_list.group(1)
        for num in re.findall(r'\d+', entries_text):
            entry_numbers.add(num)
    
    # Pattern 2: numbers followed by a date, likely an "Entry No X Dated Y" line
    for match in re.finditer(r'(?:Entry\s+(?:No\.?|Number))?\s*(\d{1,4})\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', entry_section, re.IGNORECASE):
        num = match.group(1)
        if is_valid_entry_mention(entry_section, match.span(1), num):
            entry_numbers.add(num)
        
    # Pattern 3: Specific entry references like "Entry No. 175" or "Entry Number 175"
    for match in re.finditer(r'Entry\s+(?:No\.?|Number)\s*[:#]?\s*(\d{1,4})', entry_section, re.IGNORECASE):
        num = match.group(1)
        if is_valid_entry_mention(entry_section, match.span(1), num):
            entry_numbers.add(num)
    
    # Pattern 4: Look for entry numbers in Gujarati context
    for match in re.finditer(r'(?:નોંધ|નૂધ|નોન્ધ)\s*(?:નંબર|નં\.?)\s*[:#]?\s*(\d+)', entry_section):
        entry_numbers.add(match.group(1))
    
    # Pattern 5: numbers in a tabular format with dates (first col is number)
    for match in re.finditer(r'(?:^|\n|\r)\s*(\d{3,4})\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', entry_section):
        num = match.group(1)
        if is_valid_entry_mention(entry_section, match.span(1), num):
            entry_numbers.add(num)
    
    # Pattern 6: Look for Hindi entry references
    for match in re.finditer(r'प्रविष्टि\s*(?:संख्या|सं\.?)\s*[:#]?\s*(\d+)', entry_section):
        entry_numbers.add(match.group(1))
    
    # Pattern 7: Emphasized numbers (bold/asterisk). Require 3-4 digits and filter context
    for match in re.finditer(r'(?:<b>|<strong>|\*\*|\[|\()(\d{3,4})(?:</b>|</strong>|\*\*|\]|\))', entry_section):
        num = match.group(1)
        if is_valid_entry_mention(entry_section, match.span(1), num):
            entry_numbers.add(num)
    
    # If no entry numbers found in the entry section, search the entire document
    if not entry_numbers:
        logger.debug("No entry numbers found in Entry Details section, searching entire document")
        
        # Look for entry references throughout the document
        for match in re.finditer(r'Entry\s+(?:No\.?|Number)\s*[:#]?\s*(\d+)', pdf_text, re.IGNORECASE):
            num = match.group(1)
            if is_valid_entry_mention(pdf_text, match.span(1), num):
                entry_numbers.add(num)
        
        # Look for Gujarati entry references throughout the document
        for match in re.finditer(r'(?:નોંધ|નૂધ|નોન્ધ)\s*(?:નંબર|નં\.?)\s*[:#]?\s*(\d+)', pdf_text):
            num = match.group(1)
            if is_valid_entry_mention(pdf_text, match.span(1), num):
                entry_numbers.add(num)
        
        # Look for Hindi entry references throughout the document
        for match in re.finditer(r'प्रविष्टि\s*(?:संख्या|सं\.?)\s*[:#]?\s*(\d+)', pdf_text):
            num = match.group(1)
            if is_valid_entry_mention(pdf_text, match.span(1), num):
                entry_numbers.add(num)
    
    if entry_numbers:
        logger.debug(f"Identified {len(entry_numbers)} probable entry numbers: {sorted(list(entry_numbers))}")
        return sorted(list(entry_numbers), key=lambda x: int(x) if x.isdigit() else float('inf'))
    
    logger.warning("No entry numbers found in the document")
    return []

def extract_entry_details(pdf_text):
    """
    Main function for extracting entry details using the AI-based approach.
    
    Args:
        pdf_text (str): The full text of the PDF document
        
    Returns:
        list: A list of structured entry objects
    """
    logger = logging.getLogger(__name__)
    logger.debug("Extracting entry details using enhanced AI-based approach")
    
    # Extract the section between "Entry Details" and "Jantri Detail"
    entry_section = pdf_text  # Default to full text
    
    # Look for the "Entry Details" section heading
    entry_start_match = re.search(r'(?:Entry Details|[\u0A95-\u0AC5]\s*[\u0A95-\u0AC5].*?Details)', pdf_text, re.IGNORECASE)
    
    # Look for "Jantri Detail" as end marker
    entry_end_match = re.search(r'(?:Jantri Detail|Jantri Details|જાન્ત્રી\s*વિગત)', pdf_text, re.IGNORECASE)
    
    if entry_start_match:
        start_position = entry_start_match.start()
        
        # If both start and end markers are found, extract the section between them
        if entry_end_match and entry_end_match.start() > start_position:
            entry_section = pdf_text[start_position:entry_end_match.start()]
            logger.debug(f"Extracted section between 'Entry Details' and 'Jantri Detail' for processing ({len(entry_section)} characters)")
        else:
            # If only start marker is found, take all text from that point to the end
            entry_section = pdf_text[start_position:]
            logger.debug(f"Extracted section from 'Entry Details' to end of document for processing ({len(entry_section)} characters)")
    else:
        logger.warning("Entry Details section not found. Using full document text for processing.")
    
    # First identify all entry numbers in the document, regardless of extraction success
    all_entry_numbers = identify_all_entry_numbers(entry_section)
    logger.debug(f"Found {len(all_entry_numbers)} entry numbers in the document")
    
    try:
        # Use the dedicated AI function to extract detailed entries
        raw_entries = extract_entry_details_ai(entry_section)
        
        if not raw_entries:
            logger.warning("No entries extracted, using all identified entry numbers")
            raw_entries = []
            # If no entries were extracted but we have entry numbers, create placeholders for all of them
            if all_entry_numbers:
                for entry_num in all_entry_numbers:
                    raw_entries.append({
                        'entry_number': entry_num,
                        'date': "",
                        'type': "",
                        'description': "",
                        'certification': ""
                    })
            else:
                # If no entry numbers were found, create a single default entry
                raw_entries = [{
                    'entry_number': "1",
                    'date': datetime.now().strftime('%d/%m/%Y'),
                    'type': "Summary",
                    'description': "This land record document contains information about land ownership and historical records.",
                    'certification': "The Entry is certified but date is not legible."
                }]
        
        # Process the raw entries into structured entry objects
        processed_entries = process_entry_details(raw_entries)
        
        # Drop placeholder/empty entries to avoid phantom rows in report
        filtered_entries = [e for e in processed_entries if getattr(e, 'formatted_description', '').strip()]
        logger.debug(f"Successfully extracted and processed {len(filtered_entries)} entries (filtered from {len(processed_entries)})")
        return filtered_entries
        
    except Exception as e:
        logger.error(f"Error in entry extraction process: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Create placeholder entries for all identified entry numbers instead of just one default entry
        processed_entries = []
        
        if all_entry_numbers:
            logger.debug(f"Creating placeholder entries for {len(all_entry_numbers)} identified entry numbers despite extraction error")
            for entry_num in all_entry_numbers:
                entry = BaseEntry(
                    entry_number=entry_num,
                    date="Not available",
                    type=EntryType.UNKNOWN,
                    raw_description="Entry mentioned in the document but details not available due to processing error.",
                    formatted_description="Entry mentioned in the document but details not available due to processing error.",
                    certification="The Entry is certified but details are not available."
                )
                processed_entries.append(entry)
        else:
            # If no entry numbers were found, create a single default entry
            default_entry = BaseEntry(
                entry_number="1",
                date=datetime.now().strftime('%d/%m/%Y'),
                type=EntryType.UNKNOWN,
                raw_description="This land record document contains information about land ownership and historical records.",
                formatted_description="This land record document contains information about land ownership and historical records.",
                certification="The Entry is certified but date is not legible."
            )
            processed_entries.append(default_entry)
        
        return processed_entries

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
    logger.debug("Translation already handled within extraction process")
    return entries 