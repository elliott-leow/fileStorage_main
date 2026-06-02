"""
Main routes for file browsing and serving.
"""
import os
import uuid
import shutil
from datetime import datetime

from flask import (
    Blueprint, render_template, send_from_directory, session,
    abort, request, jsonify, current_app
)
import humanize

from ..utils.path_utils import (
    normalize_path, normalize_path_display,
    url_decode_path, url_encode_path
)
from ..utils.file_utils import format_file_info

main_bp = Blueprint("main", __name__)


def _client_id() -> str:
    """Stable per-browser id used to group analytics into sessions."""
    cid = session.get("cid")
    if not cid:
        cid = uuid.uuid4().hex
        session["cid"] = cid
        session.modified = True
    return cid


def _build_breadcrumbs(display_path: str):
    """[{name, url}] from Home down to the current folder."""
    crumbs = [{"name": "Home", "url": "/"}]
    if not display_path:
        return crumbs
    parts = display_path.strip("/").split("/")
    acc = ""
    for part in parts:
        acc = f"{acc}/{part}" if acc else part
        crumbs.append({"name": part, "url": "/" + url_encode_path(acc)})
    return crumbs


def _wants_json() -> bool:
    """Agents can request JSON via ?format=json or an Accept: application/json header."""
    if request.args.get("format") == "json":
        return True
    accept = request.headers.get("Accept", "")
    return "application/json" in accept and "text/html" not in accept


def _entry_to_json(info: dict) -> dict:
    """Serialize a listing/search entry into a clean JSON object for agents."""
    etype = "shortcut" if info.get("is_shortcut") else ("dir" if info.get("is_dir") else "file")
    out = {
        "name": info.get("display_name"),
        "path": info.get("rel_path"),
        "type": etype,
        "size": info.get("size"),
        "size_bytes": info.get("size_bytes"),
        "modified": info.get("mtime"),
        "modified_ts": info.get("mtime_ts"),
        "protected": bool(info.get("is_protected")),
        "hidden": bool(info.get("is_hidden")),
        "url": "/" + (info.get("rel_path_encoded") or ""),
    }
    if info.get("score"):
        out["score"] = info["score"]
    snippet = info.get("snippet")
    if snippet:
        import html as _html
        out["snippet"] = _html.unescape(snippet.replace("<mark>", "").replace("</mark>", ""))
    return out


@main_bp.route("/", defaults={"path": ""})
@main_bp.route("/<path:path>")
def serve(path):
    """Serve directory listings, files, or search results."""
    # Get services from app context
    file_service = current_app.file_service
    auth_service = current_app.auth_service
    visibility_service = current_app.visibility_service
    search_service = current_app.search_service
    shortcut_service = current_app.shortcut_service
    analytics_service = current_app.analytics_service
    navigation_service = current_app.navigation_service
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
        is_preview = request.args.get("preview") == "1"
        analytics_service.log(
            "preview" if is_preview else "open",
            path=norm_current_path, client=_client_id(),
        )
        return send_from_directory(
            config.PUBLIC_DIR, path,
            as_attachment=request.args.get("download") == "1",
        )
    
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
                    navigation_service,
                    analytics_service,
                    _client_id(),
                    show_hidden_files
                )
                if not search_service.is_available:
                    title += " (Semantic Model Error)"
                elif not search_service.is_index_ready:
                    title += " (Semantic Index Not Ready)"
                analytics_service.log(
                    "search", query=smart_query, client=_client_id(),
                    meta={"mode": "smart", "results": len(entries)},
                )
            elif filename_search_query:
                entries = _handle_filename_search(
                    filename_search_query,
                    norm_current_path,
                    recursive,
                    file_service,
                    show_hidden_files
                )
                analytics_service.log(
                    "search", query=filename_search_query, client=_client_id(),
                    meta={"mode": "filename", "results": len(entries)},
                )
            else:
                analytics_service.log(
                    "navigate", path=norm_current_path, client=_client_id()
                )
                dir_entries, success = file_service.list_directory(
                    norm_current_path,
                    show_hidden=show_hidden_files
                )
                if success:
                    for entry in dir_entries:
                        entries[entry["rel_path"]] = entry
                else:
                    title += " (Error Listing Directory)"

                # Inject shortcuts for this directory
                for sc in shortcut_service.get_shortcuts_for_path(norm_current_path):
                    sc_key = "__shortcut__/" + (sc["location"] + "/" if sc["location"] else "") + sc["name"]
                    entries[sc_key] = {
                        "is_dir": True,
                        "is_shortcut": True,
                        "display_name": sc["name"],
                        "rel_path": sc_key,
                        "rel_path_encoded": sc["target"].strip("/"),
                        "size": "\u2192 " + sc["target"],
                        "mtime": "",
                        "is_protected": False,
                        "is_hidden": False,
                        "error": False,
                    }

        # Sort entries
        if is_smart_search_results:
            sorted_entries = entries
        else:
            sorted_entries = dict(
                sorted(entries.items(), key=lambda x: x[1].get("display_name", "").lower())
            )
        
        current_path_display = normalize_path_display(norm_current_path)

        # Agent-friendly JSON response (listing or search results)
        if _wants_json():
            if permission_denied:
                return jsonify(
                    error="Access denied", path=norm_current_path, requires_key=True
                ), 403
            return jsonify({
                "path": norm_current_path,
                "is_search": bool(is_smart_search_results or filename_search_query),
                "query": smart_query or filename_search_query or None,
                "breadcrumbs": _build_breadcrumbs(current_path_display),
                "count": len(sorted_entries),
                "entries": [_entry_to_json(i) for i in sorted_entries.values()],
            })

        return render_template(
            "index.html",
            title=title,
            entries=sorted_entries,
            breadcrumbs=_build_breadcrumbs(current_path_display),
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
            show_hidden_files=show_hidden_files,
            master_key_configured=len(auth_service.master_keys) > 0,
            master_unlocked=auth_service.is_master_unlocked()
        )
    
    abort(500)


