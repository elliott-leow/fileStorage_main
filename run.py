#!/usr/bin/env python3
"""
Entry point for the file server.

Serves two ports from one process (shared services / index / analytics):
  - PORT     (default 8000): human web UI (HTML, Catppuccin)
  - AI_PORT  (default 8001): AI-navigable version (self-describing Markdown)

Usage:
    python run.py
    FLASK_ENV=production python run.py
"""
import os
import threading

from app import create_app
from app.config import get_config


def main():
    config_name = os.getenv("FLASK_ENV", "development")
    config = get_config(config_name)
    app = create_app(config_name)

    # Start the AI-version server (same app, different port) in a background
    # thread. Skip the duplicate start in the reloader's parent process.
    start_ai = (not config.DEBUG) or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if start_ai and config.AI_PORT and config.AI_PORT != config.PORT:
        from werkzeug.serving import make_server

        ai_server = make_server(config.HOST, config.AI_PORT, app, threaded=True)
        threading.Thread(target=ai_server.serve_forever, daemon=True).start()
        print(f"AI-navigable version on http://{config.HOST}:{config.AI_PORT}")

    # Human web UI (main thread)
    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG,
        threaded=True,
    )


if __name__ == "__main__":
    main()
