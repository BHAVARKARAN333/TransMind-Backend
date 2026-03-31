import datetime
from auth_middleware import get_db

class HistoryManager:
    """Manages document translation history per-user in Firestore."""
    def __init__(self):
        pass

    def _get_collection(self, user_id: str):
        db = get_db()
        if not db:
            return None
        return db.collection("users").document(user_id).collection("translation_history")

    def get_history(self, user_id: str):
        """Fetches all history records for a user, sorted by date descending."""
        col = self._get_collection(user_id)
        if not col:
            return []
            
        docs = col.order_by("created_at", direction="DESCENDING").stream()
        records = []
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            records.append(data)
        return records

    def add_record(self, user_id: str, filename: str, source_lang: str, target_lang: str, 
                   original_format: str, target_format: str, status: str, word_count: int, file_size: str = "Unknown"):
        """Adds a new translated document record to history."""
        col = self._get_collection(user_id)
        if not col:
            return None

        data = {
            "filename": filename,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "original_format": original_format,
            "target_format": target_format,
            "status": status,
            "word_count": word_count,
            "file_size": file_size,
            "created_at": datetime.datetime.now(datetime.timezone.utc)
        }
        
        # Add new document with auto-generated ID
        new_doc_ref = col.document()
        new_doc_ref.set(data)
        
        data["id"] = new_doc_ref.id
        return data

    def delete_record(self, user_id: str, record_id: str):
        """Deletes a specific history record."""
        col = self._get_collection(user_id)
        if not col:
            return False
            
        col.document(record_id).delete()
        return True

# Global instance
history_db = HistoryManager()
