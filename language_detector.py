from langdetect import detect, DetectorFactory

# Make detection deterministic
DetectorFactory.seed = 0

LANGUAGE_NAMES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "zh-cn": "Chinese (Simplified)",
    "zh-tw": "Chinese (Traditional)",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
    "hi": "Hindi",
    "ru": "Russian",
    "nl": "Dutch",
    "pl": "Polish",
    "tr": "Turkish",
}

def detect_language(text: str) -> dict:
    """Detect the language of a given text block."""
    try:
        code = detect(text)
        name = LANGUAGE_NAMES.get(code, code.upper())
        return {"code": code, "name": name, "success": True}
    except Exception as e:
        return {"code": "en", "name": "English (default)", "success": False, "error": str(e)}

def get_supported_languages() -> list[dict]:
    """Return list of supported target languages."""
    return [{"code": k, "name": v} for k, v in LANGUAGE_NAMES.items()]
