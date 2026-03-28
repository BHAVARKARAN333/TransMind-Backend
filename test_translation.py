import os, logging
logging.basicConfig(level=logging.INFO)
os.environ.setdefault("GEMINI_API_KEY", "AIzaSyAjp4F10ku3g2dcUzr09YL56dTClxwQSvc")

from llm_translator import translate_batch

sentences = [
    "Medical Report",
    "The patient presents with severe hypertension.",
    "Administer 50mg of Losartan daily."
]

print("=" * 60)
print("RUN 1: Should call API for all 3 sentences")
print("=" * 60)
res1 = translate_batch(sentences, "English", "Spanish", tone="Medical")
for r in res1:
    print(f"  [{r['mode']:>10}] {r['source'][:40]} → {r['translated'][:40]}")

print()
print("=" * 60)
print("RUN 2: Should reuse ALL from memory (ZERO API calls)")
print("=" * 60)
res2 = translate_batch(sentences, "English", "Spanish", tone="Medical")
for r in res2:
    print(f"  [{r['mode']:>10}] {r['source'][:40]} → {r['translated'][:40]}")

# Verify
all_memory = all(r['mode'] == 'memory' for r in res2)
print()
print(f"✅ ALL FROM MEMORY: {all_memory}")
