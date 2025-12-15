import logging
from typing import List, Dict, Any, Optional, Tuple


def detect_active_encumbrances(entries: List[Dict]) -> Tuple[List[Dict], List[str]]:
    """
    Detect active encumbrances (loans/mortgages without matching releases).
    
    Enhanced logic:
    1. Match releases to loans by explicit entry number references
    2. Match releases to loans by lender/bank name + chronological order
    3. A release clears all previous loans from the same lender
    
    Args:
        entries: List of extracted mutation entries with type and entry_number
        
    Returns:
        Tuple of (active_encumbrance_entries, active_entry_numbers)
    """
    logger = logging.getLogger(__name__)
    
    if not entries:
        return [], []
    
    import re
    
    # Sort entries by entry number (chronological order)
    sorted_entries = sorted(entries, key=lambda x: int(x.get('entry_number', '0')) if str(x.get('entry_number', '')).isdigit() else 0)
    
    # Track loans and releases
    loans = []  # List of (entry_number, entry_dict, lender_name)
    released_entry_numbers = set()
    
    for entry in sorted_entries:
        entry_type = str(entry.get('type', '')).upper()
        entry_number = str(entry.get('entry_number', ''))
        description = str(entry.get('description', ''))
        
        # Identify loan/mortgage entries
        if entry_type in ['LOAN', 'MORTGAGE'] or 'took a loan' in description.lower():
            # Extract lender/bank name from description
            lender = _extract_lender_name(description)
            loans.append((entry_number, entry, lender))
            logger.debug(f"Loan Entry {entry_number}: lender={lender}")
        
        # Identify release entries
        elif entry_type in ['RELEASE', 'LOAN CLOSE'] or 'removing the charge' in description.lower() or 'exemption of burden' in description.lower():
            # Strategy 1: Look for explicit "Entry No. X" references
            ref_matches = re.findall(r'Entry\s*(?:No\.?)?\s*(\d+)', description, re.IGNORECASE)
            for ref in ref_matches:
                released_entry_numbers.add(ref)
                logger.debug(f"Release Entry {entry_number}: explicitly clears Entry {ref}")
            
            # Strategy 2: Match by lender name (clears all previous loans from same lender)
            release_lender = _extract_lender_name(description)
            if release_lender:
                # Find all previous loans from this lender
                for loan_num, loan_entry, loan_lender in loans:
                    if loan_lender and _lenders_match(loan_lender, release_lender):
                        # Only clear loans that came BEFORE this release
                        if int(loan_num) < int(entry_number) if loan_num.isdigit() and entry_number.isdigit() else True:
                            released_entry_numbers.add(loan_num)
                            logger.debug(f"Release Entry {entry_number}: clears Entry {loan_num} (same lender: {release_lender})")
    
    # Find active loans (not released)
    active_encumbrances = []
    active_entry_numbers = []
    
    for entry_num, entry, lender in loans:
        if entry_num not in released_entry_numbers:
            active_encumbrances.append(entry)
            active_entry_numbers.append(entry_num)
            logger.debug(f"Active encumbrance: Entry {entry_num} (lender: {lender})")
    
    logger.info(f"Detected {len(active_encumbrances)} active encumbrances from {len(loans)} loan entries")
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


def detect_rejected_entries(entries: List[Dict]) -> List[str]:
    """
    Detect entries that were rejected or not accepted.
    
    Args:
        entries: List of extracted mutation entries
        
    Returns:
        List of rejected entry numbers
    """
    rejected = []
    
    for entry in entries:
        status = str(entry.get('entry_status', '')).lower()
        if status in ['rejected', 'not_accepted', 'not accepted']:
            rejected.append(str(entry.get('entry_number', '')))
    
    return rejected


