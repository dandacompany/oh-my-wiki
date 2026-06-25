from scripts import ingest, registry


def _vault(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    return make_vault_with_pages(tmp_path, monkeypatch, pages={"wiki/index.md": "# I\n"})


def test_ocr_fallback_on_empty_extract(tmp_path, monkeypatch):
    db, vid = _vault(tmp_path, monkeypatch)
    # A minimal PDF whose extract_text yields empty (patch the reader path by
    # patching _ocr_pdf to the OCR seam result).
    monkeypatch.setattr(ingest, "_ocr_pdf", lambda b: "scanned text")
    # Force extract_text empty by using a stub PDF + patching PdfReader pages.
    import scripts.ingest as ing

    class _Page:
        def extract_text(self): return ""
        images = []

    class _Reader:
        def __init__(self, *a, **k): self.pages = [_Page()]
    monkeypatch.setattr(ing, "PdfReader", _Reader, raising=False)
    relpath, text = ingest.save_raw_pdf(db, vault_id=vid, pdf_bytes=b"%PDF-1.4 fake",
                                        title="Scan", date_str="2026-06-24")
    root = registry.get_vault_root(db, vid)
    assert (root / relpath).exists()              # original PDF saved
    assert text == "scanned text"                 # OCR fallback used


def test_ocr_missing_extra_returns_empty(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "pytesseract":
            raise ImportError("no pytesseract")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert ingest._ocr_pdf(b"%PDF-1.4 fake") == ""   # graceful no-op


def test_text_pdf_skips_ocr(tmp_path, monkeypatch):
    db, vid = _vault(tmp_path, monkeypatch)
    import scripts.ingest as ing
    called = {"ocr": False}
    monkeypatch.setattr(ing, "_ocr_pdf", lambda b: called.__setitem__("ocr", True) or "X")

    class _Page:
        def extract_text(self): return "real text"
        images = []

    class _Reader:
        def __init__(self, *a, **k): self.pages = [_Page()]
    monkeypatch.setattr(ing, "PdfReader", _Reader, raising=False)
    _rel, text = ingest.save_raw_pdf(db, vault_id=vid, pdf_bytes=b"%PDF",
                                     title="T", date_str="2026-06-24")
    assert text == "real text" and called["ocr"] is False


def test_ocr_image_cap(monkeypatch):
    from scripts import ingest
    calls = {"n": 0}

    class _Img:
        data = b"x"

    class _Page:
        images = [_Img() for _ in range(60)]

    class _Reader:
        def __init__(self, *a, **k): self.pages = [_Page()]
    monkeypatch.setattr(ingest, "PdfReader", _Reader, raising=False)

    import sys
    import types
    fake_pt = types.ModuleType("pytesseract")
    fake_pt.image_to_string = lambda im: (calls.__setitem__("n", calls["n"] + 1) or "x")
    fake_pil = types.ModuleType("PIL")
    fake_image = types.ModuleType("PIL.Image")
    fake_image.open = lambda b: object()
    fake_pil.Image = fake_image
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pt)
    monkeypatch.setitem(sys.modules, "PIL", fake_pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", fake_image)
    ingest._ocr_pdf(b"%PDF")
    assert calls["n"] == ingest._OCR_MAX_IMAGES
