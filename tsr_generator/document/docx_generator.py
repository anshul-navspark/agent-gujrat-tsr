import logging
import re
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT

def add_table_with_header(doc, headers, rows, style=None):
    """
    Add a table with headers to the document
    
    Args:
        doc (Document): The document object
        headers (list): List of header strings
        rows (list): List of row data lists
        style (str, optional): Table style
        
    Returns:
        Table: The created table object
    """
    num_cols = len(headers)
    table = doc.add_table(rows=1, cols=num_cols)
    if style:
        table.style = style
    else:
        table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    
    # Add headers
    header_cells = table.rows[0].cells
    for i, header in enumerate(headers):
        header_cells[i].text = header
        header_cells[i].paragraphs[0].runs[0].bold = True
        header_cells[i].paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        
        # Apply font and line spacing to header cells
        for paragraph in header_cells[i].paragraphs:
            for run in paragraph.runs:
                run.font.name = 'Times New Roman'
                run.font.size = Pt(12.5)
            paragraph.paragraph_format.line_spacing = 1.15
    
    # Add data rows
    for row_data in rows:
        row_cells = table.add_row().cells
        for i, cell_data in enumerate(row_data):
            row_cells[i].text = str(cell_data)
            row_cells[i].paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.LEFT
            
            # Apply font and line spacing to data cells
            for paragraph in row_cells[i].paragraphs:
                for run in paragraph.runs:
                    run.font.name = 'Times New Roman'
                    run.font.size = Pt(12.5)
                paragraph.paragraph_format.line_spacing = 1.15
    
    return table

def add_section_heading(doc, text, level=1, numbered=True):
    """
    Add a section heading to the document
    
    Args:
        doc (Document): The document object
        text (str): Heading text
        level (int): Heading level (1-9)
        numbered (bool): Whether to use numbered style
        
    Returns:
        Paragraph: The created heading paragraph
    """
    heading = doc.add_paragraph()
    if numbered:
        heading.style = 'Normal'
        run = heading.add_run(text)
        run.bold = True
        run.font.name = 'Times New Roman'
        run.font.size = Pt(12.5)
    else:
        heading.style = f'Heading {level}'
        run = heading.add_run(text)
        run.font.name = 'Times New Roman'
        run.font.size = Pt(12.5)
    
    heading.paragraph_format.line_spacing = 1.15
    heading.paragraph_format.space_after = Pt(6)
    heading.paragraph_format.space_before = Pt(12)
    
    return heading

