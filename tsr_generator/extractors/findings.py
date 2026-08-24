import logging
import re
from typing import List, Dict, Any, Optional, Tuple, Union


def _get_field(entry, key: str, default: str = "") -> str:
    """Get a field from either a dataclass entry or a dict."""
    if isinstance(entry, dict):
        return str(entry.get(key, default))
    return str(getattr(entry, key, default) or default)


def _get_entry_type_str(entry) -> str:
    """Get the entry type as an uppercase string."""
    if isinstance(entry, dict):
        raw = entry.get('type', '')
    else:
        raw = getattr(entry, 'type', '')
    if hasattr(raw, 'value'):
        raw = raw.value
    return str(raw).upper().replace(' ', '_')


def _get_lender_from_entry(entry) -> Optional[str]:
    """
    Get lender name from a structured entry object or dict.
    Prefers structured 'lender' field; falls back to regex on description.
    """
    # Try structured field first (works for both dataclass and dict)
    lender = None
    if isinstance(entry, dict):
        lender = entry.get('lender', '') or ''
    else:
        lender = getattr(entry, 'lender', '') or ''

    if lender and lender.strip():
        return lender.strip()

    # For SEIZURE entries, try 'bank' field
    if isinstance(entry, dict):
        bank = entry.get('bank', '') or ''
    else:
        bank = getattr(entry, 'bank', '') or ''
    if bank and bank.strip():
        return bank.strip()

    # Fallback to regex extraction from description
    description = _get_field(entry, 'description') or _get_field(entry, 'formatted_description')
    return _extract_lender_name(description) if description else None


