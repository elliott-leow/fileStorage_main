"""Tests for the analytics service (deterministic via injected `now`)."""
import pytest

from app.services.analytics_service import AnalyticsService, folder_of


@pytest.fixture
def svc(tmp_path):
    return AnalyticsService(str(tmp_path / "a.db"), enabled=True, idle_timeout_min=30)


def test_folder_of():
    assert folder_of("a/b/c.txt") == "a/b"
    assert folder_of("c.txt") == ""
    assert folder_of("") == ""


def test_tables_created(svc):
    rows = svc._q("SELECT name FROM sqlite_master WHERE type='table'")
    names = {r["name"] for r in rows}
    assert {"events", "sessions"} <= names


def test_same_session_within_timeout(svc):
    s1 = svc.log("navigate", path="a", client="u1", now=1000.0)
    s2 = svc.log("navigate", path="a/b", client="u1", now=1000.0 + 60)  # 1 min later
    assert s1 == s2


def test_new_session_after_timeout(svc):
    s1 = svc.log("navigate", path="a", client="u1", now=1000.0)
    s2 = svc.log("navigate", path="a", client="u1", now=1000.0 + 40 * 60)  # 40 min later
    assert s1 != s2


def test_different_client_different_session(svc):
    s1 = svc.log("navigate", path="a", client="u1", now=1000.0)
    s2 = svc.log("navigate", path="a", client="u2", now=1000.0 + 1)
    assert s1 != s2


def test_disabled_logs_nothing(tmp_path):
    svc = AnalyticsService(str(tmp_path / "a.db"), enabled=False)
    assert svc.log("open", path="x") is None
    assert svc.totals() == [] or svc.totals().get("opens", 0) == 0


def test_top_files_and_queries(svc):
    for _ in range(3):
        svc.log("open", path="docs/a.pdf", client="u1", now=1000.0)
    svc.log("open", path="docs/b.pdf", client="u1", now=1001.0)
    svc.log("search", query="enzymes", client="u1", now=1002.0)
    svc.log("search", query="enzymes", client="u1", now=1003.0)
    top = svc.top_files(limit=5)
    assert top[0]["path"] == "docs/a.pdf" and top[0]["count"] == 3
    tq = svc.top_queries()
    assert tq[0]["query"] == "enzymes" and tq[0]["count"] == 2
    pop = svc.file_popularity()
    assert pop["docs/a.pdf"]["count"] == 3


def test_current_trajectory_active_only(svc):
    svc.log("navigate", path="study", client="u1", now=1000.0)
    svc.log("navigate", path="study/mcat", client="u1", now=1000.0 + 30)
    traj = svc.current_trajectory("u1", now=1000.0 + 60)
    assert [t["path"] for t in traj] == ["study", "study/mcat"]
    # After the idle timeout the session is no longer active.
    assert svc.current_trajectory("u1", now=1000.0 + 40 * 60) == []


def test_session_outcomes(svc):
    # Session 1: visit study, study/mcat -> open a file in study/biochem
    svc.log("navigate", path="study", client="u1", now=1000.0)
    svc.log("navigate", path="study/mcat", client="u1", now=1001.0)
    svc.log("open", path="study/biochem/enzymes.md", client="u1", now=1002.0)
    outcomes = svc.session_outcomes()
    assert len(outcomes) == 1
    o = outcomes[0]
    assert set(o["visited"]) == {"study", "study/mcat"}
    assert o["target_folder"] == "study/biochem"


def test_folder_transitions(svc):
    svc.log("navigate", path="a", client="u1", now=1000.0)
    svc.log("navigate", path="b", client="u1", now=1001.0)
    svc.log("navigate", path="a", client="u1", now=1002.0)
    svc.log("navigate", path="b", client="u1", now=1003.0)
    trans = svc.folder_transitions()
    pairs = {(t["from"], t["to"]): t["count"] for t in trans}
    assert pairs.get(("a", "b")) == 2
