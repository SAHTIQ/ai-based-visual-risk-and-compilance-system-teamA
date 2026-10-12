"""
QUANTA — Chat & AI Assistant API Routes
=======================================
POST   /api/chat                     — Send message in thread with routing mode & dual-model gateway
GET    /api/chat/history             — Retrieve thread message history
DELETE /api/chat/history             — Clear thread message history

GET    /api/chat/threads             — List all user chat threads with time-bucket grouping
POST   /api/chat/threads             — Create a new thread / branch child thread
GET    /api/chat/threads/<thread_id> — Get messages for specific thread
PATCH  /api/chat/threads/<thread_id> — Rename or archive thread
DELETE /api/chat/threads/<thread_id> — Delete thread

GET    /api/chat/insights            — List saved user insights
POST   /api/chat/insights            — Save new insight
DELETE /api/chat/insights/<insight_id> — Delete saved insight

GET    /api/chat/context-summary     — Return real live context overview for Right Panel
"""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth
from app.services.conversation_service import (
    execute_chat_turn, get_chat_history, clear_chat_history,
    get_user_threads, create_user_thread, update_user_thread, delete_user_thread,
    get_user_insights, save_user_insight, delete_user_insight,
    get_user_context_summary
)

chat_bp = Blueprint("chat_bp", __name__, url_prefix="/api/chat")


@chat_bp.route("", methods=["POST"])
@require_auth
def send_message():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    thread_id = data.get("thread_id") or "default"
    routing_mode = data.get("routing_mode") or "auto"

    if not message:
        return jsonify({"success": False, "error": "Message cannot be empty."}), 400

    if len(message) > 2500:
        return jsonify({"success": False, "error": "Message too long (max 2500 characters)."}), 400

    result = execute_chat_turn(
        uid=g.uid,
        user_message=message,
        thread_id=thread_id,
        routing_mode=routing_mode
    )

    if result.get("error") and not result.get("reply"):
        return jsonify({"success": False, "error": result["error"]}), 500

    return jsonify({
        "success": True,
        "data": {
            "reply": result["reply"],
            "tool_calls": result.get("tool_calls", []),
            "widgets": result.get("widgets", []),
            "sources_used": result.get("sources_used", []),
            "model_used": result.get("model_used", ""),
            "fallback_used": result.get("fallback_used", False),
            "status": result.get("status", "completed"),
            "thread_id": result.get("thread_id", thread_id),
        },
    })


@chat_bp.route("/history", methods=["GET"])
@require_auth
def fetch_history():
    thread_id = request.args.get("thread_id") or "default"
    try:
        history = get_chat_history(uid=g.uid, thread_id=thread_id)
        return jsonify({"success": True, "data": history})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@chat_bp.route("/history", methods=["DELETE"])
@require_auth
def delete_history():
    thread_id = request.args.get("thread_id") or "default"
    try:
        clear_chat_history(uid=g.uid, thread_id=thread_id)
        return jsonify({"success": True, "message": "Conversation history cleared."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Thread Endpoints ──────────────────────────────────────────────────────────

@chat_bp.route("/threads", methods=["GET"])
@require_auth
def list_threads():
    try:
        threads = get_user_threads(uid=g.uid)
        return jsonify({"success": True, "data": threads})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@chat_bp.route("/threads", methods=["POST"])
@require_auth
def new_thread():
    data = request.get_json(silent=True) or {}
    title = data.get("title") or "New Chat"
    parent_id = data.get("parent_id")
    try:
        thread = create_user_thread(uid=g.uid, title=title, parent_id=parent_id)
        return jsonify({"success": True, "data": thread})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@chat_bp.route("/threads/<thread_id>", methods=["GET"])
@require_auth
def get_thread_msgs(thread_id):
    try:
        history = get_chat_history(uid=g.uid, thread_id=thread_id)
        return jsonify({"success": True, "data": history})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@chat_bp.route("/threads/<thread_id>", methods=["PATCH"])
@require_auth
def patch_thread(thread_id):
    data = request.get_json(silent=True) or {}
    title = data.get("title")
    archived = data.get("archived")
    try:
        res = update_user_thread(uid=g.uid, thread_id=thread_id, title=title, archived=archived)
        return jsonify({"success": True, "data": res})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@chat_bp.route("/threads/<thread_id>", methods=["DELETE"])
@require_auth
def remove_thread(thread_id):
    try:
        delete_user_thread(uid=g.uid, thread_id=thread_id)
        return jsonify({"success": True, "message": "Thread deleted."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Saved Insights Endpoints ──────────────────────────────────────────────────

@chat_bp.route("/insights", methods=["GET"])
@require_auth
def list_insights():
    try:
        insights = get_user_insights(uid=g.uid)
        return jsonify({"success": True, "data": insights})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@chat_bp.route("/insights", methods=["POST"])
@require_auth
def add_insight():
    data = request.get_json(silent=True) or {}
    title = data.get("title") or "Saved Insight"
    content = (data.get("content") or "").strip()
    domain = data.get("domain") or "General"
    if not content:
        return jsonify({"success": False, "error": "Insight content cannot be empty."}), 400
    try:
        res = save_user_insight(uid=g.uid, title=title, content=content, domain=domain)
        return jsonify({"success": True, "data": res})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@chat_bp.route("/insights/<insight_id>", methods=["DELETE"])
@require_auth
def remove_insight(insight_id):
    try:
        delete_user_insight(uid=g.uid, insight_id=insight_id)
        return jsonify({"success": True, "message": "Insight deleted."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Right-Side Context Summary ────────────────────────────────────────────────

@chat_bp.route("/context-summary", methods=["GET"])
@require_auth
def get_context_summary():
    try:
        summary = get_user_context_summary(uid=g.uid)
        return jsonify({"success": True, "data": summary})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
