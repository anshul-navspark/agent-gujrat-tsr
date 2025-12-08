"""
Token Usage Tracker for TSR Extraction

This module provides utilities for tracking, logging, and comparing token usage
between the original and optimized extraction methods.

Usage:
    from tsr_generator.utils.token_tracker import TokenTracker, log_token_comparison

    # Track a single extraction
    tracker = TokenTracker()
    tracker.start_extraction("document.pdf")
    # ... do extraction ...
    tracker.end_extraction(input_tokens=1000, output_tokens=500, api_calls=1)
    tracker.print_summary()

    # Compare methods
    log_token_comparison(pdf_path, logger)
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
import json


@dataclass
class ExtractionMetrics:
    """Metrics for a single extraction operation."""
    document_id: str
    start_time: float
    end_time: Optional[float] = None
    input_tokens: int = 0
    output_tokens: int = 0
    api_calls: int = 0
    method: str = "unknown"  # "original" or "optimized"
    success: bool = False
    error: Optional[str] = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def duration_ms(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0.0


@dataclass
class TokenTrackerStats:
    """Aggregated statistics from multiple extractions."""
    total_extractions: int = 0
    successful_extractions: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_api_calls: int = 0
    total_duration_ms: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def avg_tokens_per_doc(self) -> float:
        if self.total_extractions == 0:
            return 0.0
        return self.total_tokens / self.total_extractions

    @property
    def avg_api_calls_per_doc(self) -> float:
        if self.total_extractions == 0:
            return 0.0
        return self.total_api_calls / self.total_extractions


class TokenTracker:
    """
    Tracks token usage across multiple extraction operations.

    Supports tracking both original and optimized methods for comparison.
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.extractions: List[ExtractionMetrics] = []
        self._current: Optional[ExtractionMetrics] = None

    def start_extraction(self, document_id: str, method: str = "optimized"):
        """Start tracking a new extraction."""
        self._current = ExtractionMetrics(
            document_id=document_id,
            start_time=time.time(),
            method=method
        )
        self.logger.debug(f"Started tracking extraction for {document_id} ({method})")

    def end_extraction(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        api_calls: int = 1,
        success: bool = True,
        error: Optional[str] = None
    ):
        """End the current extraction and record metrics."""
        if self._current is None:
            self.logger.warning("end_extraction called without start_extraction")
            return

        self._current.end_time = time.time()
        self._current.input_tokens = input_tokens
        self._current.output_tokens = output_tokens
        self._current.api_calls = api_calls
        self._current.success = success
        self._current.error = error

        self.extractions.append(self._current)

        self.logger.debug(
            f"Extraction completed for {self._current.document_id}: "
            f"{self._current.total_tokens} tokens, {api_calls} API calls, "
            f"{self._current.duration_ms:.1f}ms"
        )

        self._current = None

    def get_stats(self, method: Optional[str] = None) -> TokenTrackerStats:
        """Get aggregated statistics, optionally filtered by method."""
        stats = TokenTrackerStats()

        for ext in self.extractions:
            if method and ext.method != method:
                continue

            stats.total_extractions += 1
            if ext.success:
                stats.successful_extractions += 1
            stats.total_input_tokens += ext.input_tokens
            stats.total_output_tokens += ext.output_tokens
            stats.total_api_calls += ext.api_calls
            stats.total_duration_ms += ext.duration_ms

        return stats

    def compare_methods(self) -> Dict[str, Any]:
        """Compare statistics between original and optimized methods."""
        original_stats = self.get_stats("original")
        optimized_stats = self.get_stats("optimized")

        if original_stats.total_extractions == 0 or optimized_stats.total_extractions == 0:
            return {
                "error": "Need extractions from both methods to compare",
                "original_count": original_stats.total_extractions,
                "optimized_count": optimized_stats.total_extractions
            }

        token_savings = original_stats.avg_tokens_per_doc - optimized_stats.avg_tokens_per_doc
        token_savings_pct = (token_savings / original_stats.avg_tokens_per_doc) * 100 if original_stats.avg_tokens_per_doc > 0 else 0

        api_call_savings = original_stats.avg_api_calls_per_doc - optimized_stats.avg_api_calls_per_doc

        return {
            "original": {
                "avg_tokens_per_doc": round(original_stats.avg_tokens_per_doc),
                "avg_api_calls_per_doc": round(original_stats.avg_api_calls_per_doc, 1),
                "total_extractions": original_stats.total_extractions
            },
            "optimized": {
                "avg_tokens_per_doc": round(optimized_stats.avg_tokens_per_doc),
                "avg_api_calls_per_doc": round(optimized_stats.avg_api_calls_per_doc, 1),
                "total_extractions": optimized_stats.total_extractions
            },
            "savings": {
                "tokens_per_doc": round(token_savings),
                "percentage": round(token_savings_pct, 1),
                "api_calls_per_doc": round(api_call_savings, 1)
            }
        }

    def print_summary(self):
        """Print a summary of tracked extractions to the logger."""
        stats = self.get_stats()

        self.logger.info("=" * 50)
        self.logger.info("TOKEN USAGE SUMMARY")
        self.logger.info("=" * 50)
        self.logger.info(f"Total extractions:    {stats.total_extractions}")
        self.logger.info(f"Successful:           {stats.successful_extractions}")
        self.logger.info(f"Total tokens used:    {stats.total_tokens:,}")
        self.logger.info(f"  - Input tokens:     {stats.total_input_tokens:,}")
        self.logger.info(f"  - Output tokens:    {stats.total_output_tokens:,}")
        self.logger.info(f"Total API calls:      {stats.total_api_calls}")
        self.logger.info(f"Avg tokens/doc:       {stats.avg_tokens_per_doc:,.0f}")
        self.logger.info(f"Avg API calls/doc:    {stats.avg_api_calls_per_doc:.1f}")
        self.logger.info("=" * 50)

    def to_json(self) -> str:
        """Export all metrics to JSON."""
        data = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_extractions": len(self.extractions),
                "total_tokens": sum(e.total_tokens for e in self.extractions),
                "total_api_calls": sum(e.api_calls for e in self.extractions)
            },
            "extractions": [
                {
                    "document_id": e.document_id,
                    "method": e.method,
                    "input_tokens": e.input_tokens,
                    "output_tokens": e.output_tokens,
                    "total_tokens": e.total_tokens,
                    "api_calls": e.api_calls,
                    "duration_ms": round(e.duration_ms, 2),
                    "success": e.success,
                    "error": e.error
                }
                for e in self.extractions
            ]
        }
        return json.dumps(data, indent=2)

    def clear(self):
        """Clear all tracked extractions."""
        self.extractions.clear()