def _handle_smart_search(query, file_service, search_service, navigation_service,
                         analytics_service, client_id, show_hidden):
    """Smart search: hybrid+rerank semantic results merged with filename matches."""
    temp_entries = {}

    # Semantic search (with popularity + trajectory personalization)
    semantic_results = {}
    snippets = {}
    if search_service.is_available and search_service.is_index_ready:
        popularity = analytics_service.file_popularity()
        trajectory = analytics_service.current_trajectory(client_id)
        prior_fn = lambda paths: navigation_service.file_priors(trajectory, paths)
        for res in search_service.search(query, popularity=popularity, prior_fn=prior_fn):
            semantic_results[res["path"]] = res["score"]
            snippets[res["path"]] = res.get("snippet")

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
            info["snippet"] = snippets.get(rel_path)
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


@main_bp.route("/validate-master-key", methods=["POST"])
def validate_master_key():
    """Validate a master key and grant full access if correct."""
    auth_service = current_app.auth_service
    visibility_service = current_app.visibility_service

    try:
        data = request.get_json()
        if not data or "key" not in data:
            return jsonify(status="error", message="Missing key."), 400

        provided_key = data["key"]

        if auth_service.validate_master_key(provided_key):
            auth_service.apply_master_access(visibility_service)
            return jsonify(status="success", message="Master access granted."), 200
        else:
            return jsonify(status="error", message="Invalid master key."), 401

    except Exception as e:
        print(f"Error in /validate-master-key: {e}")
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


def dashboard_key_valid(auth_service, config, key: str) -> bool:
    """Dashboard accepts the master key if configured, else the upload key."""
    if not key:
        return False
    if auth_service.master_keys:
        return auth_service.validate_master_key(key)
    return bool(config.UPLOAD_API_KEY) and key == config.UPLOAD_API_KEY


def dashboard_authorized(auth_service) -> bool:
    return bool(session.get("dashboard_ok")) or auth_service.is_master_unlocked()


@main_bp.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    """Analytics dashboard, gated by the master/upload key."""
    auth_service = current_app.auth_service
    analytics_service = current_app.analytics_service
    config = current_app.config_obj

    error = None
    if request.method == "POST":
        if dashboard_key_valid(auth_service, config, request.form.get("key", "")):
            session["dashboard_ok"] = True
            session.modified = True
        else:
            error = "Invalid key."

    authorized = dashboard_authorized(auth_service)
    summary = analytics_service.summary() if authorized else None
    return render_template(
        "dashboard.html",
        title="Analytics",
        authorized=authorized,
        error=error,
        summary=summary,
        analytics_enabled=analytics_service.enabled,
    )


