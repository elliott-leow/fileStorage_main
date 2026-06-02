#!/usr/bin/env python3
"""
Entry point for the file server application.

Usage:
    python run.py                    # Run with default settings
    FLASK_ENV=production python run.py   # Run in production mode
"""
import os
from app import create_app
from app.config import get_config


def main():
    """Run the application."""
    # Get configuration
    config_name = os.getenv("FLASK_ENV", "development")
    config = get_config(config_name)
    
    # Create app
    app = create_app(config_name)
    
    # Run the application. threaded=True so a slow search request never blocks
    # concurrent file downloads (the cross-encoder rerank can take a second or two).
    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG,
        threaded=True
    )


if __name__ == "__main__":
    main()


