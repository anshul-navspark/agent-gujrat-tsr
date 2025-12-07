# Streamlit Service
"""
Business logic service for the Streamlit application.

This service encapsulates the core business logic used by the Streamlit UI,
providing a clean separation between the presentation layer and business logic.
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path for imports
_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.models import LandRecordRequest, APIResponse
from core.exceptions import TSRAgentException, ValidationException
from services.file_service import FileService, get_file_service



class StreamlitService:
    """Service class for Streamlit application business logic.

    This service handles:
    - Single record processing coordination
    - Batch processing coordination
    - Retry logic for failed entries
    - Result aggregation and formatting
    """

    def __init__(
        self,
        api_client,
        file_service: Optional[FileService] = None,
        max_workers: int = 20,
        logger: Optional[logging.Logger] = None
    ):
        """Initialize the Streamlit service.

        Args:
            api_client: TSRAPIClient instance for API communication.
            file_service: FileService instance for file operations. Optional.
            max_workers: Maximum number of parallel workers for batch processing.
            logger: Optional logger instance.
        """
        self.api_client = api_client
        self.file_service = file_service or get_file_service()
        self.max_workers = max_workers
        self.logger = logger or logging.getLogger(__name__)

    def process_single_record(
        self,
        district: str,
        taluka: str,
        village: str,
        survey_number: str
    ) -> Dict[str, Any]:
        """Process a single land record via the API.

        Args:
            district: District name.
            taluka: Taluka name.
            village: Village name.
            survey_number: Survey/Block number.

        Returns:
            Dictionary with processing result containing:
            - success: bool
            - docx_content: bytes or None
            - pdf_content: bytes or None
            - error: str or None
            - timestamp: ISO format timestamp
        """
        self.logger.info(
            f"Processing single record: {district}, {taluka}, {village}, {survey_number}"
        )

        try:
            response: APIResponse = self.api_client.process_record(
                district=district,
                taluka=taluka,
                village=village,
                survey_number=survey_number
            )

            result = self._format_result(
                district=district,
                taluka=taluka,
                village=village,
                survey=survey_number,
                response=response
            )

            if response.success:
                self.logger.info(f"Successfully processed record")
            else:
                self.logger.warning(f"Failed to process record: {response.error}")

            return result

        except Exception as e:
            self.logger.error(f"Error processing record: {e}")
            return self._format_error_result(
                district=district,
                taluka=taluka,
                village=village,
                survey=survey_number,
                error=str(e)
            )

    def process_batch(
        self,
        records: List[Dict[str, str]],
        progress_callback: Optional[callable] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Process multiple records in parallel.

        Args:
            records: List of dictionaries with keys:
                - district, taluka, village, survey_number, row_idx (optional)
            progress_callback: Optional callback function(completed, total, result)
                called after each record is processed.

        Returns:
            Tuple of (results_list, summary_dict)
            - results_list: List of result dictionaries
            - summary_dict: Summary statistics including:
                - total, successful, failed, duration_seconds
        """
        total_records = len(records)
        if total_records == 0:
            return [], {"total": 0, "successful": 0, "failed": 0, "duration_seconds": 0}

        self.logger.info(
            f"Starting batch processing: {total_records} records with {self.max_workers} workers"
        )

        results: List[Dict[str, Any]] = []
        successful = 0
        failed = 0
        start_time = datetime.now()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_record = {}

            for record in records:
                future = executor.submit(
                    self._process_record_with_retry,
                    record.get("district", ""),
                    record.get("taluka", ""),
                    record.get("village", ""),
                    record.get("survey_number", ""),
                    record.get("row_idx")
                )
                future_to_record[future] = record

            for completed_count, future in enumerate(as_completed(future_to_record), start=1):
                try:
                    result = future.result()
                    results.append(result)

                    if result["success"]:
                        successful += 1
                    else:
                        failed += 1

                except Exception as e:
                    failed += 1
                    record = future_to_record[future]
                    result = self._format_error_result(
                        district=record.get("district", ""),
                        taluka=record.get("taluka", ""),
                        village=record.get("village", ""),
                        survey=record.get("survey_number", ""),
                        error=str(e),
                        row_idx=record.get("row_idx")
                    )
                    results.append(result)

                if progress_callback:
                    try:
                        progress_callback(completed_count, total_records, result)
                    except Exception as e:
                        self.logger.warning(f"Progress callback error: {e}")

        duration = datetime.now() - start_time

        summary = {
            "total": total_records,
            "successful": successful,
            "failed": failed,
            "duration_seconds": duration.total_seconds()
        }

        self.logger.info(
            f"Batch processing complete: {successful}/{total_records} successful "
            f"in {duration.total_seconds():.1f}s"
        )

        return results, summary

    def retry_failed(
        self,
        results: List[Dict[str, Any]],
        progress_callback: Optional[callable] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Retry all failed entries from a previous batch.

        Args:
            results: List of result dictionaries from previous processing.
            progress_callback: Optional callback function(completed, total, result).

        Returns:
            Tuple of (updated_results, summary)
            - updated_results: Original list with failed entries replaced
            - summary: Retry statistics
        """
        failed_indices = [
            (i, r) for i, r in enumerate(results) if not r.get("success")
        ]

        if not failed_indices:
            return results, {"total": 0, "successful": 0, "failed": 0, "duration_seconds": 0}

        self.logger.info(f"Retrying {len(failed_indices)} failed entries")

        records_to_retry = [
            {
                "district": r["district"],
                "taluka": r["taluka"],
                "village": r["village"],
                "survey_number": r["survey"],
                "row_idx": r.get("row_idx"),
                "original_index": idx
            }
            for idx, r in failed_indices
        ]

        # Process the retries
        retry_results, summary = self.process_batch(
            [
                {k: v for k, v in rec.items() if k != "original_index"}
                for rec in records_to_retry
            ],
            progress_callback
        )

        # Update the original results list
        for i, (original_idx, _) in enumerate(failed_indices):
            if i < len(retry_results):
                results[original_idx] = retry_results[i]

        return results, summary

    def create_download_zip(
        self,
        results: List[Dict[str, Any]],
        zip_filename: str = "tsr_documents.zip"
    ) -> bytes:
        """Create a ZIP file containing all successful documents.

        Args:
            results: List of processing results.
            zip_filename: Name for the ZIP file.

        Returns:
            ZIP file content as bytes.
        """
        files_to_zip: Dict[str, bytes] = {}

        for result in results:
            if not result.get("success"):
                continue

            request = LandRecordRequest(
                district=result["district"],
                taluka=result["taluka"],
                village=result["village"],
                survey_number=result["survey"]
            )

            if result.get("docx_content"):
                filename = self.file_service.generate_filename(
                    request, file_type="docx", prefix="TSR"
                )
                files_to_zip[filename] = result["docx_content"]

            if result.get("pdf_content"):
                filename = self.file_service.generate_filename(
                    request, file_type="pdf", prefix="Original"
                )
                files_to_zip[filename] = result["pdf_content"]

        return self.file_service.create_zip(files_to_zip, zip_filename)

    def _process_record_with_retry(
        self,
        district: str,
        taluka: str,
        village: str,
        survey: str,
        row_idx: Optional[int] = None
    ) -> Dict[str, Any]:
        """Process a single record with the API client's built-in retry logic.

        Args:
            district: District name.
            taluka: Taluka name.
            village: Village name.
            survey: Survey number.
            row_idx: Optional row index from source file.

        Returns:
            Result dictionary.
        """
        try:
            response: APIResponse = self.api_client.process_record(
                district=district,
                taluka=taluka,
                village=village,
                survey_number=survey
            )

            return self._format_result(
                district=district,
                taluka=taluka,
                village=village,
                survey=survey,
                response=response,
                row_idx=row_idx
            )

        except Exception as e:
            return self._format_error_result(
                district=district,
                taluka=taluka,
                village=village,
                survey=survey,
                error=str(e),
                row_idx=row_idx
            )

    def _format_result(
        self,
        district: str,
        taluka: str,
        village: str,
        survey: str,
        response: APIResponse,
        row_idx: Optional[int] = None
    ) -> Dict[str, Any]:
        """Format an API response into a standard result dictionary.

        Args:
            district: District name.
            taluka: Taluka name.
            village: Village name.
            survey: Survey number.
            response: APIResponse from the API client.
            row_idx: Optional row index.

        Returns:
            Standardized result dictionary.
        """
        docx_path = None
        pdf_path = None

        if response.success:
            if response.docx_content:
                docx_path = f"{district}_{taluka}_{village}_{survey}_TSR.docx"
            if response.pdf_content:
                pdf_path = f"{district}_{taluka}_{village}_{survey}_Original.pdf"

        result = {
            "district": district,
            "taluka": taluka,
            "village": village,
            "survey": survey,
            "success": response.success,
            "docx_path": docx_path,
            "docx_content": response.docx_content if response.success else None,
            "pdf_path": pdf_path,
            "pdf_content": response.pdf_content if response.success else None,
            "error": response.error,
            "timestamp": datetime.now().isoformat(),
        }

        if row_idx is not None:
            result["row_idx"] = row_idx

        return result

    def _format_error_result(
        self,
        district: str,
        taluka: str,
        village: str,
        survey: str,
        error: str,
        row_idx: Optional[int] = None
    ) -> Dict[str, Any]:
        """Format an error into a standard result dictionary.

        Args:
            district: District name.
            taluka: Taluka name.
            village: Village name.
            survey: Survey number.
            error: Error message.
            row_idx: Optional row index.

        Returns:
            Standardized error result dictionary.
        """
        result = {
            "district": district,
            "taluka": taluka,
            "village": village,
            "survey": survey,
            "success": False,
            "docx_path": None,
            "docx_content": None,
            "pdf_path": None,
            "pdf_content": None,
            "error": error,
            "timestamp": datetime.now().isoformat(),
        }

        if row_idx is not None:
            result["row_idx"] = row_idx

        return result


def get_streamlit_service(
    api_client,
    max_workers: int = 20
) -> StreamlitService:
    """Factory function to create a StreamlitService instance.

    Args:
        api_client: TSRAPIClient instance.
        max_workers: Maximum parallel workers for batch processing.

    Returns:
        Configured StreamlitService instance.
    """
    return StreamlitService(
        api_client=api_client,
        max_workers=max_workers
    )
