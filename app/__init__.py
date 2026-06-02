"""
Flask application factory for the file server.
"""
from flask import Flask, render_template, request, jsonify
from werkzeug.exceptions import RequestEntityTooLarge

from .config import get_config, Config
from .services.auth_service import AuthService
from .services.visibility_service import VisibilityService
from .services.file_service import FileService
from .services.search_service import SearchService
from .services.shortcut_service import ShortcutService
from .services.analytics_service import AnalyticsService
from .services.navigation_service import NavigationService
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

    # Template filters
    _register_template_filters(app)

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
    
    # Shortcut service
    app.shortcut_service = ShortcutService(config.SHORTCUTS_CONFIG_FILE)

    # Analytics service (activity logging + ranking signals)
    app.analytics_service = AnalyticsService(
        db_path=config.ANALYTICS_DB_FILE,
        enabled=config.ANALYTICS_ENABLED,
        idle_timeout_min=config.SESSION_IDLE_TIMEOUT_MIN,
    )

    # Search service (hybrid + rerank, lazy-loaded models)
    app.search_service = SearchService(
        model_name=config.SEMANTIC_MODEL_NAME,
        cache_dir=config.CACHE_DIR,
        index_file=config.SEMANTIC_INDEX_FILE,
        supported_extensions=config.SUPPORTED_EXTENSIONS,
        max_chunk_size=config.MAX_CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        max_file_size_mb=config.MAX_FILE_SIZE_MB,
        max_chunks_per_file=config.MAX_CHUNKS_PER_FILE,
        rerank_model_name=config.SEARCH_RERANK_MODEL,
        top_n=config.SEARCH_TOP_N,
        rerank_candidates=config.SEARCH_RERANK_CANDIDATES,
        w_rerank=config.SEARCH_W_RERANK,
        w_pop=config.SEARCH_W_POPULARITY,
        w_traj=config.SEARCH_W_TRAJECTORY,
    )

    # Navigation model: P(file | path), reusing the search encoder for names
    app.navigation_service = NavigationService(
        analytics_service=app.analytics_service,
        encode_fn=app.search_service.encode_texts,
    )


def _register_template_filters(app: Flask) -> None:
    """Jinja filters used by templates."""
    import datetime as _dt

    @app.template_filter("localtime")
    def _localtime(ts):
        try:
            return _dt.datetime.fromtimestamp(ts).strftime("%b %d, %H:%M")
        except Exception:
            return ""


def _error_response(code, message, description):
    """Return a JSON error for API/agent requests, else the HTML error page."""
    fmt = request.args.get("format")
    accept = request.headers.get("Accept", "")
    if fmt == "json" or ("application/json" in accept and "text/html" not in accept):
        return jsonify(error=message, code=code, description=description), code
    return render_template(
        "error.html", error_code=code, error_message=message, error_description=description
    ), code


def _register_error_handlers(app: Flask) -> None:
    """Register error handlers (HTML for browsers, JSON for API/agents)."""

    @app.errorhandler(404)
    def page_not_found(e):
        return _error_response(404, "Page Not Found", str(e))

    @app.errorhandler(403)
    def forbidden(e):
        return _error_response(403, "Forbidden", "You do not have permission to access this resource.")

    @app.errorhandler(401)
    def unauthorized(e):
        return _error_response(401, "Unauthorized", "Authentication required or failed.")

    @app.errorhandler(500)
    def internal_server_error(e):
        return _error_response(500, "Internal Server Error", "An unexpected error occurred.")

    @app.errorhandler(413)
    @app.errorhandler(RequestEntityTooLarge)
    def request_entity_too_large(e):
        return _error_response(413, "Payload Too Large", "The file exceeds the maximum allowed size.")


def _log_startup_info(app: Flask, config: Config) -> None:
    """Log startup information."""
    print("-" * 50)
    print("Starting File Browser...")
    print(f"Serving files from: {config.PUBLIC_DIR}")
    print(f"Global Upload API Key Configured: {'Yes' if config.UPLOAD_API_KEY else 'NO'}")
    print(f"Protected folders loaded: {len(app.auth_service.protected_folders)}")
    print(f"Hidden folders loaded: {len(app.visibility_service.hidden_paths)}")
    print(f"Shortcuts loaded: {len(app.shortcut_service.shortcuts)}")
    print(f"Semantic Search Available: {app.search_service.is_available}")
    
    if app.search_service.is_available:
        if app.search_service.is_index_ready:
            embed_count = app.search_service.index_data.get("embeddings").shape[0]
            print(f"Semantic index loaded with {embed_count} embeddings.")
        else:
            print("Semantic index not found. Use POST /rebuild-index to build.")
    
    print(f"Delete Key Configured: {config.DELETE_KEY_CONFIGURED}")
    print(f"Hidden Key Configured: {config.HIDDEN_KEY_CONFIGURED}")
    print(f"Analytics Enabled: {app.analytics_service.enabled} (db: {config.ANALYTICS_DB_FILE})")
    print(f"Max Upload Size: {config.MAX_UPLOAD_SIZE_GB} GB")
    
    if not config.is_secret_key_secure():
        print("!!! Flask Session Secret Key is INSECURE !!!")
    
    print("-" * 50)


