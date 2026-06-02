"""Tests for the navigation P(file|path) model (model-free fake encoder)."""
import numpy as np
import pytest

from app.services.analytics_service import AnalyticsService
from app.services.navigation_service import (
    NavigationService,
    normalize_name,
    _is_ancestor,
)


def fake_encode(texts):
    """Deterministic encoder: study-ish names cluster; 'random' is orthogonal."""
    out = []
    for t in texts:
        if any(w in t for w in ("study", "mcat", "biochem", "enzyme")):
            v = np.array([1.0, 0.2, 0.0])
        elif any(w in t for w in ("random", "grocery", "misc")):
            v = np.array([0.0, 0.0, 1.0])
        else:
            v = np.array([0.4, 0.4, 0.4])
        out.append(v / np.linalg.norm(v))
    return np.array(out)


@pytest.fixture
def nav():
    return NavigationService(analytics_service=None, encode_fn=fake_encode)


def test_normalize_name():
    assert normalize_name("BME221_BIOCHEM") == "bme 221 biochem"
    assert normalize_name("studyNotes") == "study notes"
    assert normalize_name("AMS291_LADE") == "ams 291 lade"
    assert normalize_name("") == ""


def test_is_ancestor():
    assert _is_ancestor("study", "study/mcat")
    assert _is_ancestor("", "study")
    assert not _is_ancestor("study", "study")
    assert not _is_ancestor("study/mcat", "study")


def test_context_recency_weighting(nav):
    # Newest visit (mcat) should dominate over an older unrelated visit (random).
    ctx = nav.context_embedding(["random", "study/mcat"])
    study = fake_encode(["study"])[0]
    rand = fake_encode(["random"])[0]
    assert float(np.dot(ctx, study)) > float(np.dot(ctx, rand))


def test_backtrack_penalty(nav):
    # Visiting study/mcat then returning to study marks mcat abandoned.
    weights = nav._trajectory_weights(["study/mcat", "study"])
    # index 0 (mcat) is penalized relative to its recency-only weight.
    assert weights[0] < 0.7 ** 1  # would be 0.7 without the penalty


def test_file_priors_semantic_cold_start(nav):
    # No history: pure semantic. Visiting mcat favors the biochem (study) file.
    priors = nav.file_priors(
        ["study/mcat"],
        ["study/biochem/enzymes.md", "random/grocery.txt"],
    )
    assert priors["study/biochem/enzymes.md"] > priors["random/grocery.txt"]


def test_historical_scores(tmp_path):
    a = AnalyticsService(str(tmp_path / "a.db"), enabled=True)
    # Two past sessions: visiting study/mcat ended in opening a study/biochem file.
    for t in (1000.0, 5000.0):
        a.log("navigate", path="study/mcat", client="u1", now=t)
        a.log("open", path="study/biochem/enzymes.md", client="u1", now=t + 5)
    nav = NavigationService(analytics_service=a, encode_fn=fake_encode)
    hist = nav.historical_scores(["study/mcat"])
    assert hist.get("study/biochem", 0) >= 2
    # And it shows up in the blended prior.
    priors = nav.file_priors(
        ["study/mcat"], ["study/biochem/enzymes.md", "random/grocery.txt"]
    )
    assert priors["study/biochem/enzymes.md"] > priors["random/grocery.txt"]
