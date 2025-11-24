import logging

# English to Gujarati translation dictionaries
DISTRICT_TRANSLATIONS = {
    "Patan": "પાટણ",
    "Kutch": "કચ્છ",
    "Bhuj": "ભુજ",
    "Kachchh": "કચ્છ",
    "Banaskantha": "બનાસકાંઠા",
    "Bhavnagar": "ભાવનગર",
    "Jamnagar": "જામનગર",
}

TALUKA_TRANSLATIONS = {
    "Patan": "પાટણ",
    "Bhuj": "ભુજ",
    "Anjar": "અંજાર",
    "Abdasa": "અબડાસા",
    "Dhanera": "ધાનેરા",
    "Talaja": "તળાજા",
    "Jamjodhpur": "જામજોધપુર",
    "Jamkhadaba": "જામજોધપુર",
}

VILLAGE_TRANSLATIONS = {
    "Anavada": "અનાવાડા - 091",
    "Trambo": "ત્રંબો - 033",
    "Trambau": "ત્રંબો - 033",

    "Edal": "એડાલ - 031",
    "Jadi": "જાડી - 029",
    "Jadiya" :"જડીયા - 018",
    "Janali": "જનાલી - 033",
    "Shiya": "શિયા - 030",
    "Malotra": "માલોત્રા - 050",
    "Datha": "દાઠા",
    
    # Hothiji Khadaba variations
    "Hothiji Khadba": "હોથીજી ખડબા - 034",
    "Hothiji Khadaba": "હોથીજી ખડબા - 034", 
    "Hothiji Khadba Abdasa": "હોથીજી ખડબા - 034",
    "Hothiji Khadaba Abdasa": "હોથીજી ખડબા - 034",
    "હોથીજી ખડબા": "હોથીજી ખડબા - 034",
    "Hothiji": "હોથીજી ખડબા - 034",
    "Khadaba": "હોથીજી ખડબા - 034",
    "Nagiya": "નાંગીયા - 031",
    "RAMPAR ABDA": "રામપર(અબડા) - 034",
    "Rampar Abda": "રામપર(અબડા) - 034",
    "Rampr(Abda)": "રામપર(અબડા) - 034",
    "RamprAbda": "રામપર(અબડા) - 034",
    "Rampar (Abda)": "રામપર(અબડા) - 034",
}

def translate_to_gujarati(text, translation_dict, default=None):
    """Translate English text to Gujarati using the provided dictionary"""
    if not text:
        return default or text
    
    # Try direct lookup
    if text in translation_dict:
        return translation_dict[text]
    
    # Try case-insensitive lookup
    for eng, guj in translation_dict.items():
        if eng.lower() == text.lower():
            return guj
    
    # If no match found, return original text or default
    logger = logging.getLogger(__name__)
    logger.warning(f"No Gujarati translation found for: {text}")
    return default or text
