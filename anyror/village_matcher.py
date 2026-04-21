"""
Enhanced village matching utility for AnyRoR dropdown selection.
Helps with matching when exact village names don't match dropdown options.
Falls back to LLM when exact/partial strategies fail.
"""

import logging
import os
from typing import List, Optional
import re
import unicodedata

def normalize_text(text: str) -> str:
    """Normalize text using NFKC form and remove common invisible characters."""
    if not text:
        return ""
    # Normalize unicode characters
    text = unicodedata.normalize('NFKC', text)
    # Remove zero-width spaces and other common invisible characters
    text = text.replace('\u200b', '').replace('\ufeff', '')
    return text.strip()


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
        
        # Normalize target
        target_clean = normalize_text(target_village)
        target_lower = target_clean.lower()
        
        self.logger.debug(f"Matching village: '{target_clean}' (original: '{target_village}')")
        
        # Strategy 1: Exact match with normalization
        for option in available_options:
            option_clean = normalize_text(option)
            if option_clean == target_clean:
                self.logger.debug(f"Found exact match: {option}")
                return option
        
        # Strategy 2: Case-insensitive exact match
        for option in available_options:
            option_clean = normalize_text(option)
            if option_clean.lower() == target_lower:
                self.logger.debug(f"Found case-insensitive match: {option}")
                return option
        
        # Strategy 3: Partial match (target in option)
        for option in available_options:
            option_clean = normalize_text(option)
            if target_clean in option_clean:
                self.logger.debug(f"Found partial match (target in option): {option}")
                return option
        
        # Strategy 4: Reverse partial match (option in target)
        for option in available_options:
            option_clean = normalize_text(option)
            if option_clean and option_clean in target_clean:
                self.logger.debug(f"Found reverse partial match (option in target): {option}")
                return option
        
        # Strategy 5: Case-insensitive partial matching
        for option in available_options:
            option_clean = normalize_text(option)
            option_lower = option_clean.lower()
            if target_lower in option_lower or option_lower in target_lower:
                self.logger.debug(f"Found case-insensitive partial match: {option}")
                return option
        
        # Strategy 6: LLM-based matching — ask the model to pick from dropdown options
        self.logger.debug(f"Exact/partial strategies failed for '{target_village}', trying LLM match")
        llm_match = self._llm_match(target_village, available_options)
        if llm_match:
            self.logger.info(f"LLM matched '{target_village}' → '{llm_match}'")
            return llm_match

        self.logger.warning(f"No suitable match found for village: {target_village}")
        return None

    def _llm_match(self, target_village: str, available_options: List[str]) -> Optional[str]:
        """Use LLM to pick the best matching dropdown option for a village name."""
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            from dotenv import load_dotenv
            load_dotenv()

            model_name = os.getenv('GEMINI_TRANSLATION_MODEL', 'gemini-3.1-flash-lite-preview')
            llm = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=os.getenv('GEMINI_API_KEY'),
                temperature=0.0,
            )

            # Limit options sent to LLM to keep prompt short
            options_text = "\n".join(f"{i+1}. {opt}" for i, opt in enumerate(available_options[:80]))

            prompt = f"""You are a Gujarat place name expert. A user is looking for village "{target_village}" in an AnyRoR dropdown.

The dropdown options (in Gujarati with codes) are:
{options_text}

Which option best matches "{target_village}"? Consider phonetic similarity and transliteration variations.

Rules:
- Return ONLY the exact text of the matching option (copy it exactly as shown above)
- If no option is a reasonable match, return exactly: NO_MATCH

Best match:"""

            response = llm.invoke(prompt)
            result = response.content.strip()

            if result in ("NO_MATCH", "NO MATCH"):
                self.logger.info(f"LLM found no match for '{target_village}'")
                return None

            # Verify result is actually one of the options
            if result in available_options:
                return result

            # Allow for minor whitespace differences
            for opt in available_options:
                if opt.strip() == result.strip():
                    return opt

            self.logger.warning(f"LLM returned '{result}' which is not in available options")
            return None

        except Exception as e:
            self.logger.error(f"LLM village match failed: {e}")
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
        
        # LLM match (best effort)
        llm_match = self._llm_match(target_clean, available_options)
        report.append(f"LLM match: {llm_match}")
        
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
