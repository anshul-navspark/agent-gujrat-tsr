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
    
    # ---- Per-PDF / per-client split cache ----

    def get_cached_pdf_by_key(self, pdf_key: str) -> Optional[bytes]:
        """Return the cached PDF bytes for this location key, or None on miss/expiry."""
        try:
            metadata_blob = self._bucket.blob(self._get_cache_path(pdf_key, "metadata.json"))
            pdf_blob = self._bucket.blob(self._get_cache_path(pdf_key, "original.pdf"))
            if not metadata_blob.exists() or not pdf_blob.exists():
                return None
            metadata = json.loads(metadata_blob.download_as_text())
            if not self._is_cache_valid(metadata):
                self.logger.info(f"PDF cache expired for key {pdf_key}")
                self._cleanup_cache(pdf_key)
                return None
            return pdf_blob.download_as_bytes()
        except NotFound:
            return None
        except Exception as e:
            self.logger.error(f"Error reading PDF cache: {e}")
            return None

    def cache_pdf_by_key(self, pdf_key: str, pdf_content: bytes) -> bool:
        """Store the PDF under this location key. Creates a metadata.json if absent."""
        try:
            metadata_path = self._get_cache_path(pdf_key, "metadata.json")
            metadata_blob = self._bucket.blob(metadata_path)
            if not metadata_blob.exists():
                metadata = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "ttl_days": self.ttl_days,
                }
                metadata_blob.upload_from_string(
                    json.dumps(metadata, indent=2, ensure_ascii=False),
                    content_type="application/json",
                )

            pdf_blob = self._bucket.blob(self._get_cache_path(pdf_key, "original.pdf"))
            pdf_blob.upload_from_string(pdf_content, content_type="application/pdf")
            self.logger.info(f"Cached PDF {pdf_key}: {len(pdf_content)} bytes")
            return True
        except Exception as e:
            self.logger.error(f"Failed to cache PDF: {e}")
            return False

    def get_cached_docx_by_key(self, pdf_key: str, client_id: str) -> Optional[bytes]:
        """Return the cached DOCX bytes for this (location, client) pair, or None on miss."""
        try:
            metadata_blob = self._bucket.blob(self._get_cache_path(pdf_key, "metadata.json"))
            docx_blob = self._bucket.blob(self._get_cache_path(pdf_key, f"docx_{client_id}.docx"))
            if not metadata_blob.exists() or not docx_blob.exists():
                return None
            metadata = json.loads(metadata_blob.download_as_text())
            if not self._is_cache_valid(metadata):
                self.logger.info(f"DOCX cache expired for key {pdf_key}")
                self._cleanup_cache(pdf_key)
                return None
            return docx_blob.download_as_bytes()
        except NotFound:
            return None
        except Exception as e:
            self.logger.error(f"Error reading DOCX cache: {e}")
            return None

    def cache_docx_by_key(
        self,
        pdf_key: str,
        client_id: str,
        original_request: LandRecordRequest,
        translated_district: str,
        translated_taluka: str,
        translated_village: str,
        docx_content: bytes,
        additional_metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Store the DOCX under cache/{pdf_key}/docx_{client_id}.docx."""
        try:
            metadata_path = self._get_cache_path(pdf_key, "metadata.json")
            metadata_blob = self._bucket.blob(metadata_path)
            metadata: Dict[str, Any] = {}
            if metadata_blob.exists():
                try:
                    metadata = json.loads(metadata_blob.download_as_text())
                except Exception:
                    metadata = {}
            metadata.update({
                "timestamp": metadata.get("timestamp") or datetime.now(timezone.utc).isoformat(),
                "original_district": original_request.district,
                "original_taluka": original_request.taluka,
                "original_village": original_request.village,
                "survey_number": original_request.survey_number,
                "translated_district": translated_district,
                "translated_taluka": translated_taluka,
                "translated_village": translated_village,
                "ttl_days": self.ttl_days,
                **(additional_metadata or {}),
            })
            docx_versions = metadata.get("docx_versions") or {}
            docx_versions[client_id] = datetime.now(timezone.utc).isoformat()
            metadata["docx_versions"] = docx_versions

            metadata_blob.upload_from_string(
                json.dumps(metadata, indent=2, ensure_ascii=False),
                content_type="application/json",
            )

            docx_blob = self._bucket.blob(self._get_cache_path(pdf_key, f"docx_{client_id}.docx"))
            docx_blob.upload_from_string(
                docx_content,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            self.logger.info(
                f"Cached DOCX {pdf_key}/docx_{client_id}: {len(docx_content)} bytes"
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to cache DOCX: {e}")
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
                name = b.name
                # Old combined key OR new per-client key
                if name.endswith("tsr.docx") or ("/docx_" in name and name.endswith(".docx")):
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


class LocalCacheService:
    """
    Local filesystem cache service with the same interface as CacheService.

    Stores cached records under LOCAL_CACHE_DIR (default: ~/.cache/gujrat_tsr_agent/cache).
    Used automatically when GCS_CACHE_BUCKET is not configured.
    """

    DEFAULT_TTL_DAYS = 7
    DEFAULT_CACHE_DIR = os.path.join(Path.home(), ".cache", "gujrat_tsr_agent", "cache")

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        ttl_days: int = DEFAULT_TTL_DAYS,
        logger: Optional[logging.Logger] = None
    ):
        self.cache_dir = cache_dir or os.getenv("LOCAL_CACHE_DIR", self.DEFAULT_CACHE_DIR)
        self.ttl_days = ttl_days
        self.logger = logger or logging.getLogger(__name__)
        os.makedirs(self.cache_dir, exist_ok=True)
        self.logger.info(f"Local cache service initialized at: {self.cache_dir}")

    def generate_cache_key_from_translated(
        self,
        translated_district: str,
        translated_taluka: str,
        translated_village: str,
        survey_number: str
    ) -> str:
        components = [
            translated_district.strip().lower(),
            translated_taluka.strip().lower(),
            translated_village.strip().lower(),
            survey_number.strip().lower()
        ]
        key_string = "|".join(components)
        return hashlib.sha256(key_string.encode()).hexdigest()[:32]

    def _entry_dir(self, cache_key: str) -> str:
        return os.path.join(self.cache_dir, cache_key)

    def _is_cache_valid(self, metadata: Dict[str, Any]) -> bool:
        try:
            cached_time = datetime.fromisoformat(metadata.get("timestamp", ""))
            return datetime.now(timezone.utc) < cached_time + timedelta(days=self.ttl_days)
        except (ValueError, TypeError):
            return False

    def get_cached_record_by_key(
        self,
        cache_key: str
    ) -> Optional[Tuple[bytes, Optional[bytes], Dict[str, Any]]]:
        entry = self._entry_dir(cache_key)
        metadata_path = os.path.join(entry, "metadata.json")
        docx_path = os.path.join(entry, "tsr.docx")

        if not os.path.exists(metadata_path):
            self.logger.debug(f"Local cache miss: {cache_key}")
            return None

        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception as e:
            self.logger.warning(f"Could not read local cache metadata: {e}")
            return None

        if not self._is_cache_valid(metadata):
            self.logger.info(f"Local cache expired for key {cache_key}")
            self._cleanup_cache(cache_key)
            return None

        if not os.path.exists(docx_path):
            self.logger.warning(f"Local cache incomplete: missing DOCX for {cache_key}")
            return None

        with open(docx_path, "rb") as f:
            docx_content = f.read()

        pdf_content = None
        pdf_path = os.path.join(entry, "original.pdf")
        if os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                pdf_content = f.read()

        self.logger.info(f"Local cache HIT for key {cache_key}")
        return (docx_content, pdf_content, metadata)

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
        try:
            entry = self._entry_dir(cache_key)
            os.makedirs(entry, exist_ok=True)

            metadata = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "original_district": original_request.district,
                "original_taluka": original_request.taluka,
                "original_village": original_request.village,
                "survey_number": original_request.survey_number,
                "translated_district": translated_district,
                "translated_taluka": translated_taluka,
                "translated_village": translated_village,
                "ttl_days": self.ttl_days,
                "docx_size": len(docx_content),
                "pdf_size": len(pdf_content) if pdf_content else 0,
                **(additional_metadata or {})
            }

            with open(os.path.join(entry, "metadata.json"), "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            with open(os.path.join(entry, "tsr.docx"), "wb") as f:
                f.write(docx_content)

            if pdf_content:
                with open(os.path.join(entry, "original.pdf"), "wb") as f:
                    f.write(pdf_content)

            self.logger.info(
                f"Locally cached record {cache_key}: "
                f"DOCX={len(docx_content)} bytes, PDF={len(pdf_content) if pdf_content else 0} bytes"
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to write local cache: {e}")
            return False

    # ---- Per-PDF / per-client split cache ----

    def get_cached_pdf_by_key(self, pdf_key: str) -> Optional[bytes]:
        """Return the cached PDF bytes for this location key, or None on miss/expiry."""
        entry = self._entry_dir(pdf_key)
        metadata_path = os.path.join(entry, "metadata.json")
        pdf_path = os.path.join(entry, "original.pdf")

        if not os.path.exists(metadata_path) or not os.path.exists(pdf_path):
            return None
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception as e:
            self.logger.warning(f"Could not read local cache metadata: {e}")
            return None
        if not self._is_cache_valid(metadata):
            self.logger.info(f"Local PDF cache expired for key {pdf_key}")
            self._cleanup_cache(pdf_key)
            return None
        with open(pdf_path, "rb") as f:
            return f.read()

    def cache_pdf_by_key(self, pdf_key: str, pdf_content: bytes) -> bool:
        """Store the PDF under this location key. Creates a metadata.json if absent."""
        try:
            entry = self._entry_dir(pdf_key)
            os.makedirs(entry, exist_ok=True)

            metadata_path = os.path.join(entry, "metadata.json")
            if not os.path.exists(metadata_path):
                metadata = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "ttl_days": self.ttl_days,
                }
                with open(metadata_path, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)

            with open(os.path.join(entry, "original.pdf"), "wb") as f:
                f.write(pdf_content)
            self.logger.info(f"Locally cached PDF {pdf_key}: {len(pdf_content)} bytes")
            return True
        except Exception as e:
            self.logger.error(f"Failed to write local PDF cache: {e}")
            return False

    def get_cached_docx_by_key(self, pdf_key: str, client_id: str) -> Optional[bytes]:
        """Return the cached DOCX bytes for this (location, client) pair, or None on miss."""
        entry = self._entry_dir(pdf_key)
        metadata_path = os.path.join(entry, "metadata.json")
        docx_path = os.path.join(entry, f"docx_{client_id}.docx")

        if not os.path.exists(metadata_path) or not os.path.exists(docx_path):
            return None
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception as e:
            self.logger.warning(f"Could not read local cache metadata: {e}")
            return None
        if not self._is_cache_valid(metadata):
            self.logger.info(f"Local DOCX cache expired for key {pdf_key}")
            self._cleanup_cache(pdf_key)
            return None
        with open(docx_path, "rb") as f:
            return f.read()

    def cache_docx_by_key(
        self,
        pdf_key: str,
        client_id: str,
        original_request: LandRecordRequest,
        translated_district: str,
        translated_taluka: str,
        translated_village: str,
        docx_content: bytes,
        additional_metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Store the DOCX under cache/{pdf_key}/docx_{client_id}.docx."""
        try:
            entry = self._entry_dir(pdf_key)
            os.makedirs(entry, exist_ok=True)

            metadata_path = os.path.join(entry, "metadata.json")
            metadata: Dict[str, Any] = {}
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, "r", encoding="utf-8") as f:
                        metadata = json.load(f)
                except Exception:
                    metadata = {}

            metadata.update({
                "timestamp": metadata.get("timestamp") or datetime.now(timezone.utc).isoformat(),
                "original_district": original_request.district,
                "original_taluka": original_request.taluka,
                "original_village": original_request.village,
                "survey_number": original_request.survey_number,
                "translated_district": translated_district,
                "translated_taluka": translated_taluka,
                "translated_village": translated_village,
                "ttl_days": self.ttl_days,
                **(additional_metadata or {}),
            })
            docx_versions = metadata.get("docx_versions") or {}
            docx_versions[client_id] = datetime.now(timezone.utc).isoformat()
            metadata["docx_versions"] = docx_versions

            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            with open(os.path.join(entry, f"docx_{client_id}.docx"), "wb") as f:
                f.write(docx_content)
            self.logger.info(
                f"Locally cached DOCX {pdf_key}/docx_{client_id}: {len(docx_content)} bytes"
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to write local DOCX cache: {e}")
            return False

    def _cleanup_cache(self, cache_key: str) -> None:
        import shutil
        entry = self._entry_dir(cache_key)
        try:
            if os.path.exists(entry):
                shutil.rmtree(entry)
        except Exception as e:
            self.logger.warning(f"Failed to clean up local cache {cache_key}: {e}")

    def get_cache_stats(self) -> Dict[str, Any]:
        try:
            entries = [d for d in os.listdir(self.cache_dir)
                       if os.path.isdir(os.path.join(self.cache_dir, d))]
            total_size = sum(
                os.path.getsize(os.path.join(self.cache_dir, e, f))
                for e in entries
                for f in os.listdir(os.path.join(self.cache_dir, e))
                if os.path.isfile(os.path.join(self.cache_dir, e, f))
            )
            return {
                "total_cached_records": len(entries),
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "cache_dir": self.cache_dir,
                "ttl_days": self.ttl_days
            }
        except Exception as e:
            return {"error": str(e)}

    def check_and_clear_docx_if_new_version(self, current_version: str) -> bool:
        return False


# Singleton instance
_cache_service = None


def get_cache_service(
    bucket_name: Optional[str] = None,
    ttl_days: int = CacheService.DEFAULT_TTL_DAYS,
    logger: Optional[logging.Logger] = None
):
    """
    Get or create the global cache service instance.

    Returns GCS CacheService if GCS_CACHE_BUCKET is set,
    otherwise falls back to LocalCacheService.
    """
    global _cache_service

    if _cache_service is not None:
        return _cache_service

    bucket_name = bucket_name or os.getenv("GCS_CACHE_BUCKET")

    if bucket_name:
        try:
            _cache_service = CacheService(
                bucket_name=bucket_name,
                ttl_days=ttl_days,
                logger=logger
            )
            return _cache_service
        except Exception as e:
            logging.getLogger(__name__).error(f"Failed to initialize GCS cache, falling back to local: {e}")

    # Fallback to local filesystem cache
    _cache_service = LocalCacheService(ttl_days=ttl_days, logger=logger)
    return _cache_service
