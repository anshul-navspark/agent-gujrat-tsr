import os
import logging
import traceback
from datetime import datetime
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
import re

from tsr_generator.utils.text_utils import sanitize_text
from tsr_generator.document.docx_generator import (
    add_section_heading,
    add_chain_of_title_section,
    add_findings_table
)

def create_tsr_document(entry_table, entries, land_details, findings, output_path, mutation_entries=None):
    """
    Create a TSR document with the extracted information
    
    Args:
        entries (list): List of entry dictionaries
        land_details (dict): Dictionary of land details
        findings (list): List of finding dictionaries
        output_path (str): Path to save the document
        
    Returns:
        str: Path to the created document
    """
    logger = logging.getLogger(__name__)
    logger.debug(f"Creating TSR document at {output_path}")
    
    try:
        # Create a new Document with A4 size and proper formatting
        doc = Document()
        
        # A4 size in inches
        section = doc.sections[0]
        section.page_height = Inches(11.69)
        section.page_width = Inches(8.27)
        
        # Set margins (standard A4 margins in inches)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)

        # Set default font and line spacing for the document
        style = doc.styles['Normal']
        style.font.name = 'Times New Roman'
        style.font.size = Pt(12.5)  # Main document text size
        style.paragraph_format.line_spacing = 1.15
        
        # Add header to all pages
        header = section.header
        header_para = header.paragraphs[0]
        header_para.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        
        # Add name in bold
        name_run = header_para.add_run("VIJAY CHOUDHARY")
        name_run.bold = True
        name_run.font.size = Pt(12)  # Header text size
        header_para.add_run("\n")
        
        # Add "Advocate & Associates" with underline
        advocate_run = header_para.add_run("Advocate & Associates")
        advocate_run.underline = True
        advocate_run.font.size = Pt(12)  # Header text size
        header_para.add_run("\n")
        
        # Add office addresses with bold labels
        delhi_run = header_para.add_run("Delhi Office")
        delhi_run.bold = True
        delhi_run.font.size = Pt(12)  # Header text size
        address_run = header_para.add_run(": - F-203 Ashish Complex Mayur Vihar Phase-1 Delhi-110091\n")
        address_run.font.size = Pt(12)  # Header text size
        
        jaipur_run = header_para.add_run("Jaipur Office")
        jaipur_run.bold = True
        jaipur_run.font.size = Pt(12)  # Header text size
        jaipur_address = header_para.add_run(": - Ground Floor, 114 Jai Jawan II, Tonk Road, Jaipur- 302018\n")
        jaipur_address.font.size = Pt(12)  # Header text size
        
        # Add contact information with bold labels and underline for the whole line
        contact_run = header_para.add_run("(Email ID: -")
        contact_run.bold = True
        contact_run.underline = True
        contact_run.font.size = Pt(12)  # Header text size
        
        email_para = header_para.add_run("vijaylawyer@gmail.com, ")
        email_para.underline = True
        email_para.font.size = Pt(12)  # Header text size
        
        tel_run = header_para.add_run("Tel")
        tel_run.bold = True
        tel_run.underline = True
        tel_run.font.size = Pt(12)  # Header text size
        
        number_para = header_para.add_run(": - +91-141-3559110, Mobile: - +91-9413333747) \n")
        number_para.underline = True
        number_para.font.size = Pt(12)  # Header text size
        
        profile = (land_details or {}).get("tsr_profile", "final_sample_v1")

        # Add the reference number and date
        current_date = datetime.now().strftime('%d %b %Y')
        survey_number = sanitize_text(land_details.get('survey_number', '13'))
        ref_para = doc.add_paragraph()
        village_prefix = land_details.get('village_name', 'N/A')[:3].upper()
        district_prefix = land_details.get('district_name', 'N/A')[:3].upper()
        taluka_prefix = land_details.get('taluka_name', 'N/A')[:3].upper()
        if profile == "final_sample_v1":
            report_date = sanitize_text(land_details.get("report_date")) or current_date
            ref_text_val = f"Ref. No. ABREL/GUJ/{taluka_prefix}/{village_prefix}/{survey_number}\t\t\t\tDated :{report_date}"
        else:
            ref_text_val = f"Ref. No. ABREL/GUJ/{district_prefix}/{taluka_prefix}/{village_prefix}/{survey_number}                    Dated: {current_date}"

        ref_text = ref_para.add_run(ref_text_val)
        ref_text.bold = True
        

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
        if profile == "final_sample_v1":
            client_name = sanitize_text(land_details.get("client_name")) or "ABREL SPV 2 Limited"
            client_cin = sanitize_text(land_details.get("client_cin")) or "(CIN: U40108MH2020PLC352631),"
            client_address = sanitize_text(land_details.get("client_address")) or "A-2, Aditya Birla Centre, S.K. Ahire Marg,\nWorli, Mumbai-400030."
            address_para.add_run(f"{client_name}\n{client_cin}\n{client_address}\n")
            kind_attn = sanitize_text(land_details.get("kind_attn")) or "Kind Attn.: Mr. Rahul Patil"
            doc.add_paragraph(kind_attn)
            re_line = sanitize_text(land_details.get("re_line")) or f"Re:\tEmail Dated {sanitize_text(land_details.get('reference_email_date')) or '21.11.2023'} in connection with land situated at Village- {sanitize_text(land_details.get('village_name', 'Not Available'))}, Taluka-{sanitize_text(land_details.get('taluka_name', 'Not Available'))}, District- {sanitize_text(land_details.get('district_name', 'Not Available'))} (Gujrat)."
            doc.add_paragraph(re_line)
        else:
            address_para.add_run("Aditya Birla Renewable Energy Ltd.\nA-2, Aditya Birla Centre, S.K. Ahire Marg,\nWorli, Mumbai-400030.\n")
        
        # Add introduction
        doc.add_paragraph("Dear Sir,")
        if profile == "final_sample_v1":
            intro_text = (
                f"We have been engaged as per above subject reference for the Title Investigation of land situated at "
                f"Village- {sanitize_text(land_details.get('village_name', 'Not Available'))}, "
                f"Taluka-{sanitize_text(land_details.get('taluka_name', 'Not Available'))}, "
                f"District- {sanitize_text(land_details.get('district_name', 'Not Available'))} (Gujrat). "
                f"Our detailed report and findings are as under: -"
            )
        else:
            intro_text = f"     We have been engaged for the Title Investigation of land situated at Village- {sanitize_text(land_details.get('village_name', 'Not Available'))}, Taluka-{sanitize_text(land_details.get('taluka_name', 'Not Available'))}, District- {sanitize_text(land_details.get('district_name', 'Not Available'))}. Our detailed report and findings are as under:"

        doc.add_paragraph(intro_text)
        
        # Section 1: Property Details
        add_section_heading(
            doc,
            "Description, nature, and area of land with survey/plot numbers",
            numbered=True,
        )
        if profile == "final_sample_v1":
            doc.add_paragraph("The Borrower has acquired/purchased the Immovable Properties description whereof (including the names of the Title Holders/Sellers) have been tabulated hereinbelow:")
        
        # Create property details table
        property_table = doc.add_table(rows=1, cols=5)
        property_table.style = 'Table Grid'
        property_table.autofit = False
        property_table.allow_autofit = False
        
        # Set column widths with updated proportions
        col_widths = [0.4, 0.88, 1.19, 1.19, 2.69]  # Total: 6.27 inches
        for i, width in enumerate(col_widths):
            width_in_inches = Inches(width)
            property_table.columns[i].width = width_in_inches
            property_table.rows[0].cells[i].width = width_in_inches
        
        # Add headers
        headers = ["SN", "Nature\tof Land", "Total Area in Hectare / Sq. Mtr", "Survey Number", "Name of the Title Holder"] if profile == "final_sample_v1" else ["SN", "Nature of Land", "Total Area in Hectare / Sq. Mtr", "Survey Number", "Name of the Title Holder"]
        header_cells = property_table.rows[0].cells
        for i, header in enumerate(headers):
            header_cells[i].text = header
            header_cells[i].paragraphs[0].runs[0].bold = True
            header_cells[i].paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
            
            # Set font size to 12.5pt
            for run in header_cells[i].paragraphs[0].runs:
                run.font.name = 'Times New Roman'
                run.font.size = Pt(12.5)
        
        # Add property data
        row = property_table.add_row().cells
        row[0].text = "1"
        
        nature = sanitize_text(land_details.get('nature_of_land'))
       
        if profile == "final_sample_v1":
            if 'new tenure' in nature.lower():
                row[1].text = "New Tenure  Agricultural"
            elif 'old tenure' in nature.lower():
                row[1].text = "Old Tenure  Agricultural"
            else:
                row[1].text = nature
        elif 'old tenure' in nature.lower() and 'ju. sh.' in nature.lower():
            row[1].text = "Old Tenure\nAgricultural Use"
        elif 'new tenure' in nature.lower():
            row[1].text = "New Tenure\nAgricultural Use"
        elif 'old tenure' in nature.lower():
            row[1].text = "Old Tenure\nAgricultural Use"
        else:
            row[1].text = nature
        
        # Format area display as "X-XX-XX - i.e. (XXXXX Sq. Mts)"
        area = sanitize_text(land_details.get('total_area'))
        # Strip "Hectare" if the LLM included it
        area = re.sub(r'\s*Hectare\s*', ' ', area).strip()
        # Check if area already has the format we want
        if ' i.e.' not in area and not re.search(r'\(\d+ Sq\. Mts\)', area):
            # Try to extract numeric values if in format like "2-55-98"
            area_match = re.search(r'(\d+)-(\d+)-(\d+)', area)
            if area_match:
                hectares, acres, guntha = map(int, area_match.groups())
                sq_meters = int((hectares * 10000) + (acres * 100) + guntha)
                area = f"{area} - i.e. ({sq_meters} Sq. Mts)"
        row[2].text = area
        
        survey = sanitize_text(land_details.get('survey_number'))
        old_survey = sanitize_text(land_details.get('old_survey_number'))
        # Only include old survey number if it's available and not "Not Available"
        if old_survey and old_survey.lower() != "not available":
            if profile == "final_sample_v1":
                # Keep on one line to match sample TSR
                row[3].text = f"{survey} (old Survey No. {old_survey})"
            else:
                row[3].text = f"{survey}\n(old Survey no. {old_survey})"
        else:
            row[3].text = survey
        
        # Format owner names as a numbered list
        owner = sanitize_text(land_details.get('owner'))
        
        # Clean up the owner string to remove brackets and quotes
        owner = owner.replace('[', '').replace(']', '').replace("'", "")
        
        # Format as plain list for multiple owners (no numbering)
        if ',' in owner:  # Multiple owners separated by commas
            owners = [name.strip() for name in owner.split(',')]

            owner_text = ""
            for name in owners:
                if name and name.strip():  # Only add non-empty names
                    owner_text += f"{name}\n"
        else:
            # Single owner - no numbering
            if owner and owner.strip():  # Only add non-empty names
                owner_text = f"{owner}\n"
            else:
                owner_text = ""
        
        row[4].text = owner_text.strip()
        
        # Apply cell formatting with 12.5pt font
        for i, cell in enumerate(row):
            cell.paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            
            # Set font size to 12.5pt for all runs
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.name = 'Times New Roman'
                    run.font.size = Pt(12.5)
                paragraph.paragraph_format.line_spacing = 1.15
        
        # Also set widths for cells in the new row
        for i, width in enumerate(col_widths):
            row[i].width = Inches(width)
        
        # Section 2: Documents Scrutinized
        doc.add_paragraph()
        add_section_heading(
            doc,
            "Details/Description of document scrutinized",
            numbered=True,
        )
        
        # Create documents table
        docs_table = doc.add_table(rows=1, cols=3)
        docs_table.style = 'Table Grid'
        docs_table.autofit = False  # Changed from True to False
        docs_table.allow_autofit = False  # Added this line
        
        # Set column widths - ensure total is less than available_width
        col_widths = [3.5, 1.3 , 1.47]  # Total: 6.27 inches
        for i, width in enumerate(col_widths):
            width_in_inches = Inches(width)
            docs_table.columns[i].width = width_in_inches
            docs_table.rows[0].cells[i].width = width_in_inches
        
        # Add headers
        doc_headers = ["Type of the Document/Detail of the Document", "Digitally Certified True Copy/Online Perusal", "Details of Sub-Registrar’s office."] if profile == "final_sample_v1" else ["Type of the Document/Detail of the Document", "Digitally Certified True Copy/Online Perusal", "Details of Sub-Registrar's office."]
        for i, header in enumerate(doc_headers):
            docs_table.rows[0].cells[i].text = header
            docs_table.rows[0].cells[i].paragraphs[0].runs[0].bold = True
            docs_table.rows[0].cells[i].paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
            
            # Set font size to 12.5pt
            for run in docs_table.rows[0].cells[i].paragraphs[0].runs:
                run.font.name = 'Times New Roman'
                run.font.size = Pt(12.5)
        
        # Add standard document types
        standard_docs = [
            ("Old & New Village Form no. 7 starting from the year 1958 till latest version available.", "Online", "Not Applicable"),
            ("Old & New Village Form no. 6 starting from the year 1958 till latest version available.", "Online", "Not Applicable"),
            ("Village Form No. 8A", "Online", "Not Applicable"),
            ("Old Scanned Village Form No. 7/12 starting from the year 1952 to 2004", "Online", "Not Applicable"),
        ]
        if profile != "final_sample_v1" and (land_details or {}).get("include_encumbrance_certificate", True):
            standard_docs.append(("Encumbrance Certificate for a period of 30 Years", "Digital Certified copy", sanitize_text(land_details.get('taluka_name', 'Not Available'))))
        
        for doc_type, perusal, office in standard_docs:
            row = docs_table.add_row().cells
            row[0].text = doc_type
            row[0].paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY
            
            # Make "Online" bold
            row[1].text = ""  # Clear default text
            row[1].paragraphs[0].add_run(perusal).bold = True
            row[1].paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
            
            row[2].text = office
            row[2].paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
            
            # Set font size to 12.5pt for all cells
            for cell in row:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        if not run.bold:  # Skip formatting of already bold runs
                            run.font.name = 'Times New Roman'
                            run.font.size = Pt(12.5)
                        else:
                            run.font.name = 'Times New Roman'
                            run.font.size = Pt(12.5)
                    paragraph.paragraph_format.line_spacing = 1.15
            
            # Set widths for new row cells
            for i, width in enumerate(col_widths):
                row[i].width = Inches(width)
        
        # Add Chain of Title section
        doc.add_paragraph()
        entry_to_row_map = add_chain_of_title_section(doc, entries, entry_table)

        # Regenerate findings with cross-references if mutation data available
        if mutation_entries is not None and entry_to_row_map:
            from tsr_generator.extractors.findings import generate_findings_table
            findings = generate_findings_table("", mutation_entries, land_details, entry_to_row_map)

        # Add Findings table
        add_findings_table(doc, findings)
        
        # Add signature block
        doc.add_paragraph("\nThanking you and assuring you of our best co-operation at all times.")
        
        signature_para = doc.add_paragraph()
        signature_para.alignment = WD_PARAGRAPH_ALIGNMENT.RIGHT
        signature_para.add_run("Regards\n\n\n\n\n\n\n")
        # Add name and designation in bold
        signature_para.add_run("Vijay Choudhary\n").bold = True
        signature_para.add_run("Advocate & Associates").bold = True
        
        # Save the document
        doc.save(output_path)
        logger.debug(f"Document saved successfully as {output_path}")
        
        return output_path
        
    except Exception as e:
        logger.error(f"Error during document generation: {str(e)}")
        logger.error(traceback.format_exc())
        
        raise 