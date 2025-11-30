"""
Flask application factory for the file server.
"""
from flask import Flask, render_template
from werkzeug.exceptions import RequestEntityTooLarge

from .config import get_config, Config
from .services.auth_service import AuthService
from .services.visibility_service import VisibilityService
from .services.file_service import FileService
from .services.search_service import SearchService
from .routes import register_blueprints


def create_app(config_name: str = None) -> Flask:
    """
    Create and configure the Flask application.
    
    Args:
        config_name: Configuration name (development, production, testing)
        
    Returns:
        Configured Flask application
    """
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    
    #load configuration
    config = get_config(config_name)
    app.config.from_object(config)
    app.secret_key = config.SECRET_KEY
    
    #set max upload size (important for large files)
    app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH
    
    #store config object for easy access
    app.config_obj = config
    
    # Warn about insecure secret key
    if not config.is_secret_key_secure():
        print("\n!!! WARNING: Using insecure default Flask secret key. !!!")
        print("!!! Set the FLASK_SECRET_KEY environment variable. !!!\n")
    
    # Ensure required directories exist
    config.ensure_directories()
    
    # Initialize services
    _init_services(app, config)
    
    # Register blueprints
    register_blueprints(app)
    
    # Register error handlers
    _register_error_handlers(app)
    
    # Log startup information
    _log_startup_info(app, config)
    
    return app


def _init_services(app: Flask, config: Config) -> None:
    """Initialize application services."""
    # Authentication service
    app.auth_service = AuthService(config.FOLDER_KEYS_CONFIG_FILE)
    
    # Visibility service
    app.visibility_service = VisibilityService(config.FOLDER_VISIBILITY_CONFIG_FILE)
    
    # File service (depends on auth and visibility)
    app.file_service = FileService(
        public_dir=config.PUBLIC_DIR,
        auth_service=app.auth_service,
        visibility_service=app.visibility_service
    )
    
    # Search service
    app.search_service = SearchService(
        model_name=config.SEMANTIC_MODEL_NAME,
        cache_dir=config.CACHE_DIR,
        index_file=config.SEMANTIC_INDEX_FILE,
        supported_extensions=config.SUPPORTED_EXTENSIONS,
        max_chunk_size=config.MAX_CHUNK_SIZE,
        max_file_size_mb=config.MAX_FILE_SIZE_MB
    )


def _register_error_handlers(app: Flask) -> None:
    """Register error handlers."""
    
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template(
            "error.html",
            error_code=404,
            error_message="Page Not Found",
            error_description=str(e)
        ), 404
    
    @app.errorhandler(403)
    def forbidden(e):
        return render_template(
            "error.html",
            error_code=403,
            error_message="Forbidden",
            error_description="You do not have permission to access this resource."
        ), 403
    
    @app.errorhandler(401)
    def unauthorized(e):
        return render_template(
            "error.html",
            error_code=401,
            error_message="Unauthorized",
            error_description="Authentication required or failed."
        ), 401
    
    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template(
            "error.html",
            error_code=500,
            error_message="Internal Server Error",
            error_description="An unexpected error occurred."
        ), 500
    
    @app.errorhandler(413)
    @app.errorhandler(RequestEntityTooLarge)
    def request_entity_too_large(e):
        return render_template(
            "error.html",
            error_code=413,
            error_message="Payload Too Large",
            error_description="The file exceeds the maximum allowed size."
        ), 413


def _log_startup_info(app: Flask, config: Config) -> None:
    """Log startup information."""
    print("-" * 50)
    print("Starting File Browser...")
    print(f"Serving files from: {config.PUBLIC_DIR}")
    print(f"Global Upload API Key Configured: {'Yes' if config.UPLOAD_API_KEY else 'NO'}")
    print(f"Protected folders loaded: {len(app.auth_service.protected_folders)}")
    print(f"Hidden folders loaded: {len(app.visibility_service.hidden_paths)}")
    print(f"Semantic Search Available: {app.search_service.is_available}")
    
    if app.search_service.is_available:
        if app.search_service.is_index_ready:
            embed_count = app.search_service.index_data.get("embeddings").shape[0]
            print(f"Semantic index loaded with {embed_count} embeddings.")
        else:
            print("Semantic index not found. Use POST /rebuild-index to build.")
    
    print(f"Delete Key Configured: {config.DELETE_KEY_CONFIGURED}")
    print(f"Hidden Key Configured: {config.HIDDEN_KEY_CONFIGURED}")
    print(f"Max Upload Size: {config.MAX_UPLOAD_SIZE_GB} GB")
    
    if not config.is_secret_key_secure():
        print("!!! Flask Session Secret Key is INSECURE !!!")
    
    print("-" * 50)


