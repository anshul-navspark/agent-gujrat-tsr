import logging

def generate_findings_table(pdf_text):
    """
    Generate standard findings for the TSR report
    
    Args:
        pdf_text (str): The full text of the PDF document
        
    Returns:
        list: A list of dictionaries with standard findings
    """
    logger = logging.getLogger(__name__)
    logger.debug("Generating standard findings")
    
    # Standard findings
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
            'observation': "30 years.\n\nAs per revenue records there is no charge subsisting over the land."
        },
        {
            'sn': '4',
            'particular': "Additional aspects relevant for investigation of title as per local laws.",
            'observation': "Mutation entries reflected in Form 6, Form 7, Form 8A, Form 12 were individually investigated in respect of the proposed property, whereas no such restriction is found, and it is in order."
        },
        {
            'sn': '5',
            'particular': "Additional suggestions if any to safeguard the interest of PFC/ensuring the perfection of security.",
            'observation': "The title of the land is clear and marketable."
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
            'observation': "As per revenue records there is no charge subsisting over the land."
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
            'observation': "The title of the land is clear and marketable."
        }
    ]
    
    logger.debug(f"Generated {len(findings)} standard findings")
    return findings 