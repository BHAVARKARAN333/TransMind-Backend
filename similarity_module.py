from sentence_transformers import SentenceTransformer, util
import torch

try:
    model = SentenceTransformer('all-MiniLM-L6-v2')
except Exception as e:
    print(f"Warning: Could not load sentence-transformer model immediately. Error: {e}")
    model = None

class VectorStoreMemory:
    def __init__(self):
        self.stored_pairs = [] # list of dicts: {"source": str, "translation": str, "target_lang": str}
        self.stored_embeddings = None

    def add_pairs(self, pairs: list[dict]) -> int:
        """
        Embeds and stores a list of source-translation pairs in memory.
        Each pair should have: {"source": str, "translation": str, "target_lang": str}
        """
        if not pairs or model is None:
            return 0
            
        sources = [p["source"] for p in pairs]
        new_embeddings = model.encode(sources, convert_to_tensor=True)
        
        if self.stored_embeddings is None:
            self.stored_embeddings = new_embeddings
            self.stored_pairs.extend(pairs)
        else:
            self.stored_embeddings = torch.cat((self.stored_embeddings, new_embeddings), 0)
            self.stored_pairs.extend(pairs)
            
        return len(pairs)

    def find_best_match(self, input_sentence: str, target_lang: str = "") -> dict:
        """
        Computes cosine similarity and builds the AI decision.
        If target_lang is provided, only matches against pairs with the same target_lang.
        """
        if self.stored_embeddings is None or len(self.stored_pairs) == 0 or model is None:
            return {
                "input_sentence": input_sentence,
                "best_match_source": None,
                "best_match_translation": None,
                "similarity_score": 0.0,
                "match_type": "New Translation Required",
                "action": "Send to AI translation",
                "confidence": "Low"
            }
        
        # Filter indices by target_lang if specified
        if target_lang:
            valid_indices = [i for i, p in enumerate(self.stored_pairs) 
                          if p.get("target_lang", "").lower() == target_lang.lower()]
        else:
            valid_indices = list(range(len(self.stored_pairs)))
        
        if not valid_indices:
            return {
                "input_sentence": input_sentence,
                "best_match_source": None,
                "best_match_translation": None,
                "similarity_score": 0.0,
                "match_type": "New Translation Required",
                "action": "Send to AI translation",
                "confidence": "Low"
            }
            
        input_emb = model.encode(input_sentence, convert_to_tensor=True)
        cosine_scores = util.cos_sim(input_emb, self.stored_embeddings)[0]
        
        # Only consider valid indices (matching language pair)
        filtered_scores = [(idx, cosine_scores[idx].item()) for idx in valid_indices]
        best_idx, best_score = max(filtered_scores, key=lambda x: x[1])
        best_pair = self.stored_pairs[best_idx]
        
        if best_score >= 0.98:
            match_type = "Exact Match"
            action = "Reuse previous translation"
            confidence = "High"
        elif best_score >= 0.85:
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
        self.stored_embeddings = None

memory_bank = VectorStoreMemory()
