"""
Main routes for file browsing and serving.
"""
import os
import urllib.parse
import shutil
from datetime import datetime

from flask import (
    Blueprint, render_template, send_from_directory, 
    abort, request, jsonify, current_app
)
import humanize

from ..utils.path_utils import (
    normalize_path, normalize_path_display, 
    url_decode_path, url_encode_path
)
from ..utils.file_utils import format_file_info

main_bp = Blueprint("main", __name__)


@main_bp.route("/", defaults={"path": ""})
@main_bp.route("/<path:path>")
def serve(path):
    """Serve directory listings, files, or search results."""
    # Get services from app context
    file_service = current_app.file_service
    auth_service = current_app.auth_service
    visibility_service = current_app.visibility_service
    search_service = current_app.search_service
    config = current_app.config_obj
    
    # Get query parameters
    filename_search_query = request.args.get("search", "").strip()
    smart_query = request.args.get("smart_query", "").strip()
    recursive = request.args.get("recursive", "true").lower() == "true"
    
    # Initialize template variables
    entries = {}
    title = ""
    show_parent = False
    parent_url = "/"
    is_smart_search_results = False
    permission_denied = False
    is_current_path_hidden = False
    
    # Path calculation and safety check
    current_path_abs = file_service.get_absolute_path(path)
    
    if not file_service.is_safe_path(current_path_abs):
        abort(403)
    if not os.path.exists(current_path_abs):
        abort(404)
    
    # Normalize path for checks
    relative_path_unquoted = url_decode_path(path)
    norm_current_path = normalize_path(relative_path_unquoted)
    
    # Check if current path is hidden
    if norm_current_path:
        is_current_path_hidden = visibility_service.is_hidden(norm_current_path)
    
    # Check authorization
    required_key = auth_service.get_required_key_for_path(norm_current_path)
    has_session_access = auth_service.has_session_access(norm_current_path, required_key)
    
    if required_key and not has_session_access:
        permission_denied = True
        if os.path.isfile(current_path_abs):
            abort(403)
    
    # Handle file request
    if os.path.isfile(current_path_abs):
        return send_from_directory(config.PUBLIC_DIR, path)
    
    # Handle directory/search
    if os.path.isdir(current_path_abs):
        show_hidden_files = visibility_service.get_show_hidden_session()
        current_display_path = relative_path_unquoted.strip("/")
        
        # Build title
        if permission_denied:
            title = f"Access Denied - /{current_display_path}" if current_display_path else "Access Denied - /"
        elif smart_query:
            title = f"Smart Search Results for '{smart_query}'"
            is_smart_search_results = True
        elif filename_search_query:
            title = f"Filename Search '{filename_search_query}'"
            title += f" {'recursively ' if recursive else ''}in /{current_display_path if current_display_path else ''}"
        else:
            title = f"Index of /{current_display_path}" if current_display_path else "Index of /"
        
        # Build parent URL
        if relative_path_unquoted:
            show_parent = True
            parent_path_rel = os.path.dirname(relative_path_unquoted).strip("/")
            parent_url = "/" + url_encode_path(parent_path_rel) if parent_path_rel else "/"
        
        # Populate entries if access granted
        if not permission_denied:
            if smart_query:
                entries = _handle_smart_search(
                    smart_query, 
                    file_service, 
                    search_service,
                    show_hidden_files
                )
                if not search_service.is_available:
                    title += " (Semantic Model Error)"
                elif not search_service.is_index_ready:
                    title += " (Semantic Index Not Ready)"
            elif filename_search_query:
                entries = _handle_filename_search(
                    filename_search_query,
                    norm_current_path,
                    recursive,
                    file_service,
                    show_hidden_files
                )
            else:
                dir_entries, success = file_service.list_directory(
                    norm_current_path, 
                    show_hidden=show_hidden_files
                )
                if success:
                    for entry in dir_entries:
                        entries[entry["rel_path"]] = entry
                else:
                    title += " (Error Listing Directory)"
        
        # Sort entries
        if is_smart_search_results:
            sorted_entries = entries
        else:
            sorted_entries = dict(
                sorted(entries.items(), key=lambda x: x[1].get("display_name", "").lower())
            )
        
        current_path_display = normalize_path_display(norm_current_path)
        
        return render_template(
            "index.html",
            title=title,
            entries=sorted_entries,
            show_parent=show_parent,
            parent_url=parent_url,
            search_query=filename_search_query,
            smart_query=smart_query,
            recursive=recursive,
            is_smart_search_results=is_smart_search_results,
            semantic_search_enabled=search_service.is_available,
            permission_denied=permission_denied,
            current_path=current_path_display,
            delete_key_configured=config.DELETE_KEY_CONFIGURED,
            hidden_key_configured=config.HIDDEN_KEY_CONFIGURED,
            is_current_path_hidden=is_current_path_hidden,
            show_hidden_files=show_hidden_files
        )
    
    abort(500)


