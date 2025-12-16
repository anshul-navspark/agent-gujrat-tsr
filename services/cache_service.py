"""
Cache service for Gujarat TSR Agent using Google Cloud Storage.

This service provides caching functionality for fetched land records,
storing them in a GCS bucket with a configurable TTL (default: 1 week).
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path for imports
_project_root = str(Path(__file__).resolve().parents[1])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import os
import json
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple

from google.cloud import storage
from google.cloud.exceptions import NotFound

from core.models import LandRecordRequest


class CacheService:
    """
    Service for caching land records in Google Cloud Storage.
    
    Cache structure in GCS:
    - bucket/
      - cache/
        - {cache_key}/
          - metadata.json (contains timestamp, request info)
          - original.pdf (scraped PDF)
          - tsr.docx (generated TSR document)
    """
    
    # Default cache TTL: 7 days (1 week)
    DEFAULT_TTL_DAYS = 7
    
    def __init__(
        self,
        bucket_name: str,
        ttl_days: int = DEFAULT_TTL_DAYS,
        cache_prefix: str = "cache",
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize cache service.
        
        Args:
            bucket_name: GCS bucket name for storing cache
            ttl_days: Time-to-live in days (default: 7 days)
            cache_prefix: Prefix path in bucket for cache files
            logger: Optional logger instance
        """
        self.bucket_name = bucket_name
        self.ttl_days = ttl_days
        self.cache_prefix = cache_prefix
        self.logger = logger or logging.getLogger(__name__)
        
        # Initialize GCS client
        try:
            self._client = storage.Client()
            self._bucket = self._client.bucket(bucket_name)
            self.logger.info(f"Cache service initialized with bucket: {bucket_name}")
        except Exception as e:
            self.logger.error(f"Failed to initialize GCS client: {e}")
            raise
    
    def _generate_cache_key(self, request: LandRecordRequest) -> str:
        """
        Generate a unique cache key for a land record request.
        
        The key is a hash of district + taluka + village + survey_number,
        normalized to lowercase and stripped of whitespace.
        
        Args:
            request: Land record request
            
        Returns:
            Cache key as a hex string
        """
        # Normalize inputs
        components = [
            request.district.strip().lower(),
            request.taluka.strip().lower(),
            request.village.strip().lower(),
            request.survey_number.strip().lower()
        ]
        
        # Create hash
        key_string = "|".join(components)
        cache_key = hashlib.sha256(key_string.encode()).hexdigest()[:32]
        
        self.logger.debug(f"Generated cache key {cache_key} for {key_string}")
        return cache_key
    
    def generate_cache_key_from_translated(
        self,
        translated_district: str,
        translated_taluka: str,
        translated_village: str,
        survey_number: str
    ) -> str:
        """
        Generate a cache key from translated Gujarati values.
        
        This ensures all English spelling variations that translate to the
        same Gujarati location will share the same cache entry.
        
        For example:
        - "Kutch" and "Kuchh" both translate to "કચ્છ" -> same cache key
        - "Trambo" and "Trambau" both translate to "ત્રંબો - 033" -> same cache key
        
        Args:
            translated_district: Gujarati district name
            translated_taluka: Gujarati taluka name  
            translated_village: Gujarati village name
            survey_number: Survey number (unchanged)
            
        Returns:
            Cache key as a hex string
        """
        # Normalize inputs using translated Gujarati values
        components = [
            translated_district.strip().lower(),
            translated_taluka.strip().lower(),
            translated_village.strip().lower(),
            survey_number.strip().lower()
        ]
        
        # Create hash
        key_string = "|".join(components)
        cache_key = hashlib.sha256(key_string.encode()).hexdigest()[:32]
        
        self.logger.debug(f"Generated cache key {cache_key} from translated: {key_string}")
        return cache_key
    
    def get_cached_record_by_key(
        self,
        cache_key: str
    ) -> Optional[Tuple[bytes, Optional[bytes], Dict[str, Any]]]:
        """
        Retrieve a cached record by its pre-computed cache key.
        
        This is used when the cache key has already been computed using
        translated values.
        
        Args:
            cache_key: Pre-computed cache key
            
        Returns:
            Tuple of (docx_content, pdf_content, metadata) if cache hit,
            None if cache miss or expired
        """
        try:
            # Check metadata first
            metadata_path = self._get_cache_path(cache_key, "metadata.json")
            metadata_blob = self._bucket.blob(metadata_path)
            
            if not metadata_blob.exists():
                self.logger.debug(f"Cache miss: no metadata for key {cache_key}")
                return None
            
            # Load and validate metadata
            metadata_content = metadata_blob.download_as_text()
            metadata = json.loads(metadata_content)
            
            if not self._is_cache_valid(metadata):
                self.logger.info(f"Cache expired for key {cache_key}")
                # Optionally clean up expired cache
                self._cleanup_cache(cache_key)
                return None
            
            # Load cached files
            docx_path = self._get_cache_path(cache_key, "tsr.docx")
            docx_blob = self._bucket.blob(docx_path)
            
            if not docx_blob.exists():
                self.logger.warning(f"Cache incomplete: missing TSR DOCX for key {cache_key}")
                return None
            
            docx_content = docx_blob.download_as_bytes()
            
            # PDF is optional
            pdf_content = None
            pdf_path = self._get_cache_path(cache_key, "original.pdf")
            pdf_blob = self._bucket.blob(pdf_path)
            
            if pdf_blob.exists():
                pdf_content = pdf_blob.download_as_bytes()
            
            self.logger.info(
                f"Cache hit for key {cache_key} - "
                f"cached on {metadata.get('timestamp', 'unknown')}"
            )
            
            return (docx_content, pdf_content, metadata)
            
        except NotFound:
            self.logger.debug(f"Cache miss: key {cache_key} not found")
            return None
        except Exception as e:
            self.logger.error(f"Error reading cache: {e}")
            return None
    
    def cache_record_by_key(
        self,
        cache_key: str,
        original_request: LandRecordRequest,
        translated_district: str,
        translated_taluka: str,
        translated_village: str,
        docx_content: bytes,
        pdf_content: Optional[bytes] = None,
        additional_metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Cache a processed record using a pre-computed cache key.
        
        This stores both the original English input and the translated
        Gujarati values for reference.
        
        Args:
            cache_key: Pre-computed cache key (from translated values)
            original_request: Original land record request (with English input)
            translated_district: Gujarati district name
            translated_taluka: Gujarati taluka name
            translated_village: Gujarati village name
            docx_content: Generated TSR DOCX content
            pdf_content: Optional original PDF content
            additional_metadata: Optional additional metadata to store
            
        Returns:
            True if caching succeeded, False otherwise
        """
        try:
            # Prepare metadata with both original and translated values
            metadata = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                # Original English input
                "original_district": original_request.district,
                "original_taluka": original_request.taluka,
                "original_village": original_request.village,
                "survey_number": original_request.survey_number,
                # Translated Gujarati values (used for cache key)
                "translated_district": translated_district,
                "translated_taluka": translated_taluka,
                "translated_village": translated_village,
                "ttl_days": self.ttl_days,
                "docx_size": len(docx_content),
                "pdf_size": len(pdf_content) if pdf_content else 0,
                **(additional_metadata or {})
            }
            
            # Store metadata
            metadata_path = self._get_cache_path(cache_key, "metadata.json")
            metadata_blob = self._bucket.blob(metadata_path)
            metadata_blob.upload_from_string(
                json.dumps(metadata, indent=2, ensure_ascii=False),
                content_type="application/json"
            )
            
            # Store DOCX
            docx_path = self._get_cache_path(cache_key, "tsr.docx")
            docx_blob = self._bucket.blob(docx_path)
            docx_blob.upload_from_string(
                docx_content,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            
            # Store PDF if available
            if pdf_content:
                pdf_path = self._get_cache_path(cache_key, "original.pdf")
                pdf_blob = self._bucket.blob(pdf_path)
                pdf_blob.upload_from_string(
                    pdf_content,
                    content_type="application/pdf"
                )
            
            self.logger.info(
                f"Cached record with key {cache_key}: "
                f"DOCX={len(docx_content)} bytes, "
                f"PDF={len(pdf_content) if pdf_content else 0} bytes"
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to cache record: {e}")
            return False
    
    def _get_cache_path(self, cache_key: str, filename: str) -> str:
        """Get full GCS path for a cached file."""
        return f"{self.cache_prefix}/{cache_key}/{filename}"
    
    def _is_cache_valid(self, metadata: Dict[str, Any]) -> bool:
        """
        Check if cached data is still valid based on TTL.
        
        Args:
            metadata: Cache metadata containing timestamp
            
        Returns:
            True if cache is valid, False if expired
        """
        try:
            cached_time = datetime.fromisoformat(metadata.get("timestamp", ""))
            expiry_time = cached_time + timedelta(days=self.ttl_days)
            now = datetime.now(timezone.utc)
            
            is_valid = now < expiry_time
            
            if not is_valid:
                days_expired = (now - expiry_time).days
                self.logger.info(f"Cache expired {days_expired} days ago")
            
            return is_valid
            
        except (ValueError, TypeError) as e:
            self.logger.warning(f"Invalid cache timestamp: {e}")
            return False
    
    def get_cached_record(
        self,
        request: LandRecordRequest
    ) -> Optional[Tuple[bytes, Optional[bytes], Dict[str, Any]]]:
        """
        Retrieve a cached record if available and not expired.
        
        Args:
            request: Land record request
            
        Returns:
            Tuple of (docx_content, pdf_content, metadata) if cache hit,
            None if cache miss or expired
        """
        cache_key = self._generate_cache_key(request)
        
        try:
            # Check metadata first
            metadata_path = self._get_cache_path(cache_key, "metadata.json")
            metadata_blob = self._bucket.blob(metadata_path)
            
            if not metadata_blob.exists():
                self.logger.debug(f"Cache miss: no metadata for key {cache_key}")
                return None
            
            # Load and validate metadata
            metadata_content = metadata_blob.download_as_text()
            metadata = json.loads(metadata_content)
            
            if not self._is_cache_valid(metadata):
                self.logger.info(f"Cache expired for key {cache_key}")
                # Optionally clean up expired cache
                self._cleanup_cache(cache_key)
                return None
            
            # Load cached files
            docx_path = self._get_cache_path(cache_key, "tsr.docx")
            docx_blob = self._bucket.blob(docx_path)
            
            if not docx_blob.exists():
                self.logger.warning(f"Cache incomplete: missing TSR DOCX for key {cache_key}")
                return None
            
            docx_content = docx_blob.download_as_bytes()
            
            # PDF is optional
            pdf_content = None
            pdf_path = self._get_cache_path(cache_key, "original.pdf")
            pdf_blob = self._bucket.blob(pdf_path)
            
            if pdf_blob.exists():
                pdf_content = pdf_blob.download_as_bytes()
            
            self.logger.info(
                f"Cache hit for key {cache_key} - "
                f"cached on {metadata.get('timestamp', 'unknown')}"
            )
            
            return (docx_content, pdf_content, metadata)
            
        except NotFound:
            self.logger.debug(f"Cache miss: key {cache_key} not found")
            return None
        except Exception as e:
            self.logger.error(f"Error reading cache: {e}")
            return None
    
    def cache_record(
        self,
        request: LandRecordRequest,
        docx_content: bytes,
        pdf_content: Optional[bytes] = None,
        additional_metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Cache a processed record.
        
        Args:
            request: Original land record request
            docx_content: Generated TSR DOCX content
            pdf_content: Optional original PDF content
            additional_metadata: Optional additional metadata to store
            
        Returns:
            True if caching succeeded, False otherwise
        """
        cache_key = self._generate_cache_key(request)
        
        try:
            # Prepare metadata
            metadata = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "district": request.district,
                "taluka": request.taluka,
                "village": request.village,
                "survey_number": request.survey_number,
                "ttl_days": self.ttl_days,
                "docx_size": len(docx_content),
                "pdf_size": len(pdf_content) if pdf_content else 0,
                **(additional_metadata or {})
            }
            
            # Store metadata
            metadata_path = self._get_cache_path(cache_key, "metadata.json")
            metadata_blob = self._bucket.blob(metadata_path)
            metadata_blob.upload_from_string(
                json.dumps(metadata, indent=2),
                content_type="application/json"
            )
            
            # Store DOCX
            docx_path = self._get_cache_path(cache_key, "tsr.docx")
            docx_blob = self._bucket.blob(docx_path)
            docx_blob.upload_from_string(
                docx_content,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            
            # Store PDF if available
            if pdf_content:
                pdf_path = self._get_cache_path(cache_key, "original.pdf")
                pdf_blob = self._bucket.blob(pdf_path)
                pdf_blob.upload_from_string(
                    pdf_content,
                    content_type="application/pdf"
                )
            
            self.logger.info(
                f"Cached record with key {cache_key}: "
                f"DOCX={len(docx_content)} bytes, "
                f"PDF={len(pdf_content) if pdf_content else 0} bytes"
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to cache record: {e}")
            return False
    
    def _cleanup_cache(self, cache_key: str) -> None:
        """
        Clean up expired cache entry.
        
        Args:
            cache_key: Cache key to clean up
        """
        try:
            prefix = f"{self.cache_prefix}/{cache_key}/"
            blobs = self._bucket.list_blobs(prefix=prefix)
            
            for blob in blobs:
                blob.delete()
                self.logger.debug(f"Deleted expired cache file: {blob.name}")
                
        except Exception as e:
            self.logger.warning(f"Failed to cleanup cache {cache_key}: {e}")
    
    def invalidate_cache(self, request: LandRecordRequest) -> bool:
        """
        Manually invalidate a cached record.
        
        Args:
            request: Land record request to invalidate
            
        Returns:
            True if invalidation succeeded, False otherwise
        """
        cache_key = self._generate_cache_key(request)
        
        try:
            self._cleanup_cache(cache_key)
            self.logger.info(f"Invalidated cache for key {cache_key}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to invalidate cache: {e}")
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the cache.
        
        Returns:
            Dictionary with cache statistics
        """
        try:
            prefix = f"{self.cache_prefix}/"
            blobs = list(self._bucket.list_blobs(prefix=prefix))
            
            total_size = sum(blob.size or 0 for blob in blobs)
            metadata_blobs = [b for b in blobs if b.name.endswith("metadata.json")]
            
            return {
                "total_cached_records": len(metadata_blobs),
                "total_files": len(blobs),
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "bucket": self.bucket_name,
                "ttl_days": self.ttl_days
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get cache stats: {e}")
            return {"error": str(e)}
    
    def clear_all_docx_cache(self) -> int:
        """
        Clear all generated TSR DOCX files from the cache.
        
        Returns:
            Number of files deleted.
        """
        try:
            # Clear DOCX files
            # Note: List all blobs with prefix. This can be slow for very large buckets.
            blobs = self._bucket.list_blobs(prefix=self.cache_prefix)
            deleted_count = 0
            
            for b in blobs:
                if b.name.endswith("tsr.docx"):
                    try:
                        b.delete()
                        deleted_count += 1
                        if deleted_count % 100 == 0:
                            self.logger.info(f"Deleted {deleted_count} DOCX files so far...")
                    except Exception as e:
                        self.logger.warning(f"Failed to delete {b.name}: {e}")
            
            self.logger.info(f"Cache clearing complete. Deleted {deleted_count} DOCX files.")
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"Error during DOCX cache clearing: {e}")
            return 0

    def check_and_clear_docx_if_new_version(self, current_version: str) -> bool:
        """
        Check if the deployed version is new, and if so, clear generated DOCX files.
        
        Args:
            current_version: The current git commit SHA or version string.
            
        Returns:
            True if cache was cleared, False otherwise.
        """
        if not current_version:
            self.logger.warning("No version provided for cache check.")
            return False
            
        version_file = "deployed_version.txt"
        
        try:
            # Check existing version in cache
            blob = self._bucket.blob(version_file)
            if blob.exists():
                stored_version = blob.download_as_text().strip()
                if stored_version == current_version:
                    self.logger.info(f"Cache version match ({current_version}). No clearing needed.")
                    return False
                self.logger.info(f"New version detected (old: {stored_version}, new: {current_version}). Clearing DOCX cache...")
            else:
                self.logger.info(f"No previous version found. Setting version to {current_version}.")
            
            # Clear DOCX files
            self.clear_all_docx_cache()
            
            # Update version file
            blob.upload_from_string(current_version)
            return True
            
        except Exception as e:
            self.logger.error(f"Error during conditional cache clearing: {e}")
            return False


# Singleton instance
_cache_service: Optional[CacheService] = None


def get_cache_service(
    bucket_name: Optional[str] = None,
    ttl_days: int = CacheService.DEFAULT_TTL_DAYS,
    logger: Optional[logging.Logger] = None
) -> Optional[CacheService]:
    """
    Get or create the global cache service instance.
    
    Args:
        bucket_name: GCS bucket name (required on first call, or from env var)
        ttl_days: Cache TTL in days
        logger: Optional logger instance
        
    Returns:
        CacheService instance, or None if bucket not configured
    """
    global _cache_service
    
    if _cache_service is not None:
        return _cache_service
    
    # Get bucket name from argument or environment
    bucket_name = bucket_name or os.getenv("GCS_CACHE_BUCKET")
    
    if not bucket_name:
        logging.getLogger(__name__).warning(
            "Cache service not initialized: GCS_CACHE_BUCKET not configured"
        )
        return None
    
    try:
        _cache_service = CacheService(
            bucket_name=bucket_name,
            ttl_days=ttl_days,
            logger=logger
        )
        return _cache_service
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to initialize cache service: {e}")
        return None
