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
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text
    except Exception as e:
        print(f"Error extracting text from PDF: {str(e)}")
        return None

def generate_tsr(pdf_text):
    """Generate structured TSR content using AI with improved prompting"""
    logger = setup_logging()
    
    logger.info("Initializing Azure OpenAI client")
    llm = AzureChatOpenAI(
        model="gpt-4o",
        api_version='2024-02-15-preview',
        azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT', ''),
        api_key=SecretStr(os.getenv('AZURE_OPENAI_KEY', '')),
        temperature=0.0
    )

    prompt = """Analyze this land record document and extract information in a detailed structured format. Pay special attention to:
    1. Exact property measurements and survey numbers
    2. Complete chain of title with all dates and changes
    3. All findings and observations about the title
    4. Any encumbrances or restrictions on the land
    
    Return the data as a JSON object with these exact keys and substructures:
    
    {
        "property_details": [{
            "district": "string",
            "taluka": "string",
            "village": "string",
            "survey_number": "string",
            "old_survey_number": "string",
            "total_area": "string",
            "nature_of_land": "string",
            "land_use_zone": "string",
            "boundaries": {
                "north": "string",
                "south": "string",
                "east": "string",
                "west": "string"
            }
        }],
        "documents_scrutinized": [{
            "document_type": "string",
            "reference_number": "string",
            "date": "string",
            "issuing_authority": "string",
            "details": "string",
            "verification_status": "string"
        }],
        "chain_of_title": [{
            "entry_number": "string",
            "date": "string",
            "type_of_change": "string",
            "survey_number": "string",
            "previous_owner": "string",
            "new_owner": "string",
            "transaction_type": "string",
            "description": "string"
        }],
        "findings": [{
            "aspect": "string",
            "details": "string",
            "remarks": "string",
            "risk_level": "string",
            "recommendation": "string"
        }],
        "standard_findings": [{
            "sn": "string",
            "particular": "string",
            "observation": "string"
        }],
        "additional_details": {
            "jurisdiction_info": "string",
            "land_use_restrictions": "string",
            "pending_litigations": "string",
            "encumbrances": "string",
            "special_requirements": "string",
            "title_status": "string",
            "remarks": "string"
        }
    }

    For the standard_findings section, include answers to these specific questions:

    1. Online Records Verification:
       a) Whether the records of registrar office or revenue authorities relevant to the property in question are available for verification through any online portal or computer system?
       b) If such online/computer records are available, whether any verification or cross checking are made and the comments/ findings in this regard.
       c) Whether the genuineness of the stamp paper is possible to be got verified from any online portal and if so whether such verification was made?

    2. Registration Jurisdiction:
       a) Immoveable Properties falls within the jurisdiction of which sub-registrar office?
       b) Whether it is possible to have registration of documents in respect of the property in question, at more than one office of sub-registrar/ district registrar/ registrar- general. If so, please name all such offices?
       c) Whether search has been made at all the offices named at (b) above?

    3. The period covered under the Encumbrances Certificate and the name of the person in whose favour the encumbrance is created and if so, satisfaction of charge, if any.

    4. Additional aspects relevant for investigation of title as per local laws.

    5. Additional suggestions if any to safeguard the interest of PFC/ensuring the perfection of security.

    6. The specific persons who are required to create mortgage/to deposit documents creating mortgage.

    7. Current land use – Agriculture/ Residential/industrial/commercial

    8. Requirement of Change in Land Use and position as per policy of the state

    9. Permission under the urban land (Ceiling and Regulation) Act,1976

    10. Details of creation of charge or redemption for a minimum period of 13 year and subsisting charges, as per encumbrance certificate for the last 13 year.

    11. Additional documents required.

    12. Findings based on ROC Search and list of encumbrances

    13. Pending litigation before any court of law/ forum in respect of the property.

    14. Availability of No encumbrance certificate from the concerned Registrar of Assurances.

    15. Any minor's interest if involved in the property proposed to be mortgaged or any other claims.

    16. Whether the property is acquired under Land Acquisition Act, 1894 and applicability of other State Legislation

    17. Any other special enactment which is applicable to the property proposed to be mortgaged and affects the title

    18. Findings on absolute, clear, and marketable title of the immovable property proposed to be mortgaged

    If any field is not available in the document, use "Not Available" instead of "N/A".
    For dates, use the format DD/MM/YYYY.
    For areas, specify the unit (e.g., "2-55-98 Hectares-Ares-SqMt").
    
    Document Content:
    """ + pdf_text

    logger.info("Sending prompt to Azure OpenAI")
    logger.debug(f"Prompt sent to model: {prompt}")
    
    response = llm.invoke(prompt)
    logger.info("Received response from Azure OpenAI")
    logger.debug(f"Raw response from model: {response.content}")
    
    try:
        cleaned_json = clean_and_validate_json(response.content)
        logger.info("Successfully cleaned and validated JSON response")
        logger.debug(f"Cleaned JSON: {json.dumps(cleaned_json, indent=2)}")
        return cleaned_json
    except Exception as e:
        logger.error(f"Error processing AI response: {str(e)}")
        logger.error("Stack trace:", exc_info=True)
        raise

