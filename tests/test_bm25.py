"""Tests for the hand-rolled BM25."""
from app.services.bm25 import BM25, tokenize


def test_term_presence_scores_higher():
    corpus = [
        tokenize("the cat sat on the mat"),
        tokenize("dogs run in the park"),
        tokenize("nothing relevant here"),
    ]
    bm = BM25(corpus)
    scores = bm.get_scores(tokenize("cat"))
    assert scores[0] > scores[1]
    assert scores[0] > scores[2]


def test_idf_downweights_common_terms():
    corpus = [
        tokenize("the unicorn"),
        tokenize("the the the"),
        tokenize("the cat"),
    ]
    bm = BM25(corpus)
    rare = bm.get_scores(tokenize("unicorn"))
    common = bm.get_scores(tokenize("the"))
    # A rare term match should outweigh the best common-term match.
    assert rare[0] > common.max()


def test_empty_corpus_is_safe():
    bm = BM25([])
    assert bm.get_scores(tokenize("anything")).shape == (0,)
