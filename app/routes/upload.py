"""
Upload routes for file uploads.
"""
import os
from flask import Blueprint, request, jsonify, current_app, abort
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge

from ..utils.path_utils import normalize_path

upload_bp = Blueprint("upload", __name__)


@upload_bp.route("/upload/<path:filename>", methods=["POST"])
def upload_file(filename):
    """Handle file uploads via POST request with streaming support."""
    config = current_app.config_obj
    file_service = current_app.file_service
    auth_service = current_app.auth_service
    
    provided_upload_key = request.headers.get("X-Upload-Key")
    
    #sanitize path
    safe_parts = []
    try:
        path_parts = filename.strip("/").split("/")
        for part in path_parts:
            clean_part = secure_filename(part)
            if clean_part and clean_part != "..":
                safe_parts.append(clean_part)
            elif part == ".":
                continue
            else:
                abort(400)
    except Exception:
        abort(400)
    
    if not safe_parts:
        abort(400)
    
    safe_relative_path = os.path.join(*safe_parts)
    destination_abs = file_service.get_absolute_path(safe_relative_path)
    
    if not file_service.is_safe_path(destination_abs):
        abort(403)
    
    #authentication check
    target_dir_rel = os.path.dirname(safe_relative_path)
    required_key = auth_service.get_required_key_for_path(target_dir_rel)
    
    auth_ok = False
    if required_key:
        auth_ok = provided_upload_key == required_key
    else:
        auth_ok = provided_upload_key == config.UPLOAD_API_KEY
    
    if not auth_ok:
        abort(401)
    
    #check content length header
    content_length = request.content_length
    if content_length is None or content_length == 0:
        abort(400)
    
    try:
        #use streaming for all uploads to avoid memory issues
        chunk_size = getattr(config, 'UPLOAD_CHUNK_SIZE', 64 * 1024)
        success, message = file_service.save_uploaded_file_stream(
            request.stream,
            safe_relative_path,
            chunk_size=chunk_size
        )
        if success:
            return jsonify({
                "status": "success",
                "message": message,
                "filename": safe_relative_path
            }), 201
        else:
            abort(500)
    except RequestEntityTooLarge:
        abort(413)
    except Exception as e:
        print(f"Upload error: {e}")
        abort(500)


@upload_bp.route("/rebuild-index", methods=["POST"])
def trigger_rebuild_index():
    """Manually trigger a rebuild of the semantic search index."""
    config = current_app.config_obj
    search_service = current_app.search_service
    
    provided_key = request.headers.get("X-Upload-Key")
    if not provided_key or provided_key != config.UPLOAD_API_KEY:
        return jsonify(status="error", message="Unauthorized"), 401
    
    if not search_service.is_available:
        return jsonify(status="error", message="Search model not loaded."), 500
    
    print("Manual index rebuild requested...")
    
    try:
        new_index = search_service.build_index(config.PUBLIC_DIR)
        if new_index is not None:
            return jsonify(
                status="success",
                message="Semantic index rebuilt successfully."
            )
        else:
            return jsonify(
                status="error",
                message="Index rebuild failed or empty."
            ), 500
    except Exception as e:
        return jsonify(status="error", message=f"Rebuild failed: {e}"), 500