def _get_reference_entry_number(entry) -> Optional[str]:
    """Get reference entry number from structured field or regex fallback."""
    # Try structured field
    ref = None
    if isinstance(entry, dict):
        ref = entry.get('reference_entry_number', '') or ''
    else:
        ref = getattr(entry, 'reference_entry_number', '') or ''
        if not ref:
            ref = getattr(entry, 'reference_to_original', '') or ''

    if ref and ref.strip():
        return ref.strip()

    # Fallback: regex on description
    description = _get_field(entry, 'description') or _get_field(entry, 'formatted_description')
    if description:
        match = re.search(r'Entry\s*(?:No\.?)?\s*(\d+)', description, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def detect_active_encumbrances(entries: List) -> Tuple[List, List[str]]:
    """
    Detect active encumbrances (loans/mortgages without matching releases).

    Accepts both typed entry dataclass objects (new pipeline) and plain dicts
    (old pipeline) for backward compatibility.

    Matching strategy:
    1. Match releases to loans by explicit reference_entry_number
    2. Match releases to loans by lender name + chronological order
    3. SEIZURE entries are NOT separate encumbrances (enforcement on existing loan)

    Args:
        entries: List of entry objects (dataclass) or dicts.

    Returns:
        Tuple of (active_encumbrance_entries, active_entry_numbers)
    """
    logger = logging.getLogger(__name__)

    if not entries:
        return [], []

    # Sort entries by entry number (chronological order)
    def _sort_key(e):
        num = _get_field(e, 'entry_number', '0')
        return int(num) if num.isdigit() else 0

    sorted_entries = sorted(entries, key=_sort_key)

    # Track loans and releases
    loans = []  # List of (entry_number, entry, lender_name)
    released_entry_numbers = set()

    for entry in sorted_entries:
        entry_type = _get_entry_type_str(entry)
        entry_number = _get_field(entry, 'entry_number')

        # Identify LOAN/MORTGAGE entries
        if entry_type in ('LOAN', 'MORTGAGE'):
            lender = _get_lender_from_entry(entry)
            loans.append((entry_number, entry, lender))
            logger.debug("Loan Entry %s: lender=%s", entry_number, lender)

        # Identify RELEASE entries
        elif entry_type in ('RELEASE', 'LOAN_CLOSE'):
            # Strategy 1: explicit reference entry number
            ref = _get_reference_entry_number(entry)
            if ref:
                released_entry_numbers.add(ref)
                logger.debug("Release Entry %s: explicitly clears Entry %s", entry_number, ref)

            # Strategy 2: match by lender name
            release_lender = _get_lender_from_entry(entry)
            if release_lender:
                for loan_num, _loan_entry, loan_lender in loans:
                    if loan_lender and _lenders_match(loan_lender, release_lender):
                        if loan_num.isdigit() and entry_number.isdigit():
                            if int(loan_num) < int(entry_number):
                                released_entry_numbers.add(loan_num)
                                logger.debug(
                                    "Release Entry %s: clears Entry %s (same lender: %s)",
                                    entry_number, loan_num, release_lender,
                                )
                        else:
                            released_entry_numbers.add(loan_num)

    # Find active loans (not released)
    active_encumbrances = []
    active_entry_numbers = []

    for entry_num, entry, lender in loans:
        if entry_num not in released_entry_numbers:
            active_encumbrances.append(entry)
            active_entry_numbers.append(entry_num)
            logger.debug("Active encumbrance: Entry %s (lender: %s)", entry_num, lender)

    logger.info(
        "Detected %d active encumbrances from %d loan entries",
        len(active_encumbrances), len(loans),
    )
    return active_encumbrances, active_entry_numbers


def _extract_lender_name(description: str) -> Optional[str]:
    """Extract lender/bank name from loan or release description."""
    import re
    
    # Common patterns for lender names
    patterns = [
        r'from\s+([A-Za-z\s]+(?:Bank|BANK)[^.,\n]{0,50})',  # "from XYZ Bank"
        r'of\s+([A-Za-z\s]+(?:Bank|BANK)[^.,\n]{0,50})',    # "charge of XYZ Bank"
        r'([A-Za-z\s]+(?:Bank|BANK)[^.,\n]{0,50})',         # Any bank name
    ]
    
    for pattern in patterns:
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            lender = match.group(1).strip()
            # Clean up common suffixes
            lender = re.sub(r'\s+(Branch|BRANCH).*$', '', lender)
            lender = re.sub(r'\s*\(.*?\)', '', lender)  # Remove parenthetical notes
            return lender.strip()
    
    return None


def _lenders_match(lender1: str, lender2: str) -> bool:
    """Check if two lender names refer to the same institution."""
    if not lender1 or not lender2:
        return False
    
    # Normalize for comparison
    l1 = lender1.lower().strip()
    l2 = lender2.lower().strip()
    
    # Exact match
    if l1 == l2:
        return True
    
    # Check if one contains the other (handles variations like "Bank of Baroda" vs "Bank of Baroda (Old Dena Bank)")
    if l1 in l2 or l2 in l1:
        return True
    
    # Extract core bank name (first 2-3 significant words)
    import re
    words1 = [w for w in re.findall(r'\b\w+\b', l1) if len(w) > 2][:3]
    words2 = [w for w in re.findall(r'\b\w+\b', l2) if len(w) > 2][:3]
    
    # If at least 2 words match, consider it the same bank
    common_words = set(words1) & set(words2)
    if len(common_words) >= 2:
        return True
    
    return False


def detect_rejected_entries(entries: List) -> List[str]:
    """
    Detect entries that were rejected or not accepted.

    Args:
        entries: List of entry objects (dataclass) or dicts.

    Returns:
        List of rejected entry numbers
    """
    rejected = []

    for entry in entries:
        status = _get_field(entry, 'entry_status').lower()
        if status in ('rejected', 'not_accepted', 'not accepted'):
            rejected.append(_get_field(entry, 'entry_number'))

    return rejected


def generate_findings_table(pdf_text: str, entries: Optional[List[Dict]] = None, land_details: Optional[Dict[str, str]] = None, entry_to_row_map: Optional[Dict[str, int]] = None) -> List[Dict[str, str]]:
    """
    Generate findings for the TSR report with dynamic encumbrance detection.
    
    Args:
        pdf_text (str): The full text of the PDF document
        entries (list, optional): List of extracted mutation entries for encumbrance analysis
        land_details (dict, optional): Land details for dynamic location values
        
    Returns:
        list: A list of dictionaries with findings
    """
    logger = logging.getLogger(__name__)
    logger.debug("Generating findings with dynamic encumbrance detection")
    
    profile = (land_details or {}).get("tsr_profile", "legacy")

    # Detect active encumbrances and rejected entries
    active_encumbrances, active_entry_nums = detect_active_encumbrances(entries or [])
    rejected_entries = detect_rejected_entries(entries or [])
    
    has_encumbrances = len(active_encumbrances) > 0
    has_rejected = len(rejected_entries) > 0
    
    # Generate dynamic encumbrance text
    if profile == "final_sample_v1":
        # Match the hand-typed "Final TSR Sample" phrasing more closely
        encumbrance_period = (land_details or {}).get("encumbrance_period_years", "30")
        if has_encumbrances:
            encumbrance_text = f"{encumbrance_period} years.  As per revenue records there is charge subsisting over the land."
            charge_detail_text = "As per revenue records there is charge subsisting over the land."
        else:
            encumbrance_text = f"{encumbrance_period} years.  As per revenue records there is no charge subsisting over the land."
            charge_detail_text = "As per revenue records there is no charge subsisting over the land."
    else:
        if has_encumbrances:
            encumbrance_text = f"30 years.\n\nAs per revenue records there is charge subsisting over the land (Entry No. {', '.join(active_entry_nums)})."
            charge_detail_text = f"As per revenue records there is charge subsisting over the land. Active loan/mortgage entries: {', '.join(active_entry_nums)}."
        else:
            encumbrance_text = "30 years.\n\nAs per revenue records there is no charge subsisting over the land."
            charge_detail_text = "As per revenue records there is no charge subsisting over the land."
    
    # Generate conditional title conclusion with dynamic cross-references
    if has_encumbrances and entry_to_row_map:
        # Resolve active encumbrance entry numbers to their chain-of-title row numbers
        # Emit a marker rather than a bare number: the DOCX writer turns each
        # {{XREF:<entry>:<row>}} into a Word REF field bound to that chain row's
        # bookmark, so the reference follows Word's renumbering when a row is
        # inserted. Static numbers went stale twice in the 2026-07-28 batch.
        row_numbers = []
        for entry_num in active_entry_nums:
            if entry_num in entry_to_row_map:
                row_numbers.append(
                    "{{XREF:%s:%s}}" % (entry_num, entry_to_row_map[entry_num]))

        if row_numbers:
            if len(row_numbers) == 1:
                point_ref = f"point {row_numbers[0]} in table no. 3 above"
            else:
                point_ref = f"point {' and '.join(row_numbers)} in table no. 3 above"
            title_conclusion = f"The title of the land is clear and marketable subject to {point_ref}."
        else:
            title_conclusion = "The title of the land is clear and marketable Subject to bank charge."
    elif has_encumbrances:
        # Fallback when no entry_to_row_map provided
        title_conclusion = "The title of the land is clear and marketable Subject to bank charge."
    else:
        title_conclusion = "The title of the land is clear and marketable."
    
    # Standard findings with dynamic content
    findings = [
        {
            'sn': '1.',
            'particular': "a) Whether the records of registrar office or revenue authorities relevant to the property in question are available for verification through any online portal or computer system?",
            'observation': "YES"
        },
        {
            'sn': '',
            'particular': "b) If such online/computer records are available, whether any verification or cross checking are made and the comments/ findings in this regard.",
            'observation': "The records were verified and were found to be consistent with the online records."
        },
        {
            'sn': '',
            'particular': "c) Whether the genuineness of the stamp paper is possible to be got verified from any online portal and if so whether such verification was made?",
            'observation': "No.\nOnline verification can be done only for E-Stamp Papers.\n\nThe records of registrar can only be accessed online if the registration number of a deed is available."
        },
        {
            'sn': '2.',
            'particular': "a) Immoveable Properties falls within the jurisdiction of which sub-registrar office?",
            'observation': land_details.get('taluka_name', 'Not Available') if land_details else "Not Available"
        },
        {
            'sn': '',
            'particular': "b) Whether it is possible to have registration of documents in respect of the property in question, at more than one office of sub-registrar/ district registrar/ registrar-general. If so, please name all such offices?",
            'observation': "No"
        },
        {
            'sn': '',
            'particular': "c)Whether search has been made at all the offices named at (b) above?",
            'observation': "No.\n\nSearch is to be made at jurisdictional Sub Registrar's offices, as all entries and conveyance are recorded there relating to the property(s)."
        },
        {
            'sn': '3.',
            'particular': "The period covered under the Encumbrances Certificate and the name of the person in whose favour the encumbrance is created and if so, satisfaction of charge, if any.",
            'observation': encumbrance_text  # DYNAMIC
        },
        {
            'sn': '4.',
            'particular': "Additional aspects relevant for investigation of title as per local laws.",
            'observation': "Mutation entries reflected in Form 6, Form 7, Form 8A, Form 12 were individually investigated in respect of the proposed property, whereas no such restriction is found, and it is in order."
        },
        {
            'sn': '5.',
            'particular': "Additional suggestions if any to safeguard the interest of PFC/ensuring the perfection of security.",
            'observation': title_conclusion  # DYNAMIC
        },
        {
            'sn': '6.',
            'particular': "The specific persons who are required to create mortgage/to deposit documents creating mortgage.",
            'observation': "Not Applicable"
        },
        {
            'sn': '7.',
            'particular': "Current land use -- Agriculture/ Residential/industrial/commercial",
            'observation': "Agricultural"
        },
        {
            'sn': '8.',
            'particular': "Requirement of Change in Land Use and position as per policy of the state",
            'observation': "Prior permission of the Collector is required for the industrial use of agricultural land."
        },
        {
            'sn': '9.',
            'particular': "Permission under the urban land (Ceiling and Regulation) Act,1976",
            'observation': "No such requirement is stated in the revenue records. However, if the company intends to purchase more than 25 Acres of land in a particular village, then prior permission of Industries Commissioner would be required. However, if the company is acquiring the land by way of lease, then no urban land ceiling clearance is required."
        },
        {
            'sn': '10.',
            'particular': "Details of creation of charge or redemption for a minimum period of 30 year and subsisting charges, as per encumbrance certificate for the last 30 year.",
            'observation': charge_detail_text  # DYNAMIC
        },
        {
            'sn': '11.',
            'particular': "Additional documents required.",
            'observation': "It is as per the standard operating procedure of the Financial Institution."
        },
        {
            'sn': '12.',
            'particular': "Findings based on ROC Search and list of encumbrances",
            'observation': "Not Applicable"
        },
        {
            'sn': '13.',
            'particular': "Pending litigation before any court of law/ forum in respect of the property.",
            'observation': "As per updated revenue records there is no pending litigation on the land."
        },
        {
            'sn': '14.',
            'particular': "Availability of No encumbrance certificate from the concerned Registrar of Assurances.",
            'observation': "Not Applicable"
        },
        {
            'sn': '15.',
            'particular': "Any minor's interest if involved in the property proposed to be mortgaged or any other claims. If minor's interest is involved, what precautions are to be taken to protect PFC's interest as a mortgagee",
            'observation': "Not Applicable"
        },
        {
            'sn': '16.',
            'particular': "Whether the property is acquired under Land Acquisition Act, 1894 and applicability of other State Legislation",
            'observation': "As per revenue records, the property is not acquired under Land Acquisition Act"
        },
        {
            'sn': '17.',
            'particular': "Any other special enactment which is applicable to the property proposed to be mortgaged and affects the title",
            'observation': "No"
        },
        {
            'sn': '18.',
            'particular': "Findings on absolute, clear, and marketable title of the immovable property proposed to be mortgaged",
            'observation': title_conclusion  # DYNAMIC
        }
    ]
    
    logger.debug(f"Generated {len(findings)} findings (encumbrances: {has_encumbrances}, rejected: {has_rejected})")
    return findings