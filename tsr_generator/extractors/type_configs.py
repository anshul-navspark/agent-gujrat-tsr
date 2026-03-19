"""
Type configuration registry for structured extraction pipeline.

Maps each canonical entry type to its field schema, description template,
and few-shot examples for LLM-based extraction.
"""

from typing import Dict, List, Any


# ---------------------------------------------------------------------------
# TYPE_CONFIGS: one key per canonical EntryType enum name
# Each value has:
#   - "fields": dict of field_name -> type description string
#   - "template": description template string
#   - "examples": list of {"input": raw text, "output": structured JSON}
# ---------------------------------------------------------------------------

TYPE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "SALE": {
        "fields": {
            "sellers": "[string]",
            "buyers": "[string]",
            "survey_numbers": "[string]",
            "area": "string",
            "consideration_amount": "string",
            "document_number": "string",
            "document_date": "string",
        },
        "template": (
            "That {sellers} sold land bearing Survey No. {survey_nos} measuring "
            "{area} to {buyers} through document no. {document_number} dated "
            "{document_date} in consideration of Rs. {consideration_amount}/-."
        ),
        "examples": [
            {
                "input": (
                    "16/06/2022, Entry No. 4558, That the said Thakor Chaturji "
                    "Gelaji, Thakor Amartji Gelaji and Thakor Bachuji Gelaji sold "
                    "their land bearing Survey 105 measuring 0-80-94 Hectare to "
                    "Bharwad Nagjibhai Motibhai through the document no. 484/2022 "
                    "dated 16.06.2022 in the consideration of Rs. 2,50,000/-. "
                    "The entry is certified by C.O. Sami B.J. Choudhary on 06.05.2022."
                ),
                "output": {
                    "entry_number": "4558",
                    "date": "16/06/2022",
                    "type": "SALE",
                    "sellers": [
                        "Thakor Chaturji Gelaji",
                        "Thakor Amartji Gelaji",
                        "Thakor Bachuji Gelaji",
                    ],
                    "buyers": ["Bharwad Nagjibhai Motibhai"],
                    "survey_numbers": ["105"],
                    "area": "0-80-94 Hectare",
                    "consideration_amount": "2,50,000",
                    "document_number": "484/2022",
                    "document_date": "16.06.2022",
                    "certification_status": "certified",
                    "certification_official": "C.O. Sami B.J. Choudhary",
                    "certification_date": "06.05.2022",
                },
            },
            {
                "input": (
                    "Entry No. 1332, That the said Harijan Bhawnaben Sitaram sold "
                    "her respective share in the land bearing Survey 107 & 108 to "
                    "Vadher Bhawanbhai Amthabhai. "
                    "The entry is certified but the date is not legible."
                ),
                "output": {
                    "entry_number": "1332",
                    "date": "",
                    "type": "SALE",
                    "sellers": ["Harijan Bhawnaben Sitaram"],
                    "buyers": ["Vadher Bhawanbhai Amthabhai"],
                    "survey_numbers": ["107", "108"],
                    "area": "",
                    "consideration_amount": "",
                    "document_number": "",
                    "document_date": "",
                    "certification_status": "certified",
                    "certification_official": "",
                    "certification_date": "",
                },
            },
        ],
    },
    "INHERITANCE": {
        "fields": {
            "deceased": "string",
            "heirs": "[string]",
            "survey_numbers": "[string]",
            "area": "string",
        },
        "template": (
            "That upon the demise of {deceased}, the land bearing Survey No. "
            "{survey_nos} measuring {area} came to be mutated in the names of "
            "legal heirs: {heirs}."
        ),
        "examples": [
            {
                "input": (
                    "Entry No. 1368 That upon the demise of Thakor Sukhaji Karmal "
                    "his land bearing survey no. 102 came to be mutated in his legal "
                    "heirs which are as under:- 1. Sonaji Sukhaji 2. Puriben Sukhaji "
                    "3. Hamirji Sukhaji. The entry is certified but the date is not legible."
                ),
                "output": {
                    "entry_number": "1368",
                    "date": "",
                    "type": "INHERITANCE",
                    "deceased": "Thakor Sukhaji Karmal",
                    "heirs": [
                        "Sonaji Sukhaji",
                        "Puriben Sukhaji",
                        "Hamirji Sukhaji",
                    ],
                    "survey_numbers": ["102"],
                    "area": "",
                    "certification_status": "certified",
                    "certification_official": "",
                    "certification_date": "",
                },
            },
            {
                "input": (
                    "16/11/2017, Entry No. 3998, That upon the demise of Bharwad "
                    "Motibhai Sagarambhai, his land bearing survey no. 103(150), "
                    "104(150), 158/10 (150), came to be mutated in his legal heirs "
                    "which are as under:- 1. Bharwad Zabiben Motibhai "
                    "2. Bharwad Bhikhabhai Motibhai 3. Bharwad Sonalben Motibhai "
                    "4. Bharwad Shivabhai Motibhai 5. Bharwad Bhagubhai Motibhai "
                    "6. Bharwad Kankuben Motibhai. "
                    "This entry is certified by C.O. Sami on 11.01.2018."
                ),
                "output": {
                    "entry_number": "3998",
                    "date": "16/11/2017",
                    "type": "INHERITANCE",
                    "deceased": "Bharwad Motibhai Sagarambhai",
                    "heirs": [
                        "Bharwad Zabiben Motibhai",
                        "Bharwad Bhikhabhai Motibhai",
                        "Bharwad Sonalben Motibhai",
                        "Bharwad Shivabhai Motibhai",
                        "Bharwad Bhagubhai Motibhai",
                        "Bharwad Kankuben Motibhai",
                    ],
                    "survey_numbers": ["103(150)", "104(150)", "158/10 (150)"],
                    "area": "",
                    "certification_status": "certified",
                    "certification_official": "C.O. Sami",
                    "certification_date": "11.01.2018",
                },
            },
        ],
    },
    "PARTITION": {
        "fields": {
            "original_owner": "string",
            "recipients": "[string]",
            "survey_numbers": "[string]",
            "area": "string",
            "allocations": "[{name: string, survey_number: string, area: string}]",
        },
        "template": (
            "That {original_owner} distributed the land as follows: "
            "{allocation_table}. The partition was recorded based on application "
            "and consent as per respective rights and physical possession."
        ),
        "examples": [
            {
                "input": (
                    "09/11/2009, Entry No. 2953, That the said Vadher Jivabhai "
                    "Sukhabhai distributed his land as follows:- "
                    "1. Vadher Jalabhai Jivabhai - Survey No. 121 - 1-56-82 Hectare "
                    "2. Vadher Bachubhai Jivabhai - Survey No. 71/1p1 - 1-40-00 Hectare. "
                    "The distribution of the shares as mentioned above was recorded "
                    "based on their application and their consent answers according "
                    "to their respective rights and possessions. "
                    "The Entry is certified by C.O. K.N. Solanki on 05/01/2010."
                ),
                "output": {
                    "entry_number": "2953",
                    "date": "09/11/2009",
                    "type": "PARTITION",
                    "original_owner": "Vadher Jivabhai Sukhabhai",
                    "recipients": [
                        "Vadher Jalabhai Jivabhai",
                        "Vadher Bachubhai Jivabhai",
                    ],
                    "survey_numbers": ["121", "71/1p1"],
                    "area": "",
                    "allocations": [
                        {
                            "name": "Vadher Jalabhai Jivabhai",
                            "survey_number": "121",
                            "area": "1-56-82 Hectare",
                        },
                        {
                            "name": "Vadher Bachubhai Jivabhai",
                            "survey_number": "71/1p1",
                            "area": "1-40-00 Hectare",
                        },
                    ],
                    "certification_status": "certified",
                    "certification_official": "C.O. K.N. Solanki",
                    "certification_date": "05/01/2010",
                },
            },
            {
                "input": (
                    "Entry no. 879, that the said Dave Kantilal Mugatram and "
                    "Dave Shantilal Mugatram distributed their respective land "
                    "bearing old survey no. 33 & 34 among themselves as under:- "
                    "1. Old Survey No. 33 :- Dave Shantilal Mugatram "
                    "2. Old Survey No. 34 :- Dave Kantilal Mugatram. "
                    "The entry is certified but the date is not legible."
                ),
                "output": {
                    "entry_number": "879",
                    "date": "",
                    "type": "PARTITION",
                    "original_owner": "Dave Kantilal Mugatram and Dave Shantilal Mugatram",
                    "recipients": [
                        "Dave Shantilal Mugatram",
                        "Dave Kantilal Mugatram",
                    ],
                    "survey_numbers": ["33", "34"],
                    "area": "",
                    "allocations": [
                        {
                            "name": "Dave Shantilal Mugatram",
                            "survey_number": "33",
                            "area": "",
                        },
                        {
                            "name": "Dave Kantilal Mugatram",
                            "survey_number": "34",
                            "area": "",
                        },
                    ],
                    "certification_status": "certified",
                    "certification_official": "",
                    "certification_date": "",
                },
            },
        ],
    },
    "RELINQUISHMENT": {
        "fields": {
            "relinquisher": "string",
            "beneficiaries": "[string]",
            "survey_numbers": "[string]",
            "area": "string",
            "relationship": "string",
        },
        "template": (
            "That {relinquisher} relinquished their share in land bearing "
            "Survey No. {survey_nos} measuring {area} in favour of {beneficiaries}."
        ),
        "examples": [
            {
                "input": (
                    "Entry No. 632 reflects that Koli Dhudiben Dayabhai, Koli "
                    "Gangaben Dayabhai and Koli Samuben Dayabhai relinquished their "
                    "respective share in favour of Koli Somabhai Dayabhai. "
                    "The Entry is certified but the date is not legible."
                ),
                "output": {
                    "entry_number": "632",
                    "date": "",
                    "type": "RELINQUISHMENT",
                    "relinquisher": "Koli Dhudiben Dayabhai, Koli Gangaben Dayabhai and Koli Samuben Dayabhai",
                    "beneficiaries": ["Koli Somabhai Dayabhai"],
                    "survey_numbers": [],
                    "area": "",
                    "relationship": "",
                    "certification_status": "certified",
                    "certification_official": "",
                    "certification_date": "",
                },
            },
            {
                "input": (
                    "Entry No. 863 Dated 23/02/2007 That Kapadi Chothibai Venaji, "
                    "relinquished her respective share in favour of Kapadi Piraji "
                    "Venaji further she died on 17/06/2006. "
                    "The Entry is certified by C.O. Jadiya on 07/05/2007."
                ),
                "output": {
                    "entry_number": "863",
                    "date": "23/02/2007",
                    "type": "RELINQUISHMENT",
                    "relinquisher": "Kapadi Chothibai Venaji",
                    "beneficiaries": ["Kapadi Piraji Venaji"],
                    "survey_numbers": [],
                    "area": "",
                    "relationship": "",
                    "certification_status": "certified",
                    "certification_official": "C.O. Jadiya",
                    "certification_date": "07/05/2007",
                },
            },
        ],
    },
    "EXCHANGE": {
        "fields": {
            "party_a": "[string]",
            "party_b": "[string]",
            "survey_a": "[string]",
            "survey_b": "[string]",
            "area_a": "string",
            "area_b": "string",
        },
        "template": (
            "That {party_a} and {party_b} exchanged their lands. {party_a} "
            "transferred Survey No. {survey_a} measuring {area_a} and received "
            "Survey No. {survey_b} measuring {area_b}."
        ),
        "examples": [
            {
                "input": (
                    "Entry No. 1256 Thakor Mulji Gagji and Gagji Maldevji and "
                    "Thakor Chaganbhai Khushalsinghji exchanged their respective "
                    "lands through a registered document no. 2472 dated 26/06/2000 "
                    "and got land as follows:- "
                    "1. Thakor Chaganbhai Khushalsinghji 104/3p 3 Acre-00 Guntha "
                    "2. Thakor Mulji Gagji 104/1p 3 Acre-00 Guntha. "
                    "The Entry is certified."
                ),
                "output": {
                    "entry_number": "1256",
                    "date": "",
                    "type": "EXCHANGE",
                    "party_a": ["Thakor Mulji Gagji", "Gagji Maldevji"],
                    "party_b": ["Thakor Chaganbhai Khushalsinghji"],
                    "survey_a": ["104/1p"],
                    "survey_b": ["104/3p"],
                    "area_a": "3 Acre-00 Guntha",
                    "area_b": "3 Acre-00 Guntha",
                    "certification_status": "certified",
                    "certification_official": "",
                    "certification_date": "",
                },
            },
            {
                "input": (
                    "Entry No. 384 Dated 23/04/1966 Thakkar Harjeevan Motiji and "
                    "Thakor Becharji Okhaji exchanged their respective lands through "
                    "a registered dated 08/03/1966 and got land as follows:- "
                    "1. Thakkar Harjeevan Motiji - Survey No. 188p - 5-07 Acre/Guntha "
                    "2. Thakor Becharji Okhaji - Survey No. 186 - 4-19 Acre/Guntha. "
                    "The Entry is certified on 13/07/1966."
                ),
                "output": {
                    "entry_number": "384",
                    "date": "23/04/1966",
                    "type": "EXCHANGE",
                    "party_a": ["Thakkar Harjeevan Motiji"],
                    "party_b": ["Thakor Becharji Okhaji"],
                    "survey_a": ["188p"],
                    "survey_b": ["186"],
                    "area_a": "5-07 Acre/Guntha",
                    "area_b": "4-19 Acre/Guntha",
                    "certification_status": "certified",
                    "certification_official": "",
                    "certification_date": "13/07/1966",
                },
            },
        ],
    },
    "LIFETIME_DISTRIBUTION": {
        "fields": {
            "distributor": "string",
            "recipients": "[string]",
            "survey_numbers": "[string]",
            "area": "string",
            "allocations": "[{name: string, survey_number: string, area: string}]",
        },
        "template": (
            "That {distributor} distributed the land during their lifetime "
            "as follows: {allocation_table}."
        ),
        "examples": [
            {
                "input": (
                    "Entry No. 268 That Kanbi Hema Devan and Kanbi Jevat Devan "
                    "with oral agreement gave his land bearing Survey No. 193, 237, "
                    "186, 253p (Area 5 Acre 23 Guntha) to Govindbhai in family "
                    "distribution. The entry is certified."
                ),
                "output": {
                    "entry_number": "268",
                    "date": "",
                    "type": "LIFETIME_DISTRIBUTION",
                    "distributor": "Kanbi Hema Devan and Kanbi Jevat Devan",
                    "recipients": ["Govindbhai"],
                    "survey_numbers": ["193", "237", "186", "253p"],
                    "area": "5 Acre 23 Guntha",
                    "allocations": [
                        {
                            "name": "Govindbhai",
                            "survey_number": "193, 237, 186, 253p",
                            "area": "5 Acre 23 Guntha",
                        },
                    ],
                    "certification_status": "certified",
                    "certification_official": "",
                    "certification_date": "",
                },
            },
        ],
    },
    "GIFT": {
        "fields": {
            "donor": "string",
            "recipients": "[string]",
            "survey_numbers": "[string]",
            "area": "string",
            "document_number": "string",
            "document_date": "string",
        },
        "template": (
            "That {donor} gifted land bearing Survey No. {survey_nos} measuring "
            "{area} to {recipients} through document no. {document_number} dated "
            "{document_date}."
        ),
        # No examples found in sampleentry.md for GIFT type
        "examples": [
            {
                "input": (
                    "Entry No. 2150 Dated 15/03/2018 That the said Patel Ramanbhai "
                    "Motibhai gifted land bearing Survey No. 45 measuring 0-50-00 "
                    "Hectare to Patel Sureshbhai Ramanbhai through gift deed no. "
                    "312/2018 dated 10/03/2018. "
                    "The Entry is certified by C.O. Sami on 20/04/2018."
                ),
                "output": {
                    "entry_number": "2150",
                    "date": "15/03/2018",
                    "type": "GIFT",
                    "donor": "Patel Ramanbhai Motibhai",
                    "recipients": ["Patel Sureshbhai Ramanbhai"],
                    "survey_numbers": ["45"],
                    "area": "0-50-00 Hectare",
                    "document_number": "312/2018",
                    "document_date": "10/03/2018",
                    "certification_status": "certified",
                    "certification_official": "C.O. Sami",
                    "certification_date": "20/04/2018",
                },
            },
        ],
    },
    "LOAN": {
        "fields": {
            "borrowers": "[string]",
            "lender": "string",
            "survey_numbers": "[string]",
            "amount": "string",
        },
        "template": (
            "That {borrowers} created a charge on land bearing Survey No. "
            "{survey_nos} by taking loan from {lender} for a sum of Rs. "
            "{amount}/-. Therefore a charge in favour of {lender} was "
            "registered in the revenue records."
        ),
        "examples": [
            {
                "input": (
                    "16/04/2012, Entry No. 3302; That the said Thakor Sonaji "
                    "Sukhaji has created a charge on the land bearing Survey No. "
                    "102 by taking loan from Jilwana Seva Sahakari Mandali Bank, "
                    "for a sum of Rs. 60,000/- and therefore a charge in favour of "
                    "Jilwana Seva Sahakari Mandali Bank was registered in the "
                    "revenue records. "
                    "The entry is certified by C.O. Sami on 16.06.2012."
                ),
                "output": {
                    "entry_number": "3302",
                    "date": "16/04/2012",
                    "type": "LOAN",
                    "borrowers": ["Thakor Sonaji Sukhaji"],
                    "lender": "Jilwana Seva Sahakari Mandali Bank",
                    "survey_numbers": ["102"],
                    "amount": "60,000",
                    "certification_status": "certified",
                    "certification_official": "C.O. Sami",
                    "certification_date": "16.06.2012",
                },
            },
            {
                "input": (
                    "13/03/2018, Entry No. 4028; That the said Thakor Manchiben "
                    "Bharmalji, Thakor Bachuji Bharmalji and Thakor Ghiraji "
                    "Bharmalji has created a charge on the land bearing Survey No. "
                    "124 & 146 by taking loan from Jilwana Seva Sahakari Mandali "
                    "Bank, for a sum of Rs. 1,00,000/- and therefore a charge in "
                    "favour of Jilwana Seva Sahakari Mandali Bank was registered "
                    "in the revenue records. "
                    "The entry is certified by C.O. Sami on 30.05.2018."
                ),
                "output": {
                    "entry_number": "4028",
                    "date": "13/03/2018",
                    "type": "LOAN",
                    "borrowers": [
                        "Thakor Manchiben Bharmalji",
                        "Thakor Bachuji Bharmalji",
                        "Thakor Ghiraji Bharmalji",
                    ],
                    "lender": "Jilwana Seva Sahakari Mandali Bank",
                    "survey_numbers": ["124", "146"],
                    "amount": "1,00,000",
                    "certification_status": "certified",
                    "certification_official": "C.O. Sami",
                    "certification_date": "30.05.2018",
                },
            },
        ],
    },
    "RELEASE": {
        "fields": {
            "applicants": "[string]",
            "lender": "string",
            "survey_numbers": "[string]",
            "reference_entry_number": "string",
        },
        "template": (
            "That upon receiving an application from {applicants} for exemption "
            "of burden of {lender} (Entry No. {reference_entry_number}), the "
            "said exemption of burden has been recorded."
        ),
        "examples": [
            {
                "input": (
                    "07/05/2022, Entry No. 4531; That upon receiving an application "
                    "from said Thakor Chaturji Gelaji, Thakor Amartji Gelaji, "
                    "Thakor Bachuji Gelaji for removing the charge of Jilwana Seva "
                    "Sahakari Mandali Bank (Entry No. 4134). The said exemption of "
                    "burden has been recorded. "
                    "The entry is certified by C.O. Sami B.J. Choudhary on 07.06.2022."
                ),
                "output": {
                    "entry_number": "4531",
                    "date": "07/05/2022",
                    "type": "RELEASE",
                    "applicants": [
                        "Thakor Chaturji Gelaji",
                        "Thakor Amartji Gelaji",
                        "Thakor Bachuji Gelaji",
                    ],
                    "lender": "Jilwana Seva Sahakari Mandali Bank",
                    "survey_numbers": [],
                    "reference_entry_number": "4134",
                    "certification_status": "certified",
                    "certification_official": "C.O. Sami B.J. Choudhary",
                    "certification_date": "07.06.2022",
                },
            },
            {
                "input": (
                    "Entry No. 3716 Dated 27.12.2021, That upon receiving an "
                    "application from said Choudhary Riyaben Dajabhai for removing "
                    "the charge (Entry No. 796 & 1106) of Ekalava Seva Sahakari "
                    "Mandli Ltd. The said exemption of burden has been recorded. "
                    "The Entry is Certified by C.O. Harij on 21.02.2022."
                ),
                "output": {
                    "entry_number": "3716",
                    "date": "27/12/2021",
                    "type": "RELEASE",
                    "applicants": ["Choudhary Riyaben Dajabhai"],
                    "lender": "Ekalava Seva Sahakari Mandli Ltd",
                    "survey_numbers": [],
                    "reference_entry_number": "796 & 1106",
                    "certification_status": "certified",
                    "certification_official": "C.O. Harij",
                    "certification_date": "21.02.2022",
                },
            },
        ],
    },
    "SEIZURE": {
        "fields": {
            "bank": "string",
            "survey_numbers": "[string]",
            "borrowers": "[string]",
            "reference_entry_number": "string",
        },
        "template": (
            "That {bank} seized the land bearing Survey No. {survey_nos} of "
            "{borrowers} under the charge created in Entry No. "
            "{reference_entry_number}."
        ),
        "examples": [
            {
                "input": (
                    "Entry No. 3290 Dated 21/10/2022 Vide order of Special Recovery "
                    "Officer, Order No. Rev/Recovery/Seizure/22/2022, Dated "
                    "11/10/2022 has recorded an entry regarding the seizure order "
                    "issued as per the following details from the Bhavnagar District "
                    "Co-operative Bank Ltd. Survey Numbers 37p2,68,173p1,417/3,"
                    "417/2p1,482,483, have been subject to seizure. "
                    "The Entry is certified by C.O. Talaja on 10/11/2022."
                ),
                "output": {
                    "entry_number": "3290",
                    "date": "21/10/2022",
                    "type": "SEIZURE",
                    "bank": "Bhavnagar District Co-operative Bank Ltd",
                    "survey_numbers": [
                        "37p2", "68", "173p1", "417/3", "417/2p1", "482", "483",
                    ],
                    "borrowers": [],
                    "reference_entry_number": "",
                    "certification_status": "certified",
                    "certification_official": "C.O. Talaja",
                    "certification_date": "10/11/2022",
                },
            },
        ],
    },
    "ORDER": {
        "fields": {
            "authority": "string",
            "order_number": "string",
            "order_date": "string",
            "survey_numbers": "[string]",
            "affected_parties": "[string]",
            "order_summary": "string",
        },
        "template": (
            "That {authority} vide Order No. {order_number} dated {order_date} "
            "ordered {order_summary}."
        ),
        "examples": [
            {
                "input": (
                    "Entry No. 391 Dated 17/01/2007, In seat number 3, the land "
                    "described with survey number is located in Moje Sohanpura, "
                    "Kankrej. To carry out computerization (L.R.C.) for the purpose "
                    "of mutation, as per the order of Mamlatdar Saheb Kankrej, "
                    "LR.C. mutation is being initiated. Sr. no. 15, The Cancellation "
                    "of Entry No. 71, 75, 118, 326, 327 & 329. "
                    "The Entry is certified by C.O. Thara on 29/09/2007."
                ),
                "output": {
                    "entry_number": "391",
                    "date": "17/01/2007",
                    "type": "ORDER",
                    "authority": "Mamlatdar Saheb Kankrej",
                    "order_number": "",
                    "order_date": "",
                    "survey_numbers": [],
                    "affected_parties": [],
                    "order_summary": (
                        "Computerization (L.R.C.) mutation initiated. "
                        "Cancellation of Entry No. 71, 75, 118, 326, 327 & 329."
                    ),
                    "certification_status": "certified",
                    "certification_official": "C.O. Thara",
                    "certification_date": "29/09/2007",
                },
            },
        ],
    },
    "ALLOTMENT": {
        "fields": {
            "grantee": "[string]",
            "survey_numbers": "[string]",
            "area": "string",
            "authority": "string",
            "legal_basis": "string",
        },
        "template": (
            "That {grantee} was granted land bearing Survey No. {survey_nos} "
            "measuring {area} by {authority} under {legal_basis}."
        ),
        "examples": [
            {
                "input": (
                    "Entry No. 421 That the said Mamlatdar Sami in tribunal sr. "
                    "no. 23 allotted the land to Sukha Karmal for survey no. 102. "
                    "The said land will be of new tenure. "
                    "The Entry is certified but the date is not legible."
                ),
                "output": {
                    "entry_number": "421",
                    "date": "",
                    "type": "ALLOTMENT",
                    "grantee": ["Sukha Karmal"],
                    "survey_numbers": ["102"],
                    "area": "",
                    "authority": "Mamlatdar Sami",
                    "legal_basis": "tribunal sr. no. 23",
                    "certification_status": "certified",
                    "certification_official": "",
                    "certification_date": "",
                },
            },
            {
                "input": (
                    "Entry No. 204, That Harijan Dhuda was granted the land bearing "
                    "survey no. 103, 104. This Entry shows that Land was allotted "
                    "under section 43 (Gannotdhara) of the Bombay Tenancy Act. "
                    "The entry is certified but date is not legible."
                ),
                "output": {
                    "entry_number": "204",
                    "date": "",
                    "type": "ALLOTMENT",
                    "grantee": ["Harijan Dhuda"],
                    "survey_numbers": ["103", "104"],
                    "area": "",
                    "authority": "",
                    "legal_basis": "Section 43 (Gannotdhara) of the Bombay Tenancy Act",
                    "certification_status": "certified",
                    "certification_official": "",
                    "certification_date": "",
                },
            },
        ],
    },
    "TENURE_CHANGE": {
        "fields": {
            "authority": "string",
            "order_number": "string",
            "order_date": "string",
            "survey_numbers": "[string]",
            "from_tenure": "string",
            "to_tenure": "string",
        },
        "template": (
            "That {authority} vide Order No. {order_number} dated {order_date} "
            "changed the condition of the land from {from_tenure} to {to_tenure}. "
            "The aforesaid land is free from the restrictions of {from_tenure}."
        ),
        "examples": [
            {
                "input": (
                    "Entry No. 1422 That Mamlatdar Sami vide Order No. "
                    "Jamin/Vashi/New Sharat/54451/48/1997 dated 09/09/1997 changed "
                    "the condition of the Land to old condition. The aforesaid land "
                    "is free from the restrictions of new condition. "
                    "The entry is certified but the date is not legible."
                ),
                "output": {
                    "entry_number": "1422",
                    "date": "",
                    "type": "TENURE_CHANGE",
                    "authority": "Mamlatdar Sami",
                    "order_number": "Jamin/Vashi/New Sharat/54451/48/1997",
                    "order_date": "09/09/1997",
                    "survey_numbers": [],
                    "from_tenure": "New Tenure",
                    "to_tenure": "Old Tenure",
                    "certification_status": "certified",
                    "certification_official": "",
                    "certification_date": "",
                },
            },
            {
                "input": (
                    "Entry No. 509 Dated 29/12/2009 Vide order of "
                    "Mamlatdar-Lakhpat, Order no. "
                    "Land/New/Old Condition/Worksheet/Baranda/09 dated 19/11/2009 "
                    "in old Survey No. 133p38 (Khatedar Saleman Ismail Sameja) "
                    "tenure was converted from New Tenure to Old Tenure. "
                    "The Entry is certified by Mamlatdar Lakhpat on 15/02/2010."
                ),
                "output": {
                    "entry_number": "509",
                    "date": "29/12/2009",
                    "type": "TENURE_CHANGE",
                    "authority": "Mamlatdar-Lakhpat",
                    "order_number": "Land/New/Old Condition/Worksheet/Baranda/09",
                    "order_date": "19/11/2009",
                    "survey_numbers": ["133p38"],
                    "from_tenure": "New Tenure",
                    "to_tenure": "Old Tenure",
                    "certification_status": "certified",
                    "certification_official": "Mamlatdar Lakhpat",
                    "certification_date": "15/02/2010",
                },
            },
        ],
    },
    "LAND_ACQUISITION": {
        "fields": {
            "authority": "string",
            "award_number": "string",
            "award_date": "string",
            "survey_numbers": "[string]",
            "areas": "[string]",
            "purpose": "string",
        },
        "template": (
            "That {authority} vide Award No. {award_number} dated {award_date} "
            "acquired land bearing Survey No. {survey_nos} for {purpose}."
        ),
        "examples": [
            {
                "input": (
                    "Entry No. 2987 Dated 17/03/2012, Land Acquisition officer "
                    "passed on award for the acquisition of Roda minor construction "
                    "of Swdrosan distributary vide order case no. 115/2010 dated "
                    "07/12/2011 for the following Survey Numbers: "
                    "1. Survey No. 220 - 0-04-28 Hectare "
                    "2. Survey No. 230 P - 0-06-11 Hectare "
                    "3. Survey No. 237 - 0-05-95 Hectare."
                ),
                "output": {
                    "entry_number": "2987",
                    "date": "17/03/2012",
                    "type": "LAND_ACQUISITION",
                    "authority": "Land Acquisition Officer",
                    "award_number": "115/2010",
                    "award_date": "07/12/2011",
                    "survey_numbers": ["220", "230 P", "237"],
                    "areas": ["0-04-28 Hectare", "0-06-11 Hectare", "0-05-95 Hectare"],
                    "purpose": "Roda minor construction of Swdrosan distributary",
                    "certification_status": "",
                    "certification_official": "",
                    "certification_date": "",
                },
            },
        ],
    },
    "LEASE": {
        "fields": {
            "lessor": "[string]",
            "lessee": "string",
            "survey_numbers": "[string]",
            "area": "string",
            "period": "string",
            "purpose": "string",
        },
        "template": (
            "That {lessor} leased land bearing Survey No. {survey_nos} measuring "
            "{area} to {lessee} for a period of {period} for {purpose}."
        ),
        "examples": [
            {
                "input": (
                    "Khatedar Devi wife of Gulab Chand executed a Lease Deed dated "
                    "29.04.2022 for the land parcel admeasuring 3.8850 Hectare "
                    "comprised in Khasra no. 848/313 in favour of M/s Juniper Green "
                    "Stellar Private Limited for a period of 29 years and 6 months."
                ),
                "output": {
                    "entry_number": "",
                    "date": "29/04/2022",
                    "type": "LEASE",
                    "lessor": ["Devi wife of Gulab Chand"],
                    "lessee": "M/s Juniper Green Stellar Private Limited",
                    "survey_numbers": ["848/313"],
                    "area": "3.8850 Hectare",
                    "period": "29 years and 6 months",
                    "purpose": "",
                    "certification_status": "",
                    "certification_official": "",
                    "certification_date": "",
                },
            },
        ],
    },
    "PROMULGATION": {
        "fields": {
            "authority": "string",
            "survey_number_mapping": "{old: [new]}",
            "effective_date": "string",
        },
        "template": (
            "That upon re-survey by {authority}, new survey numbers were assigned. "
            "Old Survey No. {old_surveys} became new Survey No. {new_surveys}."
        ),
        "examples": [
            {
                "input": (
                    "Entry No. 6649 Dated 21/04/2025 Vide order of Collection "
                    "Officer, Banaskantha-Palanpur, Order No. Re Survey/Promulgation/"
                    "Dhanera-Malotra/Obstruction Application No. 8785, 8786, 8788 "
                    "to 8790, 8792 to 8795/Worksheet/609/25 dated 19/02/2025 SVSR "
                    "Amendment Order No. 13 to 24/Dhanera details are as under:- "
                    "Old Survey No. 266p2 (7-59-29 Hectare) -> New Survey No. 1235 "
                    "(7-70-84 Hectare). "
                    "The Entry is certified by C.O. Jadiya on 07/05/2025."
                ),
                "output": {
                    "entry_number": "6649",
                    "date": "21/04/2025",
                    "type": "PROMULGATION",
                    "authority": "Collection Officer, Banaskantha-Palanpur",
                    "survey_number_mapping": {"266p2": ["1235"]},
                    "effective_date": "19/02/2025",
                    "certification_status": "certified",
                    "certification_official": "C.O. Jadiya",
                    "certification_date": "07/05/2025",
                },
            },
            {
                "input": (
                    "Entry No. 3055 Dated 30.11.2016 Vide Order no. "
                    "Jaman/Rasav/Pramal/Ekalava-Harij/Reg-12/2016 issued by SLR, "
                    "Office of the Settlement Commissioner and Director of Land "
                    "Records, Gandhinagar, promulgating the newly prepared re-survey "
                    "record and finalized it. Old survey numbers, area, shape were "
                    "reassigned new survey numbers, area, shape."
                ),
                "output": {
                    "entry_number": "3055",
                    "date": "30/11/2016",
                    "type": "PROMULGATION",
                    "authority": (
                        "SLR, Office of the Settlement Commissioner and Director "
                        "of Land Records, Gandhinagar"
                    ),
                    "survey_number_mapping": {},
                    "effective_date": "30/11/2016",
                    "certification_status": "",
                    "certification_official": "",
                    "certification_date": "",
                },
            },
        ],
    },
    "CORRECTION": {
        "fields": {
            "correction_type": "string",
            "original_value": "string",
            "corrected_value": "string",
            "reference_entry_number": "string",
        },
        "template": (
            "That {correction_type} was corrected from '{original_value}' to "
            "'{corrected_value}' in Entry No. {reference_entry_number}."
        ),
        "examples": [
            {
                "input": (
                    "Entry No. 422 Dated 15/12/2008 Pursuant to the order of "
                    "Mamlatdar Sahib, order no. "
                    "Land/Promulgation/Error/Worksheet/08 dated 30/08/2008, the "
                    "following corrections are made: The area for Survey No. 55/1 "
                    "is amended to 4-04-69 Hectares from the previously recorded "
                    "4-00-00 Hectares. Additionally, the name is corrected from "
                    "Sujaji Togji to Sujaji Togaji. "
                    "The Entry is certified by Revenue Mamlatdar Naliya on 06/06/2009."
                ),
                "output": {
                    "entry_number": "422",
                    "date": "15/12/2008",
                    "type": "CORRECTION",
                    "correction_type": "Area and Name correction",
                    "original_value": "Area 4-00-00 Hectares, Name Sujaji Togji",
                    "corrected_value": "Area 4-04-69 Hectares, Name Sujaji Togaji",
                    "reference_entry_number": "",
                    "certification_status": "certified",
                    "certification_official": "Revenue Mamlatdar Naliya",
                    "certification_date": "06/06/2009",
                },
            },
        ],
    },
    "NOT_RELATED": {
        "fields": {},
        "template": "This entry is not related to the present survey number(s).",
        "examples": [],
    },
    "UNAVAILABLE": {
        "fields": {},
        "template": "The data for this entry is not available.",
        "examples": [],
    },
}


def get_config_for_types(types: List[str]) -> Dict[str, Dict]:
    """Return subset of TYPE_CONFIGS for only the requested types.

    Args:
        types: List of canonical type name strings (e.g. ["SALE", "LOAN"]).

    Returns:
        Dict mapping each requested type to its config dict.
        Types not found in TYPE_CONFIGS are silently skipped.
    """
    return {t: TYPE_CONFIGS[t] for t in types if t in TYPE_CONFIGS}
