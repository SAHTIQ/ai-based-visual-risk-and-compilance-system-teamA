from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth
from app.services.crud_service import create_document, get_document, list_documents, update_document, delete_document
from app.utils.serializers import serialize_doc, serialize_docs
from app.utils.validators import validate_required_fields, validate_positive_number, validate_enum

habit_bp = Blueprint('habit_bp', __name__, url_prefix='/api/habits')
COLLECTION = 'habits'
ENTITY_TYPE = 'habit'

@habit_bp.route('', methods=['POST'])
@require_auth
def create():
    data = request.get_json() or {}
    missing = validate_required_fields(data, ['name', 'category'])
    if missing:
        return jsonify({"success": False, "error": f"Missing fields: {missing}"}), 400
        
    if not validate_enum(data['category'], ['health', 'wellness', 'productivity', 'learning', 'social', 'other']):
        return jsonify({"success": False, "error": "Invalid category"}), 400

        
    if 'frequency' in data and not validate_enum(data['frequency'], ['daily', 'weekly', 'monthly']):
        return jsonify({"success": False, "error": "Invalid frequency"}), 400

    try:
        doc = create_document(COLLECTION, g.uid, data, entity_type=ENTITY_TYPE)
        return jsonify({"success": True, "data": doc}), 201
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@habit_bp.route('', methods=['GET'])
@require_auth
def list_records():
    try:
        docs = list_documents(COLLECTION, g.uid)
        return jsonify({"success": True, "data": docs})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@habit_bp.route('/<doc_id>', methods=['GET'])
@require_auth
def get(doc_id):
    try:
        doc = get_document(COLLECTION, doc_id, g.uid)
        return jsonify({"success": True, "data": doc})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except PermissionError as e:
        return jsonify({"success": False, "error": str(e)}), 403
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@habit_bp.route('/<doc_id>', methods=['PUT'])
@require_auth
def update(doc_id):
    data = request.get_json() or {}
    if 'category' in data and not validate_enum(data['category'], ['health', 'wellness', 'productivity', 'learning', 'social', 'other']):
        return jsonify({"success": False, "error": "Invalid category"}), 400

    if 'frequency' in data and not validate_enum(data['frequency'], ['daily', 'weekly', 'monthly']):
        return jsonify({"success": False, "error": "Invalid frequency"}), 400
        
    try:
        doc = update_document(COLLECTION, doc_id, g.uid, data, entity_type=ENTITY_TYPE)
        return jsonify({"success": True, "data": doc})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except PermissionError as e:
        return jsonify({"success": False, "error": str(e)}), 403
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@habit_bp.route('/<doc_id>/delete', methods=['DELETE'])
@habit_bp.route('/<doc_id>', methods=['DELETE'])
@require_auth
def delete(doc_id):
    try:
        delete_document(COLLECTION, doc_id, g.uid, entity_type=ENTITY_TYPE)
        return jsonify({"success": True})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except PermissionError as e:
        return jsonify({"success": False, "error": str(e)}), 403
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@habit_bp.route('/<doc_id>/shield', methods=['POST'])
@require_auth
def shield_habit(doc_id):
    """
    Actionable Habit Risk Shield:
    Action 'micro_task': Complete 2-min micro-task to shield streak & gain +10 XP.
    Action 'xp_freeze': Use 30 XP to freeze streak for 24 hours.
    """
    from datetime import date
    from app.services.firebase_service import get_firestore_client
    from app.services.crud_service import invalidate_user_cache
    from app.services.activity_service import log_activity

    try:
        data = request.get_json() or {}
        action = data.get('action', 'micro_task')

        habit = get_document(COLLECTION, doc_id, g.uid)
        db = get_firestore_client()
        user_ref = db.collection("users").document(g.uid)
        user_snap = user_ref.get()
        user_data = user_snap.to_dict() or {} if user_snap.exists else {}

        current_xp = user_data.get("xp", 0)
        habit_name = habit.get("name", "Habit")
        today_iso = date.today().isoformat()

        if action == 'xp_freeze':
            if current_xp < 30:
                return jsonify({"success": False, "error": "Insufficient XP! You need at least 30 XP to activate Streak Freeze."}), 400
            new_xp = current_xp - 30
            user_ref.set({"xp": new_xp}, merge=True)

            updates = {
                "streak_protected": True,
                "last_completed": today_iso,
                "risk_score": 0.05,
                "status": "active"
            }
            msg = f"🛡️ Streak Freeze activated for '{habit_name}' (-30 XP). Streak protected for 24h!"
            log_activity(g.uid, f"Activated Streak Freeze for habit '{habit_name}'", category="habit", impact="positive")

        else: # micro_task default
            current_streak = habit.get("streak", habit.get("streak_count", 0))
            new_xp = current_xp + 10
            user_ref.set({"xp": new_xp}, merge=True)

            updates = {
                "streak": current_streak + 1,
                "streak_count": current_streak + 1,
                "last_completed": today_iso,
                "streak_protected": True,
                "risk_score": 0.1,
                "status": "active"
            }
            msg = f"⚡ Micro-Task completed for '{habit_name}'! Streak shielded & earned +10 XP."
            log_activity(g.uid, f"Shielded habit '{habit_name}' via 2-min micro task", category="habit", impact="positive")

        updated_doc = update_document(COLLECTION, doc_id, g.uid, updates, entity_type=ENTITY_TYPE)
        invalidate_user_cache(g.uid)

        return jsonify({
            "success": True,
            "message": msg,
            "data": updated_doc,
            "new_xp": new_xp
        })

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except PermissionError as e:
        return jsonify({"success": False, "error": str(e)}), 403
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

