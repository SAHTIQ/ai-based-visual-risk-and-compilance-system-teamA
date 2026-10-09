from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth
from app.services.crud_service import create_document, get_document, list_documents, update_document, delete_document
from app.utils.serializers import serialize_doc, serialize_docs
from app.utils.validators import validate_required_fields, validate_positive_number, validate_enum

goal_bp = Blueprint('goal_bp', __name__, url_prefix='/api/goals')
COLLECTION = 'goals'
ENTITY_TYPE = 'goal'

@goal_bp.route('', methods=['POST'])
@require_auth
def create():
    data = request.get_json() or {}
    missing = validate_required_fields(data, ['title', 'category'])
    if missing:
        return jsonify({"success": False, "error": f"Missing fields: {missing}"}), 400
        
    if not validate_enum(data['category'], ['financial', 'finance', 'academic', 'learning', 'fitness', 'personal', 'career', 'health']):
        return jsonify({"success": False, "error": "Invalid category"}), 400

        
    if 'status' in data and not validate_enum(data['status'], ['not-started', 'in-progress', 'completed', 'abandoned']):
        return jsonify({"success": False, "error": "Invalid status"}), 400

    if 'priority' in data and not validate_enum(data['priority'], ['low', 'medium', 'high']):
        return jsonify({"success": False, "error": "Invalid priority"}), 400

    try:
        doc = create_document(COLLECTION, g.uid, data, entity_type=ENTITY_TYPE)
        return jsonify({"success": True, "data": doc}), 201
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@goal_bp.route('', methods=['GET'])
@require_auth
def list_records():
    try:
        docs = list_documents(COLLECTION, g.uid)
        return jsonify({"success": True, "data": docs})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@goal_bp.route('/<doc_id>', methods=['GET'])
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

@goal_bp.route('/<doc_id>', methods=['PUT'])
@require_auth
def update(doc_id):
    data = request.get_json() or {}
    if 'category' in data and not validate_enum(data['category'], ['financial', 'finance', 'academic', 'learning', 'fitness', 'personal', 'career', 'health']):
        return jsonify({"success": False, "error": "Invalid category"}), 400

    if 'status' in data and not validate_enum(data['status'], ['not-started', 'in-progress', 'completed', 'abandoned']):
        return jsonify({"success": False, "error": "Invalid status"}), 400
    if 'priority' in data and not validate_enum(data['priority'], ['low', 'medium', 'high']):
        return jsonify({"success": False, "error": "Invalid priority"}), 400
        
    try:
        doc = update_document(COLLECTION, doc_id, g.uid, data, entity_type=ENTITY_TYPE)
        return jsonify({"success": True, "data": doc})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except PermissionError as e:
        return jsonify({"success": False, "error": str(e)}), 403
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@goal_bp.route('/<doc_id>', methods=['DELETE'])
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
