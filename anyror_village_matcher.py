"""
Enhanced village matching utility for AnyRoR dropdown selection.
Helps with fuzzy matching when exact village names don't match dropdown options.
"""

import logging
from typing import List, Optional, Tuple
import difflib
import re


class VillageNameMatcher:
    """Utility class for matching village names with dropdown options."""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def find_best_match(self, target_village: str, available_options: List[str]) -> Optional[str]:
        """
        Find the best matching village name from available dropdown options.
        
        Args:
            target_village: The village name we're trying to match
            available_options: List of available options from the dropdown
            
        Returns:
            Best matching option or None if no good match found
        """
        if not target_village or not available_options:
            return None
        
        target_clean = target_village.strip()
        
        # Strategy 1: Exact match
        for option in available_options:
            if option.strip() == target_clean:
                self.logger.info(f"Found exact match: {option}")
                return option
        
        # Strategy 2: Case-insensitive exact match
        target_lower = target_clean.lower()
        for option in available_options:
            if option.strip().lower() == target_lower:
                self.logger.info(f"Found case-insensitive match: {option}")
                return option
        
        # Strategy 3: Partial match (target in option)
        for option in available_options:
            if target_clean in option.strip():
                self.logger.info(f"Found partial match (target in option): {option}")
                return option
        
        # Strategy 4: Reverse partial match (option in target)
        for option in available_options:
            option_clean = option.strip()
            if option_clean and option_clean in target_clean:
                self.logger.info(f"Found reverse partial match (option in target): {option}")
                return option
        
        # Strategy 5: Case-insensitive partial matching
        for option in available_options:
            option_lower = option.strip().lower()
            if target_lower in option_lower or option_lower in target_lower:
                self.logger.info(f"Found case-insensitive partial match: {option}")
                return option
        
        # Strategy 6: Fuzzy matching using difflib
        matches = difflib.get_close_matches(target_clean, available_options, n=3, cutoff=0.6)
        if matches:
            best_match = matches[0]
            self.logger.info(f"Found fuzzy match: {best_match}")
            return best_match
        
        # Strategy 7: Word-based matching (split by spaces and check individual words)
        target_words = set(target_clean.lower().split())
        best_score = 0
        best_option = None
        
        for option in available_options:
            option_words = set(option.strip().lower().split())
            # Calculate Jaccard similarity
            intersection = len(target_words.intersection(option_words))
            union = len(target_words.union(option_words))
            if union > 0:
                score = intersection / union
                if score > best_score and score > 0.3:  # At least 30% similarity
                    best_score = score
                    best_option = option
        
        if best_option:
            self.logger.info(f"Found word-based match with score {best_score:.2f}: {best_option}")
            return best_option
        
        # Strategy 8: Enhanced Gujarati-English transliteration matching
        # Common transliteration mappings
        transliteration_map = {
            'hothiji': 'હોથીજી',
            'khadaba': 'ખડબા',
            'khadba': 'ખડબા',
            'trambo': 'ત્રંબો',
            'trambau': 'ત્રંબો',
            'abdasa': 'અબડાસા',
            'kutch': 'કચ્છ',
            'jamnagar': 'જામનગર'
        }
        
        # Try to find matches using transliteration
        target_lower = target_clean.lower()
        for option in available_options:
            option_lower = option.strip().lower()
            
            # Check if any part of the target transliterates to something in the option
            for eng, guj in transliteration_map.items():
                if eng in target_lower and guj in option:
                    self.logger.info(f"Found transliteration match: {option} (matched {eng} → {guj})")
                    return option
        
        # Strategy 9: Pattern matching for codes (like "- 034")
        # If target contains only letters, look for similar letters with codes
        if re.match(r'^[a-zA-Z\s]+$', target_clean):
            # Remove common words and look for the main part
            main_words = [w for w in target_clean.lower().split() if w not in ['village', 'gram', 'gam']]
            if main_words:
                main_part = ' '.join(main_words)
                for option in available_options:
                    # Extract the name part before any dash/code
                    option_name = re.split(r'\s*-\s*\d+', option)[0].strip()
                    if option_name and len(option_name) > 2:
                        # Use fuzzy matching on the name part
                        similarity = difflib.SequenceMatcher(None, main_part.lower(), option_name.lower()).ratio()
                        if similarity > 0.4:  # Lower threshold for cross-language matching
                            self.logger.info(f"Found pattern match: {option} (similarity: {similarity:.2f})")
                            return option
        
        self.logger.warning(f"No suitable match found for village: {target_village}")
        return None
    
    def get_match_strategies_report(self, target_village: str, available_options: List[str]) -> str:
        """
        Generate a detailed report of matching attempts for debugging.
        
        Args:
            target_village: The village name we're trying to match
            available_options: List of available options from the dropdown
            
        Returns:
            Detailed report as string
        """
        report = [f"Village Matching Report for: '{target_village}'"]
        report.append(f"Total available options: {len(available_options)}")
        
        if len(available_options) <= 20:
            report.append(f"Available options: {available_options}")
        else:
            report.append(f"First 10 options: {available_options[:10]}")
            report.append(f"Last 10 options: {available_options[-10:]}")
        
        # Check each strategy
        target_clean = target_village.strip()
        target_lower = target_clean.lower()
        
        # Exact matches
        exact_matches = [opt for opt in available_options if opt.strip() == target_clean]
        report.append(f"Exact matches: {exact_matches}")
        
        # Case-insensitive matches
        case_matches = [opt for opt in available_options if opt.strip().lower() == target_lower]
        report.append(f"Case-insensitive matches: {case_matches}")
        
        # Partial matches
        partial_matches = [opt for opt in available_options if target_clean in opt.strip()]
        report.append(f"Partial matches (target in option): {partial_matches[:5]}")
        
        # Fuzzy matches
        fuzzy_matches = difflib.get_close_matches(target_clean, available_options, n=5, cutoff=0.5)
        report.append(f"Fuzzy matches (cutoff=0.5): {fuzzy_matches}")
        
        return "\n".join(report)


# Utility function for easy import
def find_village_match(target_village: str, available_options: List[str], logger=None) -> Optional[str]:
    """
    Convenience function to find best village match.
    
    Args:
        target_village: Village name to match
        available_options: Available dropdown options
        logger: Optional logger instance
        
    Returns:
        Best matching option or None
    """
    matcher = VillageNameMatcher(logger)
    return matcher.find_best_match(target_village, available_options)