def clean_and_validate_json(response_text):
    """Clean and validate JSON response"""
    logger = logging.getLogger(__name__)
    logger.info("Starting JSON cleaning and validation")
    
    # Find and extract JSON content
    json_start = response_text.find('{')
    json_end = response_text.rfind('}') + 1
    if json_start == -1 or json_end == 0:
        logger.error("No JSON object found in response")
        raise ValueError("No JSON object found in response")
    
    json_str = response_text[json_start:json_end]
    logger.debug(f"Extracted JSON string: {json_str}")
    
    # Clean the JSON string
    json_str = json_str.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    json_str = ''.join(char for char in json_str if ord(char) >= 32 or char in '\n\r\t')
    logger.info("Basic JSON string cleaning completed")
    
    # Parse JSON
    try:
        parsed_json = json.loads(json_str)
        logger.info("Successfully parsed JSON")
    except json.JSONDecodeError as e:
        logger.warning(f"Initial JSON parsing failed: {str(e)}")
        logger.info("Attempting additional cleaning")
        
        # Additional cleaning if needed
        import re
        json_str = re.sub(r'[^\x00-\x7F]+', '', json_str)
        json_str = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', json_str)
        parsed_json = json.loads(json_str)
        logger.info("Successfully parsed JSON after additional cleaning")
    
    # Validate and clean up the data
    cleaned_data = validate_and_clean_data(parsed_json)
    logger.info("Data validation and cleanup completed")
    return cleaned_data

def validate_and_clean_data(data):
    """Validate and clean up the parsed JSON data"""
    logger = logging.getLogger(__name__)
    logger.info("Starting data validation and cleaning")
    
    # Replace empty or None values with "Not Available"
    def clean_value(v):
        if v is None or v == "" or v == "N/A":
            return "Not Available"
        return str(v)

    def clean_dict(d):
        logger.debug(f"Cleaning dictionary: {d}")
        return {k: clean_value(v) if isinstance(v, (str, type(None))) 
               else clean_dict(v) if isinstance(v, dict)
               else [clean_dict(i) if isinstance(i, dict) else clean_value(i) for i in v] if isinstance(v, list)
               else v
               for k, v in d.items()}

    cleaned_data = clean_dict(data)
    logger.info("Data validation and cleaning completed")
    logger.debug(f"Cleaned data: {cleaned_data}")
    return cleaned_data

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

def add_section_heading(doc, text, level=1):
    heading = doc.add_paragraph()
    heading.add_run(text).bold = True
    heading.style = f'Heading {level}'
    return heading

