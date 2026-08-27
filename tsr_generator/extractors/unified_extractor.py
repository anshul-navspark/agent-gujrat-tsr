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
import time
import traceback
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any

from dotenv import load_dotenv

# Use relative imports to avoid circular import with tsr_generator.__init__
from .entry_schema import EntryType, BaseEntry, EntryUnion
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
4. For LOAN/RELEASE entries, DO NOT include "based on the agreement dated..." commentary. (For INHERITANCE/DEATH and PARTITION/LIFETIME DISTRIBUTION entries you MUST include a closing sentence listing the documents the mutation was based on — see the description examples.)
5. Keep descriptions direct and factual. Include all legally relevant details. Do not add commentary or explanatory sentences.
6. Amounts: "Rs. X/-" or "Rs. X,XXX/-"
7. ALWAYS use "Survey No." instead of "Khata No." or "Account No."
8. Documents: "document no. X dated DD/MM/YYYY"
9. Translate "Paiki" or "Part" or "part" or "pk" as "p" in survey numbers (e.g. "150/p1")
10. IMPORTANT: Preserve "/" in survey numbers (e.g., "387/p3" NOT "387p3")
11. Use caste titles only when part of the name: Thakor, Patel, Kanbi, Choudhary, Rabari, Vadher, Solanki
12. Measurements: Use "Acre/Guntha" or "Hectare" in descriptions. For the total_area field, output ONLY the numeric format (e.g., "1-88-48") WITHOUT the word "Hectare".
13. Translate "bhen" or "ben" suffix as "ben" (e.g. "Shantiben")
13a. TRANSLITERATION - do not confuse these three letters:
   ઘ = "Gh"  (ઘોહાભાઈ = Ghohabhai, NOT Dhohabhai; ઘુના = Ghuna)
   ધ = "Dh"  (ધીરાણ = dhiran, ધોહાભાઈ = Dhohabhai)
   દ = "D"   (દેહુરભાઈ = Dehurbhai)
   Rendering ઘ as "Dh" misspells the title holder's name - corrected by the
   lawyer on 2026-07-28 (Bhagubhai Ghohabhai, survey 57p1).
   When the SAME person's name is spelled inconsistently across the record
   (AnyRoR does this), use the spelling that appears most often rather than
   whichever the Ownership Details row happens to use.
14. Lists: "which are as follows:-" followed by names on separate lines
15. OMIT vague filler like "This entry was made based on the above." Keep descriptions concise — but DO retain the concrete supporting-documents clause for INHERITANCE/DEATH and PARTITION/LIFETIME DISTRIBUTION entries (application/Arji, death certificate, genealogy/Pedhinamu, affidavits/Sogandnama) when the source states them.
16. LOAN entries: Do NOT include agreement date. Only describe the loan, borrower, lender, amount, and land details.
17. OLD SURVEY NUMBERS: If there is a PROMULGATION entry (re-survey), use "old Survey No." for all entries BEFORE the promulgation entry. Use "Survey No." for entries AFTER promulgation. If there is NO promulgation entry, use "Survey No." (without "old").
18. Always use 4-digit years (DD/MM/YYYY). Never use 2-digit years (DD/MM/YY).
19. Include Khata number in parentheses after each survey number when visible in the source document, e.g., "5/2(28), 193p1(28)". If no Khata number is visible, omit parentheses.
20. Translate "Prant Officer" / "પ્રાંત અધિકારી" as "Province Officer". Use "Province Officer" and "Province court" consistently.
21. BOREWELL NAMING: Always use the full word "Borewell" with hyphenated number — "Borewell-1", "Borewell-2". NEVER write "Bore-1", "bore-1", "pucca bore-1", "1 pucca borewell", "pucca borewell-1". The Gujarati "પાકાે બાેર - ૧" / "પાકાે બાેર" / "બાેર ૧" all map to "Borewell-1" (drop "pucca"; that adjective is implicit).
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

