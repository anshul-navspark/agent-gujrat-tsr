import sys
import os
import logging
from pathlib import Path

# Add project root to path
current_file = Path(__file__).resolve()
project_root = str(current_file.parents[1])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Set env var if missing, to ensure get_cache_service works
# Using the bucket name found in clear_docx_cache.sh
if "GCS_CACHE_BUCKET" not in os.environ:
    os.environ["GCS_CACHE_BUCKET"] = "neon-alcove-479309-q3-tsr-cache"

from services.cache_service import get_cache_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("manual_clear_cache")

def main():
    logger.info("Starting manual cache clear...")
    
    # Initialize cache service
    cache_service = get_cache_service()
    
    if not cache_service:
        logger.error("Failed to initialize CacheService.")
        return

    logger.info(f"Clearing all DOCX files from bucket: {cache_service.bucket_name}")
    try:
        count = cache_service.clear_all_docx_cache()
        logger.info(f"Successfully cleared {count} DOCX files from cache.")
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        if "Anonymous caller" in str(e) or "credentials" in str(e).lower():
             logger.error("Authentication failed. Please run `gcloud auth application-default login` or set GOOGLE_APPLICATION_CREDENTIALS.")

if __name__ == "__main__":
    main()
