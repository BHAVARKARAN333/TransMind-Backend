"""
Lightweight Translation Memory using TF-IDF + Cosine Similarity.
This replaces the heavy sentence-transformers + PyTorch approach
to stay under Render's 512MB RAM free-tier limit.
"""
from difflib import SequenceMatcher

class VectorStoreMemory:
    def __init__(self):
        self.stored_pairs = []  # list of dicts: {"source": str, "translation": str, "target_lang": str}

    def _similarity(self, a: str, b: str) -> float:
        """Compute similarity ratio between two strings using SequenceMatcher (0.0 to 1.0)."""
        return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()

    def add_pairs(self, pairs: list) -> int:
        """
        Stores a list of source-translation pairs in memory.
        Each pair should have: {"source": str, "translation": str, "target_lang": str}
        """
        if not pairs:
            return 0
        self.stored_pairs.extend(pairs)
        return len(pairs)

    def find_best_match(self, input_sentence: str, target_lang: str = "") -> dict:
        """
        Finds the best matching source sentence using sequence-based similarity.
        If target_lang is provided, only matches against pairs with the same target_lang.
        """
        if not self.stored_pairs:
            return {
                "input_sentence": input_sentence,
                "best_match_source": None,
                "best_match_translation": None,
                "similarity_score": 0.0,
                "match_type": "New Translation Required",
                "action": "Send to AI translation",
                "confidence": "Low"
            }

        # Filter by target_lang if specified
        if target_lang:
            candidates = [p for p in self.stored_pairs
                          if p.get("target_lang", "").lower() == target_lang.lower()]
        else:
            candidates = self.stored_pairs

        if not candidates:
            return {
                "input_sentence": input_sentence,
                "best_match_source": None,
                "best_match_translation": None,
                "similarity_score": 0.0,
                "match_type": "New Translation Required",
                "action": "Send to AI translation",
                "confidence": "Low"
            }

        # Compute similarity for each candidate
        scored = [(p, self._similarity(input_sentence, p["source"])) for p in candidates]
        best_pair, best_score = max(scored, key=lambda x: x[1])

        if best_score >= 0.95:
            match_type = "Exact Match"
            action = "Reuse previous translation"
            confidence = "High"
        elif best_score >= 0.75:
            match_type = "Fuzzy Match"
            action = "Suggest with review"
            confidence = "Medium"
        else:
            match_type = "New Translation Required"
            action = "Send to AI translation"
            confidence = "Low"

        return {
            "input_sentence": input_sentence,
            "best_match_source": best_pair["source"] if match_type != "New Translation Required" else None,
            "best_match_translation": best_pair["translation"] if match_type != "New Translation Required" else None,
            "similarity_score": round(best_score, 4),
            "match_type": match_type,
            "action": action,
            "confidence": confidence
        }

    def clear_memory(self):
        self.stored_pairs = []

memory_bank = VectorStoreMemory()
