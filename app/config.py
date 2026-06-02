"""
Configuration management for the file server application.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration class."""
    
    # Flask settings (accept either env name for robustness)
    SECRET_KEY = (
        os.getenv("FLASK_SECRET_KEY")
        or os.getenv("FLASK_SECRET")
        or "dev-insecure-fallback-key"
    )
    
    # File storage settings
    PUBLIC_DIR = os.path.expanduser(os.getenv("PUBLIC_DIR", "./public"))
    
    # API Keys
    UPLOAD_API_KEY = os.getenv("KEY")
    DELETE_KEY = os.getenv("DELETE_KEY")
    HIDDEN_KEY = os.getenv("HIDDEN_KEY")
    
    # Feature flags (derived from key configuration)
    DELETE_KEY_CONFIGURED = bool(DELETE_KEY)
    HIDDEN_KEY_CONFIGURED = bool(HIDDEN_KEY)
    
    # Configuration file paths
    FOLDER_KEYS_CONFIG_FILE = os.getenv("FOLDER_KEYS_CONFIG", "folder_keys.json")
    FOLDER_VISIBILITY_CONFIG_FILE = os.getenv("FOLDER_VISIBILITY_CONFIG", "folder_visibility.json")
    SHORTCUTS_CONFIG_FILE = os.getenv("SHORTCUTS_CONFIG", "shortcuts.json")
    
    # Search settings.
    # bge-small-en-v1.5 = best recall (default). all-MiniLM-L6-v2 indexes ~4x
    # faster on a CPU if you'd rather trade a little quality for build speed.
    SEMANTIC_MODEL_NAME = os.getenv("SEMANTIC_MODEL", "BAAI/bge-small-en-v1.5")
    SEARCH_RERANK_MODEL = os.getenv("SEARCH_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    SEMANTIC_INDEX_FILE = "semantic_index_v2.pkl"
    CACHE_DIR = os.path.expanduser(os.getenv("CACHE_DIR", "~/.cache/filebrowser_cache"))

    # Hybrid search tuning
    SEARCH_TOP_N = int(os.getenv("SEARCH_TOP_N", 15))            # results returned
    SEARCH_RERANK_CANDIDATES = int(os.getenv("SEARCH_RERANK_CANDIDATES", 30))  # before rerank
    SEARCH_W_RERANK = float(os.getenv("SEARCH_W_RERANK", 0.70))      # cross-encoder weight
    SEARCH_W_POPULARITY = float(os.getenv("SEARCH_W_POPULARITY", 0.15))  # access freq/recency
    SEARCH_W_TRAJECTORY = float(os.getenv("SEARCH_W_TRAJECTORY", 0.15))  # P(file | path)

    # File processing settings
    SUPPORTED_EXTENSIONS = [".txt", ".pdf", ".md", ".markdown"]
    MAX_CHUNK_SIZE = 256   # Words per chunk (good context; fits bge's 512-token limit)
    CHUNK_OVERLAP = 64     # Words of overlap between consecutive chunks
    MAX_FILE_SIZE_MB = 50  # Skip files larger than this
    # Cap chunks per file (evenly sampled). 0 = unlimited (full content coverage,
    # including big textbooks) — slower build but every passage is searchable.
    MAX_CHUNKS_PER_FILE = int(os.getenv("MAX_CHUNKS_PER_FILE", 0))

    # Analytics settings
    ANALYTICS_ENABLED = os.getenv("ANALYTICS_ENABLED", "true").lower() == "true"
    ANALYTICS_DB_FILE = os.getenv("ANALYTICS_DB", "analytics.db")
    SESSION_IDLE_TIMEOUT_MIN = int(os.getenv("SESSION_IDLE_TIMEOUT_MIN", 30))
    
    # Server settings
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 8000))          # human (HTML) UI
    AI_PORT = int(os.getenv("AI_PORT", 8001))    # AI-navigable (Markdown) version
    DEBUG = os.getenv("DEBUG", "true").lower() == "true"
    
    # Upload settings
    MAX_UPLOAD_SIZE_GB = float(os.getenv("MAX_UPLOAD_SIZE_GB", "10"))
    MAX_CONTENT_LENGTH = int(MAX_UPLOAD_SIZE_GB * 1024 * 1024 * 1024)  #convert to bytes
    UPLOAD_CHUNK_SIZE = 64 * 1024  #64KB chunks for streaming
    
    @classmethod
    def is_secret_key_secure(cls) -> bool:
        """Check if the secret key is secure (not the default)."""
        return cls.SECRET_KEY != "dev-insecure-fallback-key"
    
    @classmethod
    def ensure_directories(cls):
        """Ensure required directories exist."""
        os.makedirs(cls.PUBLIC_DIR, exist_ok=True)
        os.makedirs(cls.CACHE_DIR, exist_ok=True)


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    PUBLIC_DIR = "./test_public"


# Configuration dictionary for easy access
config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig
}


def get_config(config_name: str = None) -> Config:
    """Get configuration by name, defaulting to environment variable or development."""
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development")
    return config_by_name.get(config_name, DevelopmentConfig)


