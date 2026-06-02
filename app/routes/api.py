"""
API routes for programmatic access.
"""
import io
import os
import zipfile
from flask import Blueprint, request, jsonify, current_app, Response, session

from ..utils.path_utils import normalize_path

api_bp = Blueprint("api", __name__)


@api_bp.route("/analytics/summary", methods=["GET"])
def analytics_summary():
    """Aggregated analytics for the dashboard (same gate as /dashboard)."""
    auth_service = current_app.auth_service
    analytics_service = current_app.analytics_service
    authorized = bool(session.get("dashboard_ok")) or auth_service.is_master_unlocked()
    if not authorized:
        return jsonify(error="Unauthorized."), 401
    return jsonify(analytics_service.summary())


@api_bp.route("/list-dirs", methods=["POST"])
def list_dirs():
    """List subdirectories within a given path."""
    file_service = current_app.file_service
    auth_service = current_app.auth_service
    visibility_service = current_app.visibility_service
    
    data = request.get_json()
    relative_req_path = data.get("path", "").strip("/") if data else ""
    norm_path = normalize_path(relative_req_path)
    
    # Safety check
    abs_path = file_service.get_absolute_path(norm_path)
    if not file_service.is_safe_path(abs_path):
        return jsonify(error="Access forbidden."), 403
    if not os.path.isdir(abs_path):
        return jsonify(error="Path not found or not a directory."), 404
    
    # Check authorization
    required_key = auth_service.get_required_key_for_path(norm_path)
    if required_key and not auth_service.has_session_access(norm_path, required_key):
        return jsonify(
            error="Authentication required.",
            requires_key=True,
            path=norm_path
        ), 401
    
    # List subdirectories
    show_hidden = visibility_service.get_show_hidden_session()
    subdirs_data = []
    try:
        for name in sorted(os.listdir(abs_path), key=lambda s: s.lower()):
            entry_abs = os.path.join(abs_path, name)
            if not file_service.is_safe_path(entry_abs):
                continue

            if os.path.isdir(entry_abs):
                item_rel = normalize_path(os.path.join(norm_path, name))

                if not show_hidden and visibility_service.is_hidden(item_rel):
                    continue

                subdirs_data.append({
                    "name": name,
                    "is_protected": auth_service.is_path_protected(item_rel)
                })
    except OSError as e:
        return jsonify(error=f"Error listing directory: {e}"), 500
    
    return jsonify(subdirs=subdirs_data, current_path=norm_path)


@api_bp.route("/toggle-hidden", methods=["POST"])
def toggle_hidden():
    """Toggle folder visibility."""
    config = current_app.config_obj
    visibility_service = current_app.visibility_service
    file_service = current_app.file_service
    
    if not config.HIDDEN_KEY_CONFIGURED:
        return jsonify(error="Hidden feature not configured."), 501
    
    data = request.get_json()
    if not data or "path" not in data or "key" not in data or "hide" not in data:
        return jsonify(error="Invalid request."), 400
    
    if data["key"] != config.HIDDEN_KEY:
        return jsonify(error="Invalid key."), 401
    
    relative_path = data["path"]
    should_hide = data["hide"]
    norm_path = normalize_path(relative_path)
    
    if not norm_path:
        return jsonify(error="Cannot hide root directory."), 400
    
    # Validate path exists
    abs_path = file_service.get_absolute_path(norm_path)
    if not file_service.is_safe_path(abs_path) or not os.path.isdir(abs_path):
        return jsonify(error="Invalid path."), 404
    
    if visibility_service.toggle_visibility(norm_path, should_hide):
        action = "hidden" if should_hide else "unhidden"
        return jsonify(
            status="success",
            message=f"Folder '{norm_path}' is now {action}.",
            path=norm_path,
            is_hidden=should_hide
        )
    else:
        return jsonify(error="Failed to save visibility state."), 500


@api_bp.route("/toggle-view-hidden", methods=["POST"])
def toggle_view_hidden():
    """Toggle session state for viewing hidden folders."""
    config = current_app.config_obj
    visibility_service = current_app.visibility_service
    
    if not config.HIDDEN_KEY_CONFIGURED:
        return jsonify(error="Hidden feature not configured."), 501
    
    data = request.get_json()
    if data.get("key") != config.HIDDEN_KEY:
        return jsonify(error="Invalid key."), 401
    
    new_state = visibility_service.toggle_show_hidden_session()
    message = "Hidden folders are now visible." if new_state else "Hidden folders are now hidden."
    
    return jsonify(status="success", message=message, show_hidden=new_state)


