"""
Digital Twin AI — Serialization Utilities

Converts Firestore documents to JSON-safe Python dicts.
Handles Firestore timestamps, GeoPoints, and other special types.
"""
from datetime import datetime


def serialize_doc(doc_dict):
    """
    Convert a Firestore document dict to a JSON-serializable dict.

    Handles:
    - Firestore Timestamps → ISO 8601 strings
    - datetime objects → ISO 8601 strings
    - Nested dicts and lists
    - GeoPoints → {lat, lng} dicts

    Args:
        doc_dict: A dict from Firestore doc.to_dict().

    Returns:
        A JSON-safe dict.
    """
    if doc_dict is None:
        return None

    serialized = {}
    for key, value in doc_dict.items():
        serialized[key] = _serialize_value(value)

    return serialized


def serialize_docs(doc_list):
    """
    Serialize a list of Firestore document dicts.

    Args:
        doc_list: List of dicts from Firestore.

    Returns:
        List of JSON-safe dicts.
    """
    return [serialize_doc(doc) for doc in doc_list]


def _serialize_value(value):
    """Recursively serialize a single value."""
    if value is None:
        return None

    # Handle datetime / Firestore Timestamp
    if isinstance(value, datetime):
        return value.isoformat()

    # Handle DatetimeWithNanoseconds (Firestore)
    if hasattr(value, 'isoformat'):
        return value.isoformat()

    # Handle GeoPoint
    if hasattr(value, 'latitude') and hasattr(value, 'longitude'):
        return {
            'latitude': value.latitude,
            'longitude': value.longitude,
        }

    # Handle nested dict
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}

    # Handle list
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]

    # Primitives (str, int, float, bool) pass through
    return value
