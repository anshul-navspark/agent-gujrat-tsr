"""
Unified TSR Extractor - Optimized for minimal token usage.

This module consolidates land details, entry numbers, and mutation entry extraction
into a SINGLE LLM API call, reducing token usage by ~60-70%.

Token savings achieved by:
1. Sending document text only ONCE (was sent 2-3 times)
2. Separating static prompt content (examples, rules) from dynamic content
3. Combining extraction tasks into one structured JSON response
"""

import os
import json
import re
import logging
import traceback
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any

from dotenv import load_dotenv

# Use relative imports to avoid circular import with tsr_generator.__init__
from .entry_schema import (
    EntryType, Person, BaseEntry, EntryUnion, create_entry_from_dict,
    SaleEntry, MortgageEntry, ReleaseEntry, InheritanceEntry,
    PartitionEntry, RelinquishmentEntry, OrderEntry, CorrectionEntry, GenericEntry
)
from ..utils.text_utils import convert_gujarati_to_english_numerals, translate_gujarati_text
from ..utils.retry_utils import retry_with_backoff, RetryableError

# Initialize logger (before using it in imports below)
logger = logging.getLogger(__name__)

# Import LLM logger for API call tracking
try:
    from utils.llm_logger import log_llm_request, log_llm_response, get_llm_logger
    LLM_LOGGING_ENABLED = True
except ImportError:
    LLM_LOGGING_ENABLED = False
    logger.warning("LLM logging module not available - API calls will not be logged")

# Model configuration
MODEL_NAME = os.getenv('GEMINI_MODEL_NAME', 'gemini-3-pro-preview')

# Singleton LLM instance - avoid re-initialization overhead on every request
_llm_instance = None

def _get_llm():
    """Get or create singleton LLM instance for unified extraction."""
    global _llm_instance
    if _llm_instance is None:
        load_dotenv()
        from langchain_google_genai import ChatGoogleGenerativeAI
        _llm_instance = ChatGoogleGenerativeAI(
            model=MODEL_NAME,
            google_api_key=os.getenv('GEMINI_API_KEY', ''),
            temperature=0.0,
            convert_system_message_to_human=True,
        )
        logger.info(f"Initialized unified extractor LLM: {MODEL_NAME}")
    return _llm_instance


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
Formatting Rules - USE COMPACT LANGUAGE:
1. ALL descriptions MUST start with "That" (except NOT RELATED, PROMULGATION)
2. DO NOT use honorifics like "Shri", "Smt", "Mr.", "Mrs."
3. DO NOT use "account holder", "mortgaged his total land", "of [village] village"
4. DO NOT include sentences like "This encumbrance entry was recorded based on..." or "This inheritance entry was made..."
5. Keep descriptions SHORT and DIRECT - one sentence if possible
6. Amounts: "Rs. X/-" or "Rs. X,XXX/-"
7. ALWAYS use "Survey No." instead of "Khata No." or "Account No."
8. Documents: "document no. X dated DD/MM/YYYY"
9. Translate "Paiki" or "Part" or "part" or "pk" as "p" in survey numbers (e.g. "150/p1")
10. Use caste titles only when part of the name: Thakor, Patel, Kanbi, Choudhary, Rabari, Vadher, Solanki
11. Measurements: Use "Acre/Guntha" or "Hectare". REPLACE "H.Are.SqMt." with "Hectare".
   - Example: Convert "1-88-48 H.Are.SqMt. i.e.(18848 Sq. Mts)" to "1-88-48 Hectare (i.e. 18848 Sq. Mts)"
12. Translate "bhen" or "ben" suffix as "ben" (e.g. "Shantiben")
13. Lists: "which are as follows:-" + bullet points (Use "•" not "*")
14. OMIT sentences like "This entry was made based on..." or "This inheritance entry was made...". Keep descriptions concise.
15. LOAN entries: Do NOT include agreement date. Only describe the loan, borrower, lender, amount, and land details.
16. CRITICAL - Survey Number Prefix Rule: If a PROMULGATION entry exists in the document, ALL entries with entry numbers LESS THAN the promulgation entry number MUST have "old" before "Survey No." in their descriptions.
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
- IMPORTANT: If the document shows a 2-digit year (e.g., 30/09/05), still extract it as DD/MM/YY; it will be normalized later.
- Default if unclear: entry_status: "" (empty)

