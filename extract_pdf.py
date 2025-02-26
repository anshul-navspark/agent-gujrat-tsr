from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT


def create_document_with_a4_size():
    """Create a new document with A4 page size and proper margins"""
    document = Document()
    
    # A4 size in inches
    section = document.sections[0]
    section.page_height = Inches(11.69)
    section.page_width = Inches(8.27)
    
    # Set margins (standard A4 margins in inches)
    section.left_margin = Inches(1.0)
    section.right_margin = Inches(1.0)
    section.top_margin = Inches(1.0)
    section.bottom_margin = Inches(1.0)

    # Set default font and line spacing for the document
    style = document.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(12.5)
    style.paragraph_format.line_spacing = 1.15
    
    # Add header to all pages
    header = section.header
    header_para = header.paragraphs[0]
    header_para.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    
    # Add name in bold
    name_run = header_para.add_run("VIJAY CHOUDHARY")
    name_run.bold = True
    header_para.add_run("\n")
    
    # Add "Advocate & Associates" with underline
    advocate_run = header_para.add_run("Advocate & Associates")
    advocate_run.underline = True
    header_para.add_run("\n")
    
    # Add office addresses with bold labels
    delhi_run = header_para.add_run("Delhi Office")
    delhi_run.bold = True
    header_para.add_run(": - F-203 Ashish Complex Mayur Vihar Phase-1 Delhi-110091\n")
    
    jaipur_run = header_para.add_run("Jaipur Office")
    jaipur_run.bold = True
    header_para.add_run(": - Ground Floor, 114 Jai Jawan II, Tonk Road, Jaipur- 302018\n")
    
    # Add contact information with bold labels and underline for the whole line
    contact_run = header_para.add_run("(Email ID: -")
    contact_run.bold = True
    contact_run.underline = True
    email_para = header_para.add_run("vijaylawyer@gmail.com, ")
    email_para.underline = True
    tel_run = header_para.add_run("Tel")
    tel_run.bold = True
    tel_run.underline = True
    number_para = header_para.add_run(": - +91-141-3559110, Mobile: - +91-9413333747)")
    number_para.underline = True
    
    return document

def generate_document(output_path):
    """
    Generate and save the document with A4 size and header to the specified path
    
    Args:
        output_path (str): The file path where the document will be saved
    
    Returns:
        Document: The created document object
    """
    # Create the document with A4 size and header
    document = create_document_with_a4_size()
    
    # Save the document to the specified path
    document.save(output_path)
    
    print(f"Document successfully generated and saved to: {output_path}")
    return document


# Example usage:
if __name__ == "__main__":
    try:
        output_path = "output_document.docx"
        generate_document(output_path)
        print(f"Check if the file exists at: {os.path.abspath(output_path)}")
    except Exception as e:
        print(f"Error occurred: {str(e)}")
