from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
import base64, io, os, sys, subprocess, shutil, tempfile
from text_processor import process_text
from similarity_module import memory_bank
from docx_extractor import extract_docx
from llm_translator import translate_batch, detect_language, memory_store as llm_memory_store
from docx_exporter import export_docx
from ai_validator import validate_with_ai
from glossary_manager import glossary_db

def convert_to_pdf_safe(docx_path, pdf_path):
    if sys.platform == "win32":
        try:
            from docx2pdf import convert as docx2pdf_convert
            docx2pdf_convert(docx_path, pdf_path)
            if os.path.exists(pdf_path):
                return True
        except Exception as e:
            print("docx2pdf failed on win32 fallback:", e)
    
    # Linux / Fallback: LibreOffice Subprocess
    outdir = os.path.dirname(pdf_path)
    cmd = ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", outdir, docx_path]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base_name = os.path.splitext(os.path.basename(docx_path))[0]
        generated_pdf = os.path.join(outdir, f"{base_name}.pdf")
        if generated_pdf != pdf_path and os.path.exists(generated_pdf):
            shutil.move(generated_pdf, pdf_path)
        return True
    except Exception as e:
        print("LibreOffice conversion failed:", e)
        raise Exception("Failed to convert document to PDF on this server. LibreOffice may be missing.")

