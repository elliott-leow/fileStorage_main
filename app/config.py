"""
Configuration management for the file server application.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration class."""
    
    # Flask settings
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-insecure-fallback-key")
    
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
    
    # Search settings
    SEMANTIC_MODEL_NAME = os.getenv("SEMANTIC_MODEL", "all-MiniLM-L6-v2")
    SEMANTIC_INDEX_FILE = "semantic_index.pkl"
    CACHE_DIR = os.path.expanduser(os.getenv("CACHE_DIR", "~/.cache/filebrowser_cache"))
    
    # File processing settings
    SUPPORTED_EXTENSIONS = [".txt", ".pdf"]
    MAX_CHUNK_SIZE = 500  # Max words per chunk for embedding
    MAX_FILE_SIZE_MB = 50  # Skip files larger than this
    
    # Server settings
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 8000))
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


