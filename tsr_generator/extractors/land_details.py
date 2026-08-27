import os
import json
import re
import logging
import traceback
# Imported lazily where used — only the Gemini extraction backend needs it,
# and the default backend is the local `claude` CLI.
from dotenv import load_dotenv

from tsr_generator.utils.text_utils import convert_gujarati_to_english_numerals, translate_gujarati_text
from tsr_generator.utils.retry_utils import retry_with_backoff, RetryableError

@retry_with_backoff(max_attempts=3, delay=2.0, exceptions=(RetryableError, ConnectionError, TimeoutError))
def extract_land_records_ai(pdf_text):
    """
    Extract land record information using dedicated AI call - for the first table.
    
    Args:
        pdf_text (str): The full text of the PDF document
        
    Returns:
        dict: Dictionary containing land record details
    """
    logger = logging.getLogger(__name__)
    logger.debug("Extracting land record details using dedicated AI call")
    
    try:
        # Initialize Gemini client
        load_dotenv()
        llm = _chat_google(
            model=os.getenv('GEMINI_MODEL_NAME', 'gemini-3.1-pro-preview'),
            google_api_key=os.getenv('GEMINI_API_KEY', ''),
            temperature=0.0,
            convert_system_message_to_human=True,
        )
        
        # Create a focused prompt for extracting land details
        prompt = f"""
        Extract these specific land record details from the text below, translating ALL Gujarati text to English.
        
        CRITICAL: The output must contain ONLY English text. Do NOT include any Gujarati characters. Translate every value.
        
        1. village_name - Name of the village (Translate to English)
        2. taluka_name - Name of the taluka (Translate to English)
        3. district_name - Name of the district (Translate to English)
        4. survey_number - Survey/Block Number
        5. total_area - Total area in the format like "2-79-23" (hectares-ares-square meters)
        6. nature_of_land - Nature/use of the land (Translate to English, e.g., "Agricultural", "Old Tenure", "New Tenure")
        7. owner - Name of the land owner or khatedar (Translate to English)
        
        Be precise and extract only what's clearly stated in the document. Look for sections labeled "Land Details" or similar.
        
        IMPORTANT: Return ONLY a valid JSON object with these exact keys. Do not include any explanatory text before or after the JSON.
        
        Example format:
        {{
            "village_name": "Example Village",
            "taluka_name": "Example Taluka",
            "district_name": "Example District",
            "survey_number": "123",
            "total_area": "2-79-23",
            "nature_of_land": "Agricultural",
            "owner": "Example Owner"
        }}
        
        Here's the document text:
        {pdf_text[:3000]}
        """
        
        try:
            response = llm.invoke(prompt)
        except Exception as e:
            # Check if this is a retryable error
            if any(term in str(e).lower() for term in ['timeout', 'connection', 'rate limit', 'server error']):
                logger.warning(f"Retryable error in AI call: {e}")
                raise RetryableError(f"AI service error: {e}")
            else:
                raise e
        
        # Parse JSON from the response robustly
        content = response.content if hasattr(response, 'content') else str(response)
        
        # Handle list responses if needed (ensure content is a string before cleaning)
        if isinstance(content, list):
            content_str = ""
            for part in content:
                if isinstance(part, str):
                    content_str += part
                elif isinstance(part, dict) and "text" in part:
                    content_str += part["text"]
            content = content_str
            
        logger.info(f"AI response received, length: {len(content)} characters")
        logger.debug(f"AI response content (first 500 chars): {content[:500]}")
        
        # Clean the content
        content = ''.join(ch for ch in content if ch == '\t' or ch == '\n' or ch == '\r' or ord(ch) >= 32)
        logger.debug(f"Cleaned content (first 500 chars): {content[:500]}")
        
        # Try multiple JSON extraction strategies
        land_details = None
        
        # Strategy 1: Look for JSON block wrapped in ```json
        json_code_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', content, re.IGNORECASE)
        if json_code_match:
            try:
                json_blob = json_code_match.group(1)
                json_blob = re.sub(r',\s*([\]\}])', r'\1', json_blob)  # Remove trailing commas
                land_details = json.loads(json_blob)
                logger.debug("Successfully parsed JSON from code block")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON from code block: {e}")
        
        # Strategy 2: Look for plain JSON object
        if not land_details:
            json_match = re.search(r'(\{[\s\S]*?\})', content)
            if json_match:
                try:
                    json_blob = json_match.group(1)
                    # Clean common JSON issues
                    json_blob = re.sub(r',\s*([\]\}])', r'\1', json_blob)  # Remove trailing commas
                    json_blob = re.sub(r'(["\w]+):\s*(["\w\s\-\(\)\.]+)(?=\s*[,\}])', 
                                     lambda m: f'{m.group(1)}: "{m.group(2).strip()}"' if not m.group(2).strip().startswith('"') else m.group(0), 
                                     json_blob)  # Quote unquoted values
                    land_details = json.loads(json_blob)
                    logger.debug("Successfully parsed JSON from plain text")
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON from plain text: {e}")
        
        # Strategy 3: Try to extract fields manually using regex if JSON parsing fails
        if not land_details:
            logger.warning("JSON parsing failed, attempting manual field extraction")
            land_details = {}
            field_patterns = {
                'village_name': r'(?:village_name|Village)["\s]*[:=]\s*["\']?([^"\'،\n,]+)',
                'taluka_name': r'(?:taluka_name|Taluka)["\s]*[:=]\s*["\']?([^"\'،\n,]+)',
                'district_name': r'(?:district_name|District)["\s]*[:=]\s*["\']?([^"\'،\n,]+)',
                'survey_number': r'(?:survey_number|Survey)["\s]*[:=]\s*["\']?([^"\'،\n,]+)',
                'total_area': r'(?:total_area|Area)["\s]*[:=]\s*["\']?([^"\'،\n,]+)',
                'nature_of_land': r'(?:nature_of_land|Nature)["\s]*[:=]\s*["\']?([^"\'،\n,]+)',
                'owner': r'(?:owner|Owner)["\s]*[:=]\s*["\']?([^"\'،\n,]+)'
            }
            
            for field, pattern in field_patterns.items():
                match = re.search(pattern, content, re.IGNORECASE)
                land_details[field] = match.group(1).strip() if match else 'Not Available'
        
        if land_details:
            logger.debug(f"Successfully extracted land details: {land_details}")
            return land_details
        else:
            logger.warning("All JSON parsing strategies failed")
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
    logger.debug("Extracting land details using dedicated AI approach")
    
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
        
        logger.debug(f"Land details extracted: {json.dumps(land_details, indent=2)}")
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

def _chat_google(**kwargs):
    """Construct the Gemini chat client, importing langchain only when needed."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(**kwargs)