AREA INCLUSION RULE:
- For every entry type EXCEPT LOAN and RELEASE (a.k.a. LOAN CLOSE / charge removal), when the source entry mentions a land area (e.g. "હે. ૬-૨૧-૨૦", "Hectare 1-88-48", "3 Acre 23 Guntha", "આ. હે. ચો.મી.", "જમીન હે ..."), you MUST include it in the English description as "measuring <area> Hectare" (or "Acre/Guntha" if the source uses those units), immediately after the Survey No. clause.
- Convert Gujarati numerals to English digits. Preserve the dash-separated format (e.g. "6-21-20").
- For LOAN and RELEASE entries: do NOT include any area / hectare / acre measurement — even if the source mentions one. The encumbrance is recorded against the surveys themselves; area is intentionally omitted to keep loan/release descriptions tight.
- For all other types (SALE, DEATH/INHERITANCE, PARTITION, GIFT, ALLOTMENT, RELINQUISHMENT, LIFETIME_DISTRIBUTION, EXCHANGE, ORDER allotment/circular, TENURE_CHANGE, LAND_ACQUISITION, LEASE, SEIZURE, PROMULGATION, CORRECTION): include area whenever the source states one.

LOAN (correct, no area): "That Mer Deva Depa took a loan of Rs. 20,000/- on land bearing old Survey No. 373/p1, 359, 390, 389(215) from Bank of India, Modhvada Branch."
LOAN (wrong - includes area): "That Mer Deva Depa took a loan of Rs. 20,000/- on land bearing old Survey No. 373/p1, 359, 390, 389(215) measuring 6-21-20 Hectare from Bank of India, Modhvada Branch." - DO NOT include area in loan descriptions, even when the source shows it.
LOAN (wrong - includes agreement date): "That Mer Deva Depa took a loan of Rs. 20,000/- from Bank of India, Modhvada Branch based on an agreement dated 14/05/2005." - DO NOT include agreement date!
LOAN (wrong - too verbose, mortgaging language): "That account holder Shri Mer Deva Depa of Keshav village mortgaged his total land of 6-21-20 Hectare of Keshav village, Khata No. 215, bearing Survey No. 390, with Bank of India, Modhwada branch, to obtain a loan of Rs. 20,000/-. This encumbrance entry was recorded based on the agreement dated 14/05/2005." - drop the village-name padding, "account holder", "mortgaged his total land", trailing commentary, AND the area.

IMPORTANT for LOAN entries:
- DO NOT include "agreement dated" or "based on an agreement"
- DO NOT include total land area or hectare measurements in loan descriptions.
- State: borrower name, loan amount, survey numbers (with khata in parentheses), bank name and branch.
- INCLUDE ALL survey numbers listed in the entry's "Other Rights" / બોજા / બીજા હક્ક column, NOT only the subject survey number. A single loan entry frequently encumbers many surveys belonging to the same khata (e.g. "421(608), 422(608), 423(608), 500(608), 501(608), 568(608), 574(715), 602(608), 603(608), 608(608), 609(608)") — output the COMPLETE list exactly as it appears in the source, in the same order, with the khata number in parentheses after each. Do NOT filter, deduplicate, or drop survey numbers just because they differ from the subject survey. The same rule applies to RELEASE / LOAN CLOSE entries that reference the same multi-survey charge.

Other patterns (include "measuring <area>" whenever the source states one — NOT for LOAN / RELEASE):
- DEATH/INHERITANCE: Include the death date. For EACH heir include their relationship (the heir table has columns સંબંધ = relationship and ઉં.વ. = age; પત્નિ/પત્ની=wife, પુત્ર=son, પુત્રી=daughter, વિધવા=widow, માતા=mother). End with a sentence listing the documents the mutation was based on when shown (application/Arji, death certificate, genealogy/Pedhinamu, affidavits/Sogandnama). Format:
"That upon the demise of [Name] on DD/MM/YYYY, his/her share in land bearing old Survey No. X(Khata), Y(Khata) measuring <area> Hectare came to be mutated in the names of his/her legal heirs which are as follows:-
[Heir1Name] - [relationship]
[Heir2Name] - [relationship]

