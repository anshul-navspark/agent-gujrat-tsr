"""
JSON-Based Translation System with AI-Assisted Dictionary Lookup

This module provides translation from English to Gujarati using anyror_hierarchy.json
with AI assistance to find matches for unknown spelling variations.
"""
import json
import logging
from typing import Optional, Dict, List, Tuple
from langchain_google_genai import ChatGoogleGenerativeAI
import os
from dotenv import load_dotenv
from difflib import SequenceMatcher

load_dotenv()



class TranslationNotFoundError(Exception):
    """Raised when a translation cannot be found for a given text"""
    pass

class JSONTranslationSystem:
    """Translation system using anyror_hierarchy.json with AI-assisted lookup"""
    
    def __init__(self, json_path='anyror_hierarchy.json'):
        self.json_path = json_path
        self.hierarchy = self._load_json()
        self.llm = ChatGoogleGenerativeAI(
            model=os.getenv('GEMINI_MODEL_NAME', 'gemini-2.5-flash'),
            google_api_key=os.getenv('GEMINI_API_KEY'),
            temperature=0.0  # Deterministic for matching
        )
        self.logger = logging.getLogger(__name__)
        
        # Build reverse lookup cache for fast English → Gujarati
        self.english_to_gujarati = self._build_reverse_lookup()
        self.logger.info(f"Loaded {len(self.english_to_gujarati)} translations from {json_path}")
    
    def _load_json(self) -> Dict:
        """Load the hierarchy JSON"""
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            self.logger.error(f"Translation file not found: {self.json_path}")
            return {}
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in {self.json_path}: {e}")
            return {}
    
    def _build_reverse_lookup(self) -> Dict[str, str]:
        """Build English → Gujarati lookup cache"""
        cache = {}
        
        for guj_district, district_data in self.hierarchy.items():
            # District mappings
            for eng_name in district_data.get('english_names', []):
                cache[eng_name.lower().strip()] = guj_district
            
            # Taluka mappings
            for guj_taluka, taluka_data in district_data.get('talukas', {}).items():
                for eng_name in taluka_data.get('english_names', []):
                    cache[eng_name.lower().strip()] = guj_taluka
                
                # Village mappings
                for guj_village, eng_names in taluka_data.get('villages', {}).items():
                    for eng_name in eng_names:
                        cache[eng_name.lower().strip()] = guj_village
        
        return cache
    
    def translate(self, english_text: str, context: str = 'village') -> str:
        """
        Translate English to Gujarati using dictionary lookup
        
        Args:
            english_text: English name to translate
            context: Type ('district', 'taluka', 'village')
        
        Returns:
            Gujarati translation from dictionary
            
        Raises:
            TranslationNotFoundError: If no translation is found
        """
        if not english_text:
            return english_text
        
        normalized = english_text.lower().strip()
        
        # Try exact match in cache
        gujarati = self.english_to_gujarati.get(normalized)
        if gujarati:
            return gujarati
        
        # Try fuzzy match in cache (before AI)
        self.logger.debug(f"No exact match for '{english_text}', trying fuzzy match")
        gujarati = self._fuzzy_match(english_text, context)
        if gujarati:
            self.logger.info(f"Fuzzy matched '{english_text}' → '{gujarati}'")
            self._add_spelling_variation(english_text, gujarati, context)
            return gujarati
        
        # Try AI-assisted dictionary search
        self.logger.debug(f"No fuzzy match for '{english_text}', trying AI-assisted search")
        gujarati = self._ai_find_match(english_text, context)
        
        if gujarati:
            # Add this spelling variation to JSON
            self._add_spelling_variation(english_text, gujarati, context)
            return gujarati
        
        # No match found - Raise exception instead of returning original
        error_msg = f"No translation found for '{english_text}' (context: {context})"
        self.logger.error(error_msg)
        raise TranslationNotFoundError(error_msg)
    
    def _fuzzy_match(self, english_text: str, context: str, threshold: float = 0.85) -> Optional[str]:
        """
        Try fuzzy string matching against cached English names
        
        Args:
            english_text: English name to match
            context: Type of name
            threshold: Similarity threshold (0.0-1.0)
        
        Returns:
            Gujarati name if good match found, None otherwise
        """
        best_match = None
        best_score = 0.0
        normalized_input = english_text.lower().strip()
        
        for eng_key, guj_value in self.english_to_gujarati.items():
            # Calculate similarity ratio
            similarity = SequenceMatcher(None, normalized_input, eng_key).ratio()
            
            if similarity > best_score:
                best_score = similarity
                best_match = guj_value
        
        if best_score >= threshold:
            return best_match
        
        return None
    
    def _ai_find_match(self, english_text: str, context: str) -> Optional[str]:
        """
        Use AI to find best match from existing dictionary entries
        
        Args:
            english_text: English name to match
            context: Type of name
        
        Returns:
            Gujarati name if match found, None otherwise
        """
        # Get candidate entries from dictionary with smart filtering
        candidates = self._get_smart_candidates(english_text, context, limit=30)
        
        if not candidates:
            self.logger.warning(f"No candidates found for context: {context}")
            return None
        
        # Build prompt with dictionary entries
        prompt = self._build_matching_prompt(english_text, candidates, context)
        
        try:
            response = self.llm.invoke(prompt)
            result = response.content.strip()
            
            # Check if AI returned NO_MATCH
            if result == "NO_MATCH" or result == "NO MATCH":
                self.logger.info(f"AI found no match for '{english_text}'")
                return None
            
            # Verify the result is actually in our dictionary
            candidate_gujarati_names = [c['gujarati'] for c in candidates]
            if result in candidate_gujarati_names:
                self.logger.info(f"AI matched '{english_text}' → '{result}'")
                return result
            else:
                self.logger.warning(f"AI returned invalid match: {result}")
                return None
                
        except Exception as e:
            self.logger.error(f"AI matching failed: {e}")
            return None
    
    def _get_smart_candidates(self, english_text: str, context: str, limit: int = 30) -> List[Dict]:
        """Get candidate entries with phonetic/similarity filtering"""
        all_candidates = []
        
        if context == 'district':
            for guj_name, data in self.hierarchy.items():
                all_candidates.append({
                    'gujarati': guj_name,
                    'english_names': data.get('english_names', [])
                })
        
        elif context == 'taluka':
            for district_data in self.hierarchy.values():
                for guj_name, data in district_data.get('talukas', {}).items():
                    all_candidates.append({
                        'gujarati': guj_name,
                        'english_names': data.get('english_names', [])
                    })
        
        elif context == 'village':
            for district_data in self.hierarchy.values():
                for taluka_data in district_data.get('talukas', {}).values():
                    for guj_name, eng_names in taluka_data.get('villages', {}).items():
                        all_candidates.append({
                            'gujarati': guj_name,
                            'english_names': eng_names
                        })
        
        # Score candidates by similarity to input
        scored_candidates = []
        normalized_input = english_text.lower().strip()
        
        for candidate in all_candidates:
            max_similarity = 0.0
            for eng_name in candidate['english_names']:
                similarity = SequenceMatcher(None, normalized_input, eng_name.lower().strip()).ratio()
                max_similarity = max(max_similarity, similarity)
            
            scored_candidates.append((candidate, max_similarity))
        
        # Sort by similarity and take top candidates
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        top_candidates = [c[0] for c in scored_candidates[:limit]]
        
        return top_candidates
    
    def _build_matching_prompt(self, english_text: str, candidates: List[Dict], context: str) -> str:
        """Build prompt for AI to find best match"""
        
        # Format candidates with all their spellings
        candidates_text = "\n".join([
            f"{i+1}. {c['gujarati']} → {', '.join(c['english_names'][:5])}"
            for i, c in enumerate(candidates)
        ])
        
        prompt = f"""You are a Gujarat place name expert. Find the BEST MATCH for this {context} name.

INPUT: "{english_text}"

DICTIONARY (sorted by similarity):
{candidates_text}

MATCHING RULES:
- Consider phonetic similarity (e.g., "Tramboo" ≈ "Trambo")
- Consider common misspellings and transliteration variations
- Consider missing/extra letters, vowel changes
- The input is likely a variation of one of the dictionary entries above

RESPONSE FORMAT:
- If you find a good match: Return ONLY the Gujarati name (e.g., "ત્રંબો - 033")
- If no good match exists: Return exactly "NO_MATCH"
- Do NOT include explanations or additional text

Best match:"""
        
        return prompt
    
    def _add_spelling_variation(self, english_name: str, gujarati_name: str, context: str):
        """Add new spelling variation to JSON"""
        try:
            updated = False
            
            if context == 'district':
                if gujarati_name in self.hierarchy:
                    if english_name not in self.hierarchy[gujarati_name]['english_names']:
                        self.hierarchy[gujarati_name]['english_names'].append(english_name)
                        updated = True
            
            elif context == 'taluka':
                for district_data in self.hierarchy.values():
                    if gujarati_name in district_data.get('talukas', {}):
                        if english_name not in district_data['talukas'][gujarati_name]['english_names']:
                            district_data['talukas'][gujarati_name]['english_names'].append(english_name)
                            updated = True
                            break
            
            elif context == 'village':
                for district_data in self.hierarchy.values():
                    for taluka_data in district_data.get('talukas', {}).values():
                        if gujarati_name in taluka_data.get('villages', {}):
                            if english_name not in taluka_data['villages'][gujarati_name]:
                                taluka_data['villages'][gujarati_name].append(english_name)
                                updated = True
                                break
                    if updated:
                        break
            
            if updated:
                self._save_json()
                # Update cache
                self.english_to_gujarati[english_name.lower().strip()] = gujarati_name
                self.logger.info(f"Added spelling variation: '{english_name}' → '{gujarati_name}'")
        
        except Exception as e:
            self.logger.error(f"Failed to add spelling variation: {e}")
    
    def _save_json(self):
        """Save updated hierarchy to JSON"""
        try:
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(self.hierarchy, f, ensure_ascii=False, indent=2)
            self.logger.debug(f"Saved updated translations to {self.json_path}")
        except Exception as e:
            self.logger.error(f"Failed to save JSON: {e}")


# Global instance
_translator = None


def get_translator() -> JSONTranslationSystem:
    """Get or create global translator instance"""
    global _translator
    if _translator is None:
        _translator = JSONTranslationSystem()
    return _translator


def translate_to_gujarati(english_text: str, context: str = 'village') -> str:
    """
    Translate English place name to Gujarati from dictionary
    
    Args:
        english_text: English name
        context: Type ('district', 'taluka', 'village')
    
    Returns:
        Gujarati translation from dictionary
    """
    translator = get_translator()
    return translator.translate(english_text, context)
