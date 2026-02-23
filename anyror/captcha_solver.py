"""
CAPTCHA Solver for Gujarat Land Record Automation

Handles CAPTCHA recognition using Google Gemini AI.
"""

import os
import io
import re
import base64
import time
import tempfile
import logging
import traceback
from PIL import Image, ImageEnhance
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from pydantic import SecretStr


class CaptchaSolver:
    """Handles CAPTCHA recognition using Google Gemini."""
    
    def __init__(self, logger=None):
        """
        Initialize the CAPTCHA solver.
        
        Args:
            logger: Logger instance for logging.
        """
        self.logger = logger or logging.getLogger(__name__)
        self.llm = self._initialize_llm()
        
    def _initialize_llm(self):
        """
        Initialize the LLM client.
        
        Returns:
            An initialized LLM client.
        """
        api_key = SecretStr(os.getenv('GEMINI_API_KEY', ''))
        return ChatGoogleGenerativeAI(
            model=os.getenv('GEMINI_MODEL_NAME', 'gemini-2.5-flash'),
            google_api_key=api_key.get_secret_value(),
            temperature=0.0,
            convert_system_message_to_human=True,
        )
    
    def solve(self, image_data, max_attempts=3):
        """
        Recognize CAPTCHA from image data.
        
        Args:
            image_data: Binary image data of the CAPTCHA.
            max_attempts: Maximum number of attempts to solve the captcha.
            
        Returns:
            The recognized CAPTCHA text or None if recognition failed.
        """
        for attempt in range(max_attempts):
            self.logger.debug(f"Using LLM to recognize captcha (attempt {attempt + 1}/{max_attempts})")
            try:
                # Convert image data to base64 for sending to the LLM
                img = Image.open(io.BytesIO(image_data))
                
                # ENHANCEMENT: Preprocess image for better recognition
                # This is especially important in Cloud Run where image quality might be lower
                try:
                    # Convert to RGB if needed
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    # Resize if too small (improves recognition)
                    if img.width < 200 or img.height < 100:
                        scale_factor = max(200 / img.width, 100 / img.height)
                        new_size = (int(img.width * scale_factor), int(img.height * scale_factor))
                        img = img.resize(new_size, Image.Resampling.LANCZOS)
                        self.logger.debug(f"Resized captcha image to {new_size}")
                    
                    # Enhance contrast for better digit recognition
                    enhancer = ImageEnhance.Contrast(img)
                    img = enhancer.enhance(1.5)  # Increase contrast by 50%
                    
                    # Enhance sharpness
                    enhancer = ImageEnhance.Sharpness(img)
                    img = enhancer.enhance(2.0)  # Double the sharpness
                    
                    self.logger.debug("Applied image preprocessing for better recognition")
                except Exception as e:
                    self.logger.warning(f"Image preprocessing failed, using original: {e}")
                
                # Save to a temporary file
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                    img.save(temp_file, format='PNG', quality=95)
                    temp_file_path = temp_file.name
                
                try:
                    # Create a message with the image - enhanced prompt for better recognition
                    message = HumanMessage(
                        content=[
                            {
                                "type": "text", 
                                "text": """This is a CAPTCHA image containing exactly 6 numeric digits (0-9).
Please carefully examine the image and identify all 6 digits from left to right.
The digits may be slightly distorted or have noise, but focus on the core shapes.
Return ONLY the 6 digits as a single number with no spaces, punctuation, or explanation.
Example response format: 123456"""
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64.b64encode(open(temp_file_path, 'rb').read()).decode('utf-8')}"
                                }
                            }
                        ]
                    )
                    
                    # Direct LLM call (avoid signal and thread timers for Streamlit compatibility)
                    try:
                        response = self.llm.invoke([message])
                    except Exception as e:
                        self.logger.error(f"LLM request failed on attempt {attempt + 1}: {str(e)}")
                        self.logger.error(traceback.format_exc())
                        if attempt < max_attempts - 1:
                            time.sleep(1)  # Brief delay before retry
                            continue
                        return None
                    
                    # Clean up the temporary file
                    try:
                        os.unlink(temp_file_path)
                    except Exception:
                        pass
                    
                    # Extract only digits from the response
                    content = response.content
                    if isinstance(content, list):
                        # Handle cases where content is a list of parts (common in newer models/APIs)
                        content_str = ""
                        for part in content:
                            if isinstance(part, str):
                                content_str += part
                            elif isinstance(part, dict) and "text" in part:
                                content_str += part["text"]
                        content = content_str
                    
                    captcha_text = ''.join(re.findall(r'\d', content))
                    
                    if len(captcha_text) == 6:  # Verify we got exactly 6 digits
                        self.logger.debug(f"LLM recognized captcha: {captcha_text} (attempt {attempt + 1})")
                        return captcha_text
                    elif len(captcha_text) > 6:
                        # Take first 6 digits if more were found
                        captcha_text = captcha_text[:6]
                        self.logger.debug(f"LLM returned {len(captcha_text)} digits, using first 6: {captcha_text} (attempt {attempt + 1})")
                        return captcha_text
                    else:
                        self.logger.warning(f"Attempt {attempt + 1}: Invalid captcha format (got {len(captcha_text)} digits): {response.content}")
                        if attempt < max_attempts - 1:
                            time.sleep(1)  # Brief delay before retry
                            continue
                        return None
                        
                except Exception as e:
                    self.logger.error(f"Error in LLM processing on attempt {attempt + 1}: {str(e)}")
                    self.logger.error(traceback.format_exc())
                    try:
                        os.unlink(temp_file_path)
                    except Exception:
                        pass
                    if attempt < max_attempts - 1:
                        time.sleep(1)
                        continue
                    return None
                    
            except Exception as e:
                self.logger.error(f"Error recognizing captcha with LLM on attempt {attempt + 1}: {str(e)}")
                self.logger.error(traceback.format_exc())
                if attempt < max_attempts - 1:
                    time.sleep(1)
                    continue
                return None
        
        return None
