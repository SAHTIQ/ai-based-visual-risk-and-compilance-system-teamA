"""
Digital Twin AI — Streak API Routes
"""
from flask import Blueprint, jsonify, g
from app.middleware.auth import require_auth
from app.services.streak_service import get_streak_data, daily_checkin
from firebase_admin import firestore

streak_bp = Blueprint('streak_bp', __name__, url_prefix='/api/streak')


@streak_bp.route('', methods=['GET'])
@require_auth
def get_streak():
    """Return current streak, XP, level, achievements for the logged-in user."""
    try:
        db = firestore.client()
        data = get_streak_data(g.uid, db)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@streak_bp.route('/checkin', methods=['POST'])
@require_auth
def checkin():
    """Perform today's daily check-in. Safe to call multiple times — idempotent."""
    try:
        db = firestore.client()
        result = daily_checkin(g.uid, db)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