def add_findings_section(doc, content):
    """Add findings section with both standard and general findings"""
    logger = logging.getLogger(__name__)
    logger.info("Adding Findings & Opinion section")
    
    add_section_heading(doc, "4. Findings & Opinion Based on Title Investigation")
    
    # Create table for standard findings
    headers = ["SN", "Particular", "Observations"]
    rows = []
    
    # Define standard questions with proper formatting
    standard_questions = [
        ("1", "Online Records Verification:", ""),
        ("", "a) Whether the records of registrar office or revenue authorities relevant to the property in question are available for verification through any online portal or computer system?", ""),
        ("", "b) If such online/computer records are available, whether any verification or cross checking are made and the comments/ findings in this regard.", ""),
        ("", "c) Whether the genuineness of the stamp paper is possible to be got verified from any online portal and if so whether such verification was made?", ""),
        
        ("2", "Registration Jurisdiction:", ""),
        ("", "a) Immoveable Properties falls within the jurisdiction of which sub-registrar office?", ""),
        ("", "b) Whether it is possible to have registration of documents in respect of the property in question, at more than one office of sub-registrar/ district registrar/ registrar- general. If so, please name all such offices?", ""),
        ("", "c) Whether search has been made at all the offices named at (b) above?", ""),
        
        ("3", "The period covered under the Encumbrances Certificate and the name of the person in whose favour the encumbrance is created and if so, satisfaction of charge, if any.", ""),
        ("4", "Additional aspects relevant for investigation of title as per local laws.", ""),
        ("5", "Additional suggestions if any to safeguard the interest of PFC/ensuring the perfection of security.", ""),
        ("6", "The specific persons who are required to create mortgage/to deposit documents creating mortgage.", ""),
        ("7", "Current land use – Agriculture/ Residential/industrial/commercial", ""),
        ("8", "Requirement of Change in Land Use and position as per policy of the state", ""),
        ("9", "Permission under the urban land (Ceiling and Regulation) Act,1976", ""),
        ("10", "Details of creation of charge or redemption for a minimum period of 13 year and subsisting charges, as per encumbrance certificate for the last 13 year.", ""),
        ("11", "Additional documents required.", ""),
        ("12", "Findings based on ROC Search and list of encumbrances", ""),
        ("13", "Pending litigation before any court of law/ forum in respect of the property.", ""),
        ("14", "Availability of No encumbrance certificate from the concerned Registrar of Assurances.", ""),
        ("15", "Any minor's interest if involved in the property proposed to be mortgaged or any other claims.", ""),
        ("16", "Whether the property is acquired under Land Acquisition Act, 1894 and applicability of other State Legislation", ""),
        ("17", "Any other special enactment which is applicable to the property proposed to be mortgaged and affects the title", ""),
        ("18", "Findings on absolute, clear, and marketable title of the immovable property proposed to be mortgaged", "")
    ]

    if content.get('standard_findings'):
        logger.info("Processing standard findings")
        findings_dict = {f.get('sn', ''): f.get('observation', 'Not Available') for f in content['standard_findings']}
        
        for sn, particular, _ in standard_questions:
            observation = findings_dict.get(sn, 'Not Available') if sn else 'Not Available'
            rows.append([sn, particular, observation])
    else:
        logger.warning("No standard findings data available")
        rows = standard_questions

    # Create and format the table
    table = doc.add_table(rows=1, cols=3)
    table.style = 'Table Grid'
    table.autofit = False
    
    # Set column widths
    table.columns[0].width = Inches(0.5)  # SN column
    table.columns[1].width = Inches(4.0)  # Particular column
    table.columns[2].width = Inches(3.5)  # Observations column
    
    # Add headers with bold formatting
    header_cells = table.rows[0].cells
    for i, header in enumerate(headers):
        header_cells[i].text = header
        header_cells[i].paragraphs[0].runs[0].bold = True
        header_cells[i].paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    
    # Add data rows
    for row_data in rows:
        cells = table.add_row().cells
        for i, cell_text in enumerate(row_data):
            cells[i].text = str(cell_text)
            # Set cell properties
            cells[i].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
            paragraph = cells[i].paragraphs[0]
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.space_before = Pt(0)
            # Center align the SN column
            if i == 0:  # SN column
                paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
            # Make main questions (with SN) bold
            if i == 1 and row_data[0]:  # Particular column and has SN
                paragraph.runs[0].bold = True
    
    # Add spacing after table
    doc.add_paragraph()
    logger.info("Findings section completed")

