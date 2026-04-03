import os
import tempfile
from docx import Document

debug_path = os.path.join(tempfile.gettempdir(), "transmind_last_upload.docx")
print("Reading:", debug_path)

if os.path.exists(debug_path):
    doc = Document(debug_path)
    for para in doc.paragraphs:
        t = para.text.strip()
        if "Highly motivated" in t:
            print(repr(t))
else:
    print("File not found")
