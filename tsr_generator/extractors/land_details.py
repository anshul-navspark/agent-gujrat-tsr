import os
import json
import re
import logging
import traceback
from langchain_openai import AzureChatOpenAI
from pydantic import SecretStr
from dotenv import load_dotenv

from tsr_generator.utils.text_utils import convert_gujarati_to_english_numerals, translate_gujarati_text

def extract_land_records_ai(pdf_text):
    """
    Extract land record information using dedicated AI call - for the first table.
    
    Args:
        pdf_text (str): The full text of the PDF document
        
    Returns:
        dict: Dictionary containing land record details
    """
    logger = logging.getLogger(__name__)
    logger.info("Extracting land record details using dedicated AI call")
    
    try:
        # Initialize Azure OpenAI client
        load_dotenv()
        llm = AzureChatOpenAI(
            model="gpt-4o",
            api_version='2024-02-15-preview',
            azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT', ''),
            api_key=SecretStr(os.getenv('AZURE_OPENAI_KEY', '')),
            temperature=0.0
        )
        
        # Create a focused prompt for extracting land details
        prompt = f"""
        Extract these specific land record details from the text below, translating from Gujarati to English as needed:
        
        1. village_name - Name of the village
        2. taluka_name - Name of the taluka
        3. district_name - Name of the district 
        4. survey_number - Survey/Block Number
        5. total_area - Total area in the format like "2-79-23" (hectares-ares-square meters)
        6. nature_of_land - Nature/use of the land (like agricultural, old tenure,new tenure etc.)
        7. owner - Name of the land owner or khatedar
        
        Be precise and extract only what's clearly stated in the document. Look for sections labeled "Land Details" or similar.
        Format your response as a JSON object with these exact keys.
        
        Here's the document text:
        {pdf_text[:3000]}
        """
        
        response = llm.invoke(prompt)
        
        # Parse JSON from the response
        json_match = re.search(r'({.*})', response.content, re.DOTALL)
        if json_match:
            land_details = json.loads(json_match.group(1))
            logger.info(f"Successfully extracted land details: {land_details}")
            return land_details
        else:
            logger.warning("Failed to parse JSON from AI response for land details")
            return {
                'village_name': 'Not Available',
                'taluka_name': 'Not Available',
                'district_name': 'Not Available',
                'survey_number': 'Not Available',
                'total_area': 'Not Available',
                'nature_of_land': 'Not Available',
                'owner': 'Not Available'
            }
    
    except Exception as e:
        logger.error(f"Error in AI-based land record extraction: {str(e)}")
        return {
            'village_name': 'Not Available',
            'taluka_name': 'Not Available',
            'district_name': 'Not Available',
            'survey_number': 'Not Available',
            'total_area': 'Not Available',
            'nature_of_land': 'Not Available',
            'owner': 'Not Available'
        }

def extract_land_details(pdf_text):
    """
    Extract land details dynamically from the PDF using the dedicated AI-based approach.
    
    Args:
        pdf_text (str): The full text of the PDF document
        
    Returns:
        dict: Dictionary containing processed land details
    """
    logger = logging.getLogger(__name__)
    logger.info("Extracting land details using dedicated AI approach")
    
    try:
        # Use the dedicated AI function to extract land details
        land_details = extract_land_records_ai(pdf_text)
        
        # Ensure all required fields exist
        required_fields = [
            'village_name', 'taluka_name', 'district_name', 'survey_number', 
            'total_area', 'nature_of_land', 'owner'
        ]
        
        for field in required_fields:
            if field not in land_details or not land_details[field]:
                land_details[field] = 'Not Available'
        
        # Add old_survey_number if not present
        if 'old_survey_number' not in land_details:
            land_details['old_survey_number'] = 'Not Available'
        
        # Convert Gujarati numerals in all text fields
        for key, value in land_details.items():
            if isinstance(value, str):
                land_details[key] = convert_gujarati_to_english_numerals(value)
                land_details[key] = translate_gujarati_text(land_details[key])
        
        logger.info(f"Land details extracted: {json.dumps(land_details, indent=2)}")
        return land_details
        
    except Exception as e:
        logger.error(f"Error extracting land details: {str(e)}")
        logger.error(traceback.format_exc())
        # Return default values
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