def create_docx_report(content, filename="13_ouptut_TSR.docx"):
    logger = setup_logging()
    logger.info("Starting TSR document generation")
    
    try:
        doc = Document()
        logger.info("Created new Document object")
        
        # Document setup
        set_document_styling(doc)
        
        # Reference number and date
        ref_date = doc.add_paragraph()
        ref_date.add_run(f"Ref. No. ABREL/GUJ/KUT/ABD/VAL/13").bold = True
        ref_date.add_run(f"\tDated: {datetime.now().strftime('%d %b %Y')}")
        
        # Title
        title = doc.add_paragraph()
        title_run = title.add_run("TITLE INVESTIGATION REPORT")
        title_run.bold = True
        title_run.underline = True
        title.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        
        # Address block
        doc.add_paragraph("To")
        address = doc.add_paragraph()
        address.paragraph_format.left_indent = Inches(0.5)
        address.add_run("Aditya Birla Renewable Energy Ltd.\nA-2, Aditya Birla Centre, S.K. Ahire Marg,\nWorli, Mumbai-400030.\n\nKind Attn.: Mr. Rahul Patil")
        
        doc.add_paragraph("Dear Sir,")
        
        # Introduction with location details
        intro = doc.add_paragraph()
        if content.get('property_details') and content['property_details']:
            prop = content['property_details'][0]
            intro.add_run(f"We have been engaged for the Title Investigation of land situated at Village- {prop.get('village', 'Not Available')}, Taluka-{prop.get('taluka', 'Not Available')}, District- {prop.get('district', 'Not Available')}. Our detailed report and findings are as under:")
        else:
            intro.add_run("We have been engaged for the Title Investigation of land. Our detailed report and findings are as under:")

        # Section 1: Property Details
        doc.add_paragraph("• Description, nature, and area of land with survey/plot numbers", style='List Bullet')
        
        # Create property details table
        headers = ["SN", "Nature of Land", "Total Area in Hectare / Sq. Mtr", "Survey Number", "Name of the Title Holder"]
        table = doc.add_table(rows=1, cols=5)
        table.style = 'Table Grid'
        
        # Add headers
        for i, header in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = header
            cell.paragraphs[0].runs[0].bold = True
            cell.paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        
        # Add property data
        if content.get('property_details'):
            for idx, prop in enumerate(content['property_details'], 1):
                row = table.add_row().cells
                row[0].text = str(idx)
                row[1].text = f"{prop.get('nature_of_land', 'Not Available')}"
                row[2].text = prop.get('total_area', 'Not Available')
                row[3].text = prop.get('survey_number', 'Not Available')
                row[4].text = "Not Available"  # Add title holder if available in your data
        
        doc.add_paragraph()  # Add spacing
        
        doc.add_paragraph("• Details/Description of document scrutinized", style='List Bullet')
        
        # Create documents table
        headers = ["Type of the Document/Detail of the Document", "Digitally Certified True Copy/Online Perusal", "Details of Sub-Registrar's office."]
        table = doc.add_table(rows=1, cols=3)
        table.style = 'Table Grid'
        
        # Add headers
        for i, header in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = header
            cell.paragraphs[0].runs[0].bold = True
            cell.paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        
        # Add document data
        if content.get('documents_scrutinized'):
            for doc_data in content['documents_scrutinized']:
                row = table.add_row().cells
                row[0].text = doc_data.get('document_type', 'Not Available')
                row[1].text = doc_data.get('verification_status', 'Online')
                row[2].text = doc_data.get('issuing_authority', 'Not Applicable')
        
        doc.add_paragraph()  # Add spacing

        # Section 3: Chain of Title
        logger.info("Processing Section 3: Chain of Title")
        add_section_heading(doc, "3. Chain of Title")
        headers = ["Entry Number", "Date", "Type of Change", "Survey Number", "Details of Change"]
        rows = []
        if content.get('chain_of_title'):
            logger.info(f"Found {len(content['chain_of_title'])} chain of title entries")
            for c in content['chain_of_title']:
                row = [
                    c.get('entry_number', 'N/A'),
                    c.get('date', 'N/A'),
                    c.get('type_of_change', 'N/A'),
                    c.get('survey_number', 'N/A'),
                    c.get('description', 'N/A')
                ]
                rows.append(row)
        else:
            logger.warning("No chain of title entries found in content")
            rows.append(['N/A'] * len(headers))
        add_table_with_header(doc, headers, rows)
        doc.add_paragraph()

        # Section 4: Findings
        logger.info("Processing Section 4: Findings & Opinion")
        add_findings_section(doc, content)

        # Conclusion
        logger.info("Adding conclusion")
        conclusion = doc.add_paragraph()
        conclusion.add_run("Conclusion").bold = True
        if content.get('additional_details'):
            doc.add_paragraph(content['additional_details'].get('title_status', 'No conclusion available.'))
        else:
            logger.warning("No additional details found for conclusion")
            doc.add_paragraph("No conclusion available.")

        # Continue with other sections...
        
        doc.save(filename)
        logger.info(f"Document saved successfully as {filename}")
        return filename
        
    except Exception as e:
        logger.error(f"Error during document generation: {str(e)}")
        logger.error("Stack trace:", exc_info=True)
        raise

def set_document_styling(doc):
    """Set document styles and formatting"""
    # Set margins
    for section in doc.sections:
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
    
    # Set default font
    style = doc.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(12)

if __name__ == "__main__":
    logger = setup_logging()
    try:
        logger.info("Starting TSR generation process")
        
        # Extract text from PDF
        pdf_path = "test_files/13_anyror.pdf"
        logger.info(f"Extracting text from PDF: {pdf_path}")
        pdf_text = extract_text_from_pdf(pdf_path)
        
        if pdf_text is None:
            logger.error("Failed to extract text from PDF")
            raise Exception("Failed to extract text from PDF")
        
        # Generate structured content
        logger.info("Generating structured content from PDF text")
        structured_content = generate_tsr(pdf_text)
        
        # Create DOCX report
        logger.info("Creating DOCX report")
        output_file = create_docx_report(structured_content, "13_TSR.docx")
        logger.info(f"Report generated successfully: {output_file}")
        
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        logger.error("Stack trace:", exc_info=True)
        raise