@api_bp.route("/create-folder", methods=["POST"])
def create_folder():
    """Create a new folder."""
    config = current_app.config_obj
    file_service = current_app.file_service
    auth_service = current_app.auth_service
    
    data = request.get_json()
    if not data:
        return jsonify(error="Invalid request."), 400
    
    parent_path = data.get("parent_path", "")
    folder_name = data.get("folder_name", "")
    provided_key = data.get("key")
    protection_password = data.get("protection_password")
    
    if not folder_name:
        return jsonify(error="Folder name required."), 400
    if not provided_key:
        return jsonify(error="API Key required."), 401
    
    if not config.UPLOAD_API_KEY:
        return jsonify(error="Server upload key not configured."), 501
    if provided_key != config.UPLOAD_API_KEY:
        return jsonify(error="Invalid API Key."), 401
    
    success, message, new_folder_path = file_service.create_folder(parent_path, folder_name)
    
    if success:
        # Set protection if requested
        if protection_password and new_folder_path:
            auth_service.set_path_protection(new_folder_path, protection_password)
        return jsonify(status="success", message=message), 201
    else:
        return jsonify(error=message), 400


@api_bp.route("/set-path-protection", methods=["POST"])
def set_path_protection():
    """Set password protection for a path."""
    config = current_app.config_obj
    auth_service = current_app.auth_service
    file_service = current_app.file_service
    
    data = request.get_json()
    if not data:
        return jsonify(error="Invalid request."), 400
    
    path_to_protect = data.get("path", "")
    protection_password = data.get("password", "")
    provided_key = data.get("key")
    
    if not path_to_protect:
        return jsonify(error="Path required."), 400
    if not protection_password:
        return jsonify(error="Protection password required."), 400
    if not provided_key:
        return jsonify(error="API Key required."), 401
    
    if not config.UPLOAD_API_KEY:
        return jsonify(error="Server key not configured."), 501
    if provided_key != config.UPLOAD_API_KEY:
        return jsonify(error="Invalid API Key."), 401
    
    norm_path = normalize_path(path_to_protect)
    if not norm_path:
        return jsonify(error="Cannot protect root."), 400
    
    # Validate path exists
    abs_path = file_service.get_absolute_path(norm_path)
    if not file_service.is_safe_path(abs_path) or not os.path.exists(abs_path):
        return jsonify(error="Path not found."), 404
    
    if auth_service.set_path_protection(norm_path, protection_password):
        return jsonify(
            status="success",
            message=f"Path '{norm_path}' is now protected."
        )
    else:
        return jsonify(error="Failed to save protection."), 500


@api_bp.route("/move", methods=["POST"])
def move_item():
    """Move or rename a file/folder (requires the upload key)."""
    config = current_app.config_obj
    file_service = current_app.file_service

    data = request.get_json()
    if not data:
        return jsonify(error="Invalid request."), 400
    src = data.get("src", "").strip()
    dst = data.get("dst", "").strip()
    provided_key = data.get("key")

    if not src or not dst:
        return jsonify(error="Both 'src' and 'dst' are required."), 400
    if not provided_key:
        return jsonify(error="API Key required."), 401
    if not config.UPLOAD_API_KEY:
        return jsonify(error="Server upload key not configured."), 501
    if provided_key != config.UPLOAD_API_KEY:
        return jsonify(error="Invalid API Key."), 401

    success, message = file_service.move_item(src, dst)
    if success:
        return jsonify(status="success", message=message)
    return jsonify(error=message), 400


@api_bp.route("/delete-items", methods=["POST"])
def delete_items():
    """Delete files or folders."""
    config = current_app.config_obj
    file_service = current_app.file_service
    
    if not config.DELETE_KEY_CONFIGURED:
        return jsonify(error="Deletion not configured."), 501
    
    provided_key = request.headers.get("X-Delete-Key")
    if not provided_key or provided_key != config.DELETE_KEY:
        return jsonify(error="Invalid delete key."), 401
    
    data = request.get_json()
    if not data or "items_to_delete" not in data or not isinstance(data["items_to_delete"], list):
        return jsonify(error="Invalid request body."), 400
    
    result = file_service.delete_items(data["items_to_delete"])
    
    status_code = 200 if result["fail_count"] == 0 else 207
    return jsonify(result), status_code


