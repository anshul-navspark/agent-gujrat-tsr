"""
Unified TSR Extractor - Optimized for minimal token usage.

This module consolidates land details, entry numbers, and mutation entry extraction
into a SINGLE LLM API call, reducing token usage by ~60-70%.

Token savings achieved by:
1. Sending document text only ONCE (was sent 2-3 times)
2. Separating static prompt content (examples, rules) from dynamic content
3. Combining extraction tasks into one structured JSON response

Two-pass structured extraction (extract_all_structured):
  Pass 1: Classification + land details (lightweight)
  Pass 2: Type-aware structured field extraction (dynamic prompt)
  -> Deterministic template rendering for descriptions
"""

import os
import json
import re
import logging
import time
import traceback
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any

from dotenv import load_dotenv

# Use relative imports to avoid circular import with tsr_generator.__init__
from .entry_schema import (
    EntryType, Person, BaseEntry, EntryUnion, create_entry_from_dict,
    SaleEntry, MortgageEntry, ReleaseEntry, InheritanceEntry,
    PartitionEntry, RelinquishmentEntry, OrderEntry, CorrectionEntry, GenericEntry,
    normalize_entry_type, _build_certification_string,
)
# NOTE: pass1_prompt, pass2_prompt, template_renderer are imported lazily
# inside extract_all_structured() to avoid circular imports (pass1_prompt
# imports _normalize_date_str from this module).
from ..utils.text_utils import convert_gujarati_to_english_numerals, translate_gujarati_text
from ..utils.retry_utils import retry_with_backoff, RetryableError

# Initialize logger
logger = logging.getLogger(__name__)

# Model configuration
MODEL_NAME = os.getenv('GEMINI_MODEL_NAME', 'gemini-3.1-pro-preview')

# Feature flag: classify entries about other survey numbers as NOT RELATED
CLASSIFY_NOT_RELATED_ENTRIES = True


# =============================================================================
# STATIC PROMPT CONSTANTS - These are separated to visualize token overhead
# =============================================================================

# Entry type classification rules (~200 tokens)
ENTRY_TYPE_RULES = """
Entry Type Classification:
- LOAN: "took a loan" or "loan of Rs."
- RELEASE/LOAN CLOSE: "removing the charge" or "exemption of burden"
- SALE: "sold" and "consideration of Rs."
- INHERITANCE/DEATH: "upon the demise" or "came to be mutated in his legal heirs"
- PARTITION: "distribution took place" or "distributed his land"
- EXCHANGE: "exchanged their respective lands"
- RELINQUISHMENT: "relinquished their respective share"
- ORDER: "Taluka Circular" or "was allotted"
- LIFETIME DISTRIBUTION: "life time distribution"
- NOT RELATED: "not related to present survey"
- PROMULGATION: "re-survey" or "promulgation"
"""

# Formatting rules (~150 tokens)
FORMATTING_RULES = """
Formatting Rules:
1. ALL descriptions MUST start with "That" (except NOT RELATED, PROMULGATION)
2. DO NOT use honorifics like "Shri", "Smt", "Mr.", "Mrs."
3. DO NOT use "account holder", "mortgaged his total land", "of [village] village"
4. DO NOT include sentences like "This encumbrance entry was recorded based on..." or "This inheritance entry was made..."
5. Keep descriptions direct and factual. Include all legally relevant details. Do not add commentary or explanatory sentences.
6. Amounts: "Rs. X/-" or "Rs. X,XXX/-"
7. ALWAYS use "Survey No." instead of "Khata No." or "Account No."
8. Documents: "document no. X dated DD/MM/YYYY"
9. Translate "Paiki" or "Part" or "part" or "pk" as "p" in survey numbers (e.g. "150/p1")
10. IMPORTANT: Preserve "/" in survey numbers (e.g., "387/p3" NOT "387p3")
11. Use caste titles only when part of the name: Thakor, Patel, Kanbi, Choudhary, Rabari, Vadher, Solanki
12. Measurements: Use "Acre/Guntha" or "Hectare" in descriptions. For the total_area field, output ONLY the numeric format (e.g., "1-88-48") WITHOUT the word "Hectare".
13. Translate "bhen" or "ben" suffix as "ben" (e.g. "Shantiben")
14. Lists: "which are as follows:-" followed by names on separate lines
15. OMIT sentences like "This entry was made based on..." or "This inheritance entry was made...". Keep descriptions concise.
16. LOAN entries: Do NOT include agreement date. Only describe the loan, borrower, lender, amount, and land details.
17. OLD SURVEY NUMBERS: If there is a PROMULGATION entry (re-survey), use "old Survey No." for all entries BEFORE the promulgation entry. Use "Survey No." for entries AFTER promulgation. If there is NO promulgation entry, use "Survey No." (without "old").
18. Always use 4-digit years (DD/MM/YYYY). Never use 2-digit years (DD/MM/YY).
19. Include Khata number in parentheses after each survey number when visible in the source document, e.g., "5/2(28), 193p1(28)". If no Khata number is visible, omit parentheses.
20. Translate "Prant Officer" / "પ્રાંત અધિકારી" as "Province Officer". Use "Province Officer" and "Province court" consistently.
"""

# Certification patterns (~150 tokens)
CERTIFICATION_PATTERNS = """
CRITICAL - Translate Gujarati status words in certification:
| Gujarati | English Translation | entry_status value |
| રદ | cancelled | "rejected" |
| ના મંજૂર | not accepted | "not_accepted" |
| નામંજુર | rejected | "rejected" |
| નામંજૂર | rejected | "rejected" |
| પ્રમાણિત | certified | "certified" |

Certification output formats:
- If રદ found: "The Entry is cancelled by [Name] on DD/MM/YYYY." + entry_status: "rejected"
- If ના મંજૂર or નામંજુર found: "The Entry is not accepted by [Name] on DD/MM/YYYY." + entry_status: "not_accepted"
- If પ્રમાણિત found: "The Entry is certified by [Name] on DD/MM/YYYY." + entry_status: "certified"
- Always output certification dates in 4-digit year format (DD/MM/YYYY).
- Default if unclear: entry_status: "" (empty)

IMPORTANT: Do NOT output "certified" if the Gujarati text contains રદ, ના મંજૂર, or નામંજુર!

CERTIFICATION EXTRACTION IS REQUIRED:
- certification_official and certification_date are REQUIRED fields for all certified/rejected entries when visible in the source document.
- Always extract the certifying officer designation and place (e.g., "C.O. Jadiya", "Mamlatdar Dhanera") into certification_official.
- Always extract the certification date in DD/MM/YYYY format into certification_date.
- Do NOT output just "The Entry is certified." if officer name or date is visible in the document.
"""

