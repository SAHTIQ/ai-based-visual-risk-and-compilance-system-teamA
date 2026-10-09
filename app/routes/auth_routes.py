from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth
from app.services.crud_service import create_document_with_id

auth_bp = Blueprint('auth_bp', __name__, url_prefix='/api/auth')

@auth_bp.route('/verify', methods=['POST'])
@require_auth
def verify_token():
    return jsonify({
        "success": True,
        "data": {
            "uid": g.uid,
            "email": g.user.get('email')
        }
    })

@auth_bp.route('/create-profile', methods=['POST'])
@require_auth
def create_profile():
    data = request.get_json() or {}
    email = data.get('email')
    display_name = data.get('display_name')
    
    if not email or not display_name:
        return jsonify({"success": False, "error": "email and display_name are required"}), 400
        
    try:
        profile_data = {
            "uid": g.uid,
            "email": email,
            "display_name": display_name
        }
        doc_id = create_document_with_id('users', g.uid, profile_data, entity_type='profile')
        return jsonify({"success": True, "data": {"id": doc_id}}), 201
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