IMPORTANT: Do NOT output "certified" if the Gujarati text contains રદ, ના મંજૂર, or નામંજુર!
"""

# Minimal description examples - COMPACT format
DESCRIPTION_EXAMPLES = """
Example descriptions (COMPACT - follow these exact patterns):

LOAN (correct): "That Mer Deva Depa took a loan of Rs. 20,000/- on land bearing old Survey No. 373/p1, 359, 390, 389 (215) from Bank of India, Modhvada Branch."
LOAN (wrong - includes agreement date): "That Mer Deva Depa took a loan of Rs. 20,000/- from Bank of India, Modhvada Branch based on an agreement dated 14/05/2005." - DO NOT include agreement date!
LOAN (wrong - too verbose): "That account holder Shri Mer Deva Depa of Keshav village mortgaged his total land of 6-21-20 Hectare of Keshav village, Khata No. 215, bearing Survey No. 390, with Bank of India, Modhwada branch, to obtain a loan of Rs. 20,000/-. This encumbrance entry was recorded based on the agreement dated 14/05/2005."

IMPORTANT for LOAN entries:
- DO NOT include "agreement dated" or "based on an agreement"
- DO NOT include total land area or hectare measurements in loan descriptions
- Just state: borrower name, loan amount, survey numbers, bank name and branch

Other patterns:
- DEATH: "That upon demise of [Name], land bearing Survey No. X mutated to heirs: [list]"
- SALE: "That [Seller] sold Survey No. X to [Buyer] for Rs. X/- vide document no. Y dated Z."
- PARTITION: "That [Name] distributed land as follows:- [bullet list]"
- RELEASE: "That charge of [Bank] removed on application of [Name]. Ref Entry No. X."
- ORDER: "That as per Taluka Circular No. X dated Y, Survey No. Z allotted to [Name]."
- NOT RELATED: "This entry is not related to present survey no."
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
   - date: Format as DD/MM/YYYY if available, else ""
   - type: One of: LOAN, DEATH, RELEASE, LOAN CLOSE, SALE, PARTITION, PERSONS ADD, TO TRANSFER, EXCHANGE, LIFETIME DISTRIBUTION, NOT RELATED, ORDER, RELINQUISHMENT, PROMULGATION
   - description: MUST BE IN ENGLISH. Translate all Gujarati.
   - entry_status: One of: "certified", "rejected", "not_accepted". Look for Gujarati keywords નામંજૂર (rejected), રદ (cancelled). Default to "certified" if the entry says "certified" or "The Entry is certified".
   - certification_status: MUST be one of: "certified", "rejected", "not_accepted", or "" if unclear
   - certification_official: The official's POST/DESIGNATION and PLACE (e.g., "C.O. Porbandar", "Deputy Mamlatdar Super, Porbandar"). Abbreviate "Circle Officer" as "C.O.". Do NOT include personal names.
