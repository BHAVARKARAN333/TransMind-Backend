import re

def clean_text(text: str) -> str:
    """
    Cleans the input text by normalizing spaces, newlines, and punctuation.
    """
    if not text:
        return ""
        
    # Normalize spacing around punctuation (remove spaces before punctuation)
    # e.g., "word , word" -> "word, word"
    text = re.sub(r'\s+([.,?!])', r'\1', text)
    
    # Remove extra continuous spaces (e.g., "word   word" -> "word word")
    text = re.sub(r'\s{2,}', ' ', text)
    
    # Trim leading and trailing whitespace
    return text.strip()

def split_sentences(text: str) -> list[str]:
    """
    Splits text into sentences while protecting common abbreviations.
    """
    # 1. Protect common abbreviations by temporarily replacing their periods
    abbreviations = ["Dr.", "Mr.", "Mrs.", "Ms.", "Prof.", "Ph.D.", "P.M.", "A.M.", "e.g.", "i.e.", "etc.", "Inc.", "Ltd."]
    
    protected_text = text
    for abbr in abbreviations:
        # Replace the literal period in the abbreviation with a special placeholder token
        protected_abbr = abbr.replace(".", "<PRD>")
        # Replace exact case
        protected_text = protected_text.replace(abbr, protected_abbr)
        # Handle lowercase variants like p.m., a.m., dr.
        protected_text = protected_text.replace(abbr.lower(), protected_abbr.lower())

    # 2. Split the text using standard sentence-ending punctuation (. ? !) OR literal newlines.
    # We use a regex that splits if:
    # (a) Punctuation is followed by whitespace and an uppercase letter, number, or bullet, OR
    # (b) There are one or more newlines (\\n) in the text.
    sentences_raw = re.split(r'(?<=[.?!])\s+(?=[A-Z0-9\u2022\u2023\u25aa\u2713\u2714\u2605•\-\*\"\'\(\u0900-\u097F\u00C0-\u024F])|\n+', protected_text)
    
    # 3. Restore the protected periods and clean up each sentence
    valid_sentences = []
    for sentence in sentences_raw:
        # Restore the protected period token back to actual periods
        restored_sentence = sentence.replace("<PRD>", ".")
        
        # Trim each sentence
        clean_sent = restored_sentence.strip()
        
        # Remove empty sentences
        if clean_sent:
            valid_sentences.append(clean_sent)
            
    # Fallback: if no split occurred but text has content, return it as one sentence
    if not valid_sentences and text.strip():
        valid_sentences.append(text.strip())
        
    return valid_sentences

def process_text(text: str) -> list[str]:
    """
    Main function to process raw input text into usable sentence segments.
    """
    if not text or not isinstance(text, str):
        return []
        
    cleaned = clean_text(text)
    sentences = split_sentences(cleaned)
    
    return sentences

# ==========================================
# TEST CASES
# ==========================================
if __name__ == "__main__":
    tests = [
        {
            "name": "Normal text",
            "input": "This is a normal sentence. Here is another one! Is this the third?"
        },
        {
            "name": "Text with extra spaces and newlines",
            "input": "  This   has  way  too   many spaces. \n\nAnd some newlines.   \nLet's clean it up!  "
        },
        {
            "name": "Text with abbreviations (Dr., P.M.)",
            "input": "Dr. Smith went to the hospital at 3:00 P.M. He met with Mr. Johnson regarding the Ph.D. program. They finished at 5:00 p.m. later that day."
        },
        {
            "name": "Messy punctuation spacing",
            "input": "I like apples , bananas , and oranges ! Do you ? "
        },
        {
            "name": "Edge case (empty input)",
            "input": ""
        },
        {
            "name": "None input",
            "input": None
        }
    ]

    for i, test in enumerate(tests, 1):
        print(f"\n--- Test {i}: {test['name']} ---")
        print(f"RAW INPUT: {repr(test['input'])}")
        
        try:
            results = process_text(test['input'])
            print(f"OUTPUT ({len(results)} segments):")
            for j, segment in enumerate(results, 1):
                print(f"  {j}. {segment}")
        except Exception as e:
            print(f"ERROR: {e}")