# Minimal description examples - COMPACT format
DESCRIPTION_EXAMPLES = """
Example descriptions (follow these exact patterns):

LOAN (correct): "That Mer Deva Depa took a loan of Rs. 20,000/- on land bearing old Survey No. 373/p1, 359, 390, 389(215) from Bank of India, Modhvada Branch."
LOAN (wrong - includes agreement date): "That Mer Deva Depa took a loan of Rs. 20,000/- from Bank of India, Modhvada Branch based on an agreement dated 14/05/2005." - DO NOT include agreement date!
LOAN (wrong - too verbose): "That account holder Shri Mer Deva Depa of Keshav village mortgaged his total land of 6-21-20 Hectare of Keshav village, Khata No. 215, bearing Survey No. 390, with Bank of India, Modhwada branch, to obtain a loan of Rs. 20,000/-. This encumbrance entry was recorded based on the agreement dated 14/05/2005."

IMPORTANT for LOAN entries:
- DO NOT include "agreement dated" or "based on an agreement"
- DO NOT include total land area or hectare measurements in loan descriptions
- Just state: borrower name, loan amount, survey numbers, bank name and branch
- INCLUDE ALL survey numbers listed in the entry's "Other Rights" / બોજા / બીજા હક્ક column, NOT only the subject survey number. A single loan entry frequently encumbers many surveys belonging to the same khata (e.g. "421(608), 422(608), 423(608), 500(608), 501(608), 568(608), 574(715), 602(608), 603(608), 608(608), 609(608)") — output the COMPLETE list exactly as it appears in the source, in the same order, with the khata number in parentheses after each. Do NOT filter, deduplicate, or drop survey numbers just because they differ from the subject survey. The same rule applies to RELEASE / LOAN CLOSE entries that reference the same multi-survey charge.

Other patterns:
- DEATH: "That upon the demise of [Name], his share in land bearing old Survey No. X(Khata), Y(Khata) came to be mutated in the names of his legal heirs which are as follows:
[Heir1Name]
[Heir2Name]"
- SALE: "That [Seller] sold Survey No. X to [Buyer] for Rs. X/- vide document no. Y dated DD/MM/YYYY."
- PARTITION: "That Family members distributed their land among themselves as follows:-"
- RELEASE: "That upon receiving an application from [Name] for removing the charge of [Bank], [Branch]. The said exemption of burden has been recorded. Entry No. X."
- ORDER (government allotment): "That Government survey was conducted and land bearing Survey No. X was allotted to [Name]."
- ORDER (circular): "That as per Taluka Circular No. X dated Y, Survey No. Z allotted to [Name]."
- ORDER (error correction): Include ALL survey numbers and corrections listed in the order exactly as they appear in the source. Do NOT filter or omit corrections for other survey numbers. Example: "Vide order was passed by the Mamlatdar, Abdasa, vide No. E-Dhara/Record Promulgation/Error Correction/08 dated 30/09/2008, in land bearing Survey No. 26, remove entry 56 and add 165."
- NOT RELATED: "This Entry is not related to Present Survey Number."
- PROMULGATION: Extract the FULL procedural text. Include: issuing authority, court name, all order numbers with dates, public notice and objection period, Mamlatdar preparation, Province Office verification, finalization, page/survey range. Do NOT summarize.
"""


# =============================================================================
# UNIFIED EXTRACTION PROMPT - Single prompt for all extraction tasks
# =============================================================================

