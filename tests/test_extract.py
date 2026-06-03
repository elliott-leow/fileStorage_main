"""Tests for the multi-format text extractor."""
import zipfile

from app.services.search_service import extract_text_file, _strip_markup


def test_strip_markup():
    out = _strip_markup("<p>Hello <b>world</b></p><p>second &amp; line</p>")
    assert "Hello world" in out
    assert "second & line" in out
    assert "<" not in out


def test_extract_html(tmp_path):
    p = tmp_path / "a.html"
    p.write_text("<html><body><h1>T</h1><p>enzyme kinetics here</p></body></html>", encoding="utf-8")
    out = extract_text_file(str(p), 50)
    assert "enzyme kinetics here" in out and "<" not in out


def test_extract_docx(tmp_path):
    p = tmp_path / "d.docx"
    doc = ('<?xml version="1.0"?><w:document xmlns:w="x"><w:body>'
           '<w:p><w:r><w:t>Hello docx michaelis menten</w:t></w:r></w:p></w:body></w:document>')
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("[Content_Types].xml", "<a/>")
        z.writestr("word/document.xml", doc)
    assert "Hello docx michaelis menten" in extract_text_file(str(p), 50)


def test_extract_epub(tmp_path):
    p = tmp_path / "b.epub"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("OEBPS/ch1.xhtml", "<html><body><p>Photosynthesis chloroplast thylakoid</p></body></html>")
    assert "Photosynthesis chloroplast thylakoid" in extract_text_file(str(p), 50)


def test_extract_code(tmp_path):
    p = tmp_path / "s.py"
    p.write_text("def foo():\n    return 'bar baz'\n", encoding="utf-8")
    out = extract_text_file(str(p), 50)
    assert "def foo" in out and "bar baz" in out


def test_oversize_skipped(tmp_path):
    p = tmp_path / "big.txt"
    p.write_text("x" * 100, encoding="utf-8")
    assert extract_text_file(str(p), 0) is None  # 0 MB limit
