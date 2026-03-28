"""
AI-Powered Source Validator
Uses Gemini LLM (with key rotation) to perform intelligent proofreading:
  - Spelling errors (context aware — won't flag emails, URLs, proper nouns)
  - Grammar & Punctuation issues
  - Consistency analysis (terminology variations)
  - Severity levels: high, medium, low
  - AI-suggested corrections for each issue
"""

import json
import logging
import re

logger = logging.getLogger(__name__)

# We import the key rotation helpers from llm_translator to reuse the same pool
from llm_translator import _get_active_model, _rotate_key, API_KEYS, GENAI_AVAILABLE


def validate_with_ai(segments: list[dict]) -> dict:
    """
    Sends document segments to Gemini for intelligent proofreading.
    Returns structured issue report with severity levels and AI suggestions.
    """
    if not API_KEYS or not GENAI_AVAILABLE:
        logger.warning("No API keys available. Returning empty validation.")
        return {"stats": {"spelling": 0, "grammar": 0, "punctuation": 0, "consistency": 0, "total": 0}, "details": []}

    # Prepare text blocks with indices for the LLM
    text_blocks = []
    for idx, seg in enumerate(segments):
        text = seg.get("sentence", "").strip()
        if text and len(text) > 3:
            text_blocks.append({"idx": idx, "text": text})

    if not text_blocks:
        return {"stats": {"spelling": 0, "grammar": 0, "punctuation": 0, "consistency": 0, "total": 0}, "details": []}

    # Process in chunks of 50 sentences to stay within token limits
    chunk_size = 50
    all_issues = []
    total_stats = {"spelling": 0, "grammar": 0, "punctuation": 0, "consistency": 0}

    for i in range(0, len(text_blocks), chunk_size):
        chunk = text_blocks[i:i + chunk_size]
        chunk_issues = _validate_chunk(chunk)
        if chunk_issues:
            all_issues.extend(chunk_issues)

    # Calculate stats from collected issues
    for detail in all_issues:
        for iss in detail.get("issues", []):
            cat = iss.get("type", "grammar")
            if cat in total_stats:
                total_stats[cat] += 1

    total = sum(total_stats.values())
    return {
        "stats": {**total_stats, "total": total},
        "details": all_issues
    }


def _validate_chunk(chunk: list[dict]) -> list[dict]:
    """Sends a chunk of text blocks to Gemini for proofreading."""

    # Build the input JSON for the prompt
    input_json = json.dumps([{"id": b["idx"], "text": b["text"]} for b in chunk], ensure_ascii=False)

    prompt = f"""You are a world-class professional proofreader and editor.

Analyze the following array of text segments for quality issues.

IMPORTANT RULES:
* DO NOT flag proper nouns, brand names, person names, company names, or place names as spelling errors.
* DO NOT flag email addresses, URLs, LinkedIn profiles, phone numbers, or technical terms.
* DO NOT flag programming terms like "API", "admin", "backend", "frontend", "heatmap", "hackathon", etc.
* Only flag REAL errors that a human proofreader would catch.
* For each issue found, provide a clear suggested fix.

Check for these 4 categories:
1. "spelling" — Actual misspelled words (NOT proper nouns, NOT tech jargon, NOT names)
2. "grammar" — Grammatical errors (subject-verb agreement, tense issues, article misuse)
3. "punctuation" — Missing periods, incorrect comma usage, missing question marks
4. "consistency" — Same concept referred to differently (e.g., "e-mail" vs "email", "web-site" vs "website")

For each issue, assign a severity:
- "high" for errors that change meaning or look unprofessional
- "medium" for issues that affect readability
- "low" for minor stylistic suggestions

Return a JSON array of objects. Each object represents ONE segment with issues:
{{
  "segment_index": <id from input>,
  "text": "<original text exactly as given>",
  "corrected_text": "<the FULL corrected version of the ENTIRE segment with ALL fixes applied>",
  "issues": [
    {{
      "type": "spelling" | "grammar" | "punctuation" | "consistency",
      "severity": "high" | "medium" | "low",
      "message": "<clear description of the issue>",
      "suggestion": "<short description of what was changed>"
    }}
  ]
}}

CRITICAL: The "corrected_text" field MUST contain the COMPLETE corrected sentence — not just the fixed word. 
Example: if the original text is "Bachelor of Computer Engineering (BE) SPPU University, Pune" and the issue is that "University" is redundant after "SPPU", then corrected_text should be "Bachelor of Computer Engineering (BE) SPPU, Pune" — the full sentence with the fix applied.

If a segment has NO issues, do NOT include it in the output.
If there are zero issues across all segments, return an empty array: []

ONLY output the JSON array. No explanations, no markdown.

Input segments:
{input_json}
"""

    # Try with retry and key rotation (up to 3 full rotations)
    max_retries = max(len(API_KEYS) * 3, 6)

    for attempt in range(max_retries):
        model = _get_active_model()
        if not model:
            return []

        try:
            response = model.generate_content(prompt)

            if not response.candidates or not response.candidates[0].content.parts:
                raise ValueError("Empty or blocked response")

            raw = response.candidates[0].content.parts[0].text
            logger.info(f"[VALIDATOR] Raw AI response (Key #{attempt+1}):\n{raw[:500]}...")

            # Parse JSON from response
            text = raw.replace("```json", "").replace("```", "").strip()

            try:
                result = json.loads(text)
            except Exception:
                match = re.search(r"\[[\s\S]*\]", text)
                if match:
                    result = json.loads(match.group(0))
                else:
                    raise ValueError("Could not extract JSON from response")

            if not isinstance(result, list):
                raise ValueError("Response is not a list")

            return result

        except Exception as e:
            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg or "resource" in error_msg:
                logger.warning(f"[VALIDATOR] Rate limit hit on attempt {attempt+1}, rotating key...")
                _rotate_key()
                import time
                time.sleep(2)
            else:
                logger.error(f"[VALIDATOR] Error on attempt {attempt+1}: {e}")
                _rotate_key()

    logger.error("[VALIDATOR] All retries exhausted.")
    return []