@api_bp.route("/create-shortcut", methods=["POST"])
def create_shortcut():
    """Create a folder shortcut."""
    config = current_app.config_obj
    shortcut_service = current_app.shortcut_service

    data = request.get_json()
    if not data:
        return jsonify(error="Invalid request."), 400

    name = data.get("name", "").strip()
    location = data.get("location", "").strip("/")
    target = data.get("target", "").strip().strip("/")
    provided_key = data.get("key")

    if not name:
        return jsonify(error="Shortcut name required."), 400
    if not target:
        return jsonify(error="Target folder required."), 400
    if not provided_key:
        return jsonify(error="API Key required."), 401

    if not config.UPLOAD_API_KEY:
        return jsonify(error="Server upload key not configured."), 501
    if provided_key != config.UPLOAD_API_KEY:
        return jsonify(error="Invalid API Key."), 401

    if shortcut_service.add_shortcut(name, location, target):
        return jsonify(status="success", message=f"Shortcut '{name}' created."), 201
    else:
        return jsonify(error="Failed to save shortcut."), 500


@api_bp.route("/delete-shortcut", methods=["POST"])
def delete_shortcut():
    """Delete a folder shortcut."""
    config = current_app.config_obj
    shortcut_service = current_app.shortcut_service

    data = request.get_json()
    if not data:
        return jsonify(error="Invalid request."), 400

    name = data.get("name", "").strip()
    location = data.get("location", "").strip("/")
    provided_key = data.get("key")

    if not name:
        return jsonify(error="Shortcut name required."), 400
    if not provided_key:
        return jsonify(error="API Key required."), 401

    if not config.UPLOAD_API_KEY:
        return jsonify(error="Server upload key not configured."), 501
    if provided_key != config.UPLOAD_API_KEY:
        return jsonify(error="Invalid API Key."), 401

    if shortcut_service.remove_shortcut(name, location):
        return jsonify(status="success", message=f"Shortcut '{name}' removed.")
    else:
        return jsonify(error="Failed to save shortcut removal."), 500


@api_bp.route("/validate-upload-key", methods=["POST"])
def validate_upload_key():
    """Validate upload key before starting upload."""
    config = current_app.config_obj
    auth_service = current_app.auth_service

    data = request.get_json()
    if not data:
        return jsonify(error="Invalid request."), 400

    provided_key = data.get("key", "")
    target_path = normalize_path(data.get("path", ""))

    if not provided_key:
        return jsonify(error="Upload key required."), 400

    #check folder-specific key first
    required_key = auth_service.get_required_key_for_path(target_path)

    if required_key:
        #folder has specific key requirement
        if provided_key == required_key:
            return jsonify(status="success", message="Key valid.")
        else:
            return jsonify(error="Invalid key for this folder."), 401
    else:
        #use global upload key
        if not config.UPLOAD_API_KEY:
            return jsonify(error="Server upload key not configured."), 501
        if provided_key == config.UPLOAD_API_KEY:
            return jsonify(status="success", message="Key valid.")
        else:
            return jsonify(error="Invalid upload key."), 401


@api_bp.route("/download-folder", methods=["GET"])
def download_folder():
    """Download a folder as a zip file."""
    file_service = current_app.file_service
    auth_service = current_app.auth_service

    folder_path = request.args.get("path", "").strip("/")
    norm_path = normalize_path(folder_path)

    abs_path = file_service.get_absolute_path(norm_path)
    if not file_service.is_safe_path(abs_path):
        return jsonify(error="Access forbidden."), 403
    if not os.path.isdir(abs_path):
        return jsonify(error="Path not found or not a directory."), 404

    # Check authorization
    required_key = auth_service.get_required_key_for_path(norm_path)
    if required_key and not auth_service.has_session_access(norm_path, required_key):
        return jsonify(error="Authentication required."), 401

    # Build zip in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(abs_path):
            # Filter out unsafe paths
            dirs[:] = [d for d in dirs if file_service.is_safe_path(os.path.join(root, d))]
            for filename in files:
                file_abs = os.path.join(root, filename)
                if not file_service.is_safe_path(file_abs):
                    continue
                arcname = os.path.relpath(file_abs, abs_path)
                zf.write(file_abs, arcname)
    zip_buffer.seek(0)

    folder_name = os.path.basename(abs_path) if norm_path else "root"
    zip_filename = f"{folder_name}.zip"

    return Response(
        zip_buffer.getvalue(),
        mimetype="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'}
    )


