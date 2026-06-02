"""Tests for snippet building and score normalization (pure, model-free)."""
from app.services.search_service import make_snippet, _minmax, cap_chunks


def test_cap_chunks_samples_evenly():
    chunks = list(range(1000))
    out = cap_chunks(chunks, 50)
    assert len(out) == 50
    assert out[0] == 0                 # starts at the beginning
    assert out[-1] >= 950              # reaches near the end (covers whole doc)
    assert out == sorted(out)          # preserves order


def test_cap_chunks_no_op_when_small():
    assert cap_chunks([1, 2, 3], 50) == [1, 2, 3]
    assert cap_chunks([1, 2, 3], 0) == [1, 2, 3]   # 0 = unlimited


def test_snippet_highlights_query_terms():
    text = "Background. The mutation rate of the gene is unusually high in this cohort."
    snip = make_snippet(text, "mutation rate")
    assert "<mark>mutation</mark>" in snip
    assert "<mark>rate</mark>" in snip


def test_snippet_escapes_html():
    text = "An <script>alert(1)</script> tag near the mutation site."
    snip = make_snippet(text, "mutation")
    assert "<script>" not in snip
    assert "&lt;script&gt;" in snip
    assert "<mark>mutation</mark>" in snip


def test_snippet_windows_long_text():
    words = ["filler"] * 200 + ["needle"] + ["tail"] * 200
    snip = make_snippet(" ".join(words), "needle", window=20)
    assert "<mark>needle</mark>" in snip
    assert "…" in snip  # truncated on at least one side
    assert len(snip.split()) < 40


def test_minmax():
    out = _minmax({"a": 0.0, "b": 10.0, "c": 5.0})
    assert out["a"] == 0.0 and out["b"] == 1.0 and 0.4 < out["c"] < 0.6
    assert _minmax({"a": 3.0, "b": 3.0}) == {"a": 0.0, "b": 0.0}