def build_unified_prompt(pdf_text: str, entry_numbers_hint: List[str] = None) -> str:
    """
    Build the unified extraction prompt.

    This is a SINGLE prompt that extracts:
    1. Land details (village, taluka, district, survey_number, area, nature, owner)
    2. Entry numbers from the Entry Details table
    3. Full mutation entry details with descriptions

    Args:
        pdf_text: The document text (sent only ONCE)
        entry_numbers_hint: Optional pre-detected entry numbers

    Returns:
        The complete prompt string
    """
    entry_hint_text = ""
    if entry_numbers_hint:
        entry_hint_text = f"\nCandidate entry numbers detected: {', '.join(entry_numbers_hint)}"

    not_related_instruction = ""
    if CLASSIFY_NOT_RELATED_ENTRIES:
        not_related_instruction = """
NOT RELATED ENTRIES: If an entry clearly pertains to survey numbers different from the subject survey number being investigated, classify it as NOT RELATED with description: "This Entry is not related to Present Survey Number."
"""

    return f"""Extract ALL information from this Gujarat land record in ONE response.

OUTPUT FORMAT - Return ONLY valid JSON with this exact structure:
{{
  "land_details": {{
    "village_name": "",
    "taluka_name": "",
    "district_name": "",
    "survey_number": "",
    "old_survey_number": "",
    "total_area": "",
    "nature_of_land": "",
    "owner": ""
  }},
  "entry_numbers": [],
  "mutation_entries": [
    {{
      "entry_number": "",
      "date": "",
      "type": "",
      "description": "",
      "entry_status": "",
      "certification_status": "",
      "certification_official": "",
      "certification_date": ""
    }}
  ]
}}

EXTRACTION INSTRUCTIONS:

1. LAND DETAILS: Extract from the "Land Details" section. Translate ALL Gujarati to English.
   - For "nature_of_land", include BOTH tenure (Old/New) and use (Agricultural/Non-Agri), separated by comma.
   - For "survey_number", translate "Paiki" or "Part" or "part" to "p"(e.g. "150/p1").
   - For "old_survey_number", look for re-survey promulgation entries (Entry 3888-type) that map old→new survey numbers.
     Extract the old survey number. If found, format as just the number (e.g. "258" not "Old Survey No. 258").

2. ENTRY NUMBERS: Extract from "Entry Details" table. Output as array of number strings.
   - Remove asterisks (*) and trailing Gujarati text
   - Only include actual entry numbers, NOT khata/survey/form numbers
{entry_hint_text}

3. MUTATION ENTRIES: For each entry number, extract:
   - entry_number: The numeric entry number
   - date: Format as DD/MM/YYYY (4-digit year) if available, else ""
   - type: One of: LOAN, DEATH, RELEASE, LOAN CLOSE, SALE, PARTITION, PERSONS ADD, TO TRANSFER, EXCHANGE, LIFETIME DISTRIBUTION, NOT RELATED, ORDER, RELINQUISHMENT, PROMULGATION
   - description: MUST BE IN ENGLISH. Translate all Gujarati.
   - entry_status: One of: "certified", "rejected", "not_accepted". Look for Gujarati keywords નામંજૂર (rejected), રદ (cancelled). Default to "certified" if the entry says "certified" or "The Entry is certified".
   - certification_status: MUST be one of: "certified", "rejected", "not_accepted", or "" if unclear
   - certification_official: The official's POST/DESIGNATION and PLACE (e.g., "C.O. Porbandar", "Deputy Mamlatdar Super, Porbandar"). Abbreviate "Circle Officer" as "C.O.". Do NOT include personal names.
     
      IMPORTANT: All three certification fields MUST be extracted if available in the document.
      The certification text is very often located in the "Remarks of the Inspecting Officer" (written in gujrati)
      column of the chain of title / Entry Details table. You MUST carefully read and translate
      the content of this "Remarks of the Inspecting Officer" column (including Gujarati text)
      to determine certification_status, certification_official, and certification_date for each
      entry. Do NOT ignore this column.
      Examples of what to extract:
      - certification_status: "certified", certification_official: "C.O. Porbandar", certification_date: "21/06/2005"
      - certification_status: "rejected", certification_official: "Deputy Mamlatdar Super, Porbandar", certification_date: "19/03/2007"

{ENTRY_TYPE_RULES}
{FORMATTING_RULES}
{DESCRIPTION_EXAMPLES}
{CERTIFICATION_PATTERNS}
{not_related_instruction}
For entries with only a number in the table (no details), include with empty fields:
{{"entry_number": "X", "date": "", "type": "", "description": "", "entry_status": "", "certification_status": "", "certification_official": "", "certification_date": ""}}

IMPORTANT: For entries where content is not legible/available, set description to:
"Entry mentioned in the document but content is not legible."

DOCUMENT TEXT:
{pdf_text}

Return ONLY the JSON object, no explanations."""


# =============================================================================
# MAIN EXTRACTION FUNCTION
# =============================================================================

class UnifiedExtractionResult:
    """Result container for unified extraction."""

    def __init__(self):
        self.land_details: Dict[str, str] = {}
        self.entry_numbers: List[str] = []
        self.mutation_entries: List[Dict] = []
        self.raw_response: str = ""
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.success: bool = False
        self.error: Optional[str] = None


def extract_all_unified(pdf_text: str) -> UnifiedExtractionResult:
    """
    Extract all TSR data in a SINGLE LLM API call.

    This replaces the previous 2-3 separate calls:
    - extract_entry_table()
    - extract_land_records_ai()
    - extract_entry_details_ai()

    Args:
        pdf_text: The full PDF document text

    Returns:
        UnifiedExtractionResult containing all extracted data
    """
    result = UnifiedExtractionResult()

    try:
        # Pre-detect entry numbers using regex (zero-cost, helps LLM accuracy)
        entry_numbers_hint = _identify_entry_numbers_fast(pdf_text)

        # Extract relevant section to minimize tokens sent
        # (Land details are in first 3000 chars, entries are in middle section)
        document_text = _extract_relevant_sections(pdf_text)

        # Build the unified prompt
        prompt = build_unified_prompt(document_text, entry_numbers_hint)

        # Estimate input tokens (rough: 1 token ≈ 4 chars)
        result.input_tokens = len(prompt) // 4
        logger.debug(f"Unified extraction: ~{result.input_tokens} input tokens")

        # Initialize LLM
        load_dotenv()
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(
            model=MODEL_NAME,
            google_api_key=os.getenv('GEMINI_API_KEY', ''),
            temperature=0.0,
            convert_system_message_to_human=True,
        )

        # Make the SINGLE API call with retry
        response = _invoke_with_retry(llm, prompt, max_retries=3)

        # Parse the response
        content = response.content if hasattr(response, 'content') else str(response)
        result.raw_response = content
        result.output_tokens = len(content) // 4

        # Extract JSON from response
        parsed_data = _parse_json_response(content)

        if parsed_data:
            # Extract land details
            result.land_details = parsed_data.get('land_details', {})
            _normalize_land_details(result.land_details)

            # Extract entry numbers
            result.entry_numbers = parsed_data.get('entry_numbers', [])
            if isinstance(result.entry_numbers, list):
                result.entry_numbers = [str(n) for n in result.entry_numbers]

            # Extract mutation entries
            result.mutation_entries = parsed_data.get('mutation_entries', [])
            _normalize_mutation_entries(result.mutation_entries)

            # Trim multi-survey listings in entry descriptions down to the
            # subject survey. Safe by construction — falls back to original
            # text if filtering would produce nothing meaningful.
            try:
                subject_survey = (result.land_details or {}).get("survey_number", "")
                # land_details may hold a comma-joined string; use the first one
                if subject_survey and "," in subject_survey:
                    subject_survey = subject_survey.split(",")[0].strip()
                aliases = _compute_survey_aliases(subject_survey, pdf_text)
                if aliases:
                    trimmed = 0
                    for ed in result.mutation_entries:
                        for key in ("description", "formatted_description", "raw_description"):
                            desc = ed.get(key, "") if isinstance(ed, dict) else ""
                            if not desc:
                                continue
                            new_desc = _filter_description_to_subject_survey(desc, aliases)
                            if new_desc != desc:
                                ed[key] = new_desc
                                trimmed += 1
                    if trimmed:
                        logger.info(
                            "Survey filter: trimmed %d field(s) to subject survey %s",
                            trimmed, subject_survey,
                        )
            except Exception as e:
                logger.warning("Survey filter skipped due to error: %s", e)

            # Ensure all pre-detected entry numbers are included
            # NO: Do not force include hints as they might be years/survey numbers (false positives)
            # _ensure_all_entries_included(result, entry_numbers_hint)

            result.success = True
            logger.info(f"Unified extraction successful: {len(result.entry_numbers)} entries, ~{result.input_tokens + result.output_tokens} total tokens")
        else:
            result.error = "Failed to parse JSON response"
            logger.warning("Unified extraction: JSON parsing failed")

    except Exception as e:
        result.error = str(e)
        logger.error(f"Unified extraction error: {e}")
        logger.error(traceback.format_exc())

    return result


