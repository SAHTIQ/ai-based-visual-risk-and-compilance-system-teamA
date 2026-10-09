"""
QUANTA — Chat API Routes
=========================
POST   /api/chat          — Send a message, get Quanta's response.
GET    /api/chat/history   — Retrieve conversation history.
DELETE /api/chat/history   — Clear conversation history.
"""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth
from app.services.conversation_service import run_chat_turn, get_chat_history, clear_chat_history

chat_bp = Blueprint("chat_bp", __name__, url_prefix="/api/chat")


@chat_bp.route("", methods=["POST"])
@require_auth
def send_message():
    """
    Send a user message to Quanta Assistant.

    Request body:
        { "message": "Can I afford ₹5,000 this week?" }

    Response:
        {
          "success": true,
          "data": {
            "reply":      "...",
            "tool_calls": [{"tool": "...", "args": {...}, "result_summary": "..."}]
          }
        }
    """
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()

    if not message:
        return jsonify({"success": False, "error": "Message cannot be empty."}), 400

    if len(message) > 2000:
        return jsonify({"success": False, "error": "Message too long (max 2000 characters)."}), 400

    result = run_chat_turn(uid=g.uid, user_message=message)

    if result.get("error") and not result.get("reply"):
        return jsonify({"success": False, "error": result["error"]}), 500

    return jsonify({
        "success": True,
        "data": {
            "reply":      result["reply"],
            "tool_calls": result.get("tool_calls", []),
        },
    })


@chat_bp.route("/history", methods=["GET"])
@require_auth
def fetch_history():
    """Return stored conversation history for this user."""
    try:
        history = get_chat_history(uid=g.uid)
        return jsonify({"success": True, "data": history})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@chat_bp.route("/history", methods=["DELETE"])
@require_auth
def delete_history():
    """Clear all conversation history for this user."""
    try:
        clear_chat_history(uid=g.uid)
        return jsonify({"success": True, "message": "Conversation history cleared."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
