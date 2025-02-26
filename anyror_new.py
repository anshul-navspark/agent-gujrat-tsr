from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
import time
import os
import base64
from PIL import Image
import io
import re
from selenium.webdriver.chrome.service import Service
import logging
from datetime import datetime
import traceback
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage
from pydantic import SecretStr
import tempfile
from webdriver_manager.chrome import ChromeDriverManager

def setup_logging():
    """Setup logging configuration"""
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Create a timestamp for the log file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = f'logs/anyror_{timestamp}.log'

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()  # Also print to console
        ]
    )
    
    # Disable verbose logging from Selenium/urllib3
    logging.getLogger('selenium').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)

def recognize_captcha_with_llm(image_data, logger):
    """Use Azure OpenAI to recognize captcha"""
    logger.info("Using LLM to recognize captcha")
    try:
        # Initialize the LLM
        llm = AzureChatOpenAI(
            model="gpt-4o",
            api_version='2024-02-15-preview',
            azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT', ''),
            api_key=SecretStr(os.getenv('AZURE_OPENAI_KEY', '')),
            temperature=0.0
        )
        
        # Convert image data to base64 for sending to the LLM
        img = Image.open(io.BytesIO(image_data))
        
        # Save to a temporary file
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            img.save(temp_file, format='PNG')
            temp_file_path = temp_file.name
        
        # Create a message with the image
        message = HumanMessage(
            content=[
                {
                    "type": "text", 
                    "text": "This is a captcha image. Please identify the 6 digits shown in the image. Return ONLY the digits with no additional text or explanation."
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64.b64encode(open(temp_file_path, 'rb').read()).decode('utf-8')}"
                    }
                }
            ]
        )
        
        # Get response from LLM
        response = llm.invoke([message])
        
        # Clean up the temporary file
        os.unlink(temp_file_path)
        
        # Extract only digits from the response
        captcha_text = ''.join(re.findall(r'\d', response.content))
        
        logger.info(f"LLM recognized captcha: {captcha_text}")
        return captcha_text
        
    except Exception as e:
        logger.error(f"Error recognizing captcha with LLM: {str(e)}")
        logger.error(traceback.format_exc())
        return None

