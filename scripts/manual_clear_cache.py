import sys
import os
import logging
from pathlib import Path

# Add project root to path to allow imports
current_file = Path(__file__).resolve()
project_root = str(current_file.parents[1])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from services.cache_service import get_cache_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("manual_clear_cache")

def main():
    """
    Manually clear all TSR DOCX files from the cache.
    """
    # Ensure bucket name is set from cloudbuild info if not in env
    bucket_name = os.getenv("GCS_CACHE_BUCKET")
    if not bucket_name:
        # Fallback to the one we discovered
        bucket_name = "neon-alcove-479309-q3-tsr-cache"
        os.environ["GCS_CACHE_BUCKET"] = bucket_name
        logger.info(f"GCS_CACHE_BUCKET not set, Using discovered bucket: {bucket_name}")

    logger.info(f"Initializing cache service for bucket: {bucket_name}...")
    
    # Initialize cache service
    cache_service = get_cache_service(bucket_name=bucket_name)
    
    if not cache_service:
        logger.error("Failed to initialize CacheService. Check GCS_CACHE_BUCKET env var.")
        return

    logger.info("Clearing all TSR DOCX files from cache...")
    try:
        deleted_count = cache_service.clear_all_docx_cache()
        logger.info(f"Success! Deleted {deleted_count} DOCX files from cache.")
        
    except Exception as e:
        logger.error(f"An error occurred during cache clearing: {e}")

if __name__ == "__main__":
    main()
