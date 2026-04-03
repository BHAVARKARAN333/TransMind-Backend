from text_processor import process_text

text = "Highly motivated Bachelor of Computer Science student (2025) with strong foundation in Java, and Database Management Systems. Experienced in developing academic projects including a Tuition Management System."
sentences = process_text(text)

import json
print(json.dumps(sentences, indent=2))
