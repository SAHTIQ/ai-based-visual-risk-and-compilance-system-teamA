from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth
from app.services.crud_service import get_document
from app.utils.serializers import serialize_doc
from firebase_admin import firestore

profile_bp = Blueprint('profile_bp', __name__, url_prefix='/api/profile')

@profile_bp.route('', methods=['GET'])
@require_auth
def get_profile_route():
    try:
        doc = get_document('users', g.uid, g.uid)
        return jsonify({"success": True, "data": doc})
    except ValueError:
        return jsonify({"success": False, "error": "Profile not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@profile_bp.route('', methods=['PUT'])
@require_auth
def update_profile():
    data = request.get_json() or {}
    allowed_fields = ['display_name', 'date_of_birth', 'gender', 'phone', 'location', 'occupation', 'bio']
    update_data = {k: v for k, v in data.items() if k in allowed_fields}
    
    try:
        db = firestore.client()
        update_data['updated_at'] = firestore.SERVER_TIMESTAMP
        doc_ref = db.collection('users').document(g.uid)
        doc_ref.set(update_data, merge=True)

        doc = doc_ref.get()
        doc_data = doc.to_dict() or {}
        doc_data['id'] = doc.id
        return jsonify({"success": True, "data": serialize_doc(doc_data)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
