from flask import Blueprint, jsonify, request, session
from functools import wraps

api_bp = Blueprint("api", __name__)


def api_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_email" not in session:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


def api_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_email" not in session:
            return jsonify({"error": "Unauthorized"}), 401
        if not session.get("is_admin"):
            return jsonify({"error": "Admin required"}), 403
        return f(*args, **kwargs)
    return decorated


@api_bp.route("/tcg/search")
@api_admin_required
def tcg_search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"results": []})
    from app.services.tcg import search_cards
    try:
        results = search_cards(query)
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
