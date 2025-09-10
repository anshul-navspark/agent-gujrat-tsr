"""
TSR Agent Tools - Modular tools for Title Search Report generation
"""
from typing import Dict, List, Any, Optional
from pydantic import BaseModel
from datetime import datetime


class LandDetailsExtractionTool(BaseModel):
    name: str = "extract_land_details"
    description: str = "Extract land record details (village, taluka, district, survey, area, nature, owner)."
    
    def run(self, text: str, section_hint: Optional[str] = None) -> Dict[str, Any]:
        # Placeholder interface; to be wired to existing extractors
        from tsr_generator.extractors.land_details import extract_land_details as legacy_extract
        details = legacy_extract(text)
        return {
            "status": "success",
            "data": details,
            "confidence": 0.9,
            "extraction_method": "legacy-ai"
        }


class EntryDetailsExtractionTool(BaseModel):
    name: str = "extract_entry_details"
    description: str = "Extract mutation entries (number, date, type, description, certification)."
    
    def run(self, text: str, entry_numbers: Optional[List[str]] = None) -> Dict[str, Any]:
        from tsr_generator.extractors.entry_details import extract_entry_details as legacy_extract
        entries = legacy_extract(text)
        serialized = []
        for e in entries:
            serialized.append({
                "entry_number": getattr(e, 'entry_number', ""),
                "date": getattr(e, 'date', ""),
                "type": getattr(e, 'type', ""),
                "description": getattr(e, 'formatted_description', getattr(e, 'raw_description', "")),
                "certification": getattr(e, 'certification', ""),
            })
        return {
            "status": "success",
            "entries": serialized,
            "total_entries_found": len(serialized),
            "extraction_method": "legacy-ai"
        }


class FindingsGenerationTool(BaseModel):
    name: str = "generate_findings"
    description: str = "Generate standard TSR findings table."
    
    def run(self, land_details: Dict, entries: List[Dict], jurisdiction: Optional[str] = None) -> List[Dict[str, str]]:
        from tsr_generator.extractors.findings import generate_findings_table
        # In current system, findings are static based on text, but we can pass a synthesized text if needed
        synthesized_text = ""
        return generate_findings_table(synthesized_text)


class DocumentSectionIdentifierTool(BaseModel):
    name: str = "identify_sections"
    description: str = "Identify Land Details, Entry Details, Jantri sections (heuristic placeholder)."
    
    def run(self, text: str) -> Dict[str, Any]:
        return {"sections": {}, "document_type": "land_record", "language": "mixed"}


class DataValidationTool(BaseModel):
    name: str = "validate_extraction"
    description: str = "Validate extracted data for completeness and consistency."
    
    def run(self, land_details: Dict, entries: List[Dict]) -> Dict[str, Any]:
        missing = []
        for key in ["village_name", "taluka_name", "district_name", "survey_number"]:
            if not land_details.get(key):
                missing.append(key)
        issues = []
        return {"is_valid": len(missing) == 0, "issues": issues, "missing_fields": missing, "suggestions": []}


class TSRDocumentGeneratorTool(BaseModel):
    name: str = "generate_tsr_document"
    description: str = "Generate TSR DOCX using existing document generator."
    
    def run(self, land_details: Dict, entries: List[Dict], findings: List[Dict], output_path: str) -> Dict[str, Any]:
        # Re-hydrate entries minimally to match create_tsr_document signature
        from tsr_generator.document.tsr_document import create_tsr_document
        # The legacy create_tsr_document accepts (entries, land_details, findings, output_path)
        # It expects entries as list of Entry objects; we pass dicts and let generator handle strings
        out = create_tsr_document(entries, land_details, findings, output_path)
        return {"status": "success", "document_path": out, "pages": 0, "generation_time": datetime.now().isoformat()}


AVAILABLE_TOOLS = {
    "extract_land_details": LandDetailsExtractionTool(),
    "extract_entry_details": EntryDetailsExtractionTool(),
    "generate_findings": FindingsGenerationTool(),
    "identify_sections": DocumentSectionIdentifierTool(),
    "validate_extraction": DataValidationTool(),
    "generate_tsr_document": TSRDocumentGeneratorTool(),
}


