"""
AI-based column detection utility for automatically mapping Excel columns
to District, Taluka, Village, and Survey fields.
"""

import pandas as pd
import logging
from typing import Dict, Optional, List, Tuple
import re
from collections import Counter


class AIColumnDetector:
    """AI-powered column detection for automatic field mapping."""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        if logger is None:
            # Create a simple logger that works well with Streamlit
            self.logger = logging.getLogger(__name__)
            if not self.logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)
                self.logger.setLevel(logging.INFO)
        else:
            self.logger = logger
        
        # Known patterns for different field types
        self.field_patterns = {
            'district': {
                'header_keywords': [
                    'district', 'જિલ્લો', 'જિલ્લા', 'dist', 'જિ', 'zilla', 'zillo'
                ],
                'content_patterns': [
                    r'કચ્છ|kutch|kachchh|bhuj|ભુજ',
                    r'પાટણ|patan',
                    r'બનાસકાંઠા|banaskantha',
                    r'ભાવનગર|bhavnagar',
                    r'જામનગર|jamnagar'
                ]
            },
            'taluka': {
                'header_keywords': [
                    'taluka', 'તાલુકો', 'તાલુકા', 'tal', 'તા', 'tehsil', 'તહેસીલ'
                ],
                'content_patterns': [
                    r'અબડાસા|abdasa',
                    r'ભુજ|bhuj',
                    r'અંજાર|anjar',
                    r'પાટણ|patan',
                    r'ધાનેરા|dhanera',
                    r'તળાજા|talaja',
                    r'જામજોધપુર|jamjodhpur'
                ]
            },
            'village': {
                'header_keywords': [
                    'village', 'ગામ', 'વિલેજ', 'વિ', 'vil', 'gram', 'ગ્રામ'
                ],
                'content_patterns': [
                    r'અનાવાડા|anavada',
                    r'ત્રંબો|trambo|trambau',
                    r'એડાલ|edal',
                    r'જાડી|jadi',
                    r'જડીયા|jadiya',
                    r'જનાલી|janali',
                    r'શિયા|shiya',
                    r'માલોત્રા|malotra',
                    r'દાઠા|datha',
                    r'હોથીજી\s*ખડબા|hothiji.*khadaba?'
                ]
            },
            'survey': {
                'header_keywords': [
                    'survey', 'સર્વે', 'સર્વેનો', r'સર્વે\s*નો', 'block', 'બ્લોક', 
                    r'સર્વે\s*નંબર', 'survey.*number', r'સર્વે.*નંબર', 'survey.*no'
                ],
                'content_patterns': [
                    r'^\d+[p]?\d*$',  # Numbers with optional 'p'
                    r'^\d+/\d+$',     # Fractions like 17/2
                    r'^\d+[p]\d+$',   # Pattern like 26p1
                    r'^\d+$'          # Simple numbers
                ]
            }
        }
    
    def detect_columns(self, df: pd.DataFrame) -> Dict[str, Optional[str]]:
        """
        Automatically detect and map columns to field types.
        
        Args:
            df: DataFrame to analyze
            
        Returns:
            Dictionary mapping field types to column names
        """
        if df is None or len(df) == 0:
            return {'district': None, 'taluka': None, 'village': None, 'survey': None}
        
        columns = list(df.columns)
        try:
            self.logger.info(f"Analyzing {len(columns)} columns for auto-detection")
        except:
            pass  # Silently continue if logging fails
        
        detected_mapping = {}
        used_columns = set()
        
        # Analyze each field type
        for field_type in ['district', 'taluka', 'village', 'survey']:
            best_column = self._find_best_column_for_field(df, field_type, columns, used_columns)
            detected_mapping[field_type] = best_column
            if best_column:
                used_columns.add(best_column)
                try:
                    self.logger.info(f"Detected {field_type} → {best_column}")
                except:
                    pass  # Silently continue if logging fails
        
        return detected_mapping
    
    def _find_best_column_for_field(self, df: pd.DataFrame, field_type: str, 
                                   columns: List[str], used_columns: set) -> Optional[str]:
        """Find the best column match for a specific field type."""
        field_config = self.field_patterns[field_type]
        column_scores = {}
        
        for col in columns:
            if col in used_columns:
                continue
                
            score = 0
            
            # Score based on header name
            header_score = self._score_header(col, field_config['header_keywords'])
            score += header_score * 10  # Weight header matching highly
            
            # Score based on content patterns
            content_score = self._score_content(df[col], field_config['content_patterns'])
            score += content_score * 5
            
            # Additional scoring for survey number patterns
            if field_type == 'survey':
                numeric_score = self._score_numeric_pattern(df[col])
                score += numeric_score * 3
            
            column_scores[col] = score
            try:
                self.logger.debug(f"Column '{col}' score for {field_type}: {score} (header:{header_score}, content:{content_score})")
            except:
                pass  # Silently continue if logging fails
        
        # Return the highest scoring column if it meets minimum threshold
        if column_scores:
            best_col = max(column_scores.items(), key=lambda x: x[1])
            if best_col[1] > 2:  # Minimum confidence threshold
                return best_col[0]
        
        return None
    
    def _score_header(self, column_name: str, keywords: List[str]) -> float:
        """Score column header based on keyword matching."""
        col_lower = column_name.lower().strip()
        
        # Exact match gets highest score
        for keyword in keywords:
            if keyword.lower() == col_lower:
                return 10.0
        
        # Partial match gets medium score
        for keyword in keywords:
            if keyword.lower() in col_lower or col_lower in keyword.lower():
                return 7.0
        
        # Fuzzy matching for common variations
        for keyword in keywords:
            if self._fuzzy_match(col_lower, keyword.lower()):
                return 5.0
        
        return 0.0
    
    def _score_content(self, column_data: pd.Series, patterns: List[str]) -> float:
        """Score column content based on pattern matching."""
        if len(column_data) == 0:
            return 0.0
        
        # Sample some non-null values for analysis
        sample_values = column_data.dropna().astype(str).head(20)
        if len(sample_values) == 0:
            return 0.0
        
        match_count = 0
        total_checked = 0
        
        for value in sample_values:
            value_clean = value.strip().lower()
            total_checked += 1
            
            for pattern in patterns:
                if re.search(pattern, value_clean, re.IGNORECASE):
                    match_count += 1
                    break
        
        # Return percentage of matches
        return (match_count / total_checked) * 10 if total_checked > 0 else 0.0
    
    def _score_numeric_pattern(self, column_data: pd.Series) -> float:
        """Special scoring for survey number patterns."""
        if len(column_data) == 0:
            return 0.0
        
        sample_values = column_data.dropna().astype(str).head(20)
        if len(sample_values) == 0:
            return 0.0
        
        numeric_count = 0
        survey_pattern_count = 0
        
        for value in sample_values:
            value_clean = value.strip()
            
            # Check if it's numeric-like
            if re.match(r'^\d+', value_clean):
                numeric_count += 1
            
            # Check for survey-specific patterns
            if re.match(r'^\d+[p]?\d*$|^\d+/\d+$', value_clean):
                survey_pattern_count += 1
        
        numeric_ratio = numeric_count / len(sample_values)
        pattern_ratio = survey_pattern_count / len(sample_values)
        
        return (numeric_ratio * 5) + (pattern_ratio * 8)
    
    def _fuzzy_match(self, str1: str, str2: str, threshold: float = 0.7) -> bool:
        """Simple fuzzy string matching."""
        if not str1 or not str2:
            return False
        
        # Levenshtein-like similarity
        longer = str1 if len(str1) > len(str2) else str2
        shorter = str2 if longer == str1 else str1
        
        if len(longer) == 0:
            return True
        
        # Calculate similarity ratio
        matches = sum(1 for a, b in zip(shorter, longer) if a == b)
        similarity = matches / len(longer)
        
        return similarity >= threshold
    
    def get_confidence_report(self, df: pd.DataFrame, detected_mapping: Dict[str, Optional[str]]) -> str:
        """Generate a confidence report for the detected mapping."""
        report = ["🤖 AI Column Detection Report:"]
        
        for field_type, column in detected_mapping.items():
            if column:
                # Calculate confidence metrics
                confidence = self._calculate_confidence(df, field_type, column)
                status = "✅ High" if confidence > 7 else "⚠️ Medium" if confidence > 4 else "❌ Low"
                report.append(f"  {field_type.title()}: '{column}' (Confidence: {status})")
            else:
                report.append(f"  {field_type.title()}: Not detected ❌")
        
        return "\n".join(report)
    
    def _calculate_confidence(self, df: pd.DataFrame, field_type: str, column: str) -> float:
        """Calculate confidence score for a detected mapping."""
        field_config = self.field_patterns[field_type]
        
        header_score = self._score_header(column, field_config['header_keywords'])
        content_score = self._score_content(df[column], field_config['content_patterns'])
        
        if field_type == 'survey':
            numeric_score = self._score_numeric_pattern(df[column])
            return (header_score + content_score + numeric_score) / 3
        
        return (header_score + content_score) / 2


def auto_detect_columns(df: pd.DataFrame, logger=None) -> Tuple[Dict[str, Optional[str]], str]:
    """
    Convenience function for automatic column detection.
    
    Args:
        df: DataFrame to analyze
        logger: Optional logger instance
        
    Returns:
        Tuple of (detected_mapping, confidence_report)
    """
    detector = AIColumnDetector(logger)
    mapping = detector.detect_columns(df)
    report = detector.get_confidence_report(df, mapping)
    
    return mapping, report