app = FastAPI(title="TransMind AI - Backend API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Seed vector store from persistent memory.json on startup
@app.on_event("startup")
async def seed_vector_store():
    """Load translations from memory.json into the RAG vector store so matches work after restart."""
    if not llm_memory_store:
        return
    pairs_by_lang = {}
    for key, translated in llm_memory_store.items():
        parts = key.split("::", 2)
        if len(parts) == 3:
            source_lang, target_lang, source_text = parts
            pair = {"source": source_text, "translation": translated, "target_lang": target_lang}
            pairs_by_lang.setdefault(target_lang, []).append(pair)
    total = 0
    for lang, pairs in pairs_by_lang.items():
        added = memory_bank.add_pairs(pairs)
        total += added
    if total > 0:
        print(f"[STARTUP] Seeded {total} translation pairs into RAG vector store from memory.json")

# ─── MODELS ───────────────────────────────────────────────

class TextRequest(BaseModel):
    text: str

class ProcessResponse(BaseModel):
    segments: list[str]
    total_segments: int

class TranslationPair(BaseModel):
    source: str
    translation: str
    target_lang: str = ""

class AddSentenceRequest(BaseModel):
    pairs: list[TranslationPair]

class MatchRequest(BaseModel):
    sentence: str

class SegmentRequest(BaseModel):
    blocks: list[dict]
    target_language: str = ""

class ValidateRequest(BaseModel):
    segments: list[dict]

class GlossaryTerm(BaseModel):
    source: str
    target: str
    context: str = ""

class LanguageRequest(BaseModel):
    text: str

class TranslateRequest(BaseModel):
    sentences: list[str]
    source_language: str
    target_language: str
    tone: str = "formal"
    glossary: dict = {}

class ExportRequest(BaseModel):
    blocks: list[dict]
    original_file_base64: str
    original_format: str = "docx"
    target_format: str = "docx"

# ─── TEXT PROCESSING ──────────────────────────────────────

@app.post("/api/process-text", response_model=ProcessResponse)
async def api_process_text(req: TextRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")
    try:
        segments = process_text(req.text)
        return ProcessResponse(segments=segments, total_segments=len(segments))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── SIMILARITY / MEMORY ──────────────────────────────────

@app.post("/api/similarity/add")
async def api_add_sentences(req: AddSentenceRequest):
    try:
        dict_pairs = [{"source": p.source, "translation": p.translation, "target_lang": p.target_lang} for p in req.pairs]
        added = memory_bank.add_pairs(dict_pairs)
        return {"message": f"Successfully added {added} pairs to memory."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/similarity/match")
async def api_match_sentence(req: MatchRequest):
    try:
        result = memory_bank.find_best_match(req.sentence)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/similarity/memory")
async def api_get_memory():
    return {"count": len(memory_bank.stored_pairs), "pairs": memory_bank.stored_pairs}

@app.delete("/api/similarity/clear")
async def api_clear_memory():
    memory_bank.clear_memory()
    return {"message": "Memory cleared."}

@app.get("/api/translation-memory")
async def api_get_translation_memory():
    """Returns the persistent LLM translation memory as a readable list."""
    items = []
    for key, translated in llm_memory_store.items():
        parts = key.split("::", 2)
        if len(parts) == 3:
            source_lang, target_lang, source_text = parts
            items.append({
                "source": source_text,
                "translated": translated,
                "source_lang": source_lang,
                "target_lang": target_lang,
            })
    return {"count": len(items), "items": items}

# ─── GLOSSARY MANAGER ─────────────────────────────────────

@app.get("/api/glossary/get")
async def api_get_glossary():
    return {"terms": glossary_db.get_terms()}

@app.post("/api/glossary/add")
async def api_add_glossary(term: GlossaryTerm):
    updated = glossary_db.add_term(term.source, term.target, term.context)
    return {"success": True, "updated": updated, "message": "Term saved."}

@app.delete("/api/glossary/delete/{source}")
async def api_delete_glossary(source: str):
    deleted = glossary_db.delete_term(source)
    if not deleted:
        raise HTTPException(status_code=404, detail="Term not found")
    return {"success": True, "message": "Term deleted."}

# ─── PIPELINE ─────────────────────────────────────────────

# Phase 1: DOCX Extraction
@app.post("/api/pipeline/extract")
async def api_extract(file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()
        filename = file.filename.lower()
        original_format = "pdf" if filename.endswith(".pdf") else "docx"

        import tempfile, os

        if original_format == "pdf":
            try:
                from pdf2docx import Converter
                with tempfile.TemporaryDirectory() as tmpdir:
                    pdf_path = os.path.join(tmpdir, "upload.pdf")
                    docx_path = os.path.join(tmpdir, "converted.docx")
                    
                    with open(pdf_path, "wb") as f:
                        f.write(file_bytes)
                    
                    print(f"[EXTRACT] Valid PDF uploaded. Converting to DOCX for processing...")
                    # Convert PDF to DOCX
                    cv = Converter(pdf_path)
                    cv.convert(docx_path)
                    cv.close()
                    
                    with open(docx_path, "rb") as f:
                        file_bytes = f.read()
                    print(f"[EXTRACT] PDF converted successfully.")
            except ImportError:
                raise HTTPException(status_code=500, detail="pdf2docx is not installed.")

        # Save DOCX file temporarily for debugging
        debug_path = os.path.join(tempfile.gettempdir(), "transmind_last_upload.docx")
        with open(debug_path, "wb") as f:
            f.write(file_bytes)
        print(f"[DEBUG] Saved upload to: {debug_path}")
        
        res = extract_docx(file_bytes)
        
        # Debug: count blocks by type
        type_counts = {}
        for b in res["blocks"]:
            t = b.get("element_type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1
        print(f"[EXTRACT] Total blocks: {len(res['blocks'])}")
        for t, c in type_counts.items():
            print(f"  → {t}: {c} blocks")
        for b in res["blocks"][:5]:
            print(f"  📝 [{b.get('type')}] {b['text'][:80]}")
        if len(res["blocks"]) > 5:
            print(f"  ... and {len(res['blocks']) - 5} more blocks")
        
        return {"blocks": res["blocks"], "total": len(res["blocks"]), "original_file_base64": res["original_file_base64"], "original_format": original_format}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# Phase 2: Sentence Segmentation from extracted blocks
@app.post("/api/pipeline/segment")
async def api_segment(req: SegmentRequest):
    try:
        segments = []
        for block in req.blocks:
            sents = process_text(block["text"])
            for s in sents:
                segment = {
                    "original_block_index": block.get("index"),
                    "block_type": block.get("type"),
                    "sentence": s,
                    # Carry over all structure mapping fields for export
                    "element_type": block.get("element_type"),
                    "element_index": block.get("element_index"),
                    "table_idx": block.get("table_idx"),
                    "row_idx": block.get("row_idx"),
                    "col_idx": block.get("col_idx")
                }
                segments.append(segment)
        return {"segments": segments, "total": len(segments)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Phase 2.5: Source Quality Validation (AI-Powered)
@app.post("/api/pipeline/validate-source")
async def api_validate_source(req: ValidateRequest):
    try:
        report = validate_with_ai(req.segments)
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Phase 3: Language Detection
@app.post("/api/pipeline/detect-language")
async def api_detect_language(req: LanguageRequest):
    try:
        result = detect_language(req.text)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))

# Phase 4+5: RAG Similarity + Decision Engine for all segments
@app.post("/api/pipeline/run-rag")
async def api_run_rag(req: SegmentRequest):
    try:
        results = []
        for seg in req.blocks:  # blocks are segments here
            sentence = seg.get("sentence", seg.get("text", ""))
            match = memory_bank.find_best_match(sentence, target_lang=req.target_language)
            results.append({
                **seg,
                "similarity_score": match["similarity_score"],
                "match_type": match["match_type"],
                "action": match["action"],
                "confidence": match["confidence"],
                "best_match_source": match.get("best_match_source"),
                "best_match_translation": match.get("best_match_translation"),
            })
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Phase 6: LLM Translation for "new" sentences
@app.post("/api/pipeline/translate")
async def api_translate(req: TranslateRequest):
    try:
        results = translate_batch(
            req.sentences,
            req.source_language,
            req.target_language,
            req.tone,
            req.glossary if req.glossary else None
        )
        return {"translations": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Phase 9+10: Export Document (DOCX or PDF)
@app.post("/api/pipeline/export")
async def api_export(req: ExportRequest):
    try:
        # 1. We always reconstruct a DOCX first
        docx_bytes = export_docx(req.blocks, req.original_file_base64)
        
        # 2. Convert to PDF if requested
        if req.target_format.lower() == "pdf":
            import tempfile, os
                
            with tempfile.TemporaryDirectory() as tmpdir:
                trans_docx_path = os.path.join(tmpdir, "translated.docx")
                trans_pdf_path = os.path.join(tmpdir, "translated.pdf")
                with open(trans_docx_path, "wb") as f:
                    f.write(docx_bytes)
                
                # Cross-platform PDF Conversion
                convert_to_pdf_safe(trans_docx_path, trans_pdf_path)
                
                with open(trans_pdf_path, "rb") as f:
                    pdf_bytes = f.read()

            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": "attachment; filename=translated_document.pdf"}
            )
        else:
            # Return DOCX
            return Response(
                content=docx_bytes,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={"Content-Disposition": "attachment; filename=translated_document.docx"}
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Preview: convert original + translated DOCX to PDF for pixel-perfect document view
@app.post("/api/pipeline/preview")
async def api_preview(req: ExportRequest):
    import tempfile, os
    
    try:
        # Create temp directory for conversion
        with tempfile.TemporaryDirectory() as tmpdir:
            # === Original Document ===
            original_bytes = base64.b64decode(req.original_file_base64)
            orig_docx_path = os.path.join(tmpdir, "original.docx")
            orig_pdf_path = os.path.join(tmpdir, "original.pdf")
            with open(orig_docx_path, "wb") as f:
                f.write(original_bytes)
            convert_to_pdf_safe(orig_docx_path, orig_pdf_path)
            with open(orig_pdf_path, "rb") as f:
                original_pdf_b64 = base64.b64encode(f.read()).decode("utf-8")

            # === Translated Document ===
            translated_docx_bytes = export_docx(req.blocks, req.original_file_base64)
            trans_docx_path = os.path.join(tmpdir, "translated.docx")
            trans_pdf_path = os.path.join(tmpdir, "translated.pdf")
            with open(trans_docx_path, "wb") as f:
                f.write(translated_docx_bytes)
            convert_to_pdf_safe(trans_docx_path, trans_pdf_path)
            with open(trans_pdf_path, "rb") as f:
                translated_pdf_b64 = base64.b64encode(f.read()).decode("utf-8")

            return {
                "original_pdf": original_pdf_b64,
                "translated_pdf": translated_pdf_b64,
                "format": "pdf"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return {"message": "TransMind AI Backend is running."}
