# Streamlit Application Services
"""
Service modules for the Streamlit application.

This package provides business logic services used by the Streamlit UI components.

Note: Import StreamlitService directly from app.services.streamlit_service
to avoid circular import issues with services.file_service.
"""

# Lazy imports to avoid circular dependencies
# from app.services.streamlit_service import StreamlitService, get_streamlit_service

__all__ = [
    'StreamlitService',
    'get_streamlit_service',
]