- certification_date: The certification date (DD/MM/YYYY preferred; DD/MM/YY is acceptable). This is DIFFERENT from the entry date - look for when the entry was certified/rejected.
     
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

        # Get singleton LLM instance (avoids re-initialization overhead)
        llm = _get_llm()

        # Make the SINGLE API call with retry
        response = _invoke_with_retry(llm, prompt, max_retries=3)

        # Parse the response
        content = response.content if hasattr(response, 'content') else str(response)
        
        # Handle cases where content might be a list of content parts (newer API format)
        if isinstance(content, list):
            # Extract text from list of content parts
            text_parts = []
            for part in content:
                if isinstance(part, dict):
                    text_parts.append(part.get('text', str(part)))
                else:
                    text_parts.append(str(part))
            content = ''.join(text_parts)
        elif not isinstance(content, str):
            content = str(content)
        
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
    Accepts DD/MM/YY (or with '-') and expands to 20YY for 00-49 else 19YY.
    """
    if not date_str:
        return ""

    s = str(date_str).strip()
    # Common separators
    m = re.fullmatch(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2}|\d{4})', s)
    if not m:
        return s

    dd, mm, yy = m.group(1), m.group(2), m.group(3)
    dd = dd.zfill(2)
    mm = mm.zfill(2)

    if len(yy) == 2:
        y = int(yy)
        yyyy = 2000 + y if 0 <= y <= 49 else 1900 + y
    else:
        yyyy = int(yy)

    return f"{dd}/{mm}/{yyyy:04d}"


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
    """Invoke LLM with retry logic for rate limits and comprehensive logging."""
    import time
    retry_delay = 5
    total_retries = 0
    
    # Start LLM logging
    log_entry = None
    start_time = time.time()
    if LLM_LOGGING_ENABLED:
        try:
            log_entry = log_llm_request(
                model_name=MODEL_NAME,
                prompt=prompt,
                caller="extract_all_unified"
            )
        except Exception as log_err:
            logger.debug(f"Failed to create LLM log entry: {log_err}")

    for attempt in range(max_retries):
        try:
            response = llm.invoke(prompt)
            
            # Log successful response
            if LLM_LOGGING_ENABLED and log_entry:
                try:
                    # Extract response content for logging
                    content = response.content if hasattr(response, 'content') else str(response)
                    if isinstance(content, list):
                        content = ''.join(
                            part.get('text', str(part)) if isinstance(part, dict) else str(part)
                            for part in content
                        )
                    log_llm_response(
                        log_entry=log_entry,
                        response=content,
                        start_time=start_time,
                        retry_count=total_retries
                    )
                except Exception as log_err:
                    logger.debug(f"Failed to log LLM response: {log_err}")
            
            return response
            
        except Exception as e:
            total_retries += 1
            is_rate_limit = any(term in str(e).lower() for term in ['429', 'resource', 'quota', 'rate limit'])
            if is_rate_limit and attempt < max_retries - 1:
                logger.warning(f"Rate limit hit. Sleeping {retry_delay}s (attempt {attempt+1}/{max_retries})")
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            
            # Log error
            if LLM_LOGGING_ENABLED and log_entry:
                try:
                    log_llm_response(
                        log_entry=log_entry,
                        error=e,
                        start_time=start_time,
                        retry_count=total_retries
                    )
                except Exception as log_err:
                    logger.debug(f"Failed to log LLM error: {log_err}")
            
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


def _fix_json_string(json_str: str) -> str:
    """
    Fix common JSON issues that cause parsing failures.
    
    Handles:
    - Newlines inside string values
    - Unescaped control characters
    - Trailing commas
    - Smart quotes
    """
    # Replace smart quotes with regular quotes
    json_str = json_str.replace('"', '"').replace('"', '"')
    json_str = json_str.replace(''', "'").replace(''', "'")
    
    # Remove trailing commas before ] or }
    json_str = re.sub(r',\s*([\]\}])', r'\1', json_str)
    
    # Fix newlines inside string values (convert to \n escape sequence)
    # This is tricky - we need to be inside a string value
    result = []
    in_string = False
    escape_next = False
    
    for i, ch in enumerate(json_str):
        if escape_next:
            result.append(ch)
            escape_next = False
            continue
            
        if ch == '\\':
            result.append(ch)
            escape_next = True
            continue
            
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
            
        if in_string and ch == '\n':
            result.append('\\n')
            continue
        elif in_string and ch == '\r':
            result.append('\\r')
            continue
        elif in_string and ch == '\t':
            result.append('\\t')
            continue
            
        result.append(ch)
    
    return ''.join(result)


def _parse_json_response(content) -> Optional[Dict]:
    """Parse JSON from LLM response with multiple strategies."""
    # Handle case where content is already a dict (new API response format)
    if isinstance(content, dict):
        logger.debug("Response is already a dict, returning directly")
        return content
    
    # Handle list responses (some models return content as list of parts)
    if isinstance(content, list):
        logger.debug(f"Response is a list with {len(content)} items")
        # Try to find the text content
        for item in content:
            if isinstance(item, str):
                content = item
                break
            elif isinstance(item, dict) and 'text' in item:
                content = item['text']
                break
        else:
            content = str(content)
    
    # Convert to string if needed
    if not isinstance(content, str):
        logger.debug(f"Converting response type {type(content).__name__} to string")
        content = str(content)
    
    logger.debug(f"Parsing JSON from response (length: {len(content)}, first 300 chars: {content[:300]})")
    
    # Clean control characters (except newlines/tabs which we handle specially)
    content = ''.join(ch for ch in content if ch in '\t\n\r' or ord(ch) >= 32)

    # Strategy 1: Look for JSON in code block (with or without "json" label)
    json_code_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', content, re.IGNORECASE)
    if json_code_match:
        try:
            json_str = _fix_json_string(json_code_match.group(1))
            result = json.loads(json_str)
            logger.debug("Successfully parsed JSON from code block")
            return result
        except json.JSONDecodeError as e:
            logger.debug(f"Failed to parse JSON from code block: {e}")

    # Strategy 2: Find JSON object containing our expected keys with balanced brace matching
    json_match = re.search(r'\{[\s\S]*?(\"land_details\"|\"entry_numbers\"|\"mutation_entries\")', content)
    if json_match:
        start = json_match.start()
        # Count braces to find the matching end
        brace_count = 0
        end = start
        in_string = False
        escape_next = False
        
        for i, ch in enumerate(content[start:]):
            if escape_next:
                escape_next = False
                continue
            if ch == '\\':
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                brace_count += 1
            elif ch == '}':
                brace_count -= 1
                if brace_count == 0:
                    end = start + i + 1
                    break
        
        if end > start:
            try:
                json_str = _fix_json_string(content[start:end])
                result = json.loads(json_str)
                logger.debug("Successfully parsed JSON using balanced brace matching")
                return result
            except json.JSONDecodeError as e:
                logger.debug(f"Failed to parse JSON with brace matching: {e}")

    # Strategy 3: Try the whole content as JSON (after fixing)
    try:
        json_str = _fix_json_string(content)
        result = json.loads(json_str)
        logger.debug("Successfully parsed whole content as JSON")
        return result
    except json.JSONDecodeError as e:
        logger.debug(f"Failed to parse whole content as JSON: {e}")

    # Strategy 4: Extract between first { and last } with fixing
    first_brace = content.find('{')
    last_brace = content.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            json_str = _fix_json_string(content[first_brace:last_brace + 1])
            result = json.loads(json_str)
            logger.debug("Successfully parsed JSON using first/last brace extraction")
            return result
        except json.JSONDecodeError as e:
            logger.debug(f"Failed to parse JSON with first/last brace: {e}")
    
    # Strategy 5: Try to use ast.literal_eval as last resort (handles some Python-like formats)
    try:
        import ast
        # Replace JSON true/false/null with Python equivalents
        py_content = content[first_brace:last_brace + 1] if first_brace != -1 else content
        py_content = py_content.replace('true', 'True').replace('false', 'False').replace('null', 'None')
        result = ast.literal_eval(py_content)
        if isinstance(result, dict):
            logger.debug("Successfully parsed using ast.literal_eval")
            return result
    except Exception as e:
        logger.debug(f"Failed to parse with ast.literal_eval: {e}")
    
    # Log detailed failure info for debugging
    logger.warning(f"All JSON parsing strategies failed.")
    logger.warning(f"Response length: {len(content)}")
    logger.warning(f"First 500 chars: {content[:500]}")
    logger.warning(f"Last 200 chars: {content[-200:] if len(content) > 200 else content}")
    
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
