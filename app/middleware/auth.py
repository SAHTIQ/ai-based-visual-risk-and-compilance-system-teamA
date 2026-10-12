"""
Digital Twin AI — Authentication Middleware

Provides the @require_auth decorator for protecting Flask routes
with Firebase ID token verification.
"""
import time
import hashlib
from threading import Lock
from functools import wraps
from flask import request, jsonify, g
from firebase_admin import auth

_TOKEN_CACHE_LOCK = Lock()
_TOKEN_CACHE = {}  # token_hash -> (decoded_token, expire_timestamp)
_TOKEN_CACHE_TTL = 180  # 3 minutes

def _get_cached_token(id_token: str):
    thash = hashlib.sha256(id_token.encode('utf-8')).hexdigest()
    now = time.time()
    with _TOKEN_CACHE_LOCK:
        entry = _TOKEN_CACHE.get(thash)
        if entry:
            decoded, exp = entry
            if now < exp:
                return decoded
            else:
                _TOKEN_CACHE.pop(thash, None)
    return None

def _set_cached_token(id_token: str, decoded_token: dict):
    thash = hashlib.sha256(id_token.encode('utf-8')).hexdigest()
    now = time.time()
    token_exp = decoded_token.get('exp', now + 3600)
    # Cache for up to _TOKEN_CACHE_TTL, but never beyond actual token expiration
    ttl = min(_TOKEN_CACHE_TTL, max(30, token_exp - now))
    with _TOKEN_CACHE_LOCK:
        # Prevent unbounded growth
        if len(_TOKEN_CACHE) > 500:
            expired = [k for k, (_, exp) in _TOKEN_CACHE.items() if now >= exp]
            for k in expired:
                _TOKEN_CACHE.pop(k, None)
        _TOKEN_CACHE[thash] = (decoded_token, now + ttl)


def require_auth(f):
    """
    Flask route decorator that verifies Firebase ID tokens.
    Uses in-memory caching to avoid repeated cryptographic verification.
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

        cached_decoded = _get_cached_token(id_token)
        if cached_decoded:
            g.user = cached_decoded
            g.uid = cached_decoded['uid']
            return f(*args, **kwargs)

        try:
            decoded_token = auth.verify_id_token(id_token)
            _set_cached_token(id_token, decoded_token)
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