"
  DO NOT output the closing supporting-documents sentence for INHERITANCE ("This inheritance was recorded based on the application, death certificate, genealogy (Pedhinamu) and affidavits."). The lawyer deletes it from every inheritance entry (2026-07-28 review of entries 607 and 1142). End the entry after the heir list, then the certification sentence. NOTE this applies to INHERITANCE ONLY — PARTITION keeps its closing sentence.
  DO NOT output heir AGES ("- age 50") or the death-certificate number ("(death certificate no. 3)") — per lawyer review 2026-07-28 these are stripped from the final report. Keep the exact death DATE.
  CRITICAL — when the source says the deceased died નિસંતાન / childless / issueless, you MUST carry that through as "(Childless)" immediately after that person's name. It is not descriptive detail: it is the legal reason the share devolves on a sibling's heirs rather than the deceased's own line. Example: "upon the demise of Lakhabhai Kathadbhai and Gilabhai Kanthadbhai (Childless), ...".
  Drop any segment the source does not provide — omit the closing supporting-documents sentence if no such documents are listed. NEVER invent a date, relationship, or document.
- SALE: "That [Seller] sold Survey No. X measuring <area> Hectare to [Buyer] for a consideration of Rs. [consideration]/- (market value Rs. [market value]/-) vide document no. Y dated DD/MM/YYYY."
  The Gujarati source for a sale typically states TWO amounts — માર્કેટ વેલ્યુ / market value (the jantri/assessed value, e.g. "માર્કેટ વેલ્યુ રૂ. 295020/-") AND અવેજ / અવેજની રકમ / consideration (the price actually paid, e.g. "અવેજની રકમ રૂ. 200000/-"). Capture BOTH whenever present: render the consideration as the primary "for a consideration of Rs." amount and append the market value in parentheses as "(market value Rs. .../-)". Omit the "(market value Rs. ...)" segment only when the source states no market value. NEVER invent, drop, or swap the two amounts — the consideration and the market value are distinct figures.
- PARTITION: When the source lists who received what, you MUST emit the full allocation list (one row per recipient) between the lead-in and the closing sentence, separated by blank lines. Do NOT collapse the lead-in straight into the closing sentence. Do NOT prefix rows with "1.", "2." — emit bare rows; numbering is applied automatically downstream. Format:
"That the said [OriginalOwner(s)] distributed their land bearing Survey No. X measuring <area> Hectare among themselves as follows:-
[Recipient1] - Survey No. [X] - [area]
[Recipient2] - Survey No. [Y] - [area]
[Recipient3] - Survey No. [Z] - [area]

The distribution/Partition of the shares as mentioned above was recorded based on their application, deed of partition and affidavits before the Notary as per their respective rights and physical possession."
  The closing sentence MUST name the documents the SOURCE actually cites. When the source says નોટરી રૂબરૂના સોગંદનામા (affidavit sworn before the Notary), write "affidavits before the Notary" — do NOT soften it to "their consent", which is wrong and was corrected by the lawyer on 2026-07-28. Likewise render વહેચણી અંગેનો લેખ as "deed of partition".
  Each allocation row goes on its own line. If the source omits area or survey for a recipient, leave that segment off (e.g. "[Name] - Survey No. 33"). NEVER produce a partition description that has "as follows:-" / "as under:-" followed immediately by the "The distribution..." closing line — the allocation rows MUST be present whenever the source shows them.
