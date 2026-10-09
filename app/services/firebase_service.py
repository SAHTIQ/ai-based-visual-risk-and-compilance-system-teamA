"""
Digital Twin AI — Firebase Service

Handles Firebase Admin SDK initialization and provides
the Firestore client singleton.
"""
import os
import firebase_admin
from firebase_admin import credentials, firestore, auth


def init_firebase():
    """
    Initialize Firebase Admin SDK if not already initialized.

    Supports two credential modes:
    1. Service account JSON file (path via FIREBASE_CREDENTIALS_PATH env var)
    2. Application Default Credentials (for Google Cloud environments)
    """
    if firebase_admin._apps:
        return  # Already initialized

    cred_path = os.getenv('FIREBASE_CREDENTIALS_PATH', 'serviceAccountKey.json')

    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
    else:
        # Fall back to Application Default Credentials (e.g., Cloud Run, Colab)
        project_id = os.getenv('FIREBASE_PROJECT_ID')
        if project_id:
            cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred, {'projectId': project_id})
        else:
            raise RuntimeError(
                "Firebase credentials not found. "
                "Set FIREBASE_CREDENTIALS_PATH to your serviceAccountKey.json "
                "or set FIREBASE_PROJECT_ID for Application Default Credentials."
            )


def get_firestore_client():
    """
    Returns the Firestore client, initializing Firebase if needed.
    """
    init_firebase()
    return firestore.client()


def get_auth():
    """
    Returns the Firebase Auth module, initializing Firebase if needed.
    """
    init_firebase()
    return auth
