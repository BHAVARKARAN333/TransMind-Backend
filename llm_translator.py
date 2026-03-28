import os
import time
import json
import logging
from dotenv import load_dotenv

load_dotenv()

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Constants ───
MAX_API_CALLS_PER_SESSION = 50
api_calls_made = 0

# ─── API Key Pool Management ───
API_KEYS = []
CURRENT_KEY_IDX = 0

def init_keys():
    global API_KEYS, CURRENT_KEY_IDX
    raw_keys = os.environ.get("GEMINI_API_KEYS", "")
    if raw_keys:
        API_KEYS = [k.strip() for k in raw_keys.split(",") if k.strip()]
    else:
        # Fallback to single key if needed
        single = os.environ.get("GEMINI_API_KEY", "")
        if single:
            API_KEYS = [single.strip()]
    CURRENT_KEY_IDX = 0

init_keys()

def _get_active_model():
    global CURRENT_KEY_IDX
    if not API_KEYS or not GENAI_AVAILABLE:
        return None
    key = API_KEYS[CURRENT_KEY_IDX]
    genai.configure(api_key=key)
    return genai.GenerativeModel('gemini-2.5-flash')

def _rotate_key():
    global CURRENT_KEY_IDX
    if len(API_KEYS) > 1:
        old_idx = CURRENT_KEY_IDX
        CURRENT_KEY_IDX = (CURRENT_KEY_IDX + 1) % len(API_KEYS)
        logger.info(f"🔄 API Key Rotated: Key #{old_idx + 1} ❌ -> Key #{CURRENT_KEY_IDX + 1} ✅")


# ─── Persistent Translation Memory ───
MEMORY_FILE = os.path.join(os.path.dirname(__file__), "memory.json")
memory_store: dict[str, str] = {}
# Structure: { "lang_pair::normalized_text": "translated_text" }

def _normalize(text: str) -> str:
    return text.strip().lower()

def _memory_key(source_text: str, source_lang: str, target_lang: str) -> str:
    return f"{source_lang}::{target_lang}::{_normalize(source_text)}"

def _load_memory():
    global memory_store
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                memory_store = json.load(f)
            logger.info(f"[MEMORY] Loaded {len(memory_store)} entries from memory.json")
        except Exception as e:
            logger.error(f"[MEMORY] Failed to load memory.json: {e}")
            memory_store = {}
    else:
        logger.info("[MEMORY] No memory.json found. Starting fresh.")

def _save_memory():
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory_store, f, ensure_ascii=False, indent=2)
        logger.info(f"[MEMORY] Saved {len(memory_store)} entries to memory.json")
    except Exception as e:
        logger.error(f"[MEMORY] Failed to save memory.json: {e}")

_load_memory()


def translate_batch(
    sentences: list[str],
    source_language: str,
    target_language: str,
    tone: str = "formal",
    glossary: dict | None = None
) -> list[dict]:
    """
    Translates a list of sentences using RAG-first memory, then Gemini API with rotating keys.
    """
    global api_calls_made

    results_map: dict[int, dict] = {}
    new_sentences: list[tuple[int, str]] = []  # (original_index, text)

    for idx, sentence in enumerate(sentences):
        key = _memory_key(sentence, source_language, target_language)
        if key in memory_store:
            logger.info(f"[MEMORY] ✅ Reused from memory: '{sentence[:50]}...'")
            results_map[idx] = {
                "source": sentence,
                "translated": memory_store[key],
                "mode": "memory"
            }
        else:
            logger.info(f"[MEMORY] ❌ Not found, will call API: '{sentence[:50]}...'")
            new_sentences.append((idx, sentence))

    if not new_sentences:
        logger.info(f"[MEMORY] All {len(sentences)} sentences served from memory. ZERO API calls!")
        return [results_map[i] for i in range(len(sentences))]

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
                    key = _memory_key(batch_text, source_language, target_language)
                    memory_store[key] = translated
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

    _save_memory()
    return [results_map[i] for i in range(len(sentences))]


def _call_gemini_with_retry(prompt, original_batch):
    """Handles API call with key rotation and retry logic."""
    expected_len = len(original_batch)
    
    # Allow attempts equal to at least looping through all keys 3 times
    total_retries = max(len(API_KEYS) * 3, 15)
    
    for attempt in range(total_retries):
        model = _get_active_model()
        if not model:
            return []
            
        try:
            response = model.generate_content(prompt)
            
            if not response.candidates or not response.candidates[0].content.parts:
                feedback = getattr(response, 'prompt_feedback', 'Blocked by safety filters')
                raise ValueError(f"Empty or blocked response from Gemini: {feedback}")
                
            raw_text = response.candidates[0].content.parts[0].text
            logger.info(f"--- [DEBUG] Raw API Response (Key #{CURRENT_KEY_IDX + 1}, Attempt {attempt+1}) ---\n{raw_text}")

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
                logger.warning(f"Quota Hit (429) on Key #{CURRENT_KEY_IDX + 1}.")
                # Only wait if we've cycled through all keys
                if (attempt + 1) % len(API_KEYS) == 0:
                    wait_time = 10
                    logger.warning(f"All {len(API_KEYS)} keys exhausted. Pausing for {wait_time}s to cool down...")
                    time.sleep(wait_time)
                else:
                    logger.warning("Instantly switching to next API key...")
                _rotate_key()
            else:
                logger.error(f"Gemini API Error (Key #{CURRENT_KEY_IDX + 1}): {e}")
                time.sleep(2)  # Short sleep for non-rate-limit network errors

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
