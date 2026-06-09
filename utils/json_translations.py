"""
JSON-Based Translation System with AI-Assisted Dictionary Lookup

This module provides translation from English to Gujarati using anyror_hierarchy.json
with AI assistance to find matches for unknown spelling variations.
"""
import json
import logging
from functools import lru_cache
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
        # Use a cheaper/faster model for simple translation matching tasks
        # Falls back to the main model if not set
        translation_model = os.getenv('GEMINI_TRANSLATION_MODEL', 'gemini-3.1-flash-lite-preview')
        self.llm = ChatGoogleGenerativeAI(
            model=translation_model,
            google_api_key=os.getenv('GEMINI_API_KEY'),
            temperature=0.0  # Deterministic for matching
        )
        self.logger = logging.getLogger(__name__)
        
        # Build context-aware reverse lookup caches for fast English → Gujarati.
        # Separate caches per context prevent collisions where a village and a
        # taluka share the same English name (e.g. both called "Dhanera").
        self._district_cache: Dict[str, str] = {}
        self._taluka_cache: Dict[str, str] = {}
        self._village_cache: Dict[str, str] = {}
        self._build_reverse_lookup()
        # Unified view used only for AI candidate scoring / legacy callers.
        self.english_to_gujarati = {
            **self._district_cache,
            **self._taluka_cache,
            **self._village_cache,
        }
        self.logger.info(
            f"Loaded {len(self.english_to_gujarati)} translations from {json_path} "
            f"(districts={len(self._district_cache)}, talukas={len(self._taluka_cache)}, "
            f"villages={len(self._village_cache)})"
        )
    
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
    
    def _build_reverse_lookup(self) -> None:
        """Build context-aware English → Gujarati lookup caches (one per context)."""
        for guj_district, district_data in self.hierarchy.items():
            # District mappings
            for eng_name in district_data.get('english_names', []):
                self._district_cache[eng_name.lower().strip()] = guj_district
            
            # Taluka mappings
            for guj_taluka, taluka_data in district_data.get('talukas', {}).items():
                for eng_name in taluka_data.get('english_names', []):
                    self._taluka_cache[eng_name.lower().strip()] = guj_taluka
                
                # Village mappings
                for guj_village, eng_names in taluka_data.get('villages', {}).items():
                    for eng_name in eng_names:
                        self._village_cache[eng_name.lower().strip()] = guj_village
    
    def translate(
        self,
        english_text: str,
        context: str = 'village',
        parent_district: Optional[str] = None,
        parent_taluka: Optional[str] = None,
    ) -> str:
        """
        Translate English to Gujarati using dictionary lookup.

        Resolution is hierarchical: when ``parent_district`` (and for villages
        ``parent_taluka``) are provided, candidates are scoped to that branch
        of the hierarchy. This avoids cross-district collisions where the same
        English spelling exists in multiple districts (e.g. "Brdeeya" lives in
        Rajkot, Porbandar, Junagadh, and Devbhumi Dwarka under different codes).

        Args:
            english_text: English name to translate
            context: Type ('district', 'taluka', 'village')
            parent_district: Gujarati district name; scopes taluka/village lookup
            parent_taluka: Gujarati taluka name; scopes village lookup (requires parent_district)

        Returns:
            Gujarati translation from dictionary

        Raises:
            TranslationNotFoundError: If no translation is found
        """
        if not english_text:
            return english_text

        normalized = english_text.lower().strip()
        cache_key = (normalized, context, parent_district or '', parent_taluka or '')

        # Check translation result cache first (avoids repeated fuzzy/AI lookups)
        if not hasattr(self, '_translation_cache'):
            self._translation_cache = {}

        if cache_key in self._translation_cache:
            return self._translation_cache[cache_key]

        # Build a scoped lookup when parents are provided; fall back to the
        # global context cache for backwards compatibility.
        scoped_lookup = self._build_scoped_lookup(context, parent_district, parent_taluka)
        if scoped_lookup is not None:
            gujarati = scoped_lookup.get(normalized)
            if gujarati:
                self._translation_cache[cache_key] = gujarati
                return gujarati
            # Deterministic scoped fuzzy match — resolves transliteration/spelling
            # variation (e.g. 'Badargadh' vs stored 'Badrgdh') WITHOUT an LLM call,
            # scoped to this district/taluka so a wrong-branch village can't win.
            gujarati = self._scoped_fuzzy_match(normalized, scoped_lookup)
            if gujarati:
                self._add_spelling_variation(english_text, gujarati, context)
                self._translation_cache[cache_key] = gujarati
                self.logger.info(f"Fuzzy-matched '{english_text}' → '{gujarati}' (deterministic, no LLM)")
                return gujarati
        else:
            # No parents provided — fall back to context-specific cache
            context_cache = {
                'district': self._district_cache,
                'taluka': self._taluka_cache,
                'village': self._village_cache,
            }.get(context, {})
            gujarati = context_cache.get(normalized)
            if gujarati:
                self._translation_cache[cache_key] = gujarati
                return gujarati

            # Legacy unified-cache fallback with context validation
            gujarati = self.english_to_gujarati.get(normalized)
            if gujarati and self._validate_context(gujarati, context):
                self._translation_cache[cache_key] = gujarati
                return gujarati

        # AI-assisted lookup, also scoped to parents when available
        self.logger.debug(
            f"No exact match for '{english_text}' (context={context}, "
            f"district={parent_district}, taluka={parent_taluka}); trying AI-assisted search"
        )
        gujarati = self._ai_find_match(english_text, context, parent_district, parent_taluka)

        if gujarati:
            self._add_spelling_variation(english_text, gujarati, context)
            self._translation_cache[cache_key] = gujarati
            return gujarati

        error_msg = (
            f"No translation found for '{english_text}' (context: {context}, "
            f"district: {parent_district}, taluka: {parent_taluka})"
        )
        self.logger.error(error_msg)
        raise TranslationNotFoundError(error_msg)

    def _build_scoped_lookup(
        self,
        context: str,
        parent_district: Optional[str],
        parent_taluka: Optional[str],
    ) -> Optional[Dict[str, str]]:
        """Build an English→Gujarati lookup scoped to a branch of the hierarchy.

        Returns ``None`` when no parent is provided (caller falls back to the
        global cache). Returns an empty dict if the parent path doesn't exist
        — that signals "no candidates here," and the AI step will fail loudly
        rather than silently matching the wrong district.
        """
        if context == 'district' or parent_district is None:
            return None

        district_data = self.hierarchy.get(parent_district)
        if district_data is None:
            self.logger.warning(f"Parent district '{parent_district}' not in hierarchy")
            return {}

        scoped: Dict[str, str] = {}

        if context == 'taluka':
            for guj_taluka, taluka_data in district_data.get('talukas', {}).items():
                for eng_name in taluka_data.get('english_names', []):
                    scoped[eng_name.lower().strip()] = guj_taluka
            return scoped

        if context == 'village':
            if parent_taluka is None:
                # Village lookup needs the taluka — fall back to global cache.
                return None
            taluka_data = district_data.get('talukas', {}).get(parent_taluka)
            if taluka_data is None:
                self.logger.warning(
                    f"Parent taluka '{parent_taluka}' not in district '{parent_district}'"
                )
                return {}
            for guj_village, eng_names in taluka_data.get('villages', {}).items():
                for eng_name in eng_names:
                    scoped[eng_name.lower().strip()] = guj_village
            return scoped

        return None
    
    def _validate_context(self, gujarati_name: str, context: str) -> bool:
        """Validate that a Gujarati name exists in the expected context."""
        if context == 'district':
            return gujarati_name in self.hierarchy
        elif context == 'taluka':
            for district_data in self.hierarchy.values():
                if gujarati_name in district_data.get('talukas', {}):
                    return True
            return False
        elif context == 'village':
            for district_data in self.hierarchy.values():
                for taluka_data in district_data.get('talukas', {}).values():
                    if gujarati_name in taluka_data.get('villages', {}):
                        return True
            return False
        return False
    
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
            # Skip if the gujarati value doesn't match the expected context
            if not self._validate_context(guj_value, context):
                continue
            
            # Calculate similarity ratio
            similarity = SequenceMatcher(None, normalized_input, eng_key).ratio()
            
            if similarity > best_score:
                best_score = similarity
                best_match = guj_value
        
        if best_score >= threshold:
            return best_match

        return None

    def _scoped_fuzzy_match(
        self, normalized: str, scoped_lookup: Dict[str, str], min_ratio: float = 0.80
    ) -> Optional[str]:
        """HIGH-PRECISION deterministic match within a scoped English→Gujarati map.

        For land records a WRONG village is far worse than no match, so this is
        built to refuse rather than guess. It never returns a "closest" match and
        never disambiguates — it only confirms a transliteration/vowel-drop variant
        of the SAME name. No LLM/network.

        AnyRoR drops vowels ('બાદરગઢ' is stored 'Badrgdh'), so 'badargadh' and
        'badrgdh' share the consonant skeleton 'bdrgdh'. A match is returned ONLY
        when BOTH hold:
          * exactly ONE distinct village in this taluka shares that skeleton
            (0 → no match; ≥2 → ambiguous, both rejected — we do not guess), AND
          * its character-level similarity is >= ``min_ratio`` (guards against a
            skeleton collision whose vowels differ wildly).
        Anything else returns None and the caller falls back to the LLM / a loud
        "not found" error so a human fixes the spelling.
        """
        import re

        def _alpha(s: str) -> str:
            s = re.sub(r"\s*-\s*\d+\s*$", "", (s or "").lower().strip())
            return re.sub(r"[^a-z]", "", s)

        _devowel = str.maketrans("", "", "aeiou")
        target_alpha = _alpha(normalized)
        target_skel = target_alpha.translate(_devowel)
        if len(target_skel) < 2:
            return None  # too short to match safely

        # Collect every distinct village whose consonant skeleton equals the input's.
        skel_hits = {}  # guj_name -> best char-ratio for that village
        for eng_key, guj in scoped_lookup.items():
            if _alpha(eng_key).translate(_devowel) == target_skel:
                r = SequenceMatcher(None, target_alpha, _alpha(eng_key)).ratio()
                if r > skel_hits.get(guj, 0.0):
                    skel_hits[guj] = r

        # Unambiguous: exactly one candidate village, and a sane character overlap.
        if len(skel_hits) == 1:
            guj, ratio = next(iter(skel_hits.items()))
            if ratio >= min_ratio:
                return guj
        # 0 candidates → no match; ≥2 → ambiguous. Either way, refuse to guess.
        return None

    def _ai_find_match(
        self,
        english_text: str,
        context: str,
        parent_district: Optional[str] = None,
        parent_taluka: Optional[str] = None,
    ) -> Optional[str]:
        """
        Use AI to find best match from existing dictionary entries

        When parents are provided, candidates are scoped to that branch of the
        hierarchy so cross-district name collisions can't be selected.
        """
        # Get candidate entries from dictionary with smart filtering
        candidates = self._get_smart_candidates(
            english_text, context, limit=30,
            parent_district=parent_district, parent_taluka=parent_taluka,
        )
        
        if not candidates:
            self.logger.warning(f"No candidates found for context: {context}")
            return None
        
        # Build prompt with dictionary entries
        prompt = self._build_matching_prompt(english_text, candidates, context)
        
        import time
        max_retries = 3
        retry_delay = 5  # seconds
        
        for attempt in range(max_retries):
            try:
                response = self.llm.invoke(prompt)
                content = response.content
                if isinstance(content, list):
                    content_str = ""
                    for part in content:
                        if isinstance(part, str):
                            content_str += part
                        elif isinstance(part, dict) and "text" in part:
                            content_str += part["text"]
                    content = content_str
                
                result = content.strip()
                
                # Check if AI returned NO_MATCH
                if result == "NO_MATCH" or result == "NO MATCH":
                    self.logger.info(f"AI found no match for '{english_text}'")
                    return None
                
                # Verify the result is actually in our dictionary
                candidate_gujarati_names = [c['gujarati'] for c in candidates]
                if result in candidate_gujarati_names:
                    self.logger.info(f"AI matched '{english_text}' → '{result}'")
                    return result

                # The LLM frequently drops the trailing " - NNN" village code or
                # prefixes "Best match:". Normalize both sides to the base Gujarati
                # name and return the FULL canonical entry (with code) so the
                # scraper still selects the correct dropdown option.
                import re as _re
                def _norm(s):
                    s = (s or "").strip()
                    for _pfx in ("Best match:", "best match:", "Answer:", "answer:", "Match:", "match:"):
                        if s.startswith(_pfx):
                            s = s[len(_pfx):].strip()
                    return _re.sub(r"\s*-\s*\d+\s*$", "", s).strip()
                norm_result = _norm(result)
                if norm_result:
                    hits = [c for c in candidate_gujarati_names if _norm(c) == norm_result]
                    if len(hits) == 1:
                        self.logger.info(
                            f"AI matched '{english_text}' → '{hits[0]}' (normalized from '{result}')"
                        )
                        return hits[0]
                    if len(hits) > 1:
                        # Same base name, different codes = different villages.
                        # Ambiguous — refuse to guess the wrong property.
                        self.logger.warning(
                            f"AI match '{result}' ambiguous across {len(hits)} candidates; refusing to guess"
                        )
                        return None

                self.logger.warning(f"AI returned invalid match: {result}")
                return None
                    
            except Exception as e:
                error_str = str(e).lower()
                is_rate_limit = "429" in error_str or "resource" in error_str or "quota" in error_str
                
                if is_rate_limit and attempt < max_retries - 1:
                    self.logger.warning(f"Rate limit hit (429). Sleeping for {retry_delay}s before retry {attempt+1}/{max_retries}...")
                    time.sleep(retry_delay)
                    continue
                
                self.logger.error(f"AI matching failed: {e}")
                return None
    
    def _get_smart_candidates(
        self,
        english_text: str,
        context: str,
        limit: int = 30,
        parent_district: Optional[str] = None,
        parent_taluka: Optional[str] = None,
    ) -> List[Dict]:
        """Get candidate entries with phonetic/similarity filtering.

        When ``parent_district`` (and for villages ``parent_taluka``) are
        provided, only candidates within that branch of the hierarchy are
        considered. This avoids cross-district name collisions.
        """
        all_candidates = []

        if context == 'district':
            for guj_name, data in self.hierarchy.items():
                all_candidates.append({
                    'gujarati': guj_name,
                    'english_names': data.get('english_names', [])
                })

        elif context == 'taluka':
            districts_iter = (
                [(parent_district, self.hierarchy.get(parent_district, {}))]
                if parent_district else self.hierarchy.items()
            )
            for _, district_data in districts_iter:
                for guj_name, data in district_data.get('talukas', {}).items():
                    all_candidates.append({
                        'gujarati': guj_name,
                        'english_names': data.get('english_names', [])
                    })

        elif context == 'village':
            if parent_district and parent_taluka:
                taluka_data = (
                    self.hierarchy.get(parent_district, {})
                    .get('talukas', {})
                    .get(parent_taluka, {})
                )
                for guj_name, eng_names in taluka_data.get('villages', {}).items():
                    all_candidates.append({
                        'gujarati': guj_name,
                        'english_names': eng_names
                    })
            else:
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
- Return ONLY the Gujarati name EXACTLY as it appears on the left side of the dictionary entry (before the "→").
- Copy it verbatim. Do not add or remove any " - NNN" code suffix. Do not invent codes that aren't in the dictionary.
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
                # Update both the unified cache and the context-specific cache
                key = english_name.lower().strip()
                self.english_to_gujarati[key] = gujarati_name
                if context == 'district':
                    self._district_cache[key] = gujarati_name
                elif context == 'taluka':
                    self._taluka_cache[key] = gujarati_name
                elif context == 'village':
                    self._village_cache[key] = gujarati_name
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


def translate_to_gujarati(
    english_text: str,
    context: str = 'village',
    parent_district: Optional[str] = None,
    parent_taluka: Optional[str] = None,
) -> str:
    """Translate English place name to Gujarati, optionally scoped by parents."""
    translator = get_translator()
    return translator.translate(english_text, context, parent_district, parent_taluka)