def _normalize_date_str(date_str: str) -> str:
    """
    Normalize common date formats to DD/MM/YYYY.
    Accepts DD/MM/YY or DD/MM/YYYY (or with '-') and expands to 4-digit year.
    Heuristic: 00-30 -> 2000-2030, 31-99 -> 1931-1999.
    """
    if not date_str:
        return ""

    s = str(date_str).strip()
    m = re.fullmatch(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2}|\d{4})', s)
    if not m:
        return s

    dd, mm, yy = m.group(1), m.group(2), m.group(3)
    dd = dd.zfill(2)
    mm = mm.zfill(2)

    # Expand 2-digit year to 4-digit
    if len(yy) == 2:
        yy_int = int(yy)
        if yy_int <= 30:
            yy = f"20{yy}"
        else:
            yy = f"19{yy}"

    return f"{dd}/{mm}/{yy}"


def _normalize_mutation_entries(mutation_entries: Any) -> None:
    """In-place normalization for extracted mutation entry dictionaries."""
    if not isinstance(mutation_entries, list):
        return

    for e in mutation_entries:
        if not isinstance(e, dict):
            continue
        if 'date' in e:
            e['date'] = _normalize_date_str(e.get('date', ''))
        if 'certification_date' in e:
            e['certification_date'] = _normalize_date_str(e.get('certification_date', ''))


def _invoke_with_retry(llm, prompt: str, max_retries: int = 3):
    """Invoke LLM with retry logic for rate limits."""
    import time
    retry_delay = 5

    for attempt in range(max_retries):
        try:
            return llm.invoke(prompt)
        except Exception as e:
            is_rate_limit = any(term in str(e).lower() for term in ['429', 'resource', 'quota', 'rate limit'])
            if is_rate_limit and attempt < max_retries - 1:
                logger.warning(f"Rate limit hit. Sleeping {retry_delay}s (attempt {attempt+1}/{max_retries})")
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            raise


def _identify_entry_numbers_fast(pdf_text: str) -> List[str]:
    """
    Fast regex-based entry number detection (no LLM call).
    Used as a hint to improve extraction accuracy.
    """
    entry_numbers = set()

    # Find the Entry Details section
    entry_start = re.search(r'Entry Details', pdf_text, re.IGNORECASE)
    entry_end = re.search(r'Jantri Detail', pdf_text, re.IGNORECASE)

    if entry_start:
        start_pos = entry_start.start()
        end_pos = entry_end.start() if entry_end and entry_end.start() > start_pos else len(pdf_text)
        section = pdf_text[start_pos:end_pos]

        # Pattern: standalone 3-4 digit numbers (typical entry numbers)
        for match in re.finditer(r'(?:^|\n|\s)(\d{3,4})\*?(?:\s|$|\n)', section):
            num = match.group(1)
            # Filter out obvious non-entries
            context = section[max(0, match.start()-30):min(len(section), match.end()+30)].lower()
            if not any(kw in context for kw in ['khata', 'survey', 'form', 'vf', 'page', 'sr']):
                # Filter out years (1900-2099) unless we are very sure
                try:
                    val = int(num)
                    if not (1900 <= val <= 2099):
                        entry_numbers.add(num)
                except ValueError:
                    # Should not happen due to regex \d+
                    pass

        # Pattern: "Entry No. X" explicit mentions
        for match in re.finditer(r'Entry\s+(?:No\.?|Number)\s*[:#]?\s*(\d{1,4})', section, re.IGNORECASE):
            entry_numbers.add(match.group(1))

    return sorted(list(entry_numbers), key=lambda x: int(x) if x.isdigit() else float('inf'))


def _extract_relevant_sections(pdf_text: str) -> str:
    """
    Extract only the relevant portions of the PDF to minimize tokens.

    Strategy:
    - Land details are in the first ~3000 chars
    - Entry details are in the middle section
    - We skip footer/repeated content
    """
    # If text is reasonably sized, use it all
    if len(pdf_text) <= 15000:
        return pdf_text

    # For larger documents, extract key sections
    sections = []

    # Always include first 3500 chars (land details header)
    sections.append(pdf_text[:3500])

    # Find and include Entry Details section
    entry_start = re.search(r'Entry Details', pdf_text, re.IGNORECASE)
    if entry_start:
        # Find end marker
        entry_end = re.search(r'Jantri Detail', pdf_text[entry_start.start():], re.IGNORECASE)
        if entry_end:
            end_pos = entry_start.start() + entry_end.start() + 500
        else:
            end_pos = min(entry_start.start() + 12000, len(pdf_text))

        entry_section = pdf_text[entry_start.start():end_pos]
        if entry_section not in sections[0]:
            sections.append(entry_section)

    return '\n\n[...]\n\n'.join(sections)


