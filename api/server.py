
"""
FastAPI Backend Server for Gujarat TSR Agent.
"""

import os
import shutil
import tempfile
import logging
from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from urllib.parse import quote

# Import core models and services
from core.models import LandRecordRequest as CoreLandRecordRequest
from core.config import get_config
from core.clients import Client, get_client_library
from core.anyror_maintenance import (
    is_anyror_maintenance_window,
    maintenance_window_message,
)
from services.file_service import get_file_service
from services.translation_service import get_translation_service
from services.scraping_service import get_scraping_service
# Lazy import for TSR generator (heavy langchain dependencies)
# This significantly improves startup time
_tsr_generator = None

def get_tsr_generator():
    """Lazy load TSR generator to improve startup time."""
    global _tsr_generator
    if _tsr_generator is None:
        from tsr_generator import generate_tsr_from_pdf
        _tsr_generator = generate_tsr_from_pdf
    return _tsr_generator


# Import dependencies and middleware
from api.dependencies import (
    get_file_service_dependency,
    get_translation_service_dependency, 
    get_scraping_service_dependency,
    get_cache_service_dependency
)
from api.middleware import TimingMiddleware
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup/shutdown tasks."""
    # Startup: Check and clear DOCX cache if new version detected
    commit_sha = os.getenv("GIT_COMMIT_SHA")
    if commit_sha:
        logger.info(f"App starting with version: {commit_sha}")
        try:
            from services.cache_service import get_cache_service
            cache_service = get_cache_service()
            if cache_service:
                if cache_service.check_and_clear_docx_if_new_version(commit_sha):
                    logger.info("✅ DOCX cache cleared due to new deployment version")
                else:
                    logger.info("Cache version unchanged, no clearing needed")
            else:
                logger.warning("Cache service not available for version check")
        except Exception as e:
            logger.error(f"Failed to check/clear cache on startup: {e}")
    else:
        logger.warning("GIT_COMMIT_SHA not set, skipping cache version check")
    
    yield  # App runs here
    
    # Shutdown (if needed)
    logger.info("App shutting down")

app = FastAPI(title="Gujarat TSR Agent API", lifespan=lifespan)
app.add_middleware(TimingMiddleware)

# Lazy configuration loading - improves startup time
# Config is loaded on first request, not at module import
_config = None

def get_lazy_config():
    """Lazy load configuration on first use."""
    global _config
    if _config is None:
        _config = get_config()
    return _config


class LandRecordRequest(BaseModel):
    """Pydantic model for API request validation."""
    district: str
    taluka: str
    village: str
    survey_number: str
    output_format: str = "zip"  # Added to support returning just docx
    client_id: Optional[str] = None  # Picks a client from clients.json
    skip_cache: bool = False  # When true, bypass cache read and write


def _build_request_metadata_for_client(
    district: str,
    taluka: str,
    village: str,
    survey_number: str,
    client: Optional[Client],
) -> dict:
    """Build the request_metadata dict, merging in client fields that are set.

    An explicitly EMPTY client field (e.g. `client_cin: ""` in clients.json)
    must be forwarded, not dropped: downstream it means "omit this line". Only
    a MISSING/None field falls back to the built-in ABREL default. Filtering on
    truthiness here made it impossible to suppress the CIN / Kind Attn lines.
    """
    metadata = {
        "district": district,
        "taluka": taluka,
        "village": village,
        "survey_number": survey_number,
    }
    if client is not None:
        for field in (
            "client_name",
            "client_cin",
            "client_address",
            "kind_attn",
            "ref_prefix",
            "reference_email_date",
        ):
            value = getattr(client, field)
            if value is not None:
                metadata[field] = value
    return metadata


@app.post("/generate-tsr")
def generate_tsr(
    background_tasks: BackgroundTasks, 
    file: UploadFile = File(...),
    file_service = Depends(get_file_service_dependency)
):
    """
    Generate a TSR DOCX document from an uploaded PDF land record.
    """
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")

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

        # Generate TSR (lazy load to improve startup time)
        generate_tsr = get_tsr_generator()
        result = generate_tsr(input_path, output_path, logger)

        if not result['success']:
            logger.error(f"Generation failed: {result.get('error')}")
            file_service.cleanup_temp_file(input_path)
            raise HTTPException(status_code=500, detail=f"Generation failed: {result.get('error')}")

        # Read file into memory before cleanup
        try:
            with open(output_path, 'rb') as f:
                docx_content = f.read()
        except Exception as e:
            logger.error(f"Failed to read generated DOCX: {e}")
            file_service.cleanup_temp_file(input_path)
            file_service.cleanup_temp_file(output_path)
            raise HTTPException(status_code=500, detail=f"Failed to read generated file: {e}")
        
        # Clean up immediately
        file_service.cleanup_temp_file(input_path)
        file_service.cleanup_temp_file(output_path)
        
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
        file_service.cleanup_temp_file(input_path)
        raise
    except Exception as e:
        file_service.cleanup_temp_file(input_path)
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/process-record")
def process_record(
    request: LandRecordRequest, 
    background_tasks: BackgroundTasks,
    file_service = Depends(get_file_service_dependency),
    translation_service = Depends(get_translation_service_dependency),
    # For now we use direct retrieval inside loop or here. 
    # With Depends, it's created per request which is good.
    # Note: scraping_service depends on being closed. 
    scraping_service = Depends(get_scraping_service_dependency),
    cache_service = Depends(get_cache_service_dependency)
):
    """
    Scrape land record PDF from AnyRoR and generate TSR DOCX.
    
    Implements caching: if a record was fetched within the last week,
    returns the cached version instead of re-fetching.
    """
    logger.info(f"Processing record: {request}")
    
    # Validate required fields are not empty
    validation_errors = []
    if not request.district or not request.district.strip():
        validation_errors.append("District is required")
    if not request.taluka or not request.taluka.strip():
        validation_errors.append("Taluka is required")
    if not request.village or not request.village.strip():
        validation_errors.append("Village is required")
    if not request.survey_number or not str(request.survey_number).strip():
        validation_errors.append("Survey number is required")
    
    if validation_errors:
        raise HTTPException(status_code=400, detail="; ".join(validation_errors))
    
    # Convert Pydantic model to core model
    try:
        core_request = CoreLandRecordRequest(
            district=request.district,
            taluka=request.taluka,
            village=request.village,
            survey_number=request.survey_number
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # ===== TRANSLATE FIRST (needed for cache key) =====
    # Translate to Gujarati early so we can use it for cache lookup
    # This ensures different English spellings that map to same Gujarati location
    # will share the same cache entry (e.g., "Kutch" and "Kuchh" -> "કચ્છ")
    try:
        district_guj = translation_service.translate_to_gujarati(request.district, context='district')
    except Exception as e:
        logger.warning(f"Invalid district '{request.district}': {e}")
        raise HTTPException(status_code=400, detail=f"Invalid district: '{request.district}' is not in our database")

    try:
        taluka_guj = translation_service.translate_to_gujarati(
            request.taluka, context='taluka', parent_district=district_guj
        )
    except Exception as e:
        logger.warning(f"Invalid taluka '{request.taluka}' under district '{district_guj}': {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid taluka: '{request.taluka}' is not in district '{request.district}'",
        )

    try:
        village_guj = translation_service.translate_to_gujarati(
            request.village, context='village',
            parent_district=district_guj, parent_taluka=taluka_guj,
        )
    except Exception as e:
        logger.warning(
            f"Invalid village '{request.village}' under {district_guj}/{taluka_guj}: {e}"
        )
        detail = (
            f"Invalid village: '{request.village}' is not in "
            f"{request.district}/{request.taluka}"
        )
        # Surface the translator's 'did you mean ...?' hint (a suggestion only).
        _msg = str(e)
        _idx = _msg.lower().find("did you mean")
        if _idx != -1:
            _hint = _msg[_idx:]
            _q = _hint.find("?")
            if _q != -1:
                _hint = _hint[: _q + 1]
            _hint = _hint.strip()
            detail += ". " + _hint[0].upper() + _hint[1:]
        raise HTTPException(status_code=400, detail=detail)
    
    # Log translations for debugging
    logger.info(f"Translation results: district '{request.district}' -> '{district_guj}', "
               f"taluka '{request.taluka}' -> '{taluka_guj}', "
               f"village '{request.village}' -> '{village_guj}'")
    
    # ===== RESOLVE CLIENT =====
    client_library = get_client_library()
    resolved_client = client_library.resolve(request.client_id)
    if request.client_id and (resolved_client is None or resolved_client.id != request.client_id):
        logger.warning(
            "Unknown client_id %r — falling back to default (%s)",
            request.client_id,
            resolved_client.id if resolved_client else None,
        )

    # ===== CACHE CHECK =====
    # Check cache using translated (Gujarati) values for the cache key
    # This ensures cache hits work correctly regardless of English spelling variations
    pdf_key = None
    cached_pdf_content: Optional[bytes] = None
    cached_docx_content: Optional[bytes] = None
    if cache_service is not None and not request.skip_cache:
        try:
            pdf_key = cache_service.generate_cache_key_from_translated(
                translated_district=district_guj,
                translated_taluka=taluka_guj,
                translated_village=village_guj,
                survey_number=request.survey_number,
            )

            cached_pdf_content = cache_service.get_cached_pdf_by_key(pdf_key)
            if resolved_client is not None:
                cached_docx_content = cache_service.get_cached_docx_by_key(
                    pdf_key, resolved_client.id
                )

            if cached_pdf_content is not None and cached_docx_content is not None:
                logger.info(
                    "✅ FULL CACHE HIT for %s/%s/%s/%s (client=%s)",
                    request.district, request.taluka, request.village,
                    request.survey_number, resolved_client.id if resolved_client else None,
                )

                docx_filename = file_service.generate_filename(core_request, file_type='docx', prefix='TSR')
                pdf_filename = file_service.generate_filename(core_request, file_type='pdf', prefix='Original')
                zip_filename = file_service.generate_filename(core_request, file_type='zip', prefix='TSR_Package')

                if getattr(request, 'output_format', 'zip') == 'docx':
                    encoded_filename = quote(docx_filename)
                    return Response(
                        content=cached_docx_content,
                        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        headers={
                            'Content-Disposition': f"attachment; filename=\"{docx_filename}\"; filename*=UTF-8''{encoded_filename}",
                            'X-Cache-Status': 'HIT',
                        }
                    )
                files_to_zip = {docx_filename: cached_docx_content}
                if cached_pdf_content:
                    files_to_zip[pdf_filename] = cached_pdf_content
                zip_content = file_service.create_zip(files_to_zip, zip_filename)
                encoded_filename = quote(zip_filename)
                zip_filename_ascii = f"TSR_Package_{os.urandom(4).hex()}.zip"
                return Response(
                    content=zip_content,
                    media_type='application/zip',
                    headers={
                        'Content-Disposition': f"attachment; filename=\"{zip_filename_ascii}\"; filename*=UTF-8''{encoded_filename}",
                        'X-Cache-Status': 'HIT',
                    }
                )

            if cached_pdf_content is not None:
                logger.info(
                    "🟡 PARTIAL CACHE HIT (PDF hit, DOCX miss) for %s/%s/%s/%s (client=%s)",
                    request.district, request.taluka, request.village,
                    request.survey_number, resolved_client.id if resolved_client else None,
                )
            else:
                logger.info(
                    "❌ CACHE MISS for %s/%s/%s/%s",
                    request.district, request.taluka, request.village, request.survey_number,
                )
        except Exception as e:
            logger.warning(f"Cache check failed, proceeding without cache: {e}")
            pdf_key = None
            cached_pdf_content = None
            cached_docx_content = None
    
    # ===== CACHE MISS - PROCEED WITH SCRAPING =====
    temp_dir = tempfile.gettempdir()
    unique_id = os.urandom(8).hex()
    pdf_path = os.path.join(temp_dir, f"scraped_{unique_id}.pdf")
    docx_path = os.path.join(temp_dir, f"TSR_{unique_id}.docx")
    
    # scraping_service is already initialized via Depends
    try:
        # Sanity check: district should not contain " - " (village code pattern)
        if " - " in district_guj:
            logger.error(f"SUSPICIOUS: District translation '{district_guj}' looks like a village code!")

        if cached_pdf_content is not None:
            with open(pdf_path, "wb") as f:
                f.write(cached_pdf_content)
            logger.info(f"Wrote cached PDF to {pdf_path}, skipping scrape")
        else:
            logger.info(
                f"Calling scraper with: district='{district_guj}', taluka='{taluka_guj}', "
                f"village='{village_guj}', survey='{request.survey_number}'"
            )
            result = scraping_service.fetch_land_record(
                district=district_guj,
                taluka=taluka_guj,
                village=village_guj,
                survey_number=request.survey_number,
                output_path=pdf_path
            )
            if not result.get('success'):
                logger.error(f"Scraping failed with result: {result}")
                from datetime import datetime, timezone as _tz
                if is_anyror_maintenance_window(datetime.now(_tz.utc)):
                    raise HTTPException(status_code=503, detail=maintenance_window_message())
                raise HTTPException(status_code=500, detail=f"Scraping failed: {result.get('error')}")
            
        # Enhanced logging for diagnostics
        logger.info(f"PDF scraped successfully: {pdf_path}")
        
        # Log PDF file details
        if os.path.exists(pdf_path):
            pdf_size = os.path.getsize(pdf_path)
            logger.info(f"Scraped PDF size: {pdf_size} bytes")
            
            # Try to get PDF page count
            try:
                import pypdf
                with open(pdf_path, 'rb') as f:
                    pdf_reader = pypdf.PdfReader(f)
                    page_count = len(pdf_reader.pages)
                    logger.info(f"Scraped PDF has {page_count} pages")
                    
                    if page_count > 0:
                        first_page_text = pdf_reader.pages[0].extract_text()[:200]
                        logger.info(f"First page preview: {first_page_text}")
            except Exception as e:
                logger.warning(f"Could not read PDF metadata: {e}")
        else:
            logger.error(f"PDF file does not exist at {pdf_path}")
        
        # Generate TSR (lazy load to improve startup time)
        logger.info(f"Starting TSR generation from PDF: {pdf_path}")
        generate_tsr = get_tsr_generator()
        _request_metadata = _build_request_metadata_for_client(
            district=request.district,
            taluka=request.taluka,
            village=request.village,
            survey_number=request.survey_number,
            client=resolved_client,
        )
        tsr_result = generate_tsr(pdf_path, docx_path, logger, request_metadata=_request_metadata)
        
        logger.info(f"TSR generation result: success={tsr_result.get('success')}, error={tsr_result.get('error')}")
        
        if not tsr_result['success']:
            raise HTTPException(status_code=500, detail=f"TSR Generation failed: {tsr_result.get('error')}")
            
        logger.info(f"TSR generated successfully: {docx_path}")
        
        # Read files into memory before cleanup
        try:
            with open(docx_path, 'rb') as f:
                docx_content = f.read()
            
            pdf_content = None
            if os.path.exists(pdf_path):
                with open(pdf_path, 'rb') as f:
                    pdf_content = f.read()
            else:
                logger.warning(f"PDF file not found at {pdf_path}")

        except Exception as e:
            logger.error(f"Failed to read generated files: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to read generated files: {e}")
        
        # Clean up immediately
        file_service.cleanup_temp_file(pdf_path)
        file_service.cleanup_temp_file(docx_path)
        
        # ===== CACHE STORE =====
        # Store the result in cache using translated values for the key
        if cache_service is not None and not request.skip_cache and pdf_key is not None:
            try:
                if cached_pdf_content is None and pdf_content:
                    cache_service.cache_pdf_by_key(pdf_key, pdf_content)
                if resolved_client is not None:
                    cache_service.cache_docx_by_key(
                        pdf_key=pdf_key,
                        client_id=resolved_client.id,
                        original_request=core_request,
                        translated_district=district_guj,
                        translated_taluka=taluka_guj,
                        translated_village=village_guj,
                        docx_content=docx_content,
                    )
                logger.info(
                    "💾 CACHED PDF + DOCX for %s/%s/%s/%s (client=%s)",
                    request.district, request.taluka, request.village,
                    request.survey_number, resolved_client.id if resolved_client else None,
                )
            except Exception as e:
                logger.warning(f"Failed to cache record: {e}")
        
        # Generate filenames using file service
        docx_filename = file_service.generate_filename(core_request, file_type='docx', prefix='TSR')
        pdf_filename = file_service.generate_filename(core_request, file_type='pdf', prefix='Original')
        zip_filename = file_service.generate_filename(core_request, file_type='zip', prefix='TSR_Package')
        
        if getattr(request, 'output_format', 'zip') == 'docx':
            encoded_filename = quote(docx_filename)
            return Response(
                content=docx_content,
                media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                headers={
                    'Content-Disposition': f"attachment; filename=\"{docx_filename}\"; filename*=UTF-8''{encoded_filename}",
                    'X-Cache-Status': 'MISS'
                }
            )
        else:
            # Create ZIP file using file service
            files_to_zip = {docx_filename: docx_content}
            if pdf_content:
                files_to_zip[pdf_filename] = pdf_content
            
            zip_content = file_service.create_zip(files_to_zip, zip_filename)
            
            # Prepare filename for header
            encoded_filename = quote(zip_filename)
            
            # Create ASCII-safe fallback filename
            zip_filename_ascii = f"TSR_Package_{os.urandom(4).hex()}.zip"
            
            return Response(
                content=zip_content,
                media_type='application/zip',
                headers={
                    'Content-Disposition': f"attachment; filename=\"{zip_filename_ascii}\"; filename*=UTF-8''{encoded_filename}",
                    'X-Cache-Status': 'MISS'
                }
            )
        
    except HTTPException:
        file_service.cleanup_temp_file(pdf_path)
        file_service.cleanup_temp_file(docx_path)
        raise
    except Exception as e:
        file_service.cleanup_temp_file(pdf_path)
        file_service.cleanup_temp_file(docx_path)
        logger.error(f"Unexpected error in process-record: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    # Finally block for scraping_service close is now handled by dependency generator!


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
    
    debug_info = {
        "platform": platform.system(),
        "python_version": platform.python_version(),
        "environment_variables": {
            "GEMINI_API_KEY": "SET" if os.getenv("GEMINI_API_KEY") else "NOT SET",
            "GEMINI_MODEL_NAME": os.getenv("GEMINI_MODEL_NAME", "default: gemini-3.1-pro-preview"),
            "CAPTCHA_MODEL": os.getenv("CAPTCHA_MODEL", "default: claude-opus-5"),
            "GEMINI_TRANSLATION_MODEL": os.getenv("GEMINI_TRANSLATION_MODEL", "default: gemini-3.1-flash-lite-preview"),
            "CHROME_BIN": os.getenv("CHROME_BIN", "NOT SET"),
            "CHROMEDRIVER_PATH": os.getenv("CHROMEDRIVER_PATH", "NOT SET"),
            "GCS_CACHE_BUCKET": os.getenv("GCS_CACHE_BUCKET", "NOT SET"),
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


@app.get("/cache-stats")
def cache_stats(cache_service = Depends(get_cache_service_dependency)):
    """
    Get statistics about the record cache.
    
    Returns cache statistics including number of cached records,
    total size, and TTL configuration.
    """
    if cache_service is None:
        return {
            "status": "disabled",
            "message": "Cache not configured. Set GCS_CACHE_BUCKET environment variable to enable."
        }
    
    try:
        stats = cache_service.get_cache_stats()
        return {
            "status": "enabled",
            **stats
        }
    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        return {
            "status": "error",
            "error": str(e)
        }
