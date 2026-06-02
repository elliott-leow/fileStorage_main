"""Tests for reciprocal rank fusion."""
from app.services.fusion import rrf


def test_rrf_rewards_agreement():
    r1 = [1, 2, 3]
    r2 = [1, 3, 2]
    out = dict(rrf([r1, r2]))
    assert out[1] > out[2]
    assert out[1] > out[3]


def test_rrf_handles_partial_lists():
    out = dict(rrf([[5, 6], [6]]))
    assert out[6] > out[5]


def test_rrf_sorted_descending():
    ranked = rrf([[1, 2, 3], [2, 1, 3]])
    scores = [s for _, s in ranked]
    assert scores == sorted(scores, reverse=True)