def _parse_json_response(content) -> Optional[Dict]:
    """Parse JSON from LLM response with multiple strategies."""
    # Handle case where content is already a dict (new API response format)
    if isinstance(content, dict):
        logger.debug("Response is already a dict, returning directly")
        return content
    
    # Handle list responses (some models return content as list of parts)
    if isinstance(content, list):
        logger.debug(f"Response is a list with {len(content)} items")
        # Try to find the text content and concatenate it properly
        content_str = ""
        for item in content:
            if isinstance(item, str):
                content_str += item
            elif isinstance(item, dict) and 'text' in item:
                content_str += item['text']
        
        if content_str:
            content = content_str
        else:
            content = str(content)
    
    # Convert to string if needed
    if not isinstance(content, str):
        logger.debug(f"Converting response type {type(content).__name__} to string")
        content = str(content)
    
    logger.debug(f"Parsing JSON from response (length: {len(content)}, first 200 chars: {content[:200]}...)")
    
    # Clean control characters
    content = ''.join(ch for ch in content if ch == '\t' or ch == '\n' or ch == '\r' or ord(ch) >= 32)

    # Strategy 1: Look for JSON in code block (with or without "json" label)
    json_code_match = re.search(r'```(?:json)?\s*(\{[\s\S]*\})\s*```', content, re.IGNORECASE)
    if json_code_match:
        try:
            json_str = json_code_match.group(1)
            json_str = re.sub(r',\s*([\]\}])', r'\1', json_str)
            result = json.loads(json_str)
            logger.debug("Successfully parsed JSON from code block")
            return result
        except json.JSONDecodeError as e:
            logger.debug(f"Failed to parse JSON from code block: {e}")

    # Strategy 2: Find JSON object containing our expected keys (flexible order)
    json_match = re.search(r'\{[\s\S]*?(\"land_details\"|\"entry_numbers\"|\"mutation_entries\")[\s\S]*\}', content)
    if json_match:
        # Find the full extent of this JSON object
        start = json_match.start()
        # Count braces to find the matching end
        brace_count = 0
        end = start
        for i, ch in enumerate(content[start:]):
            if ch == '{':
                brace_count += 1
            elif ch == '}':
                brace_count -= 1
                if brace_count == 0:
                    end = start + i + 1
                    break
        
        if end > start:
            try:
                json_str = content[start:end]
                json_str = re.sub(r',\s*([\]\}])', r'\1', json_str)
                result = json.loads(json_str)
                logger.debug("Successfully parsed JSON using brace matching")
                return result
            except json.JSONDecodeError as e:
                logger.debug(f"Failed to parse JSON with brace matching: {e}")

    # Strategy 3: Try the whole content as JSON
    try:
        result = json.loads(content)
        logger.debug("Successfully parsed whole content as JSON")
        return result
    except json.JSONDecodeError as e:
        logger.debug(f"Failed to parse whole content as JSON: {e}")

    # Strategy 4: Try to extract just the JSON object part (strip any surrounding text)
    try:
        first_brace = content.find('{')
        last_brace = content.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            json_str = content[first_brace:last_brace + 1]
            json_str = re.sub(r',\s*([\]\}])', r'\1', json_str)
            result = json.loads(json_str)
            logger.debug("Successfully parsed JSON using first/last brace extraction")
            return result
    except json.JSONDecodeError as e:
        logger.debug(f"Failed to parse JSON with first/last brace: {e}")
    
    logger.warning(f"All JSON parsing strategies failed. Response content: {content[:500]}...")
    return None


def _normalize_land_details(land_details: Dict[str, str]):
    """Normalize and clean land details."""
    required_fields = [
        'village_name', 'taluka_name', 'district_name',
        'survey_number', 'total_area', 'nature_of_land', 'owner'
    ]

    for field in required_fields:
        if field not in land_details or not land_details[field]:
            land_details[field] = 'Not Available'
        else:
            # Convert Gujarati numerals and translate text
            land_details[field] = convert_gujarati_to_english_numerals(str(land_details[field]))
            land_details[field] = translate_gujarati_text(land_details[field])

    # Add old_survey_number if not present
    if 'old_survey_number' not in land_details:
        land_details['old_survey_number'] = 'Not Available'


# =============================================================================
# TWO-PASS STRUCTURED EXTRACTION
# =============================================================================


class StructuredExtractionResult:
    """Result container for two-pass structured extraction."""

    def __init__(self):
        self.land_details: Dict[str, Any] = {}
        self.entry_numbers: List[str] = []
        self.entries: List[EntryUnion] = []
        self.mutation_entries: List[Dict] = []  # raw dicts for backward compat
        self.pass1_time_ms: int = 0
        self.pass2_time_ms: int = 0
        self.success: bool = False
        self.error: Optional[str] = None


def _format_amount(amount_str: str) -> str:
    """Ensure Indian comma formatting for amount strings (e.g. '250000' -> '2,50,000')."""
    if not amount_str:
        return ""
    # Strip existing formatting
    digits = amount_str.replace(",", "").replace(" ", "").strip()
    if not digits.isdigit():
        return amount_str  # non-numeric, return as-is
    # Indian comma formatting: last 3 digits, then groups of 2
    if len(digits) <= 3:
        return digits
    result = digits[-3:]
    remaining = digits[:-3]
    while remaining:
        result = remaining[-2:] + "," + result
        remaining = remaining[:-2]
    return result