def generate_findings_table(pdf_text: str, entries: Optional[List[Dict]] = None) -> List[Dict[str, str]]:
    """
    Generate findings for the TSR report with dynamic encumbrance detection.
    
    Args:
        pdf_text (str): The full text of the PDF document
        entries (list, optional): List of extracted mutation entries for encumbrance analysis
        
    Returns:
        list: A list of dictionaries with findings
    """
    logger = logging.getLogger(__name__)
    logger.debug("Generating findings with dynamic encumbrance detection")
    
    # Detect active encumbrances and rejected entries
    active_encumbrances, active_entry_nums = detect_active_encumbrances(entries or [])
    rejected_entries = detect_rejected_entries(entries or [])
    
    has_encumbrances = len(active_encumbrances) > 0
    has_rejected = len(rejected_entries) > 0
    
    # Generate dynamic encumbrance text
    if has_encumbrances:
        encumbrance_text = f"30 years.\n\nAs per revenue records there is charge subsisting over the land (Entry No. {', '.join(active_entry_nums)})."
        charge_detail_text = f"As per revenue records there is charge subsisting over the land. Active loan/mortgage entries: {', '.join(active_entry_nums)}."
    else:
        encumbrance_text = "30 years.\n\nAs per revenue records there is no charge subsisting over the land."
        charge_detail_text = "As per revenue records there is no charge subsisting over the land."
    
    # Generate conditional title conclusion
    caveats = []
    if has_encumbrances:
        caveats.append("point no. 3 of table no. 4")
    if has_rejected:
        caveats.append(f"rejected entries ({', '.join(rejected_entries)}) in the chain of title")
    
    if caveats:
        title_conclusion = f"The title of the land is clear and marketable subject to {' and '.join(caveats)}."
    else:
        title_conclusion = "The title of the land is clear and marketable."
    
    # Standard findings with dynamic content
    findings = [
        {
            'sn': '1',
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
            'sn': '2',
            'particular': "a) Immoveable Properties falls within the jurisdiction of which sub-registrar office?",
            'observation': "Nakhtarana and Naliya"
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
            'sn': '3',
            'particular': "The period covered under the Encumbrances Certificate and the name of the person in whose favour the encumbrance is created and if so, satisfaction of charge, if any.",
            'observation': encumbrance_text  # DYNAMIC
        },
        {
            'sn': '4',
            'particular': "Additional aspects relevant for investigation of title as per local laws.",
            'observation': "Mutation entries reflected in Form 6, Form 7, Form 8A, Form 12 were individually investigated in respect of the proposed property, whereas no such restriction is found, and it is in order."
        },
        {
            'sn': '5',
            'particular': "Additional suggestions if any to safeguard the interest of PFC/ensuring the perfection of security.",
            'observation': title_conclusion  # DYNAMIC
        },
        {
            'sn': '6',
            'particular': "The specific persons who are required to create mortgage/to deposit documents creating mortgage.",
            'observation': "Not Applicable"
        },
        {
            'sn': '7',
            'particular': "Current land use -- Agriculture/ Residential/industrial/commercial",
            'observation': "Agricultural"
        },
        {
            'sn': '8',
            'particular': "Requirement of Change in Land Use and position as per policy of the state",
            'observation': "Prior permission of the Collector is required for the industrial use of agricultural land."
        },
        {
            'sn': '9',
            'particular': "Permission under the urban land (Ceiling and Regulation) Act,1976",
            'observation': "No such requirement is stated in the revenue records. However, if the company intends to purchase more than 25 Acres of land in a particular village, then prior permission of Industries Commissioner would be required. However, if the company is acquiring the land by way of lease, then no urban land ceiling clearance is required."
        },
        {
            'sn': '10',
            'particular': "Details of creation of charge or redemption for a minimum period of 13 year and subsisting charges, as per encumbrance certificate for the last 13 year.",
            'observation': charge_detail_text  # DYNAMIC
        },
        {
            'sn': '11',
            'particular': "Additional documents required.",
            'observation': "It is as per the standard operating procedure of the Financial Institution."
        },
        {
            'sn': '12',
            'particular': "Findings based on ROC Search and list of encumbrances",
            'observation': "Not Applicable"
        },
        {
            'sn': '13',
            'particular': "Pending litigation before any court of law/ forum in respect of the property.",
            'observation': "As per updated revenue records there is no pending litigation on the land."
        },
        {
            'sn': '14',
            'particular': "Availability of No encumbrance certificate from the concerned Registrar of Assurances.",
            'observation': "Not Applicable"
        },
        {
            'sn': '15',
            'particular': "Any minor's interest if involved in the property proposed to be mortgaged or any other claims. If minor's interest is involved, what precautions are to be taken to protect PFC's interest as a mortgagee",
            'observation': "Not Applicable"
        },
        {
            'sn': '16',
            'particular': "Whether the property is acquired under Land Acquisition Act, 1894 and applicability of other State Legislation",
            'observation': "As per revenue records, the property is not acquired under Land Acquisition Act"
        },
        {
            'sn': '17',
            'particular': "Any other special enactment which is applicable to the property proposed to be mortgaged and affects the title",
            'observation': "No"
        },
        {
            'sn': '18',
            'particular': "Findings on absolute, clear, and marketable title of the immovable property proposed to be mortgaged",
            'observation': title_conclusion  # DYNAMIC
        }
    ]
    
    logger.debug(f"Generated {len(findings)} findings (encumbrances: {has_encumbrances}, rejected: {has_rejected})")
    return findings