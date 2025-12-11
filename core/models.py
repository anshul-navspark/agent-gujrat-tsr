"""
Domain models and data transfer objects for Gujarat TSR Agent.

This module defines the core data structures used throughout the application.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime


@dataclass
class LandRecordRequest:
    """Request model for land record processing."""
    
    district: str
    taluka: str
    village: str
    survey_number: str
    
    def __post_init__(self):
        """Validate and normalize input data."""
        self.district = self.district.strip()
        self.taluka = self.taluka.strip()
        self.village = self.village.strip()
        self.survey_number = self.survey_number.strip()
        
        if not all([self.district, self.taluka, self.village, self.survey_number]):
            raise ValueError("All fields (district, taluka, village, survey_number) are required")


@dataclass
class TSRDocument:
    """Model for a generated TSR document."""
    
    docx_content: bytes
    pdf_content: Optional[bytes] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate document content."""
        if not self.docx_content:
            raise ValueError("DOCX content is required")


@dataclass
class ProcessingResult:
    """Result of processing a land record request."""
    
    success: bool
    request: LandRecordRequest
    document: Optional[TSRDocument] = None
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # For backward compatibility with existing code
    @property
    def docx_content(self) -> Optional[bytes]:
        """Get DOCX content from document."""
        return self.document.docx_content if self.document else None
    
    @property
    def pdf_content(self) -> Optional[bytes]:
        """Get PDF content from document."""
        return self.document.pdf_content if self.document else None
    
    @property
    def district(self) -> str:
        """Get district from request."""
        return self.request.district
    
    @property
    def taluka(self) -> str:
        """Get taluka from request."""
        return self.request.taluka
    
    @property
    def village(self) -> str:
        """Get village from request."""
        return self.request.village
    
    @property
    def survey(self) -> str:
        """Get survey number from request."""
        return self.request.survey_number
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'success': self.success,
            'district': self.district,
            'taluka': self.taluka,
            'village': self.village,
            'survey': self.survey,
            'error': self.error,
            'timestamp': self.timestamp.isoformat(),
            'has_docx': self.docx_content is not None,
            'has_pdf': self.pdf_content is not None,
            **self.metadata
        }


@dataclass
class APIResponse:
    """Response from API processing."""
    
    success: bool
    docx_content: Optional[bytes] = None
    pdf_content: Optional[bytes] = None
    error: Optional[str] = None
    status_code: Optional[int] = None
    cache_hit: bool = False
    
    def to_processing_result(self, request: LandRecordRequest) -> ProcessingResult:
        """Convert API response to ProcessingResult."""
        document = None
        if self.success and self.docx_content:
            document = TSRDocument(
                docx_content=self.docx_content,
                pdf_content=self.pdf_content
            )
        
        return ProcessingResult(
            success=self.success,
            request=request,
            document=document,
            error=self.error,
            metadata={'status_code': self.status_code} if self.status_code else {}
        )