def add_chain_of_title_section(doc, entries):
    """
    Add the Chain of Title section to the document
    
    Args:
        doc (Document): The document object
        entries (list): List of entry dictionaries
        
    Returns:
        None
    """
    logger = logging.getLogger(__name__)
    logger.info("Adding Chain of Title section")
    
    add_section_heading(doc, "3.  Chain of Title", numbered=True)
    
    # Create and format the table
    table = doc.add_table(rows=0, cols=2)
    table.style = 'Table Grid'
    table.autofit = False
    table.allow_autofit = False
    
    # Set column widths
    widths = [Inches(0.5), Inches(5.77)]  # Total: 6.27 inches
    table.add_row()  # Add a row for setting initial widths
    
    for i, width in enumerate(widths):
        table.columns[i].width = width
        table.rows[0].cells[i].width = width
    
    # Remove the temporary row if not needed
    if len(entries) > 0:
        table._element.remove(table.rows[0]._element)
    
    # Add header row
    header_cells = table.add_row().cells
    header_cells[0].text = ""
    header_cells[1].text = "Brief history and flow of title with respect to Immovable Properties -- For 30 Year Period - Based on perusal of the documents referred in S. No. 2 above."
    
    # Format header cells
    for paragraph in header_cells[1].paragraphs:
        for run in paragraph.runs:
            run.bold = True
            run.font.name = 'Times New Roman'
            run.font.size = Pt(12.5)
        paragraph.paragraph_format.line_spacing = 1.15
    
    # Add entries
    for i, entry in enumerate(entries, 1):
        row_cells = table.add_row().cells
        
        # Add entry number in first column
        row_cells[0].text = f"{i}."
        row_cells[0].paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        row_cells[0].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        
        # Add entry details in second column with proper formatting
        entry_text = ""
        
        # Format the entry content
        entry_text = f"Entry No. {entry.get('entry_number', 'Not Available')} "
        if entry.get('date') and entry['date'] != "Not Available":
            entry_text += f"Dated {entry.get('date')} "
        
        if entry.get('type') and entry['type'] != "Not Available":
            entry_text += f"{entry.get('type')} "
        
        # Add description
        entry_text += entry.get('description', 'Not Available')
        
        # Clear the cell and add formatted text
        row_cells[1].text = ""
        paragraph = row_cells[1].paragraphs[0]
        
        # Extract the entry number part for bolding
        match = re.match(r"(Entry No\. \d+(?:\s+Dated\s+\d{2}/\d{2}/\d{4})?(?:\s+[A-Za-z]+)?)", entry_text)
        if match:
            bold_part, rest = match.group(1), entry_text[match.end():]
            bold_run = paragraph.add_run(bold_part)
            bold_run.bold = True
            bold_run.font.name = 'Times New Roman'
            bold_run.font.size = Pt(12.5)
            
            normal_run = paragraph.add_run(rest)
            normal_run.font.name = 'Times New Roman'
            normal_run.font.size = Pt(12.5)
        else:
            run = paragraph.add_run(entry_text)
            run.font.name = 'Times New Roman'
            run.font.size = Pt(12.5)
        
        paragraph.paragraph_format.line_spacing = 1.15
        
        # Set widths for cells
        for j, width in enumerate(widths):
            row_cells[j].width = width
    
    # Add note at the end
    row_cells = table.add_row().cells
    row_cells[0].text = f"{len(entries) + 1}."
    row_cells[0].paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    row_cells[0].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    
    row_cells[1].text = "Note:- The title of the land is clear and marketable."
    
    # Format note cell
    for paragraph in row_cells[1].paragraphs:
        for run in paragraph.runs:
            run.font.name = 'Times New Roman'
            run.font.size = Pt(12.5)
        paragraph.paragraph_format.line_spacing = 1.15
    
    # Set widths for final row cells
    for i, width in enumerate(widths):
        row_cells[i].width = width
    
    logger.info("Chain of title section completed")

def add_findings_table(doc, findings):
    """
    Add the Findings table to the document
    
    Args:
        doc (Document): The document object
        findings (list): List of finding dictionaries
        
    Returns:
        None
    """
    logger = logging.getLogger(__name__)
    logger.info("Adding Findings table")
    
    # Add section heading
    doc.add_paragraph()
    add_section_heading(doc, "4.  Findings & opinion based our title investigation:-", numbered=True)
    
    # Create and format the table
    table = doc.add_table(rows=1, cols=3)
    table.style = 'Table Grid'
    table.autofit = False
    table.allow_autofit = False
    
    # Set column widths
    col_widths = [0.5, 3.5, 2.27]  # Total: 6.27 inches
    for i, width in enumerate(col_widths):
        table.columns[i].width = Inches(width)
    
    # Add headers
    headers = ["SN", "Particular", "Observations"]
    header_cells = table.rows[0].cells
    for i, header in enumerate(headers):
        header_cells[i].text = header
        header_cells[i].paragraphs[0].runs[0].bold = True
        header_cells[i].paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        header_cells[i].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        
        # Apply formatting to header cells
        for paragraph in header_cells[i].paragraphs:
            for run in paragraph.runs:
                run.font.name = 'Times New Roman'
                run.font.size = Pt(12.5)
            paragraph.paragraph_format.line_spacing = 1.15
    
    # Add findings
    for finding in findings:
        row_cells = table.add_row().cells
        
        # Add serial number
        row_cells[0].text = finding['sn']
        row_cells[0].paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        row_cells[0].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        
        # Add particular
        row_cells[1].text = finding['particular']
        
        # Add observation
        row_cells[2].text = finding['observation']
        
        # Apply formatting to all cells
        for cell in row_cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.name = 'Times New Roman'
                    run.font.size = Pt(12.5)
                paragraph.paragraph_format.line_spacing = 1.15 