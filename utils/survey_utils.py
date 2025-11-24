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

def get_alternative_survey_formats(survey):
    """
    Generate alternative formats for a survey number to increase the chances of finding a match.
    
    Args:
        survey (str): The original survey number
        
    Returns:
        list: A list of alternative formats for the survey number
    """
    # Convert to string if not already
    survey = str(survey).strip()
    
    # Start with the original survey as the first alternative
    alternative_formats = [survey]
    
    # Extract the base number (everything before the first slash or non-digit)
    base_match = re.match(r'^(\d+)', survey)
    if not base_match:
        # If no base number found, return just the original
        return alternative_formats
    
    base_number = base_match.group(1)
    
    # Extract the suffix (everything after the base number)
    suffix = survey[len(base_number):]
    suffix_lower = suffix.lower()
    
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
    
    # Handle special complex patterns
    if '/paq' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/પા૧",
            f"{base_number}/પૈ",
            f"{base_number}/પૈકી",
            f"{base_number}/પૈ/પૈ"
        ])
    elif '/pae' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/પાૈ",
            f"{base_number}/પૈ",
            f"{base_number}/પૈકી",
            f"{base_number}/પૈ/પૈ"
        ])
    elif '/pac' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/પાચ",
            f"{base_number}/પૈ",
            f"{base_number}/પૈકી",
            f"{base_number}/પૈ/પૈ"
        ])
    elif '/pu' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/પુ",
            f"{base_number}/પૈ",
            f"{base_number}/ર",
            f"{base_number}/ૈ",
            f"{base_number}/પૈકી",
            f"{base_number}/પૈ/પૈ",
            f"{base_number}/pa",
            f"{base_number}/pe",
            f"{base_number}/q",
            f"{base_number}/e"
        ])
    elif '/pa3e' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/પા૩ૈ",
            f"{base_number}/પૈ",
            f"{base_number}/પૈકી",
            f"{base_number}/પૈ/પૈ"
        ])
    elif '/pax' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/પાક્ષ",
            f"{base_number}/પૈ",
            f"{base_number}/પૈકી",
            f"{base_number}/પૈ/પૈ"
        ])
    elif '/pax/pa' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/પાક્ષ/પા",
            f"{base_number}/પૈ/પૈ",
            f"{base_number}/પૈકી/પૈકી"
        ])
    elif '/pa30' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/પા૩૦",
            f"{base_number}/પૈ",
            f"{base_number}/પૈકી"
        ])
    # Handle complex patterns with multiple components
    elif '/p1/p1' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/p૧/p૧",
            f"{base_number}/પ૧/પ૧",
            f"{base_number}/p1/p1",
            f"{base_number}/પૈ/પૈ",
            f"{base_number}/પૈકી/પૈકી"
        ])
    elif '/p2/p2' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/p૨/p૨",
            f"{base_number}/પ૨/પ૨",
            f"{base_number}/p2/p2",
            f"{base_number}/પૈ/પૈ",
            f"{base_number}/પૈકી/પૈકી"
        ])
    elif '/p3/p3' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/p૩/p૩",
            f"{base_number}/પ૩/પ૩",
            f"{base_number}/p3/p3",
            f"{base_number}/પૈ/પૈ",
            f"{base_number}/પૈકી/પૈકી"
        ])
    # Handle p1, p2, p3 patterns
    elif '/p1' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/p૧",
            f"{base_number}/પ૧",
            f"{base_number}/p1",
            f"{base_number}/૧"
        ])
    elif '/p2' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/p૨",
            f"{base_number}/પ૨",
            f"{base_number}/p2",
            f"{base_number}/૨"
        ])
    elif '/p3' in suffix_lower:
        alternative_formats.extend([
            f"{base_number}/p૩",
            f"{base_number}/પ૩",
            f"{base_number}/p3",
            f"{base_number}/૩"
        ])
    # Handle direct digit patterns
    elif re.search(r'/\d', suffix):
        digit = re.search(r'/(\d)', suffix).group(1)
        gujarati_digit = digit_map.get(digit, digit)
        alternative_formats.extend([
            f"{base_number}/{gujarati_digit}",
            f"{base_number}/p{gujarati_digit}",
            f"{base_number}/{digit}"
        ])
    # Check for paiki paiki notation (abbreviated as "pa/pa" in English)
    elif re.search(r'/pa/pa', suffix_lower) or re.search(r'/પૈ/પૈ', suffix):
        alternative_formats.extend([
            f"{base_number}/પૈ/પૈ",
            f"{base_number}/પૈકી/પૈકી"
        ])
    # Check for paiki notation (abbreviated as "pa" in English)
    elif re.search(r'/pa', suffix_lower) or re.search(r'/પૈ', suffix):
        alternative_formats.extend([
            f"{base_number}/પૈ",
            f"{base_number}/પૈકી"
        ])
    
    return alternative_formats

def sanitize_filename(filename):
    """Convert a string to a valid filename by replacing invalid characters"""
    # Ensure filename is a string
    filename = str(filename).strip()
    # Replace slashes and other problematic characters with underscores
    return re.sub(r'[\\/*?:"<>|]', '_', filename)
