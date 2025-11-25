"""
Route blueprints for the file server application.
"""
from .main import main_bp
from .api import api_bp
from .upload import upload_bp

__all__ = ["main_bp", "api_bp", "upload_bp"]


def register_blueprints(app):
    """
    Register all blueprints with the Flask app.
    
    Args:
        app: Flask application instance
    """
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(upload_bp)


