import logging
import re
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from tsr_generator.extractors.findings import detect_active_encumbrances
from tsr_generator.extractors.unified_extractor import _normalize_date_str


def _create_decimal_numbering(document):
    """Create a fresh decimal numbering definition that restarts at 1.

    Returns the numId to reference from a paragraph's w:numPr. Each call yields a
    distinct numId so independent counters can coexist (e.g., one per table).

    Number is rendered by Word, so font/weight/size live in the lvl's rPr — the
    cell paragraph itself stays empty.
    """
    numbering = document.part.numbering_part.element

    existing_abs_ids = [int(a.get(qn('w:abstractNumId')))
                        for a in numbering.findall(qn('w:abstractNum'))]
    next_abs_id = (max(existing_abs_ids) + 1) if existing_abs_ids else 0

    existing_num_ids = [int(n.get(qn('w:numId')))
                        for n in numbering.findall(qn('w:num'))]
    next_num_id = (max(existing_num_ids) + 1) if existing_num_ids else 1

    abstract_num = OxmlElement('w:abstractNum')
    abstract_num.set(qn('w:abstractNumId'), str(next_abs_id))

    lvl = OxmlElement('w:lvl')
    lvl.set(qn('w:ilvl'), '0')
    for tag, val in (('w:start', '1'), ('w:numFmt', 'decimal'),
                     ('w:lvlText', '%1.'), ('w:lvlJc', 'left'),
                     ('w:suff', 'nothing')):
        e = OxmlElement(tag)
        e.set(qn('w:val'), val)
        lvl.append(e)
    lvl_pPr = OxmlElement('w:pPr')
    ind = OxmlElement('w:ind')
    ind.set(qn('w:left'), '0')
    ind.set(qn('w:firstLine'), '0')
    lvl_pPr.append(ind)
    lvl.append(lvl_pPr)
    lvl_rPr = OxmlElement('w:rPr')
    rfonts = OxmlElement('w:rFonts')
    rfonts.set(qn('w:ascii'), 'Times New Roman')
    rfonts.set(qn('w:hAnsi'), 'Times New Roman')
    lvl_rPr.append(rfonts)
    lvl_rPr.append(OxmlElement('w:b'))
    sz = OxmlElement('w:sz')
    sz.set(qn('w:val'), '25')  # 25 half-points = 12.5pt
    lvl_rPr.append(sz)
    lvl.append(lvl_rPr)
    abstract_num.append(lvl)

    # Schema requires all w:abstractNum elements to precede w:num elements.
    first_num = numbering.find(qn('w:num'))
    if first_num is not None:
        first_num.addprevious(abstract_num)
    else:
        numbering.append(abstract_num)

    num = OxmlElement('w:num')
    num.set(qn('w:numId'), str(next_num_id))
    abs_ref = OxmlElement('w:abstractNumId')
    abs_ref.set(qn('w:val'), str(next_abs_id))
    num.append(abs_ref)
    numbering.append(num)

    return next_num_id


def _apply_list_number(paragraph, num_id, ilvl=0):
    """Attach numbering properties to a paragraph so Word renders an auto-number."""
    pPr = paragraph._p.get_or_add_pPr()
    numPr = OxmlElement('w:numPr')
    ilvl_e = OxmlElement('w:ilvl')
    ilvl_e.set(qn('w:val'), str(ilvl))
    numId_e = OxmlElement('w:numId')
    numId_e.set(qn('w:val'), str(num_id))
    numPr.append(ilvl_e)
    numPr.append(numId_e)
    pPr.append(numPr)

