"""
Digital Twin AI — Activity Service

Automatically logs all user actions (create, update, delete)
to the activity_history Firestore collection.
"""
from firebase_admin import firestore
from app.services.firebase_service import get_firestore_client


def log_activity(uid, action='update', entity_type=None, entity_id='', summary='', details=None, **kwargs):
    """
    Log a user activity to the activity_history collection defensively.
    Supports both standard positional arguments and convenience keyword forms.
    """
    try:
        db = get_firestore_client()
        # Handle case where summary is passed as 2nd argument e.g. log_activity(uid, "Completed habit ...", category="habit")
        if entity_type is None and not entity_id and not summary:
            summary_text = str(action)
            act = kwargs.get('action', 'update')
            ent_type = kwargs.get('category', kwargs.get('entity_type', 'habit'))
            ent_id = kwargs.get('entity_id', '')
        else:
            summary_text = summary or str(action)
            act = action
            ent_type = entity_type or kwargs.get('category', 'general')
            ent_id = entity_id or kwargs.get('entity_id', '')

        activity_data = {
            'uid': uid,
            'action': act,
            'entity_type': ent_type,
            'entity_id': ent_id,
            'summary': summary_text,
            'details': details or kwargs.get('details', {}),
            'timestamp': firestore.SERVER_TIMESTAMP,
        }

        db.collection('activity_history').add(activity_data)
    except Exception as e:
        print(f"[Activity Log Warning]: {e}")