def log_token_comparison(pdf_path: str, logger: Optional[logging.Logger] = None) -> Dict[str, Any]:
    """
    Log a comparison of token usage between original and optimized methods.

    This is useful for validating the optimization claims.

    Args:
        pdf_path: Path to a PDF file to analyze
        logger: Optional logger

    Returns:
        Comparison dictionary
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    try:
        from tsr_generator.utils.pdf_utils import extract_text_from_pdf
        from tsr_generator.extractors.unified_extractor import estimate_token_savings

        pdf_text = extract_text_from_pdf(pdf_path)
        if not pdf_text:
            return {"error": "Failed to extract PDF text"}

        comparison = estimate_token_savings(pdf_text)

        logger.info("=" * 60)
        logger.info("TOKEN USAGE COMPARISON: Original vs Optimized")
        logger.info("=" * 60)
        logger.info(f"Document: {pdf_path}")
        logger.info("-" * 60)
        logger.info("ORIGINAL METHOD (3 separate API calls):")
        logger.info(f"  Prompt tokens:   ~{comparison['old_approach']['prompt_tokens']:,}")
        logger.info(f"  Document tokens: ~{comparison['old_approach']['document_tokens']:,}")
        logger.info(f"  Total tokens:    ~{comparison['old_approach']['total_tokens']:,}")
        logger.info(f"  API calls:        {comparison['old_approach']['api_calls']}")
        logger.info("-" * 60)
        logger.info("OPTIMIZED METHOD (1 unified API call):")
        logger.info(f"  Prompt tokens:   ~{comparison['new_approach']['prompt_tokens']:,}")
        logger.info(f"  Document tokens: ~{comparison['new_approach']['document_tokens']:,}")
        logger.info(f"  Total tokens:    ~{comparison['new_approach']['total_tokens']:,}")
        logger.info(f"  API calls:        {comparison['new_approach']['api_calls']}")
        logger.info("-" * 60)
        logger.info("SAVINGS:")
        logger.info(f"  Tokens saved:    ~{comparison['savings']['tokens_saved']:,}")
        logger.info(f"  Percentage:       {comparison['savings']['percentage']}%")
        logger.info(f"  API calls saved:  {comparison['savings']['api_calls_saved']}")
        logger.info("=" * 60)

        return comparison

    except Exception as e:
        logger.error(f"Error comparing methods: {e}")
        return {"error": str(e)}


# Global tracker instance for convenience
_global_tracker: Optional[TokenTracker] = None


def get_global_tracker() -> TokenTracker:
    """Get the global token tracker instance."""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = TokenTracker()
    return _global_tracker
