import docx
import sys
import os
from difflib import unified_diff

def get_docx_text(path):
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return []
    
    doc = docx.Document(path)
    text = []
    
    # Extract text from paragraphs
    for para in doc.paragraphs:
        if para.text.strip():
            text.append(para.text.strip())
            
    # Extract text from tables
    for table in doc.tables:
        for row in table.rows:
            row_text = []
            for cell in row.cells:
                if cell.text.strip():
                    row_text.append(cell.text.strip())
            if row_text:
                text.append(" | ".join(row_text))
                
    return text

def compare_docx(file1, file2):
    print(f"Comparing {file1} vs {file2}")
    
    text1 = get_docx_text(file1)
    text2 = get_docx_text(file2)
    
    print(f"File 1 lines: {len(text1)}")
    print(f"File 2 lines: {len(text2)}")
    
    diff = list(unified_diff(text1, text2, fromfile='Local', tofile='Cloud', lineterm=''))
    
    if not diff:
        print("No text differences found.")
    else:
        print("Differences found:")
        for line in diff:
            print(line)

if __name__ == "__main__":
    local_file = "TSR_Kutch_trambo_51.docx"
    cloud_file = "TSR_Cloud_Kutch_Trambo_51.docx"
    
    compare_docx(local_file, cloud_file)