def _merge_pass2_into_entries(
    pass1_entries: List[Dict],
    pass2_fields: List[Dict],
) -> List[Dict]:
    """
    Merge Pass 2 structured fields into Pass 1 entry dicts.

    Returns a list of dicts ready for create_entry_from_dict(), each with:
    - Pass 1 metadata (entry_number, date, type, certification_*)
    - Pass 2 type-specific fields
    - 'description' generated by template_renderer
    """
    # Index Pass 2 results by entry_number
    p2_by_num: Dict[str, Dict] = {}
    for fields in pass2_fields:
        num = str(fields.get("entry_number", "")).strip()
        if num:
            p2_by_num[num] = fields

    merged: List[Dict] = []
    for p1 in pass1_entries:
        entry_num = str(p1.get("entry_number", "")).strip()
        entry_type = p1.get("type", "").upper()

        # Start with Pass 1 metadata
        entry_dict: Dict[str, Any] = {
            "entry_number": entry_num,
            "date": p1.get("date", ""),
            "type": entry_type,
            "certification_status": p1.get("certification_status", ""),
            "certification_official": p1.get("certification_official", ""),
            "certification_date": p1.get("certification_date", ""),
            "entry_status": p1.get("entry_status", "") or p1.get("certification_status", ""),
        }

        # Merge Pass 2 fields (if available)
        p2 = p2_by_num.get(entry_num, {})
        for k, v in p2.items():
            if k not in ("entry_number", "type"):
                entry_dict[k] = v

        # Post-process amount fields
        for amount_key in ("consideration_amount", "amount"):
            if amount_key in entry_dict and entry_dict[amount_key]:
                entry_dict[amount_key] = _format_amount(str(entry_dict[amount_key]))

        # Post-process date fields
        for date_key in ("date", "certification_date", "document_date",
                         "order_date", "award_date", "effective_date"):
            if date_key in entry_dict and entry_dict[date_key]:
                entry_dict[date_key] = _normalize_date_str(str(entry_dict[date_key]))

        # Render description from template (lazy import)
        from .template_renderer import render_entry_description
        description = render_entry_description(entry_type, entry_dict)
        entry_dict["description"] = description

        # Build certification string
        if not entry_dict.get("certification"):
            entry_dict["certification"] = _build_certification_string(entry_dict)

        merged.append(entry_dict)

    return merged


def _convert_land_details_for_compat(pass1_land: Dict) -> Dict[str, str]:
    """
    Convert Pass 1 land_details (with lists) to the flat format expected
    by the rest of the pipeline (single string values).
    """
    compat: Dict[str, str] = {}

    # Direct string copies
    for key in ("village_name", "taluka_name", "district_name",
                "total_area", "nature_of_land"):
        val = pass1_land.get(key, "")
        compat[key] = convert_gujarati_to_english_numerals(str(val)) if val else "Not Available"

    # survey_numbers list -> comma-joined string (convert Gujarati numerals per item)
    sns = pass1_land.get("survey_numbers", [])
    if isinstance(sns, list) and sns:
        compat["survey_number"] = ", ".join(convert_gujarati_to_english_numerals(str(s)) for s in sns)
    else:
        compat["survey_number"] = convert_gujarati_to_english_numerals(str(sns)) if sns else "Not Available"

    # old_survey_numbers list -> comma-joined string
    old_sns = pass1_land.get("old_survey_numbers", [])
    if isinstance(old_sns, list) and old_sns:
        compat["old_survey_number"] = ", ".join(convert_gujarati_to_english_numerals(str(s)) for s in old_sns)
    else:
        compat["old_survey_number"] = convert_gujarati_to_english_numerals(str(old_sns)) if old_sns else "Not Available"

    # owners list -> comma-joined string (no numeral conversion needed for names)
    owners = pass1_land.get("owners", [])
    if isinstance(owners, list) and owners:
        compat["owner"] = ", ".join(str(o) for o in owners)
    else:
        compat["owner"] = str(owners) if owners else "Not Available"

    # Preserve survey_number_mapping for downstream use
    mapping = pass1_land.get("survey_number_mapping", {})
    if mapping:
        compat["survey_number_mapping"] = str(mapping)

    # Apply text translation
    for key in ("village_name", "taluka_name", "district_name"):
        if compat.get(key) and compat[key] != "Not Available":
            compat[key] = translate_gujarati_text(compat[key])

    return compat


def _compute_survey_aliases(subject_survey: str, pdf_text: str) -> set:
    """
    Build a match set for the subject survey, including parent and
    parenthetical resurvey aliases actually observed in the PDF.

    E.g. subject "569/p2" in a PDF containing "569/p2(922)" and "569(320)"
    yields {"569/p2", "569", "569p2", "569/p2(922)", "569(320)", "922", "320"}.
    """
    aliases: set = set()
    if not subject_survey:
        return aliases
    s = subject_survey.strip()
    aliases.add(s)
    aliases.add(s.replace(" ", ""))
    aliases.add(s.replace("/", ""))
    # Parent survey (strip "/pN" subdivision suffix)
    parent = re.sub(r"/p\d+$", "", s, flags=re.IGNORECASE)
    if parent and parent != s:
        aliases.add(parent)
    # Parenthetical resurvey aliases from the PDF text, e.g. "569/p2(922)"
    for alias in list(aliases):
        for m in re.finditer(re.escape(alias) + r"\((\d+)\)", pdf_text):
            aliases.add(m.group(0))
            aliases.add(m.group(1))
    return {a for a in aliases if a}


def _filter_description_to_subject_survey(description: str, aliases: set) -> str:
    """
    Trim multi-survey listings in an entry description down to fragments that
    reference the subject survey (per the alias match set).

    Safety valve: if filtering would leave the description empty or materially
    shorter than a sentence, return the original text unchanged. This means
    the filter can only trim verbose entries, never silently drop information.
    """
    if not description or not aliases:
        return description

    original = description

    # --- Strategy 1: comma-separated "Survey No. A, B, C ..." list ---
    # Match a "Survey No(s)." header followed by a comma-list of >=3 tokens
    # (tokens can include parenthesised resurvey numbers like "569/p2(922)").
    list_header_re = re.compile(
        r"(Survey\s+Nos?\.\s*)"
        r"((?:[^\s,()]+(?:\([^)]*\))?)(?:\s*,\s*[^\s,()]+(?:\([^)]*\))?){2,})"
    )

    def _token_base(tok: str) -> str:
        # Strip a trailing "(...)" resurvey qualifier to get the base survey id.
        return re.sub(r"\([^)]*\)$", "", tok).strip()

    def _token_matches(tok: str) -> bool:
        base = _token_base(tok)
        # Exact match only — substring matching would let parent "569" match
        # sibling subdivisions like "569/p1".
        return base in aliases or tok in aliases

    def _keep_in_list(match: "re.Match") -> str:
        header = match.group(1)
        list_part = match.group(2)
        tokens = [t.strip() for t in list_part.split(",")]
        kept = [t for t in tokens if _token_matches(t)]
        if not kept:
            return match.group(0)  # fallback: leave untouched
        return header + ", ".join(kept)

    description = list_header_re.sub(_keep_in_list, description)

    # --- Strategy 2: repeated "Survey No. X old area ... new area ..." rows ---
    row_re = re.compile(
        r"Survey\s+No\.\s*(\S+?)\s+old\s+area\s+[\d.\-]+\s+new\s+area\s+[\d.\-]+\.?",
        re.IGNORECASE,
    )
    rows = list(row_re.finditer(description))
    if len(rows) > 1:
        kept_rows = [
            m.group(0) for m in rows
            if _token_matches(m.group(1))
        ]
        if kept_rows:
            start = rows[0].start()
            end = rows[-1].end()
            description = description[:start] + " ".join(kept_rows) + description[end:]

    # Safety valve — never return something truncated into meaninglessness.
    if len(description.strip()) < 20:
        return original
    return description


