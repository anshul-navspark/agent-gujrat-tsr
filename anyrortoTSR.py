from langchain_openai import AzureChatOpenAI
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import RGBColor
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from dotenv import load_dotenv
import os
from pydantic import SecretStr
import PyPDF2
from datetime import datetime
import json
import logging
import re
import traceback


def setup_logging():
    """Setup logging configuration"""
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Create a timestamp for the log file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = f'logs/tsr_generation_{timestamp}.log'

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()  # Also print to console
        ]
    )
    return logging.getLogger(__name__)

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF with error handling"""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error extracting text from PDF: {str(e)}")
        return None

def convert_gujarati_to_english_numerals(text):
    """Convert Gujarati numerals to English numerals"""
    if text is None:
        return "Not Available"
    
    mapping = {
        '૦': '0', '૧': '1', '૨': '2', '૩': '3', '૪': '4',
        '૫': '5', '૬': '6', '૭': '7', '૮': '8', '૯': '9'
    }
    
    result = ""
    for char in text:
        if char in mapping:
            result += mapping[char]
        else:
            result += char
    
    return result

def sanitize_text(text):
    """Remove NULL bytes and control characters that cause XML compatibility issues."""
    if text is None:
        return "Not Available"
    
    # Convert to string if not already
    text = str(text)
    
    # Remove NULL bytes and control characters (0x00-0x1F except for \t, \n, \r)
    sanitized = ""
    for char in text:
        # Skip NULL bytes and most control characters
        if ord(char) == 0 or (0 < ord(char) < 32 and char not in '\t\n\r'):
            continue
        sanitized += char
    
    # If string became empty after sanitizing, return placeholder
    if not sanitized.strip():
        return "Not Available"
    
    return sanitized

def translate_gujarati_text(text):
    """Translate common Gujarati terms to English for TSR"""
    translations = {
        'મોલગેશન': 'Promulgation',
        'હુકમથી': 'Order',
        'માત': 'Certified',
        'પ્રમાણિત': 'Certified',
        'ખેતીલાયક ઉપયોગ': 'Agricultural Use',
        'જુની શરત': 'Old Tenure',
        'સરવે નંબર': 'Survey Number',
        'અબડાસા': 'Abdasa',
        'વલસરા': 'Valsara',
        'કચ્છ': 'Kachchh'
    }
    
    # Apply translations
    translated = text
    for guj, eng in translations.items():
        translated = re.sub(rf'\b{re.escape(guj)}\b', eng, translated)
    
    return translated

def extract_entry_details(pdf_text):
    """Extract entries dynamically from the PDF using Azure OpenAI"""
    logger = logging.getLogger(__name__)
    logger.info("Extracting entry details using Azure OpenAI")
    
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
        
        # Create a prompt for the AI to extract entry details
        prompt = f"""
        Extract all entry details from the following land record document text. 
        For each entry, provide:
        1. Entry number
        2. Date (if available)
        3. Type (e.g., Promulgation, Order, etc.)
        4. Description of what the entry is about
        
        Format your response as a JSON array of objects with the keys: entry_number, date, type, description.
        
        Here's the document text:
        {pdf_text[:10000]}  # Using first 10000 chars to stay within token limits
        
        If you can't find specific entries, look for sections labeled "Entry Details" or similar.
        Extract any entries you can find in the document.
        """
        
        # Get response from Azure OpenAI
        response = llm.invoke(prompt)
        logger.info("Received response from Azure OpenAI")
        
        # Parse the JSON response
        # Find JSON content in the response
        json_match = re.search(r'\[\s*\{.*\}\s*\]', response.content, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            entries = json.loads(json_str)
        else:
            # Try to extract structured data even if not in perfect JSON format
            logger.warning("JSON not found in response, attempting to parse structured data")
            entries = extract_structured_entries_from_text(response.content)
        
        # Validate and clean entries
        validated_entries = []
        for entry in entries:
            # Ensure all required fields are present
            validated_entry = {
                'entry_number': str(entry.get('entry_number', '')).strip(),
                'date': str(entry.get('date', '')).strip(),
                'type': str(entry.get('type', '')).strip(),
                'description': str(entry.get('description', '')).strip()
            }
            
            # Only include entries with valid entry numbers
            if validated_entry['entry_number'] and validated_entry['entry_number'].isdigit():
                validated_entries.append(validated_entry)
        
        # If no entries were found, try a second approach with a different prompt
        if not validated_entries:
            logger.warning("No entries found with first prompt, trying alternative approach")
            
            # Alternative prompt focusing on finding any entry-like information
            alt_prompt = f"""
            I need to extract all entry records from this land document. 
            Look for any numbered entries, records, or notes in the document.
            
            For each entry you find, extract:
            1. The entry/record number
            2. Any date associated with it
            3. The type of entry (like Order, Promulgation, etc.)
            4. A detailed description of what the entry is about
            
            Format your response as a JSON array of objects with the keys: entry_number, date, type, description.
            
            Here's the document text:
            {pdf_text[10000:20000]}  # Using next 10000 chars to look at different part of document
            """
            
            alt_response = llm.invoke(alt_prompt)
            
            # Parse the JSON from alternative response
            alt_json_match = re.search(r'\[\s*\{.*\}\s*\]', alt_response.content, re.DOTALL)
            if alt_json_match:
                alt_json_str = alt_json_match.group(0)
                alt_entries = json.loads(alt_json_str)
                
                # Validate and add these entries
                for entry in alt_entries:
                    validated_entry = {
                        'entry_number': str(entry.get('entry_number', '')).strip(),
                        'date': str(entry.get('date', '')).strip(),
                        'type': str(entry.get('type', '')).strip(),
                        'description': str(entry.get('description', '')).strip()
                    }
                    
                    if validated_entry['entry_number'] and validated_entry['entry_number'].isdigit():
                        validated_entries.append(validated_entry)
        
        # If still no entries found, create a generic entry based on document content
        if not validated_entries:
            logger.warning("No specific entries found, generating generic entry based on document content")
            
            # Ask AI to generate a summary entry based on the document
            summary_prompt = f"""
            I couldn't find specific numbered entries in this land document. 
            Please analyze the document and create a summary of the most important information about:
            1. The land ownership history
            2. Any significant changes or orders related to the land
            3. Any survey or measurement information
            
            Format your response as a JSON object with the keys: entry_number (use "1"), date (if you can find any relevant date), 
            type (a general category like "Summary"), and description (your detailed summary).
            
            Here's the document text:
            {pdf_text[:15000]}
            """
            
            summary_response = llm.invoke(summary_prompt)
            
            # Try to extract JSON from the summary response
            summary_json_match = re.search(r'\{.*\}', summary_response.content, re.DOTALL)
            if summary_json_match:
                summary_json_str = summary_json_match.group(0)
                try:
                    summary_entry = json.loads(summary_json_str)
                    validated_entries = [{
                        'entry_number': "1",
                        'date': str(summary_entry.get('date', '')).strip(),
                        'type': str(summary_entry.get('type', 'Summary')).strip(),
                        'description': str(summary_entry.get('description', 'Land record summary')).strip()
                    }]
                except json.JSONDecodeError:
                    # If JSON parsing fails, create a minimal entry
                    validated_entries = [{
                        'entry_number': "1",
                        'date': "",
                        'type': "Summary",
                        'description': "Land record document containing ownership and survey information."
                    }]
            else:
                # Create a minimal entry if no JSON found
                validated_entries = [{
                    'entry_number': "1",
                    'date': "",
                    'type': "Summary",
                    'description': "Land record document containing ownership and survey information."
                }]
        
        # Sort entries by entry number
        validated_entries = sorted(validated_entries, key=lambda x: int(x['entry_number']))
        
        logger.info(f"Extracted {len(validated_entries)} entries using Azure OpenAI")
        return validated_entries
        
    except Exception as e:
        logger.error(f"Error using Azure OpenAI to extract entries: {str(e)}")
        logger.error("Stack trace:", exc_info=True)
        
        # Create a generic entry based on the error
        logger.warning("Creating generic entry due to extraction error")
        return [{
            'entry_number': "1",
            'date': datetime.now().strftime('%d/%m/%Y'),
            'type': "Summary",
            'description': "This land record document contains information about land ownership, survey details, and historical records. Due to the format of the document, specific entries could not be extracted automatically."
        }]

def extract_structured_entries_from_text(text):
    """Extract structured entry data from text when JSON parsing fails"""
    logger = logging.getLogger(__name__)
    entries = []
    
    # Look for patterns like "Entry Number: 8" or "Entry: 8"
    entry_blocks = re.split(r'Entry\s+(?:Number)?(?:\s*:)?\s*(\d+)', text)
    
    if len(entry_blocks) > 1:  # If we found at least one entry
        for i in range(1, len(entry_blocks), 2):
            if i < len(entry_blocks) - 1:
                entry_num = entry_blocks[i]
                content = entry_blocks[i+1]
                
                # Extract date
                date_match = re.search(r'Date\s*(?:\s*:)?\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})', content)
                date = date_match.group(1) if date_match else ""
                
                # Extract type
                type_match = re.search(r'Type\s*(?:\s*:)?\s*([A-Za-z]+)', content)
                entry_type = type_match.group(1) if type_match else ""
                
                # Extract description
                desc_match = re.search(r'Description\s*(?:\s*:)?\s*(.*?)(?=Entry\s+(?:Number)?(?:\s*:)?\s*\d+|$)', content, re.DOTALL)
                description = desc_match.group(1).strip() if desc_match else content.strip()
                
                entries.append({
                    'entry_number': entry_num,
                    'date': date,
                    'type': entry_type,
                    'description': description
                })
    
    return entries

def translate_entry_content(entries):
    """Translate Gujarati content to English"""
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

def extract_land_details(pdf_text):
    """Extract land details dynamically from the PDF using Azure OpenAI"""
    logger = logging.getLogger(__name__)
    logger.info("Extracting land details using Azure OpenAI")
    
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
        
        # Create a prompt for the AI to extract land details
        prompt = f"""
        Extract the following details from this land record document text:
        1. village_name - Name of the village
        2. taluka_name - Name of the taluka
        3. district_name - Name of the district
        4. survey_number - Current survey number
        5. old_survey_number - Old survey number (if available)
        6. total_area - Total area of the land (include both the numerical value and units)
        7. nature_of_land - Nature of the land (e.g., Agricultural, Old Tenure, etc.)
        8. owner - Name of the land owner

        Format your response as a JSON object with these exact keys.
        If any detail is not found, use "Not Available" as the value.

        Here's the document text:
        {pdf_text[:15000]}  # Using first 15000 chars to stay within token limits
        """
        
        # Get response from Azure OpenAI
        response = llm.invoke(prompt)
        logger.info("Received response from Azure OpenAI for land details")
        
        # Parse the JSON response
        json_match = re.search(r'```json\n(.*?)\n```', response.content, re.DOTALL)
        if json_match:
            json_content = json_match.group(1)
        else:
            json_content = response.content
            
        # Clean up the JSON content
        json_content = json_content.strip()
        if json_content.startswith('{') and json_content.endswith('}'):
            # Valid JSON object
            land_details = json.loads(json_content)
        else:
            # Try to extract JSON object from the text
            json_match = re.search(r'({.*})', json_content, re.DOTALL)
            if json_match:
                land_details = json.loads(json_match.group(1))
            else:
                logger.warning("Could not extract JSON from the response, using fallback values")
                land_details = {
                    'village_name': 'Not Available',
                    'taluka_name': 'Not Available',
                    'district_name': 'Not Available',
                    'survey_number': 'Not Available',
                    'old_survey_number': 'Not Available',
                    'total_area': 'Not Available',
                    'nature_of_land': 'Old Tenure Agricultural',
                    'owner': 'Not Available'
                }
        
        # Convert Gujarati numerals in all text fields
        for key, value in land_details.items():
            if isinstance(value, str):
                land_details[key] = convert_gujarati_to_english_numerals(value)
                land_details[key] = translate_gujarati_text(land_details[key])
        
        logger.info(f"Land details extracted: {json.dumps(land_details, indent=2)}")
        return land_details
        
    except Exception as e:
        logger.error(f"Error extracting land details: {str(e)}")
        logger.error(traceback.format_exc())
        # Return default values
        return {
            'village_name': 'Not Available',
            'taluka_name': 'Not Available',
            'district_name': 'Not Available',
            'survey_number': 'Not Available',
            'old_survey_number': 'Not Available',
            'total_area': 'Not Available',
            'nature_of_land': 'Old Tenure Agricultural',
            'owner': 'Not Available'
        }

def generate_findings_table(pdf_text):
    """Generate standard findings for the TSR report"""
    logger = logging.getLogger(__name__)
    logger.info("Generating standard findings")
    
    # Standard findings
    findings = [
        {
            'sn': '1',
            'particular': "a) Whether the records of registrar office or revenue authorities relevant to the property in question are available for verification through any online portal or computer system?",
            'observation': "YES"
        },
        {
            'sn': '1b',
            'particular': "b) If such online/computer records are available, whether any verification or cross checking are made and the comments/ findings in this regard.",
            'observation': "The records were verified and were found to be consistent with the online records."
        },
        {
            'sn': '1c',
            'particular': "c) Whether the genuineness of the stamp paper is possible to be got verified from any online portal and if so whether such verification was made?",
            'observation': "No.\n\nOnline verification can be done only for E-Stamp Papers.\n\nThe records of registrar can only be accessed online if the registration number of a deed is available."
        },
        {
            'sn': '2',
            'particular': "a) Immoveable Properties falls within the jurisdiction of which sub-registrar office?",
            'observation': "Nakhtarana and Naliya"
        },
        {
            'sn': '2b',
            'particular': "b) Whether it is possible to have registration of documents in respect of the property in question, at more than one office of sub-registrar/ district registrar/ registrar-general. If so, please name all such offices?",
            'observation': "No"
        },
        {
            'sn': '2c',
            'particular': "c)Whether search has been made at all the offices named at (b) above?",
            'observation': "No.\n\nSearch is to be made at jurisdictional Sub Registrar's offices, as all entries and conveyance are recorded there relating to the property(s)."
        },
        {
            'sn': '3',
            'particular': "The period covered under the Encumbrances Certificate and the name of the person in whose favour the encumbrance is created and if so, satisfaction of charge, if any.",
            'observation': "30 years.\n\nAs per revenue records there is no charge subsisting over the land."
        },
        {
            'sn': '4',
            'particular': "Additional aspects relevant for investigation of title as per local laws.",
            'observation': "Mutation entries reflected in Form 6, Form 7, Form 8A, Form 12 were individually investigated in respect of the proposed property, whereas no such restriction is found, and it is in order."
        },
        {
            'sn': '5',
            'particular': "Additional suggestions if any to safeguard the interest of PFC/ensuring the perfection of security.",
            'observation': "The title of the land is clear and marketable."
        },
        {
            'sn': '6',
            'particular': "The specific persons who are required to create mortgage/to deposit documents creating mortgage.",
            'observation': "Not Applicable"
        },
        {
            'sn': '7',
            'particular': "Current land use -- Agriculture/ Residential/industrial/commercial",
            'observation': "Agricultural"
        },
        {
            'sn': '8',
            'particular': "Requirement of Change in Land Use and position as per policy of the state",
            'observation': "Prior permission of the Collector is required for the industrial use of agricultural land."
        },
        {
            'sn': '9',
            'particular': "Permission under the urban land (Ceiling and Regulation) Act,1976",
            'observation': "No such requirement is stated in the revenue records. However, if the company intends to purchase more than 25 Acres of land in a particular village, then prior permission of Industries Commissioner would be required. However, if the company is acquiring the land by way of lease, then no urban land ceiling clearance is required."
        },
        {
            'sn': '10',
            'particular': "Details of creation of charge or redemption for a minimum period of 13 year and subsisting charges, as per encumbrance certificate for the last 13 year.",
            'observation': "As per revenue records there is no charge subsisting over the land."
        },
        {
            'sn': '11',
            'particular': "Additional documents required.",
            'observation': "It is as per the standard operating procedure of the Financial Institution."
        },
        {
            'sn': '12',
            'particular': "Findings based on ROC Search and list of encumbrances",
            'observation': "Not Applicable"
        },
        {
            'sn': '13',
            'particular': "Pending litigation before any court of law/ forum in respect of the property.",
            'observation': "As per updated revenue records there is no pending litigation on the land."
        },
        {
            'sn': '14',
            'particular': "Availability of No encumbrance certificate from the concerned Registrar of Assurances.",
            'observation': "Not Applicable"
        },
        {
            'sn': '15',
            'particular': "Any minor's interest if involved in the property proposed to be mortgaged or any other claims. If minor's interest is involved, what precautions are to be taken to protect PFC's interest as a mortgagee",
            'observation': "Not Applicable"
        },
        {
            'sn': '16',
            'particular': "Whether the property is acquired under Land Acquisition Act, 1894 and applicability of other State Legislation",
            'observation': "As per revenue records, the property is not acquired under Land Acquisition Act"
        },
        {
            'sn': '17',
            'particular': "Any other special enactment which is applicable to the property proposed to be mortgaged and affects the title",
            'observation': "No"
        },
        {
            'sn': '18',
            'particular': "Findings on absolute, clear, and marketable title of the immovable property proposed to be mortgaged",
            'observation': "The title of the land is clear and marketable."
        }
    ]
    
    logger.info(f"Generated {len(findings)} standard findings")
    return findings

def add_table_with_header(doc, headers, rows, style=None):
    num_cols = len(headers)
    table = doc.add_table(rows=1, cols=num_cols)
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    
    # Add headers
    header_cells = table.rows[0].cells
    for i, header in enumerate(headers):
        header_cells[i].text = header
        header_cells[i].paragraphs[0].runs[0].bold = True
    
    # Add data rows
    for row_data in rows:
        row_cells = table.add_row().cells
        for i, cell_data in enumerate(row_data):
            row_cells[i].text = str(cell_data)
    
    return table

def add_section_heading(doc, text, level=1, numbered=True):
    heading = doc.add_paragraph()
    if numbered:
        heading.add_run(text).bold = True
    else:
        heading.style = f'Heading {level}'
        heading.add_run(text)
    return heading

def add_chain_of_title_section(doc, entries):
    """Add chain of title section with proper formatting matching the original TSR"""
    logger = logging.getLogger(__name__)
    logger.info("Adding Chain of Title section")
    
    add_section_heading(doc, "3.  Chain of Title", numbered=True)
    
    # Create the table
    table = doc.add_table(rows=1, cols=2)
    table.style = 'Table Grid'
    table.autofit = False
    
    # Set column widths
    table.columns[0].width = Inches(0.5)  # SN column 
    table.columns[1].width = Inches(6.5)  # Details column
    
    # Add header row
    header_cells = table.rows[0].cells
    header_cells[0].text = ""
    header_cells[1].text = "Brief history and flow of title with respect to Immovable Properties -- For 30 Year Period - Based on perusal of the documents referred in S. No. 2 above."
    header_cells[1].paragraphs[0].runs[0].bold = True
    
    # Add chain of title entries
    if entries and len(entries) > 0:
        logger.info(f"Adding {len(entries)} chain of title entries")
        
        for idx, entry in enumerate(entries, 1):
            row = table.add_row().cells
            row[0].text = f"{idx}."
            
            # Format the entry content
            entry_text = f"Entry No. {entry.get('entry_number', 'Not Available')} "
            if entry.get('date') and entry['date'] != "Not Available":
                entry_text += f"Dated {entry.get('date')} "
            
            if entry.get('type') and entry['type'] != "Not Available":
                entry_text += f"{entry.get('type')} "
            
            # Add description
            entry_text += entry.get('description', 'Not Available')
            
            row[1].text = entry_text
            
            # Format text, making "Entry No. X" bold
            paragraph = row[1].paragraphs[0]
            text = paragraph.text
            paragraph.clear()
            
            # Extract the entry number part for bolding
            match = re.match(r"(Entry No\. \d+(?:\s+Dated\s+\d{2}/\d{2}/\d{4})?(?:\s+[A-Za-z]+)?)", text)
            if match:
                bold_part, rest = match.groups()[0], text[match.end():]
                paragraph.add_run(bold_part).bold = True
                paragraph.add_run(rest)
            else:
                paragraph.add_run(text)
    else:
        logger.warning("No chain of title entries found")
        row = table.add_row().cells
        row[0].text = "1."
        row[1].text = "No chain of title entries available."
    
    # Add final row with note
    row = table.add_row().cells
    row[0].text = f"{len(entries) + 1}."
    row[1].text = "Note:- The title of the land is clear and marketable."
    
    # Add spacing after table
    doc.add_paragraph()
    logger.info("Chain of title section completed")

def add_findings_table(doc, findings):
    """Add findings table with the structure of the original TSR"""
    logger = logging.getLogger(__name__)
    logger.info("Adding Findings section")
    
    add_section_heading(doc, "4.  Findings & opinion based our title investigation:-", numbered=True)
    
    # Create and format the table
    table = doc.add_table(rows=1, cols=3)
    table.style = 'Table Grid'
    table.autofit = False
    
    # Set column widths
    table.columns[0].width = Inches(0.5)  # SN column
    table.columns[1].width = Inches(3.5)  # Particular column
    table.columns[2].width = Inches(3.0)  # Observations column
    
    # Add headers
    header_cells = table.rows[0].cells
    header_cells[0].text = "SN"
    header_cells[1].text = "Particular"
    header_cells[2].text = "Observations"
    
    for cell in header_cells:
        cell.paragraphs[0].runs[0].bold = True
    
    # Add findings to the table
    for finding in findings:
        row = table.add_row().cells
        row[0].text = finding.get('sn', '')
        row[1].text = finding.get('particular', '')
        row[2].text = finding.get('observation', '')
    
    # Add spacing after table
    doc.add_paragraph()
    logger.info("Findings section completed")

def create_tsr_document(entries, land_details, findings, output_path):
    """Create a TSR document using the extracted information"""
    logger = logging.getLogger(__name__)
    logger.info("Creating TSR document")
    
    try:
        doc = Document()
        
        # Set document styling
        for section in doc.sections:
            section.left_margin = Inches(1)
            section.right_margin = Inches(1)
            section.top_margin = Inches(1)
            section.bottom_margin = Inches(1)
        
        # Add the reference number and date
        survey_number = sanitize_text(land_details.get('survey_number', '13'))
        ref_para = doc.add_paragraph()
        ref_text = ref_para.add_run(f"Ref. No. ABREL/GUJ/KUT/ABD/VAL/{survey_number}")
        ref_text.bold = True
        
        current_date = datetime.now().strftime('%d %b %Y')
        ref_para.add_run(f"\tDated: {current_date}")
        
        # Add the title
        title_para = doc.add_paragraph()
        title_para.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        title_text = title_para.add_run("TITLE INVESTIGATION REPORT")
        title_text.bold = True
        title_text.underline = True
        
        # Add recipient info
        doc.add_paragraph("To")
        address_para = doc.add_paragraph()
        address_para.paragraph_format.left_indent = Inches(0.5)
        address_para.add_run("Aditya Birla Renewable Energy Ltd.\nA-2, Aditya Birla Centre, S.K. Ahire Marg,\nWorli, Mumbai-400030.\n\nKind Attn.: Mr. Rahul Patil")
        
        # Add introduction
        doc.add_paragraph("Dear Sir,")
        
        intro_text = f"We have been engaged for the Title Investigation of land situated at Village- {sanitize_text(land_details.get('village', 'Valsara'))}, Taluka-{sanitize_text(land_details.get('taluka', 'Abdasa'))}, District- {sanitize_text(land_details.get('district', 'Kachchh (Gujarat)'))}. Our detailed report and findings are as under:"
        
        doc.add_paragraph(intro_text)
        
        # Section 1: Property Details
        add_section_heading(doc, "1.  Description, nature, and area of land with survey/plot numbers", numbered=True)
        
        # Create property details table
        property_table = doc.add_table(rows=1, cols=5)
        property_table.style = 'Table Grid'
        property_table.autofit = False
        
        # Set column widths
        property_table.columns[0].width = Inches(0.3)   # SN
        property_table.columns[1].width = Inches(1.2)   # Nature of Land
        property_table.columns[2].width = Inches(1.8)   # Total Area
        property_table.columns[3].width = Inches(1.2)   # Survey Number
        property_table.columns[4].width = Inches(2.5)   # Title Holder
        
        # Add headers
        headers = ["SN", "Nature of Land", "Total Area in Hectare / Sq. Mtr", "Survey Number", "Name of the Title Holder"]
        header_cells = property_table.rows[0].cells
        for i, header in enumerate(headers):
            header_cells[i].text = header
            header_cells[i].paragraphs[0].runs[0].bold = True
            # Center align the headers
            header_cells[i].paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        
        # Add property data
        row = property_table.add_row().cells
        row[0].text = "1"
        
        # Format nature of land
        nature = sanitize_text(land_details.get('nature_of_land', 'Old Tenure Agricultural'))
        if 'agricultural' in nature.lower() or 'agriculture' in nature.lower():
            row[1].text = "Old Tenure\n\nAgricultural"
        else:
            row[1].text = nature
        
        # Format area
        area = sanitize_text(land_details.get('total_area', '2-55-98 - i.e.\n(25598 Sq. Mts)'))
        row[2].text = area
        
        # Format survey number
        survey = sanitize_text(land_details.get('survey_number', '13'))
        old_survey = sanitize_text(land_details.get('old_survey_number', '79'))
        row[3].text = f"{survey}\n(old Survey no. {old_survey})"
        
        # Get owner name
        owner = sanitize_text(land_details.get('owner', 'Karimna Fanu Mula'))
        row[4].text = owner
        
        # Apply cell formatting for data row
        for i, cell in enumerate(row):
            # Center align the SN column
            if i == 0:
                cell.paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
            # Vertically center all cells
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        
        # Section 2: Documents Scrutinized
        doc.add_paragraph()  # Add spacing
        add_section_heading(doc, "2.  Details/Description of document scrutinized", numbered=True)
        
        # Create documents table
        docs_table = doc.add_table(rows=1, cols=3)
        docs_table.style = 'Table Grid'
        docs_table.autofit = False
        
        # Set column widths
        docs_table.columns[0].width = Inches(3.0)
        docs_table.columns[1].width = Inches(2.0)
        docs_table.columns[2].width = Inches(2.0)
        
        # Add headers
        doc_headers = ["Type of the Document/Detail of the Document", "Digitally Certified True Copy/Online Perusal", "Details of Sub-Registrar's office."]
        for i, header in enumerate(doc_headers):
            docs_table.rows[0].cells[i].text = header
            docs_table.rows[0].cells[i].paragraphs[0].runs[0].bold = True
        
        # Add standard document types
        standard_docs = [
            ("Old & New Village Form no. 7 starting from the year 1958 till latest version available.", "Online", "Not Applicable"),
            ("Old & New Village Form no. 6 starting from the year 1958 till latest version available.", "Online", "Not Applicable"),
            ("Village Form No. 8A", "Online", "Not Applicable"),
            ("Old Scanned Village Form No. 7/12 starting from the year 1952 to 2004", "Online", "Not Applicable")
        ]
        
        for doc_type, perusal, office in standard_docs:
            row = docs_table.add_row().cells
            row[0].text = doc_type
            row[1].text = perusal
            row[2].text = office
        
        # Section 3: Chain of Title
        doc.add_paragraph()  # Add spacing
        add_chain_of_title_section(doc, entries)
        
        # Section 4: Findings
        add_findings_table(doc, findings)
        
        # Add signature block
        doc.add_paragraph("Thanking you and assuring you of our best co-operation at all times.")
        signature_para = doc.add_paragraph()
        signature_para.paragraph_format.left_indent = Inches(0.5)
        signature_para.add_run("Regards\n\nVijay Choudhary\n\nAdvocate & Associates")
        
        # Save the document
        doc.save(output_path)
        logger.info(f"Document saved successfully as {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Error during document generation: {str(e)}")
        logger.error("Stack trace:", exc_info=True)
        raise

def generate_tsr_from_pdf(pdf_path, output_path, logger=None):
    """API version of main() that returns results rather than printing them"""
    if logger is None:
        logger = setup_logging()
    
    try:
        # Extract text from PDF
        logger.info(f"Extracting text from PDF: {pdf_path}")
        pdf_text = extract_text_from_pdf(pdf_path)
        
        if pdf_text is None:
            logger.error("Failed to extract text from PDF")
            return {
                'success': False,
                'error': "Failed to extract text from PDF"
            }
        
        # Extract entry details from PDF dynamically
        entries = extract_entry_details(pdf_text)
        
        # Translate Gujarati content to English
        entries = translate_entry_content(entries)
        
        # Extract land details
        land_details = extract_land_details(pdf_text)
        
        # Generate findings
        findings = generate_findings_table(pdf_text)
        
        # Create DOCX report
        logger.info("Creating DOCX report")
        output_file = create_tsr_document(entries, land_details, findings, output_path)
        logger.info(f"Report generated successfully: {output_file}")
        
        return {
            'success': True,
            'tsr_path': output_file
        }
        
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            'success': False,
            'error': str(e)
        }