def fetch_land_record(district_name, taluka_name, village_name, survey_block_number, output_path, logger=None):
    """Function version of main() that returns results rather than printing them"""
    if logger is None:
        logger = setup_logging()
    
    logger.info("Starting AnyRoR automation script as API function")
    logger.info(f"Parameters - District: {district_name}, Taluka: {taluka_name}, "
                f"Village: {village_name}, Survey/Block: {survey_block_number}")
    
    try:
        # Initialize Chrome options
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--headless")  # Run in headless mode for API usage
        
        # Initialize the driver with webdriver-manager
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        wait = WebDriverWait(driver, 30)

        # Navigate to website
        logger.info("Navigating to AnyRoR website")
        driver.get("https://anyror.gujarat.gov.in/LandRecordRural.aspx")

        # --- Step 1: Select Land Record Type ---
        logger.info("Selecting Land Record Type")
        land_record_dropdown = wait.until(
            EC.visibility_of_element_located((By.ID, "ContentPlaceHolder1_drpLandRecord"))
        )
        select_land_record = Select(land_record_dropdown)
        select_land_record.select_by_value("8")
        logger.info("Selected Land Record Type: INTEGRATED SURVEY NO DETAILS")
        time.sleep(2)

        # --- Step 2: Set the District ---
        logger.info(f"Selecting District: {district_name}")
        district_dropdown = wait.until(
            EC.element_to_be_clickable((By.ID, "ContentPlaceHolder1_ddlDistrict"))
        )
        select_district = Select(district_dropdown)
        for option in select_district.options:
            if option.text.strip() == district_name:
                select_district.select_by_visible_text(district_name)
                logger.info("District selected successfully")
                break
        time.sleep(2)

        # --- Step 3: Set the Taluka ---
        logger.info(f"Selecting Taluka: {taluka_name}")
        taluka_dropdown = wait.until(
            EC.element_to_be_clickable((By.ID, "ContentPlaceHolder1_ddlTaluka"))
        )
        select_taluka = Select(taluka_dropdown)
        found_taluka = False
        for option in select_taluka.options:
            if taluka_name in option.text.strip():
                select_taluka.select_by_visible_text(option.text.strip())
                found_taluka = True
                logger.info("Taluka selected successfully")
                break
        
        if not found_taluka:
            logger.error(f"Taluka '{taluka_name}' not found in dropdown")
            return {
                'success': False,
                'error': f"Taluka '{taluka_name}' not found in dropdown"
            }
        time.sleep(2)

        # --- Step 4: Set the Village ---
        logger.info(f"Selecting Village: {village_name}")
        village_dropdown = wait.until(
            EC.element_to_be_clickable((By.ID, "ContentPlaceHolder1_ddlVillage"))
        )
        select_village = Select(village_dropdown)
        found_village = False
        for option in select_village.options:
            if village_name in option.text.strip():
                select_village.select_by_visible_text(option.text.strip())
                found_village = True
                logger.info("Village selected successfully")
                break
        
        if not found_village:
            logger.error(f"Village '{village_name}' not found in dropdown")
            return {
                'success': False,
                'error': f"Village '{village_name}' not found in dropdown"
            }
        time.sleep(2)

        # --- Step 5: Enter Survey/Block Number ---
        logger.info(f"Selecting Survey/Block Number: {survey_block_number}")
        survey_dropdown = wait.until(
            EC.element_to_be_clickable((By.ID, "ContentPlaceHolder1_ddlSurveyNo"))
        )
        select_survey = Select(survey_dropdown)
        found_survey = False
        for option in select_survey.options:
            if survey_block_number in option.text.strip():
                select_survey.select_by_visible_text(option.text.strip())
                found_survey = True
                logger.info("Survey/Block Number selected successfully")
                break
        if not found_survey:
            logger.error(f"Survey/Block Number not found matching: {survey_block_number}")
        time.sleep(2)

        # --- Step 6: Handle Captcha with AI ---
        logger.info("Starting captcha recognition process")
        
        # Capture captcha image data
        captcha_img = wait.until(
            EC.visibility_of_element_located((By.ID, "ContentPlaceHolder1_i_captcha_1"))
        )
        
        # Convert captcha to base64
        captcha_base64 = driver.execute_script("""
            var canvas = document.createElement('canvas');
            var context = canvas.getContext('2d');
            var img = document.getElementById('ContentPlaceHolder1_i_captcha_1');
            canvas.width = img.width;
            canvas.height = img.height;
            context.drawImage(img, 0, 0);
            return canvas.toDataURL('image/png').replace(/^data:image\/(png|jpg);base64,/, '');
        """)
        
        # Decode base64 to binary data
        captcha_data = base64.b64decode(captcha_base64)
        
        captcha_value = recognize_captcha_with_llm(captcha_data, logger)
        captcha_input = wait.until(
            EC.visibility_of_element_located((By.ID, "ContentPlaceHolder1_txt_captcha_1"))
        )
        captcha_input.clear()
        captcha_input.send_keys(captcha_value)
        logger.info(f"Entered captcha value: {captcha_value}")
        time.sleep(1)

        # --- Step 7: Submit the form ---
        logger.info("Submitting the form")
        submit_button = wait.until(
            EC.element_to_be_clickable((By.ID, "ContentPlaceHolder1_btnGo"))
        )
        submit_button.click()
        
        # Check for alert (captcha error)
        try:
            WebDriverWait(driver, 2).until(EC.alert_is_present())
            alert = driver.switch_to.alert
            alert_text = alert.text
            logger.warning(f"Alert present: {alert_text}")
            alert.accept()
            
            if "Capcha is not matched" in alert_text:
                # Try again with a new captcha
                return {
                    'success': False,
                    'error': f"Captcha not matched: {alert_text}"
                }
            else:
                # Some other error
                return {
                    'success': False,
                    'error': f"Alert: {alert_text}"
                }
        except:
            # No alert means success
            logger.info("Form submitted successfully")

        # --- Step 8: Generate PDF ---
        logger.info("Attempting to generate PDF")
        
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        try:
            result = driver.execute_cdp_cmd("Page.printToPDF", {"printBackground": True})
            pdf_data = result.get("data")
            if pdf_data:
                # Use the provided output_path instead of hardcoding the path
                with open(output_path, "wb") as f:
                    f.write(base64.b64decode(pdf_data))
                logger.info(f"PDF saved successfully to: {output_path}")
                return {
                    'success': True,
                    'pdf_path': output_path
                }
            else:
                logger.error("PDF generation did not return any data")
                return {
                    'success': False,
                    'error': "PDF generation did not return any data"
                }
        except Exception as e:
            logger.error(f"Error generating PDF: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': f"PDF generation error: {str(e)}"
            }
            
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            'success': False,
            'error': str(e)
        }
    finally:
        if 'driver' in locals():
            driver.quit()
        logger.info("Script execution completed")

def main():
    # Setup logging
    logger = setup_logging()
    logger.info("Starting AnyRoR automation script")

    # --- User-defined parameters ---
    district_name = "પાટણ"         # Desired District (જીલ્લો)
    taluka_name = "પાટણ"           # Desired Taluka (તાલુકો)
    village_name = "અનાવાડા - 091"  # Desired Village (ગામ)
    survey_block_number = "0z૧"     # Survey/Block Number
    output_path = os.path.join(os.path.expanduser("~"), "Downloads", "land_record.pdf")

    logger.info(f"Parameters - District: {district_name}, Taluka: {taluka_name}, "
                f"Village: {village_name}, Survey/Block: {survey_block_number}")
    
    # Call the function version with the parameters
    result = fetch_land_record(
        district_name=district_name,
        taluka_name=taluka_name,
        village_name=village_name,
        survey_block_number=survey_block_number,
        output_path=output_path,
        logger=logger
    )
    
    if result['success']:
        logger.info(f"Land record fetched successfully: {result['pdf_path']}")
    else:
        logger.error(f"Failed to fetch land record: {result['error']}")

if __name__ == "__main__":
    main()