```python
from docx import Document
from docx.oxml import OxmlElement

def _set_wt_text_with_newlines(wt, text):
    if not text:
        wt.text = ""
        return
        
    parts = text.split('\n')
    wt.text = parts[0]
    
    parent = wt.getparent()
    idx = parent.index(wt)
    
    for part in parts[1:]:
        br = OxmlElement('w:br')
        wt_new = OxmlElement('w:t')
        wt_new.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        wt_new.text = part
        idx += 1
        parent.insert(idx, br)
        idx += 1
        parent.insert(idx, wt_new)

def _replace_para_text(para, new_text: str):
    wt_elements = para._element.xpath('.//w:t')
    if not wt_elements:
        if new_text:
            para.add_run(new_text)
        return

    best_wt = None
    max_len = -1
    for wt in wt_elements:
        t = wt.text or ""
        if len(t) > max_len:
            max_len = len(t)
            best_wt = wt
            
    if best_wt is None:
        best_wt = wt_elements[0]

    for wt in wt_elements:
        if wt == best_wt:
            _set_wt_text_with_newlines(wt, new_text)
        else:
            wt.text = ""
```
