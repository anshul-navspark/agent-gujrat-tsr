"""
UI Components for the Streamlit application.

This module provides reusable UI components for the Gujarat TSR Agent application.
"""

from app.components.single_record_form import single_record_form
from app.components.batch_processing_form import batch_processing_form
from app.components.results_display import results_display

__all__ = [
    'single_record_form',
    'batch_processing_form',
    'results_display',
]