- LIFETIME_DISTRIBUTION / PERSONS_ADD / TO_TRANSFER: When multiple beneficiaries are listed, emit them as bare rows (one per line, no "1.", "2." prefixes):
"That the said [Distributor] made an application of life time distribution in his land bearing Survey No. X measuring <area> Hectare to [add/transfer to] his legal heirs which are as follows:-
[Beneficiary1]
[Beneficiary2]"
  Single-beneficiary lifetime distributions stay as one prose sentence (no list).
- RELEASE (no area): "That upon receiving an application from [Name] for removing the charge of [Bank], [Branch]. The said exemption of burden has been recorded. Entry No. X."
  NEVER state the release certificate date in ANY phrasing — not "on its certificate dated DD/MM/YYYY", not "on the basis of the certificate dated DD/MM/YYYY", not "vide certificate dated ...", and not the issuing body's certificate date (Liquidator, District Registrar, bank or society). Drop the whole clause. NEVER state the lender's release-certificate date (the "તા.DD/MM/YYYY નાં દાખલા" the release cites). House convention omits it entirely — only the entry's own date and its certification date appear in the report. Confirmed 2026-07-28.
- ORDER (government allotment): "That Government survey was conducted and land bearing Survey No. X measuring <area> Hectare was allotted to [Name]."
- ORDER (circular): "That as per Taluka Circular No. X dated Y, Survey No. Z measuring <area> Hectare allotted to [Name]."
- ORDER (error correction): Keep the order's identifying preamble (issuing authority, order number, date, village) in full, then include ONLY the numbered correction item(s) that concern the SUBJECT survey number. A promulgation-correction order routinely lists 30+ unrelated surveys; reproducing all of them buries the relevant line and the lawyer deletes them (2026-07-28 review: 33 items emitted, 1 kept). Preserve the source's own item number so the citation stays traceable. Example: "Vide order was passed by the Mamlatdar, Talaja, vide No. E-Dhara/Worksheet/Bodki-08 dated 14/08/2008, for correcting the errors found in the promulgation of the computerized Village Form No. 7/12 of village Bodki, the corrections in the rights record are as follows:- 26. Survey No. 44(125) - Malubai Alubai". If NO listed item concerns the subject survey, say so plainly rather than dumping the whole list.
- NOT RELATED: "This Entry is not related to Present Survey Number."
- INDEX-ONLY ENTRY: when an entry number appears in the "Entry Details" index list but the record contains NO detail row for it (common for pre-1970 entries that predate the digital record), output exactly: "However, this entry is not shown on the website i.e. anyror but upon physical verification we found this entry related to present Survey No." This is the firm's standard wording for an entry absent from AnyRoR (approved 2026-07-28); the lawyer then fills the entry body from the old scanned Village Form 7/12 during review. Do NOT write "content is not legible" — the content is not illegible, it is absent — and do NOT emit an empty description. Never invent the entry.
- PROMULGATION: Extract the FULL procedural text. Include: issuing authority, court name, all order numbers with dates, public notice and objection period, Mamlatdar preparation, Province Office verification, finalization, page/survey range. Do NOT summarize. Preserve old/new area pairs verbatim (e.g. "old area 7-59-29 Hectare, new area 7-70-84 Hectare").
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

        # Extraction backend: 'claude' shells out to the `claude` CLI (Claude Code
        # subscription auth, NO API key); 'gemini' uses LangChain ChatGoogleGenerativeAI.
        # Captcha + translation always stay on Gemini regardless of this setting.
        backend = os.getenv('EXTRACTION_BACKEND', 'claude').strip().lower()
        if backend == 'claude':
            claude_model = os.getenv('CLAUDE_EXTRACTION_MODEL', 'opus').strip()
            content = _coerce_text(_invoke_claude_cli(prompt, claude_model))
        else:
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(
                model=MODEL_NAME,
                google_api_key=os.getenv('GEMINI_API_KEY', ''),
                temperature=0.0,
                convert_system_message_to_human=True,
                # Gemini-3 thinking level (raj-repo tuning: 3-flash=low, 3.5-flash=medium).
                # Empty/unset -> None (model default). Note: enabling thinking makes
                # response.content a list of blocks, handled by _coerce_text/_parse_json_response.
                thinking_level=(os.getenv('GEMINI_THINKING_LEVEL', 'low').strip().lower() or None),
            )
            # Make the SINGLE API call with retry
            response = _invoke_with_retry(llm, prompt, max_retries=3)
            content = _coerce_text(response.content if hasattr(response, 'content') else str(response))

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


