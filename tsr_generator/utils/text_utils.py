import re

def convert_gujarati_to_english_numerals(text):
    """
    Convert Gujarati numerals to English numerals
    
    Args:
        text (str): Text containing Gujarati numerals
        
    Returns:
        str: Text with Gujarati numerals converted to English
    """
    if text is None:
        return "Not Available"
    
    mapping = {
        '૦': '0', '૧': '1', '૨': '2', '૩': '3', '૪': '4',
        '૫': '5', '૬': '6', '૭': '7', '૮': '8', '૯': '9'
    }
    
    result = ""
    for char in text:
        if char in mapping:
            result += mapping[char]
        else:
            result += char
    
    return result

def sanitize_text(text):
    """
    Remove NULL bytes and control characters that cause XML compatibility issues.
    
    Args:
        text (str): Text to sanitize
        
    Returns:
        str: Sanitized text
    """
    if text is None:
        return "Not Available"
    
    # Convert to string if not already
    text = str(text)
    
    # Remove NULL bytes and control characters (0x00-0x1F except for \t, \n, \r)
    sanitized = ""
    for char in text:
        # Skip NULL bytes and most control characters
        if ord(char) == 0 or (0 < ord(char) < 32 and char not in '\t\n\r'):
            continue
        sanitized += char
    
    # If string became empty after sanitizing, return placeholder
    if not sanitized.strip():
        return "Not Available"
    
    return sanitized

def translate_gujarati_text(text):
    """
    Translate common Gujarati terms to English for TSR
    
    Args:
        text (str): Text containing Gujarati terms
        
    Returns:
        str: Text with Gujarati terms translated to English
    """
    translations = {
        'મોલગેશન': 'Promulgation',
        'હુકમથી': 'Order',
        'માત': 'Certified',
        'પ્રમાણિત': 'Certified',
        'ખેતીલાયક ઉપયોગ': 'Agricultural Use',
        'જુની શરત': 'Old Tenure',
        'સરવે નંબર': 'Survey Number',
        'અબડાસા': 'Abdasa',
        'વલસરા': 'Valsara',
        'કચ્છ': 'Kachchh',
        # Enhanced translation dictionary with additional terms
        'વેચાણ': 'Sale',
        'દાન': 'Gift',
        'મૃત્યુ': 'Death',
        'વારસાઈ': 'Inheritance',
        'લોન': 'Loan',
        'ચાર્જ': 'Charge',
        'મુક્તિ': 'Release',
        'હક્ક છોડી': 'Relinquish',
        'વિતરણ': 'Distribution',
        'વહેંચણી': 'Partition',
        'વિભાજન': 'Partition',
        'જીવનકાળ વિતરણ': 'Lifetime Distribution',
        'ભાગલા': 'Partition',
        # Adding new translations
        'ભાવનગર': 'Bhavnagar',
        'તળાજા': 'Talaja',
        'દાઠા': 'Datha'
    }
    
    # Apply translations
    translated = text
    for guj, eng in translations.items():
        translated = re.sub(rf'\b{re.escape(guj)}\b', eng, translated)
    
    return translated 