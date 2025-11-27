import re

def convert_survey_number(survey_number):
    """
    Convert survey numbers to the format expected by the website.
    
    The website expects survey numbers in specific formats:
    - Simple numbers (e.g., "142", "143") remain unchanged
    - Numbers with paiki (પૈકી) are formatted as "number/પૈ" (e.g., "145/પૈ")
    - Numbers with paiki paiki (પૈકી પૈકી) are formatted as "number/પૈ/પૈ" (e.g., "144/પૈ/પૈ")
    - Numbers with 'q' or 'ર' are formatted as "number/ર" (e.g., "154/ર")
    - Numbers with 'e' or 'ૈ' are formatted as "number/ૈ" (e.g., "161/ૈ")
    - Numbers with 'p1' are formatted as "number/p૧" (with Gujarati numeral ૧)
    - Numbers with 'p2' are formatted as "number/p૨" (with Gujarati numeral ૨)
    - Numbers with 'p3' are formatted as "number/p૩" (with Gujarati numeral ૩)
    - Numbers with 'p4' are formatted as "number/p૪" (with Gujarati numeral ૪)
    - Numbers with '/1' are formatted as "/૧" (with Gujarati numeral ૧)
    - Numbers with '/2' are formatted as "/૨" (with Gujarati numeral ૨)
    - Numbers with '/3' are formatted as "/૩" (with Gujarati numeral ૩)
    - Numbers with '/4' are formatted as "/૪" (with Gujarati numeral ૪)
    
    Args:
        survey_number (str): The original survey number
        
    Returns:
        str: The converted survey number
    """
    # Convert to string if not already
    survey_number = str(survey_number).strip()
    
    # Remove any spaces in the survey number
    survey_number = survey_number.replace(" ", "")
    
    # Simple conversion rules based on patterns
    if re.match(r'^\d+$', survey_number):
        # Simple number, no conversion needed
        return survey_number
    
    # Extract the base number (everything before the first slash or non-digit)
    base_match = re.match(r'^(\d+)', survey_number)
    if not base_match:
        # If no base number found, return as is
        return survey_number
    
    base_number = base_match.group(1)
    
    # Dictionary to map Latin digits to Gujarati digits
    digit_map = {
        '0': '૦',
        '1': '૧',
        '2': '૨',
        '3': '૩',
        '4': '૪',
        '5': '૫',
        '6': '૬',
        '7': '૭',
        '8': '૮',
        '9': '૯'
    }
    
    # Extract the suffix (everything after the base number)
    suffix = survey_number[len(base_number):]
    suffix_lower = suffix.lower()
    
    # Handle Datha list specific patterns first
    if re.search(r'[/\s]?p(\d)', suffix_lower):
        # Extract the number after 'p'
        p_number = re.search(r'[/\s]?p(\d)', suffix_lower).group(1)
        # Convert to Gujarati number
        guj_number = digit_map.get(p_number, p_number)
        return f"{base_number}/p{guj_number}"
    
    # Handle other patterns
    if '/paq' in suffix_lower:
        return f"{base_number}/પા૧"
    elif '/pae' in suffix_lower:
        return f"{base_number}/પાૈ"
    elif '/pac' in suffix_lower:
        return f"{base_number}/પાચ"
    elif '/pu' in suffix_lower:
        return f"{base_number}/પુ"
    elif '/pa3e' in suffix_lower:
        return f"{base_number}/પા૩ૈ"
    elif '/pax' in suffix_lower:
        return f"{base_number}/પાક્ષ"
    elif '/pax/pa' in suffix_lower:
        return f"{base_number}/પાક્ષ/પા"
    elif '/pa30' in suffix_lower:
        return f"{base_number}/પા૩૦"
    
    # Handle complex patterns with multiple components
    if '/p1/p1' in suffix_lower:
        return f"{base_number}/p૧/p૧"
    elif '/p2/p2' in suffix_lower:
        return f"{base_number}/p૨/p૨"
    elif '/p3/p3' in suffix_lower:
        return f"{base_number}/p૩/p૩"
    elif '/p4/p4' in suffix_lower:
        return f"{base_number}/p૪/p૪"
    
    # Handle direct digit patterns (convert /1 to /૧, etc.)
    suffix = re.sub(r'/(\d)', lambda m: f"/{digit_map[m.group(1)]}", suffix)
    
    # If we've modified the suffix but none of the specific patterns matched
    if suffix != survey_number[len(base_number):]:
        return f"{base_number}{suffix}"
    
    # If no pattern matches, return as is
    return survey_number


def sanitize_filename(filename):
    """Convert a string to a valid filename by replacing invalid characters"""
    # Ensure filename is a string
    filename = str(filename).strip()
    # Replace slashes and other problematic characters with underscores
    return re.sub(r'[\\/*?:"<>|]', '_', filename)
