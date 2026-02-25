import re
import requests
from typing import Optional, Tuple
from rapidfuzz import fuzz, process
from sentence_transformers import SentenceTransformer
import numpy as np
from src.utils.logger import logger


class CompanyNormalizer:
    
    def __init__(self, use_llm: bool = True, use_embeddings: bool = True):
        self.logger = logger
        self.use_llm = use_llm
        self.use_embeddings = use_embeddings
        self.embedding_model = None
        self.embedding_cache = {}
        self.llm_url = "http://localhost:11434/api/generate"
        self.llm_model = "llama3.1:8b"
        self._llm_disabled_reason = None
    
    def normalize(self, name: str) -> str:
        """Normalize company name."""
        if not name:
            return ""
        
        normalized = name.lower().strip()
        suffixes = [
            r'\s+inc\.?$', r'\s+llc\.?$', r'\s+ltd\.?$', r'\s+corp\.?$',
            r'\s+corporation$', r'\s+gmbh$', r'\s+ag$', r'\s+sa$',
            r'\s+plc\.?$', r'\s+co\.?$', r'\s+company$', r'\s+limited$'
        ]
        for suffix in suffixes:
            normalized = re.sub(suffix, '', normalized, flags=re.IGNORECASE)
        
        return re.sub(r'\s+', ' ', normalized).strip()
    
    def find_similar_company(
        self, 
        name: str, 
        existing_companies: list[Tuple[int, str, str]]
    ) -> Optional[int]:
        """Find similar company using tiered matching."""
        if not name or not existing_companies:
            return None
        
        normalized = self.normalize(name)
        
        # Stage 1: Exact match
        for company_id, _, norm_name in existing_companies:
            if norm_name == normalized:
                return company_id
        
        # Stage 2: Fuzzy matching
        fuzzy_match = self._fuzzy_match(normalized, existing_companies)
        if not fuzzy_match:
            return None
        
        score, match_idx = fuzzy_match
        company_id, orig_name, _ = existing_companies[match_idx]
        
        # High confidence - use it
        if score >= 90:
            return company_id
        
        # Medium confidence - verify
        if score >= 75:
            if self.use_embeddings and self._embedding_verify(normalized, existing_companies[match_idx][2]):
                return company_id
            if self.use_llm and self._llm_verify(name, orig_name):
                return company_id
        
        return None
    
    def _fuzzy_match(
        self,
        normalized: str,
        existing_companies: list[Tuple[int, str, str]]
    ) -> Optional[Tuple[float, int]]:
        """Fuzzy string matching."""
        norm_names = [norm for _, _, norm in existing_companies]
        
        best_match = process.extractOne(
            normalized,
            norm_names,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=75
        )
        
        if best_match:
            matched_norm, score, match_idx = best_match
            return (score, match_idx)
        
        return None
    
    def _embedding_verify(self, normalized: str, existing_norm: str) -> bool:
        """Verify match using embeddings."""
        if self.embedding_model is None:
            self.logger.info("Loading embedding model...")
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        if normalized not in self.embedding_cache:
            self.embedding_cache[normalized] = self.embedding_model.encode(normalized)
        if existing_norm not in self.embedding_cache:
            self.embedding_cache[existing_norm] = self.embedding_model.encode(existing_norm)
        
        emb1 = self.embedding_cache[normalized]
        emb2 = self.embedding_cache[existing_norm]
        
        similarity = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
        return similarity >= 0.85
    
    def _llm_verify(self, new_name: str, existing_name: str) -> bool:
        """Verify match using LLM."""
        if not self.use_llm:
            return False
        if self._llm_disabled_reason:
            return False
        try:
            prompt = f'Are these the same company? "{new_name}" and "{existing_name}". Answer YES or NO.'
            
            response = requests.post(
                self.llm_url,
                json={"model": self.llm_model, "prompt": prompt, "stream": False},
                timeout=10
            )
            
            result = response.json().get("response", "").upper()
            return "YES" in result and "NO" not in result
        except Exception as e:
            self._llm_disabled_reason = str(e)
            self.logger.warning(f"LLM verification disabled (Ollama not available): {e}")
            return False
