"""
Digital Twin AI — Authentication Middleware

Provides the @require_auth decorator for protecting Flask routes
with Firebase ID token verification.
"""
from functools import wraps
from flask import request, jsonify, g
from firebase_admin import auth


def require_auth(f):
    """
    Flask route decorator that verifies Firebase ID tokens.

    Extracts the Bearer token from the Authorization header,
    verifies it with Firebase Admin SDK, and sets:
    - g.uid: The authenticated user's Firebase UID
    - g.user: The full decoded token dict

    Returns 401 on missing, expired, revoked, or invalid tokens.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')

        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({
                'success': False,
                'error': 'Missing or invalid Authorization header'
            }), 401

        id_token = auth_header.split('Bearer ')[1].strip()

        if not id_token:
            return jsonify({
                'success': False,
                'error': 'Empty token'
            }), 401

        try:
            decoded_token = auth.verify_id_token(id_token)
            g.user = decoded_token
            g.uid = decoded_token['uid']
        except auth.ExpiredIdTokenError as e:
            print(f"[Auth Error] Expired token: {e}")
            return jsonify({
                'success': False,
                'error': 'Token has expired. Please sign in again.'
            }), 401
        except auth.RevokedIdTokenError as e:
            print(f"[Auth Error] Revoked token: {e}")
            return jsonify({
                'success': False,
                'error': 'Token has been revoked. Please sign in again.'
            }), 401
        except auth.InvalidIdTokenError as e:
            print(f"[Auth Error] Invalid token: {e}")
            return jsonify({
                'success': False,
                'error': 'Invalid token.'
            }), 401
        except Exception as e:
            print(f"[Auth Error] Unexpected verification error: {e}")
            import traceback; traceback.print_exc()
            return jsonify({
                'success': False,
                'error': f'Authentication failed: {str(e)}'
            }), 401

        return f(*args, **kwargs)

    return decorated_function
