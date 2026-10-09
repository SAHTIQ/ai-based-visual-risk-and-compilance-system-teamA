"""
Digital Twin AI — Activity Service

Automatically logs all user actions (create, update, delete)
to the activity_history Firestore collection.
"""
from firebase_admin import firestore
from app.services.firebase_service import get_firestore_client


def log_activity(uid, action, entity_type, entity_id, summary, details=None):
    """
    Log a user activity to the activity_history collection.

    Args:
        uid: Firebase user UID.
        action: One of 'create', 'update', 'delete'.
        entity_type: The type of entity (e.g., 'income', 'expense', 'goal').
        entity_id: The Firestore document ID of the affected entity.
        summary: Human-readable description of the activity.
        details: Optional dict with a snapshot of the changed data.
    """
    db = get_firestore_client()

    activity_data = {
        'uid': uid,
        'action': action,
        'entity_type': entity_type,
        'entity_id': entity_id,
        'summary': summary,
        'details': details or {},
        'timestamp': firestore.SERVER_TIMESTAMP,
    }

    db.collection('activity_history').add(activity_data)
