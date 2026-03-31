from difflib import SequenceMatcher
from auth_middleware import get_db

class VectorStoreMemory:
    """Manages translation memory per-user in Firestore."""
    def __init__(self):
        pass

    def _get_collection(self, user_id: str):
        db = get_db()
        if not db:
            return None
        return db.collection("users").document(user_id).collection("translation_memory")

    def _similarity(self, a: str, b: str) -> float:
        return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()

    def get_memory(self, user_id: str):
        """Fetches all stored translation pairs for a user."""
        col = self._get_collection(user_id)
        if not col:
            return []
            
        docs = col.stream()
        pairs = []
        for doc in docs:
            pairs.append(doc.to_dict())
        return pairs

    def add_pairs(self, user_id: str, pairs: list) -> int:
        """Stores a list of source-translation pairs in Firestore."""
        if not pairs:
            return 0
            
        col = self._get_collection(user_id)
        if not col:
            return 0
            
        added = 0
        for p in pairs:
            source = p.get("source", "").strip()
            if not source:
                continue
            # Use source hash or cleaned source as ID to prevent duplicates
            doc_id = source.lower()[:100].replace("/", "_").replace(" ", "_")
            col.document(doc_id).set({
                "source": source,
                "translation": p.get("translation", ""),
                "target_lang": p.get("target_lang", ""),
            })
            added += 1
        return added

    def find_best_match(self, user_id: str, input_sentence: str, target_lang: str = "", preloaded_memory: list = None) -> dict:
        """Finds the best matching source sentence for a user."""
        stored_pairs = preloaded_memory if preloaded_memory is not None else self.get_memory(user_id)
        
        default_response = {
            "input_sentence": input_sentence,
            "best_match_source": None,
            "best_match_translation": None,
            "similarity_score": 0.0,
            "match_type": "New Translation Required",
            "action": "Send to AI translation",
            "confidence": "Low"
        }

        if not stored_pairs:
            return default_response

        # Filter by target_lang if specified
        if target_lang:
            candidates = [p for p in stored_pairs
                          if p.get("target_lang", "").lower() == target_lang.lower()]
        else:
            candidates = stored_pairs

        if not candidates:
            return default_response

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

    def clear_memory(self, user_id: str):
        """Clears all translation memory for the user."""
        col = self._get_collection(user_id)
        if not col:
            return
        
        # Batch delete
        docs = col.limit(100).stream()
        deleted = 0
        for doc in docs:
            doc.reference.delete()
            deleted += 1
        return deleted

# Global instance (now stateless)
memory_bank = VectorStoreMemory()
