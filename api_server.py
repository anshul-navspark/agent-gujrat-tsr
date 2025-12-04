import os
import shutil
import tempfile
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from urllib.parse import quote
from tsr_generator.api.tsr_generator import generate_tsr_from_pdf
from anyror_refactored import AnyRoRScraper, WebDriverManager
from utils.json_translations import translate_to_english
from utils.survey_utils import sanitize_filename

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Gujarat TSR Agent API")

class LandRecordRequest(BaseModel):
    district: str
    taluka: str
    village: str
    survey_number: str

def cleanup_temp_file(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"Cleaned up temporary file: {path}")
    except Exception as e:
        logger.error(f"Error cleaning up file {path}: {e}")

@app.post("/generate-tsr")
def generate_tsr(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Generate a TSR DOCX document from an uploaded PDF land record.
    """
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    # Create a temporary directory for processing
    # Note: We can't use TemporaryDirectory context manager because we need to return the file
    # and then clean up. We'll use a unique temp file path.
    temp_dir = tempfile.gettempdir()
    input_filename = f"input_{os.urandom(8).hex()}.pdf"
    input_path = os.path.join(temp_dir, input_filename)
    
    try:
        # Save uploaded file
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        logger.info(f"Received file: {file.filename}, saved to {input_path}")

        # Define output path
        output_filename = f"TSR_{os.path.splitext(file.filename)[0]}.docx"
        output_path = os.path.join(temp_dir, f"output_{os.urandom(8).hex()}.docx")

        # Generate TSR
        result = generate_tsr_from_pdf(input_path, output_path, logger)

        if not result['success']:
            logger.error(f"Generation failed: {result.get('error')}")
            # Clean up input file
            cleanup_temp_file(input_path)
            raise HTTPException(status_code=500, detail=f"Generation failed: {result.get('error')}")

        # Read file into memory before cleanup to avoid race conditions
        try:
            with open(output_path, 'rb') as f:
                docx_content = f.read()
        except Exception as e:
            logger.error(f"Failed to read generated DOCX: {e}")
            cleanup_temp_file(input_path)
            cleanup_temp_file(output_path)
            raise HTTPException(status_code=500, detail=f"Failed to read generated file: {e}")
        
        # Clean up immediately since we have the content in memory
        cleanup_temp_file(input_path)
        cleanup_temp_file(output_path)
        
        # Prepare filename for header
        encoded_filename = quote(output_filename)
        
        return Response(
            content=docx_content,
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            headers={
                'Content-Disposition': f"attachment; filename=\"TSR_Document.docx\"; filename*=UTF-8''{encoded_filename}"
            }
        )

    except HTTPException:
        cleanup_temp_file(input_path)
        raise
    except Exception as e:
        cleanup_temp_file(input_path)
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/process-record")
def process_record(request: LandRecordRequest, background_tasks: BackgroundTasks):
    """
    Scrape land record PDF from AnyRoR and generate TSR DOCX.
    """
    logger.info(f"Processing record: {request}")
    
    temp_dir = tempfile.gettempdir()
    unique_id = os.urandom(8).hex()
    pdf_path = os.path.join(temp_dir, f"scraped_{unique_id}.pdf")
    docx_path = os.path.join(temp_dir, f"TSR_{unique_id}.docx")
    
    scraper = None
    try:
        # Initialize scraper
        # Note: In Cloud Run, we might want to be careful with headless mode and resources
        scraper = AnyRoRScraper(headless=True, logger=logger)
        
        # Fetch land record
        result = scraper.fetch_land_record(
            district_name=request.district,
            taluka_name=request.taluka,
            village_name=request.village,
            survey_block_number=request.survey_number,
            output_path=pdf_path
        )
        
        if not result.get('success'):
            logger.error(f"Scraping failed with result: {result}")
            raise HTTPException(status_code=500, detail=f"Scraping failed: {result.get('error')}")
            
        # Enhanced logging for diagnostics
        logger.info(f"PDF scraped successfully: {pdf_path}")
        
        # Log PDF file details
        if os.path.exists(pdf_path):
            pdf_size = os.path.getsize(pdf_path)
            logger.info(f"Scraped PDF size: {pdf_size} bytes")
            
            # Try to get PDF page count
            try:
                import PyPDF2
                with open(pdf_path, 'rb') as f:
                    pdf_reader = PyPDF2.PdfReader(f)
                    page_count = len(pdf_reader.pages)
                    logger.info(f"Scraped PDF has {page_count} pages")
                    
                    # Log first 200 chars of first page text
                    if page_count > 0:
                        first_page_text = pdf_reader.pages[0].extract_text()[:200]
                        logger.info(f"First page preview: {first_page_text}")
            except Exception as e:
                logger.warning(f"Could not read PDF metadata: {e}")
        else:
            logger.error(f"PDF file does not exist at {pdf_path}")
        
        # Generate TSR
        logger.info(f"Starting TSR generation from PDF: {pdf_path}")
        tsr_result = generate_tsr_from_pdf(pdf_path, docx_path, logger)
        
        logger.info(f"TSR generation result: success={tsr_result.get('success')}, error={tsr_result.get('error')}")
        
        if not tsr_result['success']:
            raise HTTPException(status_code=500, detail=f"TSR Generation failed: {tsr_result.get('error')}")
            
        logger.info(f"TSR generated successfully: {docx_path}")
        
        # Read file into memory before cleanup to avoid race conditions under high concurrency
        try:
            with open(docx_path, 'rb') as f:
                docx_content = f.read()
        except Exception as e:
            logger.error(f"Failed to read generated DOCX: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to read generated file: {e}")
        
        # Clean up immediately since we have the content in memory
        cleanup_temp_file(pdf_path)
        cleanup_temp_file(docx_path)
        
        # Translate Gujarati names to English for filename
        try:
            district_eng = translate_to_english(request.district, context='district')
            taluka_eng = translate_to_english(request.taluka, context='taluka')
            village_eng = translate_to_english(request.village, context='village')
            survey_eng = sanitize_filename(request.survey_number)
            
            output_filename = f"TSR_{district_eng}_{taluka_eng}_{village_eng}_{survey_eng}.docx"
        except Exception as e:
            logger.warning(f"Failed to translate filename to English: {e}")
            # Fallback to sanitized Gujarati names
            output_filename = f"TSR_{sanitize_filename(request.village)}_{sanitize_filename(request.survey_number)}.docx"
        
        
        # Prepare filename for header
        encoded_filename = quote(output_filename)
        
        return Response(
            content=docx_content,
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            headers={
                'Content-Disposition': f"attachment; filename=\"TSR_Report.docx\"; filename*=UTF-8''{encoded_filename}"
            }
        )
        
    except HTTPException:
        cleanup_temp_file(pdf_path)
        cleanup_temp_file(docx_path)
        raise
    except Exception as e:
        cleanup_temp_file(pdf_path)
        cleanup_temp_file(docx_path)
        logger.error(f"Unexpected error in process-record: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if scraper:
            try:
                scraper.web_driver_manager.close()
            except:
                pass

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/debug-env")
def debug_environment():
    """
    Debug endpoint to verify environment configuration.
    Returns information about the environment setup.
    """
    import platform
    import subprocess
    
    debug_info = {
        "platform": platform.system(),
        "python_version": platform.python_version(),
        "environment_variables": {
            "GEMINI_API_KEY": "SET" if os.getenv("GEMINI_API_KEY") else "NOT SET",
            "GEMINI_MODEL_NAME": os.getenv("GEMINI_MODEL_NAME", "default: gemini-2.5-flash"),
            "CHROME_BIN": os.getenv("CHROME_BIN", "NOT SET"),
            "CHROMEDRIVER_PATH": os.getenv("CHROMEDRIVER_PATH", "NOT SET"),
        },
        "chrome_available": False,
        "chromedriver_available": False
    }
    
    # Check for Chrome/Chromium
    chrome_paths = [
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    ]
    
    for chrome_path in chrome_paths:
        if os.path.exists(chrome_path):
            debug_info["chrome_available"] = True
            debug_info["chrome_path"] = chrome_path
            break
    
    # Check for ChromeDriver
    chromedriver_paths = [
        "/usr/bin/chromedriver",
        "/usr/local/bin/chromedriver"
    ]
    
    for driver_path in chromedriver_paths:
        if os.path.exists(driver_path):
            debug_info["chromedriver_available"] = True
            debug_info["chromedriver_path"] = driver_path
            break
    
    return debug_info

