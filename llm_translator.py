import os
import time
import json
import logging
import threading
from dotenv import load_dotenv
from similarity_module import memory_bank

load_dotenv()

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Constants ───
MAX_API_CALLS_PER_SESSION = 500
api_calls_made = 0

# ─── Thread-Safe API Key Pool Management ───
API_KEYS = []
_key_lock = threading.Lock()
_key_counter = 0

def init_keys():
    global API_KEYS, _key_counter
    raw_keys = os.environ.get("GEMINI_API_KEYS", "")
    if raw_keys:
        API_KEYS = [k.strip() for k in raw_keys.split(",") if k.strip()]
    else:
        single = os.environ.get("GEMINI_API_KEY", "")
        if single:
            API_KEYS = [single.strip()]
    _key_counter = 0
    logger.info(f"🔑 Loaded {len(API_KEYS)} API keys for parallel processing")

init_keys()

def _get_next_key_index():
    """Thread-safe: returns a unique key index for each concurrent request."""
    global _key_counter
    with _key_lock:
        idx = _key_counter % len(API_KEYS)
        _key_counter += 1
    return idx

def _get_model_for_key(key_index: int):
    """Creates a Gemini model instance configured with a specific API key."""
    if not API_KEYS or not GENAI_AVAILABLE:
        return None
    key = API_KEYS[key_index % len(API_KEYS)]
    genai.configure(api_key=key)
    return genai.GenerativeModel('gemini-2.5-flash')

# Keep legacy functions for backward compatibility
def _get_active_model():
    idx = _get_next_key_index()
    return _get_model_for_key(idx)

def _rotate_key():
    pass  # No longer needed — key rotation is automatic via atomic counter


def _normalize(text: str) -> str:
    return text.strip().lower()

def translate_batch(
    user_id: str,
    sentences: list[str],
    source_language: str,
    target_language: str,
    tone: str = "formal",
    glossary: dict | None = None
) -> list[dict]:
    """
    Translates a list of sentences using Gemini API with rotating keys, and saves to Firestore via user_id.
    """
    global api_calls_made

    results_map: dict[int, dict] = {}
    new_sentences: list[tuple[int, str]] = [(idx, s) for idx, s in enumerate(sentences)]

    if not API_KEYS or not GENAI_AVAILABLE:
        logger.warning("Gemini API keys missing or SDK not installed. Falling back to MOCK mode.")
        for orig_idx, s in new_sentences:
            results_map[orig_idx] = {
                "source": s,
                "translated": f"[{target_language.upper()} TRANSLATION]: {s}",
                "mode": "mock"
            }
        return [results_map[i] for i in range(len(sentences))]

    only_texts = [s for _, s in new_sentences]
    batch_size = max(len(only_texts), 1)
    
    pairs_to_save = []

    for i in range(0, len(only_texts), batch_size):
        if api_calls_made >= MAX_API_CALLS_PER_SESSION:
            logger.warning("Max API calls reached for session. Falling back to original text.")
            for j in range(i, len(only_texts)):
                orig_idx = new_sentences[j][0]
                results_map[orig_idx] = {
                    "source": only_texts[j],
                    "translated": only_texts[j],
                    "mode": "fallback_limit_reached"
                }
            break

        batch_texts = only_texts[i:i+batch_size]

        glossary_hint = ""
        if glossary:
            terms = ", ".join([f'"{k}" → "{v}"' for k, v in glossary.items()])
            glossary_hint = f"\n* Use these glossary terms strictly: {terms}"

        prompt = (
            f"You are a professional {tone} translator.\n"
            f"Translate the following JSON array of strings from {source_language} to {target_language}.\n\n"
            f"STRICT RULES:\n"
            f"* Output MUST be fully in {target_language}\n"
            f"* DO NOT return original text\n"
            f"* DO NOT explain anything\n"
            f"* Keep numbers same\n"
            f"* Maintain formatting\n"
            f"* Translate technical terms properly{glossary_hint}\n"
            f"* You MUST return ONLY a valid JSON array of strings in the exact same order.\n\n"
            f"Input JSON array:\n{json.dumps(batch_texts, ensure_ascii=False)}\n"
        )

        logger.info(f"\n--- [DEBUG] Calling API for batch of {len(batch_texts)} sentences ---")
        translated_batch = _call_gemini_with_retry(prompt, batch_texts)

        # Map results back and save to memory
        for j, batch_text in enumerate(batch_texts):
            orig_idx = new_sentences[i + j][0]
            if j < len(translated_batch):
                translated = translated_batch[j]
                mode = "gemini"

                if _normalize(translated) != _normalize(batch_text):
                    pairs_to_save.append({
                        "source": batch_text,
                        "translation": translated,
                        "target_lang": target_language
                    })
                else:
                    logger.warning(f"[MEMORY] ⚠️ Translation == input, NOT saving: '{batch_text[:40]}'")
            else:
                translated = batch_text
                mode = "gemini_error_fallback"

            results_map[orig_idx] = {
                "source": batch_text,
                "translated": translated,
                "mode": mode
            }

        api_calls_made += 1

        # Throttle between batches just as standard practice
        if i + batch_size < len(only_texts):
            time.sleep(1)

    if pairs_to_save:
        memory_bank.add_pairs(user_id, pairs_to_save)
        logger.info(f"[MEMORY] Saved {len(pairs_to_save)} new translations to Firestore for user {user_id}")

    return [results_map[i] for i in range(len(sentences))]


