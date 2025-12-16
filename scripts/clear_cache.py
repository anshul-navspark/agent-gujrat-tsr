import sys
import os
import logging
from pathlib import Path

# Add project root to path to allow imports
# This allows running from root via `python scripts/clear_cache.py` 
# or from scripts dir via `python clear_cache.py`
current_file = Path(__file__).resolve()
project_root = str(current_file.parents[1])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from services.cache_service import get_cache_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("clear_cache")

def main():
    """
    Check for new version and clear DOCX cache if needed.
    """
    logger.info("Starting cache version check...")
    
    commit_sha = os.getenv("GIT_COMMIT_SHA")
    if not commit_sha:
        logger.warning("GIT_COMMIT_SHA environment variable not found. Skipping cache clearing.")
        return

    # Initialize cache service using env vars for bucket config
    cache_service = get_cache_service()
    
    if not cache_service:
        logger.error("Failed to initialize CacheService. Check GCS_CACHE_BUCKET env var.")
        return

    logger.info(f"Checking cache for version: {commit_sha}")
    try:
        if cache_service.check_and_clear_docx_if_new_version(commit_sha):
            logger.info("Cache clearing operation completed successfully.")
        else:
            logger.info("No cache clearing was performed.")
            
    except Exception as e:
        logger.error(f"An error occurred during cache check: {e}")

if __name__ == "__main__":
    main()
