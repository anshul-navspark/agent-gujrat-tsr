from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
import time
import os
import base64
from PIL import Image
import io
import easyocr
import re
from selenium.webdriver.chrome.service import Service
import logging
from datetime import datetime
import traceback

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
    return logging.getLogger(__name__)

def preprocess_captcha_image(image_data, logger):
    """Preprocess the captcha image to improve OCR accuracy"""
    logger.info("Starting captcha image preprocessing")
    try:
        img = Image.open(io.BytesIO(image_data))
        # Convert to grayscale
        img = img.convert('L')
        # Increase contrast
        img = img.point(lambda x: 0 if x < 128 else 255, '1')
        logger.info("Successfully preprocessed captcha image")
        return img
    except Exception as e:
        logger.error(f"Error preprocessing captcha image: {str(e)}")
        logger.error(traceback.format_exc())
        raise

def extract_digits_from_text(text, logger):
    """Extract digits from OCR text and ensure we get exactly 6 digits"""
    logger.info(f"Extracting digits from OCR text: {text}")
    digits = ''.join(re.findall(r'\d', text))
    logger.info(f"Extracted digits: {digits}")
    if len(digits) == 6:
        logger.info("Successfully extracted 6 digits")
        return digits
    logger.warning(f"Failed to extract exactly 6 digits. Found {len(digits)} digits")
    return None

def recognize_captcha(driver, logger, max_attempts=3):
    """Recognize the 6-digit captcha using EasyOCR with multiple attempts"""
    logger.info(f"Starting captcha recognition with {max_attempts} max attempts")
    reader = easyocr.Reader(['en'])
    
    for attempt in range(max_attempts):
        try:
            logger.info(f"Attempt {attempt + 1} of {max_attempts}")
            
            # Find the captcha image element
            logger.info("Locating captcha image element")
            captcha_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "ContentPlaceHolder1_i_captcha_1"))
            )

            # Get the image source
            logger.info("Extracting captcha image data")
            img_base64 = driver.execute_script("""
                var canvas = document.createElement('canvas');
                var context = canvas.getContext('2d');
                var img = document.getElementById('ContentPlaceHolder1_i_captcha_1');
                canvas.width = img.width;
                canvas.height = img.height;
                context.drawImage(img, 0, 0);
                return canvas.toDataURL('image/png').split(',')[1];
            """)

            # Convert base64 to image
            image_data = base64.b64decode(img_base64)
            
            # Preprocess the image
            processed_img = preprocess_captcha_image(image_data, logger)
            
            # Save processed image to bytes
            img_byte_arr = io.BytesIO()
            processed_img.save(img_byte_arr, format='PNG')
            img_byte_arr = img_byte_arr.getvalue()

            # Perform OCR
            logger.info("Performing OCR on preprocessed image")
            result = reader.readtext(img_byte_arr, detail=0)
            logger.info(f"OCR result: {result}")
            
            # Extract exactly 6 digits from the result
            if result:
                digits = extract_digits_from_text(''.join(result), logger)
                if digits:
                    logger.info(f"Successfully recognized captcha: {digits}")
                    return digits

            # If we didn't get 6 digits, refresh the captcha
            if attempt < max_attempts - 1:
                logger.info("Refreshing captcha for next attempt")
                refresh_link = driver.find_element(By.ID, "ContentPlaceHolder1_lb_refresh_1")
                refresh_link.click()
                time.sleep(2)

        except Exception as e:
            logger.error(f"Error in captcha recognition attempt {attempt + 1}: {str(e)}")
            logger.error(traceback.format_exc())
            if attempt < max_attempts - 1:
                continue
            
    # If all attempts fail, ask for manual input
    logger.warning("Automated captcha recognition failed. Falling back to manual input.")
    return input("Please enter the 6-digit captcha manually: ")

def main():
    # Setup logging
    logger = setup_logging()
    logger.info("Starting AnyRoR automation script")

    # --- User-defined parameters ---
    district_name = "પાટણ"         # Desired District (જીલ્લો)
    taluka_name = "પાટણ"           # Desired Taluka (તાલુકો)
    village_name = "અનાવાડા - 091"  # Desired Village (ગામ)
    survey_block_number = "0z૧"     # Survey/Block Number

    logger.info(f"Parameters - District: {district_name}, Taluka: {taluka_name}, "
                f"Village: {village_name}, Survey/Block: {survey_block_number}")

    try:
        # Setup ChromeDriver service
        logger.info("Setting up ChromeDriver")
        service = Service('/opt/homebrew/bin/chromedriver')
        
        # Initialize Chrome options
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        
        # Initialize the driver
        logger.info("Initializing Chrome WebDriver")
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
            logger.error(f"Taluka not found matching: {taluka_name}")
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
            logger.error(f"Village not found matching: {village_name}")
        time.sleep(2)

        # --- Step 5: Set the Survey/Block Number ---
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
        captcha_value = recognize_captcha(driver, logger)
        captcha_input = wait.until(
            EC.visibility_of_element_located((By.ID, "ContentPlaceHolder1_txt_captcha_1"))
        )
        captcha_input.clear()
        captcha_input.send_keys(captcha_value)
        logger.info(f"Entered captcha value: {captcha_value}")
        time.sleep(1)

        # --- Step 7: Submit the Form ---
        logger.info("Submitting the form")
        submit_button = wait.until(
            EC.element_to_be_clickable((By.ID, "ContentPlaceHolder1_btnGo"))
        )
        submit_button.click()

        # Handle potential alert
        try:
            alert = WebDriverWait(driver, 3).until(EC.alert_is_present())
            alert_text = alert.text
            logger.warning(f"Alert present: {alert_text}")
            alert.accept()
            return
        except:
            logger.info("No alert present, continuing with PDF generation")

        time.sleep(3)

        # --- Step 8: Generate PDF ---
        logger.info("Attempting to generate PDF")
        try:
            result = driver.execute_cdp_cmd("Page.printToPDF", {"printBackground": True})
            pdf_data = result.get("data")
            if pdf_data:
                pdf_file = os.path.join(os.path.expanduser("~"), "Downloads", "land_record.pdf")
                with open(pdf_file, "wb") as f:
                    f.write(bytearray(pdf_data, "utf-8"))
                logger.info(f"PDF saved successfully to: {pdf_file}")
            else:
                logger.error("PDF generation did not return any data")
        except Exception as e:
            logger.error(f"Error generating PDF: {str(e)}")
            logger.error(traceback.format_exc())

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        logger.error(traceback.format_exc())
    finally:
        logger.info("Cleaning up resources")
        if 'driver' in locals():
            driver.quit()
        logger.info("Script execution completed")

if __name__ == "__main__":
    main()