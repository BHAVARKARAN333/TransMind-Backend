import re

orig = "Highly motivated Bachelor of Computer Science student (2025) with strong foundation in Java, and Database Management Systems."

docx_text = "Highly motivated Bachelor of Computer Science student (2025) with strong foundation in Java, and Database Management Systems.\rExperienced in developing academic projects including a Tuition Management System.\rPassionate about software development and problem-solving, seeking an entry-level Software Developer role."

words = orig.split()
pattern = r'[\s\u200b\u00A0]*'.join(re.escape(w) for w in words)

print("PATTERN:", pattern[:50], "...")

new_text, count = re.subn(pattern, "TEST_HINDI", docx_text, count=1)
print("COUNT:", count)
print("RESULT:", repr(new_text))
