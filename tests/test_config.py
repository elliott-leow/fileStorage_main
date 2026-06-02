"""Tests for configuration loading."""
import importlib


def _fresh_config(monkeypatch):
    """Re-import config with .env disabled so env changes take effect cleanly."""
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    import app.config as cfg
    return importlib.reload(cfg)


def test_flask_secret_alias(monkeypatch):
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
    monkeypatch.setenv("FLASK_SECRET", "abc123")
    cfg = _fresh_config(monkeypatch)
    assert cfg.Config.SECRET_KEY == "abc123"
    assert cfg.Config.is_secret_key_secure() is True


def test_secret_falls_back_to_insecure(monkeypatch):
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
    monkeypatch.delenv("FLASK_SECRET", raising=False)
    cfg = _fresh_config(monkeypatch)
    assert cfg.Config.is_secret_key_secure() is False


def test_new_search_and_analytics_settings(monkeypatch):
    cfg = _fresh_config(monkeypatch)
    c = cfg.Config
    assert c.SEMANTIC_MODEL_NAME  # has a default
    assert c.SEARCH_RERANK_MODEL
    assert 0 <= c.SEARCH_W_RERANK <= 1
    assert ".md" in c.SUPPORTED_EXTENSIONS
    assert c.SESSION_IDLE_TIMEOUT_MIN > 0
    assert c.ANALYTICS_DB_FILE.endswith(".db")
