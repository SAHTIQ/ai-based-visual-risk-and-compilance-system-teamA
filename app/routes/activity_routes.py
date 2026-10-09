from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth
from firebase_admin import firestore
from app.utils.serializers import serialize_docs

activity_bp = Blueprint('activity_bp', __name__, url_prefix='/api/activities')

@activity_bp.route('', methods=['GET'])
@require_auth
def list_activities():
    try:
        limit = request.args.get('limit', default=50, type=int)
        db = firestore.client()
        query = db.collection('activity_history').where('uid', '==', g.uid).limit(limit)
        docs = query.stream()
        results = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            results.append(data)
        return jsonify({"success": True, "data": serialize_docs(results)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