def extract_all_structured(pdf_text: str) -> StructuredExtractionResult:
    """
    Two-pass structured extraction pipeline.

    Pass 1: Classify entries + extract land details (lightweight)
    Pass 2: Extract type-specific fields (dynamic prompt per document)
    Then: Deterministic template rendering for descriptions

    Args:
        pdf_text: Full text extracted from the PDF.

    Returns:
        StructuredExtractionResult with typed entry objects and land details.
    """
    result = StructuredExtractionResult()

    try:
        # Pre-detect entry numbers (regex, zero cost)
        entry_numbers_hint = _identify_entry_numbers_fast(pdf_text)

        # Lazy imports to avoid circular dependencies
        from .pass1_prompt import build_pass1_prompt, parse_pass1_response
        from .pass2_prompt import build_pass2_prompt, parse_pass2_response

        # Prepare document text
        document_text = _extract_relevant_sections(pdf_text)

        # Initialize LLM
        load_dotenv()
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(
            model=MODEL_NAME,
            google_api_key=os.getenv('GEMINI_API_KEY', ''),
            temperature=0.0,
            convert_system_message_to_human=True,
        )

        # ---- Pass 1: Classification + Land Details ----
        logger.info("Pass 1: classifying entries and extracting land details")
        t0 = time.monotonic()

        pass1_prompt = build_pass1_prompt(document_text, entry_numbers_hint)
        logger.debug("Pass 1 prompt length: %d chars", len(pass1_prompt))

        pass1_response = _invoke_with_retry(llm, pass1_prompt, max_retries=3)
        pass1_content = pass1_response.content if hasattr(pass1_response, 'content') else str(pass1_response)
        logger.debug("Pass 1 raw response length: %d chars", len(pass1_content))

        pass1_data = parse_pass1_response(pass1_content)
        result.pass1_time_ms = int((time.monotonic() - t0) * 1000)

        classified_entries = pass1_data.get("entries", [])
        pass1_land = pass1_data.get("land_details", {})

        # Log type distribution
        type_counts: Dict[str, int] = {}
        for e in classified_entries:
            t = e.get("type", "UNKNOWN")
            type_counts[t] = type_counts.get(t, 0) + 1
        logger.info(
            "Pass 1 complete: %d entries found, types: %s (%.0fms)",
            len(classified_entries), type_counts, result.pass1_time_ms,
        )

        # Extract entry numbers
        result.entry_numbers = [
            str(e.get("entry_number", ""))
            for e in classified_entries
            if e.get("entry_number")
        ]

        # Convert land details to compat format
        result.land_details = _convert_land_details_for_compat(pass1_land)

        # ---- Pass 2: Structured Field Extraction ----
        t1 = time.monotonic()
        pass2_prompt = build_pass2_prompt(document_text, classified_entries)

        pass2_fields: List[Dict] = []
        if pass2_prompt is not None:
            logger.info("Pass 2: extracting structured fields")
            logger.debug("Pass 2 prompt length: %d chars", len(pass2_prompt))

            pass2_response = _invoke_with_retry(llm, pass2_prompt, max_retries=3)
            pass2_content = pass2_response.content if hasattr(pass2_response, 'content') else str(pass2_response)
            logger.debug("Pass 2 raw response length: %d chars", len(pass2_content))

            pass2_fields = parse_pass2_response(pass2_content)
            logger.info("Pass 2 complete: %d entries extracted", len(pass2_fields))

            # Log missing fields per entry
            for pf in pass2_fields:
                missing = [k for k, v in pf.items()
                           if v is None or v == "" or v == []]
                if missing:
                    logger.warning(
                        "Pass 2: Entry %s missing fields: %s",
                        pf.get("entry_number", "?"), missing,
                    )
        else:
            logger.info("Pass 2: skipped (all entries are fixed-text types)")

        result.pass2_time_ms = int((time.monotonic() - t1) * 1000)

        # ---- Merge & Render ----
        merged_dicts = _merge_pass2_into_entries(classified_entries, pass2_fields)

        # Trim multi-survey listings in descriptions down to the subject survey.
        # Runs after merge so it operates on the final rendered description.
        # Safe by construction: falls back to original text if no match.
        try:
            subject_survey = ""
            sns = pass1_land.get("survey_numbers") if isinstance(pass1_land, dict) else None
            if sns:
                subject_survey = str(sns[0])
            aliases = _compute_survey_aliases(subject_survey, pdf_text)
            if aliases:
                trimmed = 0
                for ed in merged_dicts:
                    desc = ed.get("description", "")
                    if not desc:
                        continue
                    new_desc = _filter_description_to_subject_survey(desc, aliases)
                    if new_desc != desc:
                        ed["description"] = new_desc
                        trimmed += 1
                if trimmed:
                    logger.info(
                        "Survey filter: trimmed %d/%d entry descriptions to subject survey %s",
                        trimmed, len(merged_dicts), subject_survey,
                    )
        except Exception as e:
            logger.warning("Survey filter skipped due to error: %s", e)

        result.mutation_entries = merged_dicts  # raw dicts for backward compat

        # Create typed entry objects
        entries: List[EntryUnion] = []
        incomplete_count = 0
        for entry_dict in merged_dicts:
            entry_obj = create_entry_from_dict(entry_dict)
            desc = entry_dict.get("description", "")
            logger.debug(
                "Render: Entry %s (%s) -> %d chars",
                entry_obj.entry_number,
                entry_dict.get("type", "?"),
                len(desc),
            )
            if not desc:
                incomplete_count += 1
            entries.append(entry_obj)

        result.entries = entries
        result.success = True

        # Summary log
        logger.info(
            "Extraction complete: %d entries, Pass 1: %dms, Pass 2: %dms, "
            "Types: %s, Incomplete: %d",
            len(entries), result.pass1_time_ms, result.pass2_time_ms,
            type_counts, incomplete_count,
        )

    except Exception as e:
        result.error = str(e)
        logger.error("Structured extraction error: %s", e)
        logger.error(traceback.format_exc())

    return result


