"""
Quick diagnostic script — run this to find the exact error causing 500s.
Run from the project root with: python test_db.py
"""
import os
import sys

# Load .env
from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print("Digital Twin AI - Diagnostic Test")
print("=" * 60)

# Step 1: Firebase init
print("\n[1] Testing Firebase initialization...")
try:
    from app.services.firebase_service import init_firebase, get_firestore_client
    init_firebase()
    print("    [OK] Firebase initialized OK")
except Exception as e:
    print(f"    [FAIL] Firebase init failed: {e}")
    sys.exit(1)

# Step 2: Firestore connection
print("\n[2] Testing Firestore connection...")
try:
    db = get_firestore_client()
    print("    [OK] Firestore client created OK")
except Exception as e:
    print(f"    [FAIL] Firestore client failed: {e}")
    sys.exit(1)

# Step 3: Simple Firestore read
print("\n[3] Testing Firestore read (test_collection)...")
try:
    docs = list(db.collection('test_ping').limit(1).stream())
    print(f"    [OK] Firestore read OK (found {len(docs)} docs)")
except Exception as e:
    print(f"    [FAIL] Firestore read failed: {e}")

# Step 4: Test where() query
print("\n[4] Testing where() query on income collection...")
try:
    docs = list(db.collection('income').where('uid', '==', 'test-uid').limit(1).stream())
    print(f"    [OK] where() query OK (found {len(docs)} docs)")
except Exception as e:
    print(f"    [FAIL] where() query failed: {e}")

# Step 5: Test serializer
print("\n[5] Testing serializer...")
try:
    from app.utils.serializers import serialize_doc
    import datetime
    test_data = {
        'id': 'test-id',
        'amount': 100.0,
        'date': '2026-01-01',
        'created_at': datetime.datetime.now(),
        'uid': 'test-uid',
    }
    result = serialize_doc(test_data)
    print(f"    [OK] Serializer OK: {result}")
except Exception as e:
    print(f"    [FAIL] Serializer failed: {e}")

# Step 6: Test write
print("\n[6] Testing Firestore write (test_ping collection)...")
try:
    from firebase_admin import firestore as fs
    _, ref = db.collection('test_ping').add({
        'test': True,
        'created_at': fs.SERVER_TIMESTAMP
    })
    print(f"    [OK] Write OK - doc id: {ref.id}")
    # Clean up
    ref.delete()
    print(f"    [OK] Cleanup OK")
except Exception as e:
    print(f"    [FAIL] Write failed: {e}")

# Step 7: Test validators
print("\n[7] Testing validators...")
try:
    from app.utils.validators import validate_required_fields, validate_positive_number, validate_enum
    missing = validate_required_fields({'amount': 100}, ['amount', 'date'])
    valid = validate_positive_number(100.0)
    enum_ok = validate_enum('salary', ['salary', 'freelance'])
    print(f"    [OK] Validators OK - missing={missing}, positive={valid}, enum={enum_ok}")
except Exception as e:
    print(f"    [FAIL] Validators failed: {e}")

print("\n" + "=" * 60)
print("Diagnostic complete. Share any [FAIL] errors above.")
print("=" * 60)
