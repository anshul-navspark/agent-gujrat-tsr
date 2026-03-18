from docx import Document
import sys

def extract_full_content(filepath):
    doc = Document(filepath)
    print("=" * 100)
    print(f"FILE: {filepath}")
    print("=" * 100)
    
    print("\n### ALL PARAGRAPHS ###\n")
    for i, para in enumerate(doc.paragraphs):
        style = para.style.name if para.style else "None"
        text = para.text
        if text.strip():
            print(f"[P{i}] (style={style}) {text}")
        else:
            print(f"[P{i}] (style={style}) [EMPTY]")
    
    print("\n\n### ALL TABLES ###\n")
    for t_idx, table in enumerate(doc.tables):
        print(f"\n--- TABLE {t_idx} ({len(table.rows)} rows x {len(table.columns)} cols) ---")
        for r_idx, row in enumerate(table.rows):
            cells = []
            for c_idx, cell in enumerate(row.cells):
                cells.append(cell.text.replace('\n', ' | '))
            print(f"  Row {r_idx}: {' ||| '.join(cells)}")
    
    print("\n\n### DOCUMENT BODY ELEMENT ORDER (paragraphs + tables interleaved) ###\n")
    from docx.oxml.ns import qn
    body = doc.element.body
    p_idx = 0
    t_idx = 0
    for child in body:
        if child.tag == qn('w:p'):
            text = child.text or ''
            # Get full text from all runs
            full_text = ''
            for r in child.iter(qn('w:t')):
                full_text += (r.text or '')
            if full_text.strip():
                print(f"[PARA] {full_text}")
            p_idx += 1
        elif child.tag == qn('w:tbl'):
            print(f"[TABLE {t_idx}]")
            t_idx += 1

    print("\n" + "=" * 100)

extract_full_content("/Users/anshulgoyal/work/gujrat_tsr_agent/Final TSR Sample/S.No. 980 - Final.docx")
print("\n\n\n")
extract_full_content("/Users/anshulgoyal/work/gujrat_tsr_agent/Final AI TSR Sample/AI_S.No. 980 - Final.docx")