def add_table_with_header(doc, headers, rows, style=None, col_widths=None):
    """
    Add a table with headers to the document
    
    Args:
        doc (Document): The document object
        headers (list): List of header strings
        rows (list): List of row data lists
        style (str, optional): Table style
        col_widths (list, optional): List of column widths in inches
        
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
    table.autofit = False
    table.allow_autofit = False
    
    # Set column widths if provided
    if col_widths:
        for i, width in enumerate(col_widths):
            table.columns[i].width = Inches(width)
            # Set for the first row
            table.rows[0].cells[i].width = Inches(width)
    
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
        
        # Set widths for the new row if provided
        if col_widths:
            for i, width in enumerate(col_widths):
                row_cells[i].width = Inches(width)
        
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

def _number_names_after_follows(description: str) -> str:
    """Number newline-separated names that appear after 'as follows:' or 'as follows:-' in entry descriptions."""
    pattern = re.compile(r'(as follows:[-]?\s*\n)((?:.+\n?)+?)(\nThe Entry is|\Z)', re.IGNORECASE)

    def replacer(m):
        prefix = m.group(1)
        names_block = m.group(2)
        suffix = m.group(3)
        names = [n for n in names_block.splitlines() if n.strip()]
        numbered = "\n".join(f"{i}. {n.strip()}" for i, n in enumerate(names, 1))
        return prefix + numbered + suffix

    return pattern.sub(replacer, description)


def _parse_survey_correction_table(description):
    """Detect the 'Survey No. / Error / Correction' inline-table pattern in an entry description.

    Returns (pre_text, rows, post_text) where rows is a list of dicts with keys
    'survey_no', 'error', 'correction', or None if the pattern is not present.
    """
    MARKER = "Survey No. / Error / Correction"
    idx = description.find(MARKER)
    if idx == -1:
        return None

    pre_text = description[:idx].rstrip(": ")
    after_marker = description[idx + len(MARKER):].strip()

    # Each entry looks like: "98/p10 ! 98/p25 / Survey No. 98/p10"
    row_re = re.compile(
        r'(\S+/\S+)\s*!\s*(\S+/\S+)\s*/\s*Survey No\.\s*(\S+?)(?=[,\.])'
    )
    rows = []
    last_end = 0
    for m in row_re.finditer(after_marker):
        rows.append({
            'survey_no': m.group(1),
            'error': m.group(2),
            'correction': f"Survey No. {m.group(3)}",
        })
        last_end = m.end()

    if not rows:
        return None

    post_text = after_marker[last_end:].lstrip('., ').strip()
    return pre_text, rows, post_text


def _add_nested_table_to_cell(cell, document, headers, rows_data):
    """Insert a small bordered table inside a table cell.

    Creates the table in the document body, then moves its XML element
    into the cell before the cell's final paragraph (Word requires tc
    to end with a w:p element).
    """
    from docx.oxml.ns import qn

    nested = document.add_table(rows=0, cols=len(headers))
    nested.style = 'Table Grid'

    # Header row
    hdr_row = nested.add_row()
    for i, hdr in enumerate(headers):
        c = hdr_row.cells[i]
        c.paragraphs[0].clear()
        run = c.paragraphs[0].add_run(hdr)
        run.bold = True
        run.font.name = 'Times New Roman'
        run.font.size = Pt(11)

    # Data rows
    for rd in rows_data:
        dr = nested.add_row()
        for i, val in enumerate(rd.values()):
            c = dr.cells[i]
            c.paragraphs[0].clear()
            run = c.paragraphs[0].add_run(val)
            run.font.name = 'Times New Roman'
            run.font.size = Pt(11)

    # Move tbl XML from document body into the cell (before last w:p)
    tbl_el = nested._tbl
    tbl_el.getparent().remove(tbl_el)
    last_p = cell._tc.findall(qn('w:p'))[-1]
    cell._tc.insert(list(cell._tc).index(last_p), tbl_el)


def add_chain_of_title_section(document, entries, entry_table):
    """
    Add Chain of Title section with a two-column table format where:
    - First column (0.42 inches): empty (manual versions leave this column empty)
    - Second column (5.85 inches): Entry details including entry number, date, description, and certification

    Args:
        document: The document object to add the section to
        entries: List of entry objects to include in the Chain of Title section
        entry_table: List of entry numbers to include

    Returns:
        dict: Mapping of entry number to row index
    """
    logger = logging.getLogger(__name__)
    logger.debug("Adding Chain of Title section with two-column format")
    
    # Add section heading
    add_section_heading(document, "Chain of Title", numbered=True)

    if not entries:
        paragraph = document.add_paragraph()
        paragraph.add_run("No entries found in the document.").italic = True
        return {}
    
    # Fresh numbering definition so this table's row numbers restart at 1 and
    # auto-renumber when lawyers insert/delete rows in Word.
    num_id = _create_decimal_numbering(document)

    # Create a table for Chain of Title - two columns
    table = document.add_table(rows=0, cols=2)
    table.style = 'Table Grid'
    table.autofit = False
    table.allow_autofit = False
    
    # Set column widths - adjusted to account for margins
    # A4 page is 8.27 inches, with ~1 inch margins on each side, leaving ~6.27 inches usable
    col_widths = [0.42, 5.85]  # Widths in inches as specified - total: 6.27 inches
    for i, width in enumerate(col_widths):
        table.columns[i].width = Inches(width)
        # Also set the cell width to ensure consistent rendering
        for row in table.rows:
            row.cells[i].width = Inches(width)
    
    # Add header row with explanatory text
    header_row_cells = table.add_row().cells

    # Set cell widths for the header row
    for i, width in enumerate(col_widths):
        table.rows[-1].cells[i].width = Inches(width)

    # First column is empty

    # Second column: Add explanatory text
    header_text = "Brief history and flow of title with respect to Immovable Properties \u2013 For 30 Year Period - Based on perusal of the documents referred in S. No. 2 above."
    header_para = header_row_cells[1].paragraphs[0]
    header_run = header_para.add_run(header_text)
    header_run.bold = True
    header_run.font.name = 'Times New Roman'
    header_run.font.size = Pt(12.5)

    # Format the header paragraph
    header_para.paragraph_format.alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY
    header_para.paragraph_format.line_spacing = 1.15
    
    # Create a map of entries for quick lookup
    entry_map = {}
    if entries:
        for entry in entries:
            if getattr(entry, 'entry_number', None):
                entry_map[str(entry.entry_number).strip()] = entry
                
    # Collect all unique entry numbers from entry_table and entries
    all_entry_numbers = set()
    if entry_table:
        for num in entry_table:
            if str(num).strip():
                all_entry_numbers.add(str(num).strip())
    
    # Also include numbers from entries to be safe
    for num in entry_map.keys():
        all_entry_numbers.add(num)
        
    # Sort the numbers
    sorted_numbers = sorted(list(all_entry_numbers), key=lambda x: int(x) if x.isdigit() else float('inf'))
    
    # Iterate through all numbers and add rows
    entry_to_row_map = {}
    row_index = 0
    for row_index, num in enumerate(sorted_numbers, 1):
        try:
            entry = entry_map.get(num)
            entry_to_row_map[num] = row_index
            
            # Add a new row
            row_cells = table.add_row().cells
            
            # Set cell widths for newly added row
            for j, width in enumerate(col_widths):
                table.rows[-1].cells[j].width = Inches(width)
            
            # First column: Word renders the row number from numPr so it
            # auto-renumbers if a lawyer inserts/deletes a row.
            row_cells[0].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
            num_para = row_cells[0].paragraphs[0]
            _apply_list_number(num_para, num_id)
            
            # Second column: Entry details
            entry_para = row_cells[1].paragraphs[0]
            
            if entry:
                # Existing entry logic
                safe_date = entry.date if getattr(entry, 'date', '') else ""
                date_str = f" {safe_date}" if safe_date else ""
                header_text = f"Entry No. {entry.entry_number} Dated{date_str} "
                header_run = entry_para.add_run(header_text)
                header_run.bold = True
                header_run.font.name = 'Times New Roman'
                header_run.font.size = Pt(12.5)
                
                # Add description — detect inline survey-correction table
                description = entry.formatted_description or ""
                description = description.strip()
                if description and not description.startswith("That"):
                    description = f"That {description}"
                description = _number_names_after_follows(description)

                parsed = _parse_survey_correction_table(description)
                if parsed:
                    pre_text, corr_rows, post_text = parsed
                    # Write pre-table text into entry_para
                    desc_run = entry_para.add_run(pre_text)
                    desc_run.font.name = 'Times New Roman'
                    desc_run.font.size = Pt(12.5)
                    entry_para.paragraph_format.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT
                    entry_para.paragraph_format.line_spacing = 1.15

                    # Insert nested table in the cell
                    _add_nested_table_to_cell(
                        row_cells[1], document,
                        headers=['Survey No.', 'Error', 'Correction'],
                        rows_data=corr_rows,
                    )

                    # Any text after the table (rare) goes in a new paragraph
                    if post_text:
                        post_para = row_cells[1].add_paragraph()
                        post_run = post_para.add_run(post_text)
                        post_run.font.name = 'Times New Roman'
                        post_run.font.size = Pt(12.5)
                        post_para.paragraph_format.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT
                        post_para.paragraph_format.line_spacing = 1.15
                else:
                    desc_run = entry_para.add_run(description)
                    desc_run.font.name = 'Times New Roman'
                    desc_run.font.size = Pt(12.5)

                # Format the entry paragraph
                entry_para.paragraph_format.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT
                entry_para.paragraph_format.line_spacing = 1.15

                # Add certification: use existing cert or default for non-promulgation entries
                _entry_type_val = entry.type.value if hasattr(entry.type, 'value') else str(entry.type)
                _skip_cert_types = ['Promulgation', 'Not Related', 'PROMULGATION', 'NOT_RELATED']
                _has_cert = hasattr(entry, 'certification') and entry.certification
                if not _has_cert and _entry_type_val not in _skip_cert_types:
                    entry.certification = "The Entry is certified."
                    entry.entry_status = entry.entry_status or "certified"
                
                if hasattr(entry, 'certification') and entry.certification:
                    
                    # Determine status word based on entry_status
                    status_word = "certified"  # default
                    if hasattr(entry, 'entry_status') and entry.entry_status:
                        status_lower = entry.entry_status.lower()
                        if status_lower in ['rejected', 'cancelled']:
                            status_word = "rejected"
                        elif status_lower in ['not_accepted', 'not accepted', 'not_approved']:
                            status_word = "not accepted"
                    
                    # Get certification text
                    certification_text = entry.certification
                    
                    # USE STRUCTURED FIELDS IF AVAILABLE (Fix for regression)
                    # Check if we have structured official/date from the extractor
                    has_structured_data = (
                        (hasattr(entry, 'certification_official') and entry.certification_official) or
                        (hasattr(entry, 'certification_date') and entry.certification_date)
                    )
                    
                    if has_structured_data:
                        # Use the structured data to build the string
                        official_name = getattr(entry, 'certification_official', '') or ""
                        cert_date = getattr(entry, 'certification_date', '') or ""
                        cert_date = _normalize_date_str(cert_date)

                        # Clean up
                        official_name = official_name.strip()
                        if official_name.endswith(','): official_name = official_name[:-1]
                        
                        if official_name and cert_date:
                            certification_text = f"The Entry is {status_word} by {official_name} on {cert_date}."
                        elif official_name:
                            certification_text = f"The Entry is {status_word} by {official_name}."
                        elif cert_date:
                            certification_text = f"The Entry is {status_word} on {cert_date}."
                        else:
                            certification_text = f"The Entry is {status_word}."
                            
                    else:
                        # Fallback to Regex parsing ONLY if structured data is missing
                        import re
                        # Fixed regex: allow periods in official names (e.g. "C.O. Talaja")
                        official_match = re.search(r'by\s+(.+?)(?:\s+on\s+\d|\s+but\s|\s*\.\s*$)', certification_text)
                        date_match = re.search(r'on\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+[A-Za-z]+\s+\d{2,4})', certification_text)
                        
                        # Build the certification text with correct status word
                        if official_match:
                            official_name = official_match.group(1).strip()
                            # Clean up trailing punctuation
                            official_name = re.sub(r'[.,;:]+$', '', official_name)
                            
                            if date_match:
                                expanded_date = _normalize_date_str(date_match.group(1))
                                certification_text = f"The Entry is {status_word} by {official_name} on {expanded_date}."
                            else:
                                # Check for special cases
                                if "not legible" in entry.certification.lower() or "illegible" in entry.certification.lower():
                                    certification_text = f"The Entry is {status_word} by {official_name} but date is not legible."
                                elif "not mentioned" in entry.certification.lower() or "not specified" in entry.certification.lower():
                                    certification_text = f"The Entry is {status_word} by {official_name} but date is not mentioned."
                                else:
                                    certification_text = f"The Entry is {status_word} by {official_name}."
                        else:
                            # No official found, use simple format
                            certification_text = f"The Entry is {status_word}."

                    # Certification in a separate paragraph to avoid justification stretching
                    # the last line of the description (soft line breaks cause JUSTIFY to
                    # stretch that line; a true paragraph end does not).
                    cert_para = row_cells[1].add_paragraph()
                    cert_run = cert_para.add_run(certification_text)
                    cert_run.font.name = 'Times New Roman'
                    cert_run.font.size = Pt(12.5)
                    cert_para.paragraph_format.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT
                    cert_para.paragraph_format.line_spacing = 1.15
                    cert_para.paragraph_format.space_before = Pt(0)
            else:
                # Placeholder logic
                header_text = f"Entry No. {num} Dated : "
                header_run = entry_para.add_run(header_text)
                header_run.bold = True
                header_run.font.name = 'Times New Roman'
                header_run.font.size = Pt(12.5)
                
                entry_para.paragraph_format.alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY
                entry_para.paragraph_format.line_spacing = 1.15
                
        except Exception as e:
            logger.error(f"Error adding entry {num} to table: {str(e)}")
            continue

    # Detect active encumbrances for note row (accepts dataclass objects directly)
    active_encumbrances, active_entry_nums = detect_active_encumbrances(entries)

    note_row_cells = table.add_row().cells
    # First column: empty

    note_para_1 = note_row_cells[1].paragraphs[0]

    if active_entry_nums:
        # Format entry numbers with bank names when available
        entry_refs = ", ".join(active_entry_nums)
        note_text = f"Note:- The title of the land is clear and marketable subject to bank charge. (Entry No. {entry_refs})"
    else:
        note_text = "Note:- The title of the land is clear and marketable."

    note_run_1 = note_para_1.add_run(note_text)
    note_run_1.bold = True
    note_run_1.font.name = 'Times New Roman'
    note_run_1.font.size = Pt(12.5)

    # Add some space after the table
    document.add_paragraph()

    return entry_to_row_map

def construct_description_from_fields(entry):
    """
    Construct a description from the entry fields based on entry type
    
    Args:
        entry: Entry object with specific type fields
        
    Returns:
        str: Constructed description string
    """
    from tsr_generator.extractors.entry_schema import (
        EntryType, SaleEntry, MortgageEntry, ReleaseEntry, InheritanceEntry, 
        PartitionEntry, RelinquishmentEntry, OrderEntry
    )
    
    # Handle different entry types
    if isinstance(entry, SaleEntry):
        # Extract seller and buyer names
        sellers = entry.sellers if entry.sellers else []
        buyers = entry.buyers if entry.buyers else []
        
        # Format seller names as a string, handling single vs multiple sellers
        if len(sellers) == 1:
            seller_names = sellers[0].name if sellers[0].name else "Unknown"
        else:
            # For multiple sellers, we'll still use comma-separation in the first mention
            seller_names = ", ".join([seller.name for seller in sellers]) if sellers else "Unknown"
            
        # Format buyer names as a string
        buyer_names = ", ".join([buyer.name for buyer in buyers]) if buyers else "Unknown"
        
        # Standard format for Sale entries
        description = f"That the said {seller_names} sold their respective share in land bearing Survey No. "
        
        if hasattr(entry, 'survey_number') and entry.survey_number:
            description += f"{entry.survey_number} "
        
        if hasattr(entry, 'area') and entry.area:
            description += f"measuring {entry.area} Hectare "
        
        description += f"to {buyer_names}"
        
        if hasattr(entry, 'document_number') and entry.document_number:
            description += f" through the document no. {entry.document_number}"
        
        if hasattr(entry, 'date') and entry.date:
            description += f" dated {entry.date}"
        
        if entry.consideration:
            description += f" for a consideration of Rs. {entry.consideration}/-"
        
        description += "."
        
        # Add property details if available
        if entry.property_details:
            description += f" {entry.property_details}"
        
        return description
    
    elif isinstance(entry, MortgageEntry):
        # Extract mortgagor and mortgagee names
        mortgagors = entry.mortgagor if entry.mortgagor else []
        mortgagees = entry.mortgagee if entry.mortgagee else []
        
        mortgagor_names = ", ".join([m.name for m in mortgagors]) if mortgagors else "Unknown"
        mortgagee_names = ", ".join([m.name for m in mortgagees]) if mortgagees else "Unknown"
        
        # Standard format for Loan entries
        description = f"That {mortgagor_names} took a loan of Rs. "
        
        if entry.amount:
            # Remove 'Rs.' if already in the amount field to avoid duplication
            amount = entry.amount
            if amount.startswith("Rs."):
                amount = amount[3:].strip()
            if amount.endswith("/-"):
                amount = amount[:-2].strip()
            description += f"{amount}/- "
        else:
            description += "amount not specified/- "
        
        description += "on the land bearing "
        
        if hasattr(entry, 'survey_number') and entry.survey_number:
            description += f"Survey No. {entry.survey_number} "
        else:
            description += "Survey No. not specified "
        
        description += f"from {mortgagee_names}."
        
        # Add period and interest rate if available
        if entry.period:
            description += f" Period: {entry.period}."
        
        if entry.interest_rate:
            description += f" Interest rate: {entry.interest_rate}."
        
        return description
    
    elif isinstance(entry, ReleaseEntry):
        # Extract releasor and releasee names
        releasors = entry.releasor if entry.releasor else []
        releasees = entry.releasee if entry.releasee else []
        
        releasor_names = ", ".join([r.name for r in releasors]) if releasors else "Unknown"
        releasee_names = ", ".join([r.name for r in releasees]) if releasees else "Unknown"
        
        # Standard format for Release/Relinquishment entries
        if hasattr(entry, 'is_loan_release') and entry.is_loan_release:
            # For loan redemption entries — formal legal phrasing
            description = f"That upon receiving an application from {releasee_names} for removing the charge of {releasor_names}"

            if hasattr(entry, 'branch') and entry.branch:
                description += f", {entry.branch} Branch"

            description += ". The said exemption of burden has been recorded."

            if entry.reference_to_original:
                description += f" Entry No. {entry.reference_to_original}."
        else:
            # For regular relinquishment entries
            description = f"That reflects that {releasor_names} relinquished their respective share in favour of {releasee_names}."
            
            if entry.reference_to_original:
                description += f" Reference to original entry: {entry.reference_to_original}."
        
        return description
    
    elif isinstance(entry, InheritanceEntry):
        # Extract deceased and heir information
        deceased_name = entry.deceased.name if entry.deceased else "Unknown"
        heirs = entry.heirs if entry.heirs else []
        
        # Standard format for Death/Inheritance entries
        description = f"That upon the demise of {deceased_name}, his land bearing "
        
        if hasattr(entry, 'survey_number') and entry.survey_number:
            if hasattr(entry, 'is_old_survey') and entry.is_old_survey:
                description += f"old Survey No. {entry.survey_number} "
            else:
                description += f"Survey No. {entry.survey_number} "
        else:
            description += "Survey No. not specified "
        
        description += "came to be mutated in his legal heirs which are as follows:-"
        
        # Format heirs as plain line-break-separated list (no numbering)
        if heirs:
            description += "\n"
            for i, heir in enumerate(heirs):
                description += heir.name
                if i < len(heirs) - 1:
                    description += "\n"
        else:
            description += " No heirs specified."
        
        return description
    
    elif isinstance(entry, PartitionEntry):
        # Extract original owners
        owners = entry.original_owners if entry.original_owners else []
        owner_names = ", ".join([o.name for o in owners]) if owners else "Unknown"
        
        # Standard format for Partition entries
        description = f"That the said {owner_names} distributed his land as follows:-"
        
        # Format allocations as a table representation (text format)
        if entry.resulting_allocations and isinstance(entry.resulting_allocations, dict):
            description += "\n"
            # Add header row representation
            description += "Sr. No. | Name | Survey No. | Acre/Guntha\n"
            description += "--------|------|------------|-------------\n"
            
            # Add data rows
            for i, (name, alloc) in enumerate(entry.resulting_allocations.items(), 1):
                survey_no = alloc.get('survey_no', 'N/A')
                area = alloc.get('area', 'N/A')
                description += f"{i}. | {name} | {survey_no} | {area}\n"
                
            description += "\nThe above distribution is based on their application and their consent."
        
        return description
    
    elif isinstance(entry, RelinquishmentEntry):
        # Extract relinquisher and beneficiary information
        relinquishers = entry.relinquisher if entry.relinquisher else []
        beneficiaries = entry.beneficiary if entry.beneficiary else []
        
        relinquisher_names = ", ".join([r.name for r in relinquishers]) if relinquishers else "Unknown"
        beneficiary_names = ", ".join([b.name for b in beneficiaries]) if beneficiaries else "Unknown"
        
        # For "Persons Add" entries
        if hasattr(entry, 'is_add_persons') and entry.is_add_persons:
            description = f"That the said {relinquisher_names} made an application of life time distribution in his land bearing "
            
            if hasattr(entry, 'survey_number') and entry.survey_number:
                description += f"Survey No. {entry.survey_number} "
            else:
                description += "Survey No. not specified "
            
            description += "to add his legal heirs which are as follows:-"
            
            # Format beneficiaries as a numbered list
            if beneficiaries:
                description += "\n"
                for i, beneficiary in enumerate(beneficiaries, 1):
                    description += f"{i}. {beneficiary.name}"
                    if i < len(beneficiaries):
                        description += "\n"
            else:
                description += " No beneficiaries specified."
        
        # For "Transfer" entries
        elif hasattr(entry, 'is_transfer') and entry.is_transfer:
            description = f"That the said {relinquisher_names} made an application of life time distribution in his land bearing "
            
            if hasattr(entry, 'survey_number') and entry.survey_number:
                description += f"Survey No. {entry.survey_number} "
            else:
                description += "Survey No. not specified "
            
            description += "to transfer to his legal heirs which are as follows:-"
            
            # Format beneficiaries as a numbered list
            if beneficiaries:
                description += "\n"
                for i, beneficiary in enumerate(beneficiaries, 1):
                    description += f"{i}. {beneficiary.name}"
                    if i < len(beneficiaries):
                        description += "\n"
            else:
                description += " No beneficiaries specified."
        
        # For regular relinquishment entries
        else:
            description = f"That reflects that {relinquisher_names} relinquished their respective share in favour of {beneficiary_names}."
            
            if entry.relationship:
                description += f" Relationship: {entry.relationship}."
        
        return description
    
    elif isinstance(entry, OrderEntry):
        # Format for Order entries
        description = "Entry No. "
        
        if hasattr(entry, 'entry_number') and entry.entry_number:
            description += f"{entry.entry_number} "
        else:
            description += "not specified "
        
        description += "Dated "
        
        if hasattr(entry, 'date') and entry.date:
            description += f"{entry.date} "
        else:
            description += "not specified "
        
        description += "Vide order of "
        
        if entry.authority:
            description += f"{entry.authority}, "
        else:
            description += "authority not specified, "
        
        if hasattr(entry, 'place') and entry.place:
            description += f"{entry.place} "
        
        description += "order no. "
        
        if hasattr(entry, 'order_number') and entry.order_number:
            description += f"{entry.order_number} "
        else:
            description += "not specified "
        
        description += "dated "
        
        if hasattr(entry, 'order_date') and entry.order_date:
            description += f"{entry.order_date}"
        else:
            description += "not specified"
        
        if entry.order_details:
            description += f". {entry.order_details}"
        
        if entry.affected_parties:
            party_names = ", ".join([p.name for p in entry.affected_parties])
            description += f" Parties affected: {party_names}."
        
        return description
    
    # For other types or if we can't construct a proper description
    if hasattr(entry, 'raw_description'):
        # Add "That" prefix if it's not already there
        description = entry.raw_description
        if not description.strip().startswith("That"):
            description = f"That {description}"
        return description
    
    return "Details not available."

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
    logger.debug("Adding Findings table")
    
    # Add section heading
    doc.add_paragraph()
    add_section_heading(doc, "Findings & opinion based our title investigation:-", numbered=True)
    
    # Create and format the table
    table = doc.add_table(rows=1, cols=3)
    table.style = 'Table Grid'
    table.autofit = False
    table.allow_autofit = False
    
    # Set column widths - adjusted for better proportions
    # A4 page is 8.27 inches, with ~1 inch margins on each side, leaving ~6.27 inches usable
    col_widths = [0.5, 3.5, 2.27]  # Total: 6.27 inches
    for i, width in enumerate(col_widths):
        table.columns[i].width = Inches(width)
        # Also set the cell width to ensure consistent rendering
        for row in table.rows:
            row.cells[i].width = Inches(width)
    
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
        
        # Set cell widths for newly added row
        for i, width in enumerate(col_widths):
            table.rows[-1].cells[i].width = Inches(width)
        
        # Add serial number - Fix: Use paragraphs[0].add_run instead of directly calling add_run on the cell
        row_cells[0].text = finding['sn']
        row_cells[0].paragraphs[0].runs[0].bold = True
        

        
        # Add particular
        row_cells[1].text = finding['particular']
        row_cells[1].paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY
        # Add observation
        row_cells[2].text = finding['observation']
        row_cells[2].paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY
        
        # Apply formatting to all cells
        for cell in row_cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.name = 'Times New Roman'
                    run.font.size = Pt(12.5)
                paragraph.paragraph_format.line_spacing = 1.15