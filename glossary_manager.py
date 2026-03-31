from auth_middleware import get_db

class GlossaryManager:
    """Manages translation terminology per-user in Firestore."""
    def __init__(self):
        pass

    def _get_collection(self, user_id: str):
        db = get_db()
        if not db:
            return None
        return db.collection("users").document(user_id).collection("glossary")

    def get_terms(self, user_id: str):
        col = self._get_collection(user_id)
        if not col:
            return []
            
        docs = col.stream()
        terms = []
        for doc in docs:
            t = doc.to_dict()
            t['id'] = doc.id
            terms.append(t)
            
        if not terms:
            # Seed default data if empty
            default_terms = [
                {"source": "member", "target": "miembro", "context": "Always use this term", "status": "Active"},
                {"source": "health plan", "target": "plan de salud", "context": "Official insurance term", "status": "Active"}
            ]
            for t in default_terms:
                self.add_term(user_id, t["source"], t["target"], t["context"])
            return default_terms
            
        return terms

    def add_term(self, user_id: str, source: str, target: str, context: str = ""):
        col = self._get_collection(user_id)
        if not col:
            return False
            
        # Check if exists (case insensitive source check requires querying and filtering, or using source as ID)
        # Using source word as document ID (lower cased) to enforce uniqueness
        doc_id = source.lower().replace(" ", "_")
        doc_ref = col.document(doc_id)
        
        doc = doc_ref.get()
        existing = doc.exists
        
        doc_ref.set({
            "source": source,
            "target": target,
            "context": context,
            "status": "Active"
        })
        return existing

    def delete_term(self, user_id: str, source: str):
        col = self._get_collection(user_id)
        if not col:
            return False
            
        try:
            doc_id = source.lower().replace(" ", "_")
            doc_ref = col.document(doc_id)
            if doc_ref.get().exists:
                doc_ref.delete()
                return True
            return False
        except Exception:
            return False

# Global instance (now stateless)
glossary_db = GlossaryManager()