# =============================================================================
# COMPATIBILITY FUNCTIONS - Drop-in replacements for existing code
# =============================================================================

def extract_land_details_optimized(pdf_text: str) -> Dict[str, str]:
    """
    Drop-in replacement for extract_land_details().
    Uses unified extraction under the hood.
    """
    # Check if we have cached result from unified extraction
    if hasattr(extract_land_details_optimized, '_last_result'):
        cached = extract_land_details_optimized._last_result
        if cached.get('_pdf_hash') == hash(pdf_text[:1000]):
            return cached.get('land_details', {})

    # Run unified extraction
    result = extract_all_unified(pdf_text)

    # Cache for potential reuse
    extract_land_details_optimized._last_result = {
        '_pdf_hash': hash(pdf_text[:1000]),
        'land_details': result.land_details,
        'entry_numbers': result.entry_numbers,
        'mutation_entries': result.mutation_entries
    }

    if result.success:
        return result.land_details
    else:
        # Fallback to defaults
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


def extract_entry_table_optimized(pdf_text: str) -> List[int]:
    """
    Drop-in replacement for extract_entry_table().
    Uses unified extraction under the hood.
    """
    # Check cache
    if hasattr(extract_land_details_optimized, '_last_result'):
        cached = extract_land_details_optimized._last_result
        if cached.get('_pdf_hash') == hash(pdf_text[:1000]):
            entries = cached.get('entry_numbers', [])
            return sorted([int(n) for n in entries if n.isdigit()])

    # Run unified extraction
    result = extract_all_unified(pdf_text)

    # Cache result
    extract_land_details_optimized._last_result = {
        '_pdf_hash': hash(pdf_text[:1000]),
        'land_details': result.land_details,
        'entry_numbers': result.entry_numbers,
        'mutation_entries': result.mutation_entries
    }

    if result.success:
        return sorted([int(n) for n in result.entry_numbers if n.isdigit()])
    return []


def extract_entry_details_optimized(pdf_text: str) -> List[EntryUnion]:
    """
    Drop-in replacement for extract_entry_details().
    Uses unified extraction under the hood.
    """
    from .entry_details import process_entry_details

    # Check cache
    if hasattr(extract_land_details_optimized, '_last_result'):
        cached = extract_land_details_optimized._last_result
        if cached.get('_pdf_hash') == hash(pdf_text[:1000]):
            raw_entries = cached.get('mutation_entries', [])
            if raw_entries:
                processed = process_entry_details(raw_entries)
                # Filter empty entries
                return [e for e in processed if getattr(e, 'formatted_description', '').strip()]

    # Run unified extraction
    result = extract_all_unified(pdf_text)

    # Cache result
    extract_land_details_optimized._last_result = {
        '_pdf_hash': hash(pdf_text[:1000]),
        'land_details': result.land_details,
        'entry_numbers': result.entry_numbers,
        'mutation_entries': result.mutation_entries
    }

    if result.success and result.mutation_entries:
        processed = process_entry_details(result.mutation_entries)
        return [e for e in processed if getattr(e, 'formatted_description', '').strip()]

    # Fallback - return default entry
    return [BaseEntry(
        entry_number="1",
        date=datetime.now().strftime('%d/%m/%Y'),
        type=EntryType.UNKNOWN,
        raw_description="This land record document contains information about land ownership.",
        formatted_description="This land record document contains information about land ownership.",
        certification="The Entry is certified but date is not legible."
    )]


# =============================================================================
# TOKEN COUNTING UTILITY
# =============================================================================

def estimate_token_savings(pdf_text: str) -> Dict[str, Any]:
    """
    Estimate token savings from using unified extraction.

    Returns comparison of old vs new approach.
    """
    # Rough token estimation (1 token ≈ 4 chars)
    doc_tokens = len(pdf_text) // 4

    # Old approach tokens:
    # 1. extract_entry_table: ~350 prompt + full doc
    # 2. extract_land_records_ai: ~250 prompt + 3000 chars (750 tokens)
    # 3. extract_entry_details_ai: ~3500 prompt + entry section (~50% of doc)
    old_prompt_tokens = 350 + 250 + 3500
    old_doc_tokens = doc_tokens + 750 + (doc_tokens * 0.5)
    old_total = old_prompt_tokens + old_doc_tokens

    # New unified approach:
    # Single prompt with doc sent once
    new_prompt_tokens = 800  # Reduced static content
    new_doc_tokens = min(doc_tokens, 4000)  # We extract relevant sections
    new_total = new_prompt_tokens + new_doc_tokens

    savings_pct = ((old_total - new_total) / old_total) * 100

    return {
        'old_approach': {
            'prompt_tokens': old_prompt_tokens,
            'document_tokens': int(old_doc_tokens),
            'total_tokens': int(old_total),
            'api_calls': 3
        },
        'new_approach': {
            'prompt_tokens': new_prompt_tokens,
            'document_tokens': new_doc_tokens,
            'total_tokens': int(new_total),
            'api_calls': 1
        },
        'savings': {
            'tokens_saved': int(old_total - new_total),
            'percentage': round(savings_pct, 1),
            'api_calls_saved': 2
        }
    }
