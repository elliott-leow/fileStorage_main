"""Tests for FileService.move_item (path-safety + behavior)."""
from app.services.file_service import FileService


def _fs(tmp_path):
    # move_item only uses path utils, not auth/visibility, so None is fine here.
    return FileService(str(tmp_path), auth_service=None, visibility_service=None)


def test_move_file(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.txt").write_text("hi", encoding="utf-8")
    ok, _ = _fs(tmp_path).move_item("a/x.txt", "b/y.txt")
    assert ok
    assert (tmp_path / "b" / "y.txt").read_text(encoding="utf-8") == "hi"
    assert not (tmp_path / "a" / "x.txt").exists()


def test_move_rejects_escape(tmp_path):
    (tmp_path / "x.txt").write_text("1", encoding="utf-8")
    ok, msg = _fs(tmp_path).move_item("x.txt", "../evil.txt")
    assert not ok
    assert not (tmp_path.parent / "evil.txt").exists()


def test_move_dest_exists(tmp_path):
    (tmp_path / "x.txt").write_text("1", encoding="utf-8")
    (tmp_path / "y.txt").write_text("2", encoding="utf-8")
    ok, _ = _fs(tmp_path).move_item("x.txt", "y.txt")
    assert not ok


def test_move_missing_source(tmp_path):
    ok, _ = _fs(tmp_path).move_item("nope.txt", "z.txt")
    assert not ok