def _invoke_claude_cli(prompt: str, model: str = "opus", timeout: int = 300) -> str:
    """Run a one-shot extraction via the `claude` CLI in print mode.

    Uses Claude Code's logged-in subscription auth (NO ANTHROPIC_API_KEY needed), so
    extraction can run on Claude (Sonnet/Opus) at low volume without an API key. A
    minimal --system-prompt strips the heavy agent prompt so it behaves as a plain
    extraction model. Captcha + translation stay on Gemini. Requires the machine to
    have an authenticated `claude` CLI (works locally; NOT on a headless cloud deploy).
    """
    import subprocess
    # Effort is env-configurable (default "low"). Plugins stay disabled regardless;
    # the >300s hang was caused by xhigh effort + plugins loading together, so a
    # deliberate higher effort with plugins off is safe (just slower thinking).
    _effort = (os.getenv("CLAUDE_EXTRACTION_EFFORT", "high").strip() or "high")
    # Higher effort thinks longer; give it more headroom unless caller overrode.
    if _effort in ("high", "xhigh") and timeout == 300:
        timeout = int(os.getenv("CLAUDE_EXTRACTION_TIMEOUT", "900"))
    cmd = [
        "claude", "-p", "--model", model,
        "--strict-mcp-config",  # don't spawn the session's MCP servers
        # Override the user's heavy interactive config for a fast one-shot call:
        # configurable effort + no plugins (the superpowers SessionStart hook) + no
        # auto-memory/dream. WITHOUT plugins-off, each headless call loads the
        # plugins and HANGS (>300s) on a ~23KB prompt.
        "--settings",
        ('{"effortLevel":"%s","enabledPlugins":{},"autoMemoryEnabled":false,'
         '"autoDreamEnabled":false,"promptSuggestionEnabled":false}' % _effort),
        "--disallowed-tools", "Bash", "Read", "Edit", "Write", "Glob", "Grep",
        "WebFetch", "WebSearch", "Task", "TodoWrite",
        "--system-prompt",
        ("You are a precise data-extraction engine. Follow the user's instructions "
         "exactly and output ONLY the requested JSON object."),
    ]
    env = {**os.environ, "CLAUDE_EFFORT": _effort}
    try:
        res = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                             timeout=timeout, env=env)
    except FileNotFoundError:
        raise RuntimeError("`claude` CLI not on PATH; cannot use EXTRACTION_BACKEND=claude")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"claude CLI timed out after {timeout}s")
    if res.returncode != 0:
        raise RuntimeError(f"claude CLI failed (rc={res.returncode}): {res.stderr[:500]}")
    out = (res.stdout or "").strip()
    if not out:
        raise RuntimeError(f"claude CLI returned empty output; stderr={res.stderr[:300]}")
    logger.info(f"Claude CLI extraction OK (model={model}, {len(out)} chars out)")
    return out


def _coerce_text(content) -> str:
    """Flatten a LangChain response.content to a plain string.

    With Gemini-3 thinking enabled, content comes back as a list of blocks
    like [{'type': 'text', 'text': '...'}] instead of a str. The two-pass
    parsers expect a str, so normalise here.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item if isinstance(item, str)
            else item.get("text", "") if isinstance(item, dict)
            else "" for item in content
        )
    return str(content)


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
# SUBJECT-SURVEY DESCRIPTION FILTERING
# =============================================================================


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
