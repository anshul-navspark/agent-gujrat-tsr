import PyPDF2

def extract_text_from_pdf(pdf_path, max_chars=2000):
    """Extract text from PDF and return the first max_chars characters"""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text[:max_chars]
    except Exception as e:
        return f"Error extracting text from PDF: {str(e)}"

if __name__ == "__main__":
    pdf_path = "output/pdfs/land_record_row2_survey150_p1.pdf"
    text = extract_text_from_pdf(pdf_path)
    print(text) 