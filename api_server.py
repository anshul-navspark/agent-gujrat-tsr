import os
import shutil
import tempfile
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from tsr_generator.api.tsr_generator import generate_tsr_from_pdf
from anyror_refactored import AnyRoRScraper, WebDriverManager

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
async def generate_tsr(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
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

        # Schedule cleanup
        background_tasks.add_task(cleanup_temp_file, input_path)
        background_tasks.add_task(cleanup_temp_file, output_path)
        
        return FileResponse(
            path=output_path, 
            filename=output_filename,
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

    except HTTPException:
        cleanup_temp_file(input_path)
        raise
    except Exception as e:
        cleanup_temp_file(input_path)
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/process-record")
async def process_record(request: LandRecordRequest, background_tasks: BackgroundTasks):
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
            raise HTTPException(status_code=500, detail=f"Scraping failed: {result.get('error')}")
            
        logger.info(f"PDF scraped successfully: {pdf_path}")
        
        # Generate TSR
        tsr_result = generate_tsr_from_pdf(pdf_path, docx_path, logger)
        
        if not tsr_result['success']:
            raise HTTPException(status_code=500, detail=f"TSR Generation failed: {tsr_result.get('error')}")
            
        logger.info(f"TSR generated successfully: {docx_path}")
        
        # Schedule cleanup
        background_tasks.add_task(cleanup_temp_file, pdf_path)
        background_tasks.add_task(cleanup_temp_file, docx_path)
        
        output_filename = f"TSR_{request.village}_{request.survey_number}.docx"
        
        return FileResponse(
            path=docx_path,
            filename=output_filename,
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
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