def _handle_smart_search(query, file_service, search_service, show_hidden):
    """Handle smart search combining semantic and filename search."""
    temp_entries = {}
    
    # Semantic search
    semantic_results = {}
    if search_service.is_available and search_service.is_index_ready:
        raw_results = search_service.search(query, top_n=50)
        for res in raw_results:
            semantic_results[res["path"]] = res["score"]
    
    # Filename search
    filename_results = file_service.find_by_name(
        query, 
        start_path="", 
        recursive=True,
        show_hidden=show_hidden
    )
    filename_map = {r["rel_path"]: r for r in filename_results}
    
    # Combine results - semantic first
    for rel_path, score in semantic_results.items():
        abs_path = file_service.get_absolute_path(rel_path)
        if not os.path.exists(abs_path):
            continue
        
        if not show_hidden and file_service.visibility_service.is_hidden(rel_path):
            continue
        
        is_protected = file_service.auth_service.is_path_protected(rel_path)
        info = format_file_info(abs_path, rel_path, is_protected=is_protected)
        
        if not info["error"]:
            info["score"] = f"{score:.2f}"
            info["display_name"] = os.path.basename(rel_path)
            info["matched_name"] = rel_path in filename_map
            temp_entries[info["rel_path"]] = info
    
    # Add filename-only results
    for rel_path, item_data in filename_map.items():
        if rel_path not in temp_entries:
            abs_path = item_data["abs_path"]
            if not os.path.exists(abs_path):
                continue
            
            info = format_file_info(
                abs_path, 
                rel_path,
                is_protected=item_data.get("is_protected", False)
            )
            if not info["error"]:
                info["score"] = None
                info["display_name"] = item_data["name"]
                info["matched_name"] = True
                temp_entries[rel_path] = info
    
    # Sort by score, then name match, then alpha
    def sort_key(item):
        _, info = item
        try:
            score_val = float(info.get("score", -1.0))
        except (ValueError, TypeError):
            score_val = -1.0
        name_match = 1 if info.get("matched_name") else 0
        display_name = info.get("display_name", "").lower()
        return (-score_val, -name_match, display_name)
    
    sorted_items = sorted(temp_entries.items(), key=sort_key)
    return dict(sorted_items)


def _handle_filename_search(query, start_path, recursive, file_service, show_hidden):
    """Handle filename search."""
    entries = {}
    results = file_service.find_by_name(
        query,
        start_path=start_path,
        recursive=recursive,
        show_hidden=show_hidden
    )
    
    for item in results:
        rel_path = item["rel_path"]
        if rel_path not in entries:
            info = format_file_info(
                item["abs_path"],
                rel_path,
                is_protected=item.get("is_protected", False),
                is_hidden=item.get("is_hidden", False)
            )
            if not info["error"]:
                info["display_name"] = item["name"]
                info["score"] = None
                info["matched_name"] = True
                entries[info["rel_path"]] = info
    
    return entries


@main_bp.route("/validate-key", methods=["POST"])
def validate_access_key():
    """Validate a key for a given path and store authorization in session."""
    auth_service = current_app.auth_service
    
    try:
        data = request.get_json()
        if not data or "path" not in data or "key" not in data:
            return jsonify(status="error", message="Missing path or key."), 400
        
        target_href_path = data["path"]
        provided_key = data["key"]
        
        target_rel_path = url_decode_path(target_href_path.strip("/"))
        norm_target_path = normalize_path(target_rel_path)
        
        required_key = auth_service.get_required_key_for_path(norm_target_path)
        
        if not required_key:
            return jsonify(status="success", message="Path is not protected."), 200
        
        if required_key == provided_key:
            auth_service.grant_session_access(norm_target_path)
            return jsonify(status="success", message="Access granted."), 200
        else:
            return jsonify(status="error", message="Invalid access key."), 401
            
    except Exception as e:
        print(f"Error in /validate-key: {e}")
        return jsonify(status="error", message="Server error."), 500


@main_bp.route("/health")
def health_check():
    """Provide basic health information."""
    config = current_app.config_obj
    
    try:
        disk_usage = shutil.disk_usage(config.PUBLIC_DIR)
        return jsonify({
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "public_dir": config.PUBLIC_DIR,
            "disk_total": humanize.naturalsize(disk_usage.total, binary=True),
            "disk_used": humanize.naturalsize(disk_usage.used, binary=True),
            "disk_free": humanize.naturalsize(disk_usage.free, binary=True),
            "disk_percent_used": f"{(disk_usage.used / disk_usage.total) * 100:.1f}%"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@main_bp.route("/upload-ui")
def upload_ui():
    """Serve the upload interface."""
    file_service = current_app.file_service
    destination_dirs = file_service.get_all_directories()
    
    return render_template(
        "upload.html",
        title="Upload File",
        destination_dirs=destination_dirs
    )


