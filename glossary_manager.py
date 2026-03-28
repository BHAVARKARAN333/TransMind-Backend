import json
import os
from threading import Lock

class GlossaryManager:
    """Manages translation terminology persistently in a JSON file."""
    def __init__(self, storage_file="glossary.json"):
        self.storage_file = storage_file
        self.lock = Lock()
        self.terms = []
        self._load()

    def _load(self):
        if not os.path.exists(self.storage_file):
            # Seed with some initial data
            self.terms = [
                {"source": "member", "target": "miembro", "context": "Always use this term", "status": "Active"},
                {"source": "health plan", "target": "plan de salud", "context": "Official insurance term", "status": "Active"}
            ]
            self._save()
        else:
            try:
                with open(self.storage_file, "r", encoding="utf-8") as f:
                    self.terms = json.load(f)
            except Exception:
                self.terms = []

    def _save(self):
        with open(self.storage_file, "w", encoding="utf-8") as f:
            json.dump(self.terms, f, indent=4, ensure_ascii=False)

    def get_terms(self):
        with self.lock:
            return self.terms

    def add_term(self, source: str, target: str, context: str = ""):
        with self.lock:
            # Check if source already exists
            existing = next((t for t in self.terms if t["source"].lower() == source.lower()), None)
            if existing:
                existing["target"] = target
                existing["context"] = context
            else:
                self.terms.append({
                    "source": source,
                    "target": target,
                    "context": context,
                    "status": "Active"
                })
            self._save()
            return existing is not None

    def delete_term(self, source: str):
        with self.lock:
            original_len = len(self.terms)
            self.terms = [t for t in self.terms if t["source"].lower() != source.lower()]
            if len(self.terms) < original_len:
                self._save()
                return True
            return False

# Global instance
glossary_db = GlossaryManager()