def _call_gemini_with_retry(prompt, original_batch):
    """Handles API call with automatic key rotation and retry logic."""
    expected_len = len(original_batch)
    
    total_retries = max(len(API_KEYS) * 3, 15)
    
    for attempt in range(total_retries):
        key_idx = _get_next_key_index()
        model = _get_model_for_key(key_idx)
        if not model:
            return []
            
        try:
            response = model.generate_content(prompt)
            
            if not response.candidates or not response.candidates[0].content.parts:
                feedback = getattr(response, 'prompt_feedback', 'Blocked by safety filters')
                raise ValueError(f"Empty or blocked response from Gemini: {feedback}")
                
            raw_text = response.candidates[0].content.parts[0].text
            logger.info(f"--- [DEBUG] API Response (Key #{key_idx + 1}, Attempt {attempt+1}) ---")

            text = raw_text.replace("```json", "").replace("```", "").strip()
            
            try:
                translated_array = json.loads(text)
            except Exception:
                import re
                match = re.search(r"\[[\s\S]*\]", text)
                if match:
                    translated_array = json.loads(match.group(0))
                else:
                    raise ValueError("Could not extract JSON array from Gemini response")

            if not isinstance(translated_array, list):
                raise ValueError("Response is not a JSON list")

            if len(translated_array) < expected_len:
                logger.warning(f"Length mismatch: Expected {expected_len}, got {len(translated_array)}. Padding.")
                translated_array.extend(original_batch[len(translated_array):])
            elif len(translated_array) > expected_len:
                logger.warning(f"Length mismatch: Expected {expected_len}, got {len(translated_array)}. Truncating.")
                translated_array = translated_array[:expected_len]

            return translated_array

        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "quota" in error_str or "too many requests" in error_str or "exhausted" in error_str:
                logger.warning(f"Quota Hit (429) on Key #{key_idx + 1}. Auto-switching...")
                if (attempt + 1) % len(API_KEYS) == 0:
                    logger.warning(f"All {len(API_KEYS)} keys exhausted. Cooling down 10s...")
                    time.sleep(10)
            else:
                logger.error(f"Gemini API Error (Key #{key_idx + 1}): {e}")
                time.sleep(1)

    return []


def detect_language(text: str) -> dict:
    if not GENAI_AVAILABLE or not API_KEYS:
        return {"language": "en", "confidence": 0.5, "mode": "mock"}

    try:
        model = _get_active_model()
        prompt = f"Detect the primary language of this text. Reply with ONLY the 2-letter ISO 639-1 code (e.g., 'en', 'es', 'hi'). Text: '{text[:200]}'"
        response = model.generate_content(prompt)
        lang_code = response.text.replace("`", "").strip().lower()
        if len(lang_code) > 2:
            lang_code = lang_code[:2]
        return {"language": lang_code, "confidence": 0.9, "mode": "gemini"}
    except Exception as e:
        logger.error(f"Language detection failed: {e}")
        return {"language": "en", "confidence": 0.0, "mode": "error_fallback"}
