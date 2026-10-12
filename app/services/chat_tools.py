"""
QUANTA — Chat Tool Registry
============================
Defines the data-fetching tools that the Gemini LLM can call during a
conversation. Each tool function takes (uid, **kwargs) and returns a
plain Python dict that Gemini receives as the function result.

Tool categories:
  Profile    — get_user_profile
  Finance    — get_financial_summary, get_recent_transactions,
               create_expense, create_income,
               update_expense, update_income,
               delete_expense, delete_income
  Study      — get_study_analysis, get_study_sessions,
               create_study_session, update_study_session,
               delete_study_session
  Habits     — get_habit_analysis, get_habits,
               create_habit, update_habit, delete_habit
  Goals      — get_goal_summary
  Activity   — get_activity_summary
  ML / AI    — get_financial_forecast, get_productivity_analysis
"""

import re
from datetime import datetime, timedelta
from firebase_admin import firestore
from app.services.ml_service import forecast_finance, forecast_study, get_all_habit_risks
from app.utils.serializers import serialize_doc


# ──────────────────────────────────────────────────────────────────────────────
# Firestore helpers
# ──────────────────────────────────────────────────────────────────────────────

def _db():
    from app.services.firebase_service import get_firestore_client
    return get_firestore_client()


def _list_col(collection, uid, limit=50):
    """Return serialized docs from a collection filtered by uid."""
    db = _db()
    docs = db.collection(collection).where('uid', '==', uid).limit(limit).stream()
    results = []
    for doc in docs:
        d = doc.to_dict()
        d['id'] = doc.id
        results.append(serialize_doc(d))
    return results


def _create_doc(collection, uid, data, required_fields=None):
    """Create a Firestore doc, return the new document id."""
    db = _db()
    if required_fields:
        missing = [f for f in required_fields if f not in data or data[f] is None]
        if missing:
            return {"error": f"Missing required fields: {missing}"}
    data = dict(data)
    data['uid'] = uid
    data['created_at'] = firestore.SERVER_TIMESTAMP
    data['updated_at'] = firestore.SERVER_TIMESTAMP
    _, ref = db.collection(collection).add(data)
    try:
        from app.services.crud_service import invalidate_user_cache
        invalidate_user_cache(uid, collection)
    except Exception:
        pass
    return {"id": ref.id, "success": True}


def _update_doc(collection, doc_id, uid, data):
    """Update an existing doc — verifies ownership first."""
    db = _db()
    ref = db.collection(collection).document(doc_id)
    snap = ref.get()
    if not snap.exists:
        return {"error": f"Record {doc_id} not found."}
    existing = snap.to_dict()
    if existing.get('uid') != uid:
        return {"error": "Permission denied."}
    data = dict(data)
    data.pop('uid', None)
    data.pop('created_at', None)
    data['updated_at'] = firestore.SERVER_TIMESTAMP
    ref.update(data)
    try:
        from app.services.crud_service import invalidate_user_cache
        invalidate_user_cache(uid, collection)
    except Exception:
        pass
    return {"success": True, "id": doc_id}


def _delete_doc(collection, doc_id, uid):
    """Delete a doc — verifies ownership first."""
    db = _db()
    ref = db.collection(collection).document(doc_id)
    snap = ref.get()
    if not snap.exists:
        return {"error": f"Record {doc_id} not found."}
    if snap.to_dict().get('uid') != uid:
        return {"error": "Permission denied."}
    ref.delete()
    try:
        from app.services.crud_service import invalidate_user_cache
        invalidate_user_cache(uid, collection)
    except Exception:
        pass
    return {"success": True, "id": doc_id}


# ──────────────────────────────────────────────────────────────────────────────
# PROFILE
# ──────────────────────────────────────────────────────────────────────────────

def get_user_profile(uid, **_):
    """Return the user's Quanta profile."""
    db = _db()
    doc = db.collection('profiles').document(uid).get()
    if not doc.exists:
        return {"name": "Unknown", "note": "No profile found"}
    data = doc.to_dict()
    data.pop('uid', None)
    return serialize_doc(data)


# ──────────────────────────────────────────────────────────────────────────────
# FINANCE — Summary
# ──────────────────────────────────────────────────────────────────────────────

def get_financial_summary(uid, days=30, **_):
    """
    Aggregate income, expenses, and savings for the given period.
    Returns totals, net, category breakdown, and savings rate.
    """
    db = _db()
    today = datetime.now()
    cutoff = today - timedelta(days=int(days))
    cutoff_str = cutoff.strftime('%Y-%m-%d')

    income_total = 0.0
    expense_total = 0.0
    expense_by_cat = {}

    for doc in db.collection('income').where('uid', '==', uid).stream():
        d = doc.to_dict()
        if d.get('date', '') >= cutoff_str:
            income_total += float(d.get('amount', 0))

    for doc in db.collection('expenses').where('uid', '==', uid).stream():
        d = doc.to_dict()
        if d.get('date', '') >= cutoff_str:
            amt = float(d.get('amount', 0))
            expense_total += amt
            cat = d.get('category', 'other')
            expense_by_cat[cat] = expense_by_cat.get(cat, 0) + amt

    savings_total = 0.0
    for doc in db.collection('savings').where('uid', '==', uid).stream():
        d = doc.to_dict()
        if d.get('date', '') >= cutoff_str:
            savings_total += float(d.get('amount', 0))

    net = income_total - expense_total
    savings_rate = round((net / income_total * 100), 1) if income_total > 0 else 0

    top_cats = sorted(expense_by_cat.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "period_days": days,
        "income": round(income_total, 2),
        "expenses": round(expense_total, 2),
        "net": round(net, 2),
        "savings_deposited": round(savings_total, 2),
        "savings_rate_pct": savings_rate,
        "top_expense_categories": [
            {"category": k, "amount": round(v, 2)} for k, v in top_cats
        ],
    }


# ──────────────────────────────────────────────────────────────────────────────
# FINANCE — Transactions
# ──────────────────────────────────────────────────────────────────────────────

def get_recent_transactions(uid, days=14, type="all", limit=20, **_):
    """
    Return recent transactions. type can be 'income', 'expenses', or 'all'.
    """
    db = _db()
    today = datetime.now()
    cutoff = today - timedelta(days=int(days))
    cutoff_str = cutoff.strftime('%Y-%m-%d')
    items = []

    if type in ('income', 'all'):
        for doc in db.collection('income').where('uid', '==', uid).stream():
            d = doc.to_dict()
            if d.get('date', '') >= cutoff_str:
                items.append({
                    "id": doc.id, "type": "income",
                    "amount": float(d.get('amount', 0)),
                    "source": d.get('source', ''),
                    "date": d.get('date', ''),
                    "note": d.get('note', ''),
                })

    if type in ('expenses', 'all'):
        for doc in db.collection('expenses').where('uid', '==', uid).stream():
            d = doc.to_dict()
            if d.get('date', '') >= cutoff_str:
                items.append({
                    "id": doc.id, "type": "expense",
                    "amount": float(d.get('amount', 0)),
                    "category": d.get('category', ''),
                    "date": d.get('date', ''),
                    "note": d.get('note', ''),
                })

    items.sort(key=lambda x: x.get('date', ''), reverse=True)
    return {"transactions": items[:int(limit)], "count": len(items[:int(limit)])}


# ──────────────────────────────────────────────────────────────────────────────
# FINANCE — ML Forecast
# ──────────────────────────────────────────────────────────────────────────────

def get_financial_forecast(uid, **_):
    """
    Run the Quanta finance ML model and return the 30-day expense projection,
    trend, category breakdown, and QUANTA insight string.
    """
    result = forecast_finance(uid)
    if result is None:
        return {"error": "Finance ML model not available or insufficient data."}
    # Return a concise version (omit raw history/forecast arrays to save tokens)
    return {
        "projected_30d_expenses": result.get("projected_30d_expenses"),
        "monthly_income": result.get("current_monthly_income"),
        "expense_trend": result.get("expense_trend"),
        "category_breakdown": result.get("category_breakdown", [])[:5],
        "insight": result.get("insight"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# FINANCE — CRUD
# ──────────────────────────────────────────────────────────────────────────────

EXPENSE_CATEGORIES = ['food', 'transport', 'rent', 'utilities',
                      'entertainment', 'education', 'health', 'shopping', 'other']


def normalize_expense_category(cat: str) -> str:
    c = (cat or "").strip().lower()
    if c in EXPENSE_CATEGORIES:
        return c
    if any(k in c for k in ("food", "grocer", "dine", "dining", "meal", "coffee", "restaurant", "cafe", "dinner", "lunch", "breakfast", "snack")):
        return "food"
    if any(k in c for k in ("transport", "fuel", "gas", "petrol", "diesel", "taxi", "cab", "uber", "ola", "bus", "train", "metro", "flight", "commute", "travel")):
        return "transport"
    if any(k in c for k in ("rent", "apartment", "lease", "hostel", "pg", "flat", "housing")):
        return "rent"
    if any(k in c for k in ("utilit", "bill", "electric", "water", "wifi", "internet", "phone", "recharge")):
        return "utilities"
    if any(k in c for k in ("entertain", "movie", "film", "party", "game", "gaming", "stream", "netflix", "spotify", "hobby", "fun")):
        return "entertainment"
    if any(k in c for k in ("educat", "book", "course", "tuition", "school", "college", "fees", "study", "learning", "class")):
        return "education"
    if any(k in c for k in ("health", "med", "doctor", "pharmacy", "hospital", "clinic", "gym", "fitness", "wellness")):
        return "health"
    if any(k in c for k in ("shop", "cloth", "wear", "electronics", "gadget", "amazon", "flipkart", "store", "buy", "purchase")):
        return "shopping"
    return "other"


def create_expense(uid, amount, category="other", date=None, note="", **_):
    """Create a new expense record with auto-normalized category and default date."""
    try:
        amt = float(amount)
        if amt <= 0:
            return {"error": "Amount must be greater than zero."}
    except (ValueError, TypeError):
        return {"error": f"Invalid amount '{amount}'."}

    norm_category = normalize_expense_category(category)
    record_date = date or datetime.now().strftime("%Y-%m-%d")

    full_note = note or ""
    if norm_category == "other" and category and category.lower() != "other":
        full_note = f"[{category.capitalize()}] {full_note}".strip()

    res = _create_doc('expenses', uid, {
        "amount": amt,
        "category": norm_category,
        "date": record_date,
        "note": full_note,
        "currency": "INR"
    })
    if res.get("success"):
        return {
            "success": True,
            "id": res.get("id"),
            "amount": amt,
            "category": norm_category,
            "message": f"Successfully recorded expense of ₹{amt:,.2f} under category '{norm_category}'."
        }
    return res


def update_expense(uid, doc_id, amount=None, category=None, date=None, note=None, **_):
    """Update an existing expense record."""
    data = {}
    if amount is not None:
        data['amount'] = float(amount)
    if category is not None:
        data['category'] = normalize_expense_category(category)
    if date is not None:
        data['date'] = date
    if note is not None:
        data['note'] = note
    if not data:
        return {"error": "No fields to update."}
    return _update_doc('expenses', doc_id, uid, data)


def delete_expense(uid, doc_id, **_):
    """Delete an expense record."""
    return _delete_doc('expenses', doc_id, uid)


SAVINGS_TYPES = ['bank', 'investment', 'emergency', 'crypto', 'retirement', 'other']


def normalize_savings_type(raw_type: str) -> str:
    t = (raw_type or "").strip().lower()
    if t in SAVINGS_TYPES:
        return t
    if any(k in t for k in ("invest", "business", "stock", "equity", "share", "fund", "mutual", "trading", "gold")):
        return "investment"
    if any(k in t for k in ("bank", "saving", "deposit", "fd", "account", "cash", "recurring")):
        return "bank"
    if any(k in t for k in ("emergenc", "safety", "rainy", "buffer")):
        return "emergency"
    if any(k in t for k in ("crypto", "btc", "eth", "coin", "token", "web3")):
        return "crypto"
    if any(k in t for k in ("retire", "pension", "401k", "pf", "epf", "ppf")):
        return "retirement"
    return "other"


def create_savings(uid, amount, type="investment", date=None, target_amount=None, note="", **_):
    """Log a savings or investment deposit/record."""
    try:
        amt = float(amount)
        if amt <= 0:
            return {"error": "Amount must be greater than zero."}
    except (ValueError, TypeError):
        return {"error": f"Invalid amount '{amount}'."}

    norm_type = normalize_savings_type(type)
    record_date = date or datetime.now().strftime("%Y-%m-%d")

    full_note = note or ""
    if norm_type == "other" and type and type.lower() != "other":
        full_note = f"[{type.capitalize()}] {full_note}".strip()

    payload = {
        "amount": amt,
        "type": norm_type,
        "date": record_date,
        "currency": "INR",
        "note": full_note,
        "notes": full_note,
    }
    if target_amount:
        try:
            payload["target_amount"] = float(target_amount)
        except Exception:
            pass

    res = _create_doc('savings', uid, payload)
    if res.get("success"):
        return {
            "success": True,
            "id": res.get("id"),
            "amount": amt,
            "type": norm_type,
            "message": f"Successfully recorded savings entry of ₹{amt:,.2f} under {norm_type}."
        }
    return res


def update_savings(uid, doc_id, amount=None, type=None, date=None, note=None, **_):
    """Update a savings record."""
    data = {}
    if amount is not None:
        data['amount'] = float(amount)
    if type is not None:
        data['type'] = normalize_savings_type(type)
    if date is not None:
        data['date'] = date
    if note is not None:
        data['note'] = note
        data['notes'] = note
    if not data:
        return {"error": "No fields to update."}
    return _update_doc('savings', doc_id, uid, data)


def delete_savings(uid, doc_id, **_):
    """Delete a savings record."""
    return _delete_doc('savings', doc_id, uid)


INCOME_SOURCES = ['salary', 'freelance', 'scholarship', 'allowance', 'gift', 'investment', 'other']


def normalize_income_source(src: str) -> str:
    s = (src or "").strip().lower()
    if s in INCOME_SOURCES:
        return s
    if any(k in s for k in ("salar", "job", "paycheck", "wages", "bonus", "work")):
        return "salary"
    if any(k in s for k in ("free", "gig", "consult", "client", "contract", "project")):
        return "freelance"
    if any(k in s for k in ("scholar", "stipend", "grant", "fellowship")):
        return "scholarship"
    if any(k in s for k in ("allow", "pocket", "parent", "family")):
        return "allowance"
    if any(k in s for k in ("gift", "present", "reward")):
        return "gift"
    if any(k in s for k in ("invest", "business", "dividend", "interest", "profit", "stock", "crypto", "equity", "share", "venture")):
        return "investment"
    return "other"


def create_income(uid, amount, source="other", date=None, note="", **_):
    """Create a new income record with auto-normalized source and default date."""
    try:
        amt = float(amount)
        if amt <= 0:
            return {"error": "Amount must be greater than zero."}
    except (ValueError, TypeError):
        return {"error": f"Invalid amount '{amount}'."}

    norm_source = normalize_income_source(source)
    record_date = date or datetime.now().strftime("%Y-%m-%d")

    full_note = note or ""
    if norm_source == "other" and source and source.lower() != "other":
        full_note = f"[{source.capitalize()}] {full_note}".strip()

    res = _create_doc('income', uid, {
        "amount": amt,
        "source": norm_source,
        "date": record_date,
        "note": full_note,
        "currency": "INR"
    })
    if res.get("success"):
        return {
            "success": True,
            "id": res.get("id"),
            "amount": amt,
            "source": norm_source,
            "message": f"Successfully recorded income of ₹{amt:,.2f} from {norm_source}."
        }
    return res


def update_income(uid, doc_id, amount=None, source=None, date=None, note=None, **_):
    """Update an existing income record."""
    data = {}
    if amount is not None:
        data['amount'] = float(amount)
    if source is not None:
        data['source'] = source
    if date is not None:
        data['date'] = date
    if note is not None:
        data['note'] = note
    if not data:
        return {"error": "No fields to update."}
    return _update_doc('income', doc_id, uid, data)


def delete_income(uid, doc_id, **_):
    """Delete an income record."""
    return _delete_doc('income', doc_id, uid)


# ──────────────────────────────────────────────────────────────────────────────
# STUDY
# ──────────────────────────────────────────────────────────────────────────────

def get_study_analysis(uid, **_):
    """
    Return study consistency metrics + 7-day ML forecast.
    Includes: sessions/week, avg duration, longest streak,
    consistency %, and the Quanta study ML forecast.
    """
    db = _db()
    today = datetime.now()
    cutoff_30 = today - timedelta(days=30)
    cutoff_str = cutoff_30.strftime('%Y-%m-%d')

    sessions = []
    for doc in db.collection('study_records').where('uid', '==', uid).stream():
        d = doc.to_dict()
        date_str = d.get('date', '')
        if date_str:
            sessions.append({
                "date": date_str,
                "duration_minutes": float(d.get('duration_minutes', 0)),
                "subject": d.get('subject', ''),
            })

    recent = [s for s in sessions if s['date'] >= cutoff_str]
    total_sessions = len(recent)
    total_mins = sum(s['duration_minutes'] for s in recent)
    avg_duration = round(total_mins / total_sessions, 1) if total_sessions > 0 else 0
    sessions_per_week = round(total_sessions / 4.3, 1)

    # Streak calculation
    study_dates = sorted(set(s['date'] for s in sessions), reverse=True)
    streak = 0
    prev = None
    for d in study_dates:
        dt = datetime.strptime(d, '%Y-%m-%d').date()
        if prev is None:
            if (today.date() - dt).days <= 1:
                streak = 1
                prev = dt
        elif (prev - dt).days == 1:
            streak += 1
            prev = dt
        else:
            break

    # Days studied in last 30
    days_studied_30 = len(set(s['date'] for s in recent))
    consistency_pct = round(days_studied_30 / 30 * 100, 1)

    # ML forecast
    ml = forecast_study(uid)
    ml_summary = None
    if ml:
        ml_summary = {
            "projected_7d_hours": ml.get("projected_7d_study_hrs"),
            "study_trend": ml.get("study_trend"),
            "insight": ml.get("insight"),
        }

    return {
        "last_30_days": {
            "total_sessions": total_sessions,
            "total_hours": round(total_mins / 60, 2),
            "avg_session_minutes": avg_duration,
            "sessions_per_week": sessions_per_week,
            "days_studied": days_studied_30,
            "consistency_pct": consistency_pct,
        },
        "current_streak_days": streak,
        "ml_forecast": ml_summary,
    }


def get_study_sessions(uid, days=14, limit=20, **_):
    """Return recent study sessions."""
    db = _db()
    cutoff = (datetime.now() - timedelta(days=int(days))).strftime('%Y-%m-%d')
    items = []
    for doc in db.collection('study_records').where('uid', '==', uid).stream():
        d = doc.to_dict()
        if d.get('date', '') >= cutoff:
            items.append({
                "id": doc.id,
                "subject": d.get('subject', ''),
                "duration_minutes": d.get('duration_minutes', 0),
                "date": d.get('date', ''),
                "note": d.get('note', ''),
            })
    items.sort(key=lambda x: x.get('date', ''), reverse=True)
    return {"sessions": items[:int(limit)], "count": len(items[:int(limit)])}


def create_study_session(uid, subject, duration_minutes, date, note="", **_):
    """Log a study session."""
    if float(duration_minutes) <= 0:
        return {"error": "duration_minutes must be positive."}
    return _create_doc('study_records', uid, {
        "subject": subject,
        "duration_minutes": float(duration_minutes),
        "date": date,
        "note": note,
    })


def update_study_session(uid, doc_id, subject=None, duration_minutes=None, date=None, note=None, **_):
    """Update a study session."""
    data = {}
    if subject is not None:
        data['subject'] = subject
    if duration_minutes is not None:
        data['duration_minutes'] = float(duration_minutes)
    if date is not None:
        data['date'] = date
    if note is not None:
        data['note'] = note
    if not data:
        return {"error": "No fields to update."}
    return _update_doc('study_records', doc_id, uid, data)


def delete_study_session(uid, doc_id, **_):
    """Delete a study session."""
    return _delete_doc('study_records', doc_id, uid)


# ──────────────────────────────────────────────────────────────────────────────
# HABITS
# ──────────────────────────────────────────────────────────────────────────────

def get_habit_analysis(uid, **_):
    """
    Return active habits with ML churn risk scores.
    Sorted by risk (highest first).
    """
    risks = get_all_habit_risks(uid)
    if risks is None:
        return {"error": "Habit ML model not available."}
    return {
        "habit_count": len(risks),
        "habits": risks,
        "high_risk_count": sum(1 for h in risks if h.get("risk_level") == "High"),
        "medium_risk_count": sum(1 for h in risks if h.get("risk_level") == "Medium"),
        "low_risk_count": sum(1 for h in risks if h.get("risk_level") == "Low"),
    }


def get_habits(uid, **_):
    """Return all habits (active and inactive)."""
    return {"habits": _list_col('habits', uid, limit=100)}


HABIT_CATEGORIES = ['health', 'wellness', 'productivity', 'learning', 'social', 'finance', 'business', 'other']
HABIT_FREQUENCIES = ['daily', 'weekly', 'monthly']


def normalize_habit_category(cat: str) -> str:
    c = (cat or "").strip().lower()
    if c in HABIT_CATEGORIES:
        return c
    if any(k in c for k in ("financ", "money", "sav", "invest", "budget", "wealth", "rupee")):
        return "finance"
    if any(k in c for k in ("business", "venture", "startup", "trade", "sales", "client")):
        return "business"
    if any(k in c for k in ("health", "fitness", "workout", "gym", "exercise", "walk", "run", "diet", "sleep")):
        return "health"
    if any(k in c for k in ("wellness", "meditat", "mindful", "mental", "peace")):
        return "wellness"
    if any(k in c for k in ("productiv", "work", "focus", "deep", "discipline", "routine")):
        return "productivity"
    if any(k in c for k in ("learn", "study", "read", "book", "course", "skill")):
        return "learning"
    if any(k in c for k in ("social", "family", "friend", "network")):
        return "social"
    return "other"


def create_habit(uid, name, category="other", frequency="daily", target_count=1, note="", **_):
    """Create a new habit with intelligent auto-normalization."""
    if not name or not str(name).strip():
        return {"error": "Habit name cannot be empty."}

    norm_cat = normalize_habit_category(category)
    freq = str(frequency).strip().lower()
    if freq not in HABIT_FREQUENCIES:
        freq = "daily"

    full_note = note or ""
    if norm_cat == "other" and category and category.lower() not in ("other", "finance", "business"):
        full_note = f"[{category.capitalize()}] {full_note}".strip()

    res = _create_doc('habits', uid, {
        "name": str(name).strip(),
        "category": norm_cat,
        "frequency": freq,
        "target_count": int(target_count or 1),
        "note": full_note,
        "is_active": True,
        "current_streak": 0,
    })
    if res.get("success"):
        return {
            "success": True,
            "id": res.get("id"),
            "name": str(name).strip(),
            "category": norm_cat,
            "frequency": freq,
            "message": f"Successfully created habit '{name}' in category '{norm_cat}' ({freq})."
        }
    return res


GOAL_CATEGORIES = ['financial', 'finance', 'academic', 'learning', 'fitness', 'personal', 'career', 'health']


def normalize_goal_category(cat: str) -> str:
    c = (cat or "").strip().lower()
    if c in GOAL_CATEGORIES:
        return c
    if any(k in c for k in ("financ", "money", "sav", "invest", "budget", "wealth")):
        return "financial"
    if any(k in c for k in ("academ", "grade", "gpa", "exam", "score")):
        return "academic"
    if any(k in c for k in ("learn", "study", "read", "course", "skill")):
        return "learning"
    if any(k in c for k in ("fit", "gym", "health", "weight", "run")):
        return "fitness"
    if any(k in c for k in ("career", "job", "work", "promot", "intern")):
        return "career"
    return "personal"


def create_goal(uid, title, target_amount=None, category="financial", target_date=None, note="", **_):
    """Create a new personal or financial goal."""
    if not title or not str(title).strip():
        return {"error": "Goal title cannot be empty."}

    norm_cat = normalize_goal_category(category)
    payload = {
        "title": str(title).strip(),
        "category": norm_cat,
        "status": "in-progress",
        "priority": "medium",
        "progress_percentage": 0.0,
        "current": 0.0,
        "target": float(target_amount or 0.0),
        "target_date": target_date or "",
        "notes": note or "",
    }
    res = _create_doc('goals', uid, payload)
    if res.get("success"):
        return {
            "success": True,
            "id": res.get("id"),
            "title": str(title).strip(),
            "category": norm_cat,
            "message": f"Successfully created goal '{title}' in category '{norm_cat}'."
        }
    return res


def update_habit(uid, doc_id, name=None, category=None, frequency=None,
                 is_active=None, note=None, **_):
    """Update a habit."""
    data = {}
    if name is not None:
        data['name'] = name
    if category is not None:
        data['category'] = normalize_habit_category(category)
    if frequency is not None:
        if frequency not in HABIT_FREQUENCIES:
            return {"error": f"Invalid frequency."}
        data['frequency'] = frequency
    if is_active is not None:
        data['is_active'] = bool(is_active)
    if note is not None:
        data['note'] = note
    if not data:
        return {"error": "No fields to update."}
    return _update_doc('habits', doc_id, uid, data)


def delete_habit(uid, doc_id, **_):
    """Delete a habit."""
    return _delete_doc('habits', doc_id, uid)


def complete_habit(uid, habit_name=None, doc_id=None, **_):
    """
    Mark a habit as completed for today, increment its streak,
    and trigger the platform daily check-in (+XP, daily streak advancement).
    """
    from datetime import date, timedelta
    from app.services.streak_service import daily_checkin, get_streak_data
    from app.services.firebase_service import get_firestore_client
    from app.services.crud_service import invalidate_user_cache
    from app.services.activity_service import log_activity

    habits = _list_col('habits', uid, limit=100)
    if not habits:
        return {
            "status": "not_found",
            "error": "You don't have any habits recorded yet. You can ask me to track one (e.g. 'Track daily reading habit') first!"
        }

    target = None
    if doc_id:
        target = next((h for h in habits if h.get('id') == doc_id or h.get('doc_id') == doc_id), None)

    if not target and habit_name:
        clean_name = str(habit_name).strip().lower()
        # 1. Exact match
        target = next((h for h in habits if (h.get('name') or '').strip().lower() == clean_name), None)
        # 2. Substring match
        if not target:
            target = next((h for h in habits if clean_name in (h.get('name') or '').lower() or (h.get('name') or '').lower() in clean_name), None)
        # 3. Word token overlap match
        if not target:
            stopwords = {
                "this", "the", "my", "habit", "habits", "today", "a", "an", "daily",
                "i", "have", "completed", "complete", "completd", "finish", "finished",
                "did", "done", "of", "with", "for", "marked", "mark", "that", "and"
            }
            tokens = set(re.findall(r'\w+', clean_name)) - stopwords
            if tokens:
                for h in habits:
                    h_tokens = set(re.findall(r'\w+', (h.get('name') or '').lower()))
                    if tokens & h_tokens:
                        target = h
                        break
        # 4. Fuzzy word matching with difflib (e.g. 'bok' -> 'book')
        if not target and tokens:
            import difflib
            for h in habits:
                h_tokens = set(re.findall(r'\w+', (h.get('name') or '').lower()))
                for t in tokens:
                    if difflib.get_close_matches(t, list(h_tokens), n=1, cutoff=0.6):
                        target = h
                        break
                if target:
                    break

        # 5. Category match
        if not target:
            for h in habits:
                if (h.get('category') or '').lower() in clean_name or clean_name in (h.get('category') or '').lower():
                    target = h
                    break

    # If no target identified yet:
    if not target:
        active = [h for h in habits if h.get('is_active', True) is not False]
        if len(active) == 1:
            target = active[0]
        elif len(habits) == 1:
            target = habits[0]
        else:
            active_list = active if active else habits
            return {
                "status": "needs_selection",
                "message": f"Which habit did you complete today? You have {len(active_list)} habits: " +
                           ", ".join([f"**{h.get('name')}**" for h in active_list[:5]]) + ".",
                "habits": [{"name": h.get("name"), "id": h.get("id")} for h in active_list]
            }

    today_iso = date.today().isoformat()
    yesterday_iso = (date.today() - timedelta(days=1)).isoformat()
    last_comp_str = str(target.get('last_completed') or '')[:10]
    cur_streak = int(target.get('current_streak', target.get('streak', 0)) or 0)
    db = get_firestore_client()

    already_done = (last_comp_str == today_iso)

    if already_done:
        new_streak = cur_streak
        streak_data = get_streak_data(uid, db)
        daily_st = streak_data.get('streak_count', 0)
        xp = streak_data.get('xp', 0)
        level_title = streak_data.get('level_title', 'Rookie')
        msg = f"You've already checked in for **{target.get('name')}** today! Your habit streak is safely maintained at **{cur_streak} days** (Daily platform streak: **{daily_st} days**)."
        milestone = None
    else:
        if last_comp_str == yesterday_iso or cur_streak == 0 or not last_comp_str or target.get('streak_protected'):
            new_streak = cur_streak + 1
        else:
            new_streak = 1

        updates = {
            "current_streak": new_streak,
            "streak": new_streak,
            "streak_count": new_streak,
            "last_completed": today_iso,
            "streak_protected": False,
            "status": "active"
        }
        _update_doc('habits', target.get('id'), uid, updates)

        # Trigger user's platform daily check-in
        streak_res = daily_checkin(uid, db)
        daily_st = streak_res.get('streak_count', 1)
        xp_gained = streak_res.get('xp_gained', 10)
        xp = streak_res.get('xp', 0)
        level_title = streak_res.get('level_title', 'Rookie')
        milestone = streak_res.get('milestone')

        log_activity(uid, f"Completed habit '{target.get('name')}' (Streak: {new_streak}d)", category="habit", impact="positive")
        invalidate_user_cache(uid)

        msg = (
            f"✅ Checked in **{target.get('name')}** for today! "
            f"Your habit streak is now **{new_streak} days** 🔥. "
            f"Your daily platform streak reached **{daily_st} days** (+{xp_gained} XP, Level: {level_title})!"
        )

    # Attach interactive check-in widget
    widget = {
        "type": "habit_checkin_card",
        "payload": {
            "title": "Habit Completed Today",
            "habit_name": target.get("name"),
            "category": target.get("category", "other"),
            "habit_streak": new_streak,
            "previous_streak": cur_streak,
            "daily_streak": daily_st,
            "xp_gained": 10 if not already_done else 0,
            "total_xp": xp,
            "level": level_title,
            "milestone": milestone,
            "already_completed": already_done,
            "completed_date": today_iso,
            "view_url": "/habits"
        }
    }

    return {
        "success": True,
        "habit_id": target.get("id"),
        "habit_name": target.get("name"),
        "habit_streak": new_streak,
        "daily_streak": daily_st,
        "already_completed": already_done,
        "total_xp": xp,
        "level": level_title,
        "message": msg,
        "_widgets": [widget]
    }


# ──────────────────────────────────────────────────────────────────────────────
# GOALS
# ──────────────────────────────────────────────────────────────────────────────

def get_goal_summary(uid, **_):
    """Return the user's goals with status and progress."""
    goals = _list_col('goals', uid, limit=50)
    active = [g for g in goals if g.get('status') not in ('completed', 'abandoned')]
    completed = [g for g in goals if g.get('status') == 'completed']
    return {
        "total_goals": len(goals),
        "active_goals": active,
        "completed_count": len(completed),
    }


# ──────────────────────────────────────────────────────────────────────────────
# ACTIVITY
# ──────────────────────────────────────────────────────────────────────────────

def get_activity_summary(uid, limit=15, **_):
    """Return recent activity history."""
    db = _db()
    query = db.collection('activity_history').where('uid', '==', uid).limit(int(limit))
    items = []
    for doc in query.stream():
        d = doc.to_dict()
        d['id'] = doc.id
        items.append(serialize_doc(d))
    return {"activities": items, "count": len(items)}


# ──────────────────────────────────────────────────────────────────────────────
# PRODUCTIVITY ANALYSIS
# ──────────────────────────────────────────────────────────────────────────────

def get_productivity_analysis(uid, **_):
    """
    Analyse study sessions by time-of-day and day-of-week
    to identify when the user is most productive.
    """
    db = _db()
    sessions = []
    for doc in db.collection('study_records').where('uid', '==', uid).stream():
        d = doc.to_dict()
        date_str = d.get('date', '')
        if date_str:
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d')
                sessions.append({
                    "dow": dt.weekday(),          # 0=Mon
                    "dow_name": dt.strftime('%A'),
                    "duration": float(d.get('duration_minutes', 0)),
                    "subject": d.get('subject', ''),
                })
            except Exception:
                pass

    if not sessions:
        return {"note": "Not enough study data to analyse productivity patterns."}

    # Day-of-week breakdown
    dow_totals = {}
    dow_counts = {}
    for s in sessions:
        name = s['dow_name']
        dow_totals[name] = dow_totals.get(name, 0) + s['duration']
        dow_counts[name] = dow_counts.get(name, 0) + 1

    day_analysis = []
    for name, total in dow_totals.items():
        count = dow_counts[name]
        day_analysis.append({
            "day": name,
            "total_minutes": round(total),
            "avg_minutes": round(total / count, 1),
            "sessions": count,
        })
    day_analysis.sort(key=lambda x: x['total_minutes'], reverse=True)

    # Subject breakdown
    subj_totals = {}
    for s in sessions:
        subj = s['subject'] or 'Unspecified'
        subj_totals[subj] = subj_totals.get(subj, 0) + s['duration']
    top_subjects = sorted(subj_totals.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "total_sessions_analysed": len(sessions),
        "by_day_of_week": day_analysis,
        "top_subjects": [{"subject": k, "total_minutes": round(v)} for k, v in top_subjects],
        "most_productive_day": day_analysis[0]["day"] if day_analysis else None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# HUGGING FACE / OPENAI-COMPATIBLE TOOL DECLARATIONS
# ──────────────────────────────────────────────────────────────────────────────

def get_hf_tools():
    """
    Return the list of tool definitions in OpenAI-compatible JSON schema format
    for the Hugging Face InferenceClient. Each tool is a plain Python dict.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "get_user_profile",
                "description": "Retrieve the authenticated user's Quanta profile including name, age, and other attributes.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_financial_summary",
                "description": "Get an aggregated financial summary: total income, expenses, net balance, savings rate, and top expense categories for the specified period.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "description": "Number of days to look back (default 30)."},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_recent_transactions",
                "description": "Retrieve recent income and/or expense transactions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "days":  {"type": "integer", "description": "Days to look back (default 14)."},
                        "type":  {"type": "string",  "description": "'income', 'expenses', or 'all' (default 'all')."},
                        "limit": {"type": "integer", "description": "Max records to return (default 20)."},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_financial_forecast",
                "description": "Run Quanta's finance ML model to get the 30-day projected expenses, trend direction, and personalized insight.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_expense",
                "description": "Create a new expense record in the user's Quanta account.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "amount":   {"type": "number", "description": "Expense amount in INR."},
                        "category": {"type": "string", "description": "One of: food, transport, rent, utilities, entertainment, education, health, shopping, other."},
                        "date":     {"type": "string", "description": "Date in YYYY-MM-DD format."},
                        "note":     {"type": "string", "description": "Optional note or description."},
                    },
                    "required": ["amount", "category", "date"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_expense",
                "description": "Update an existing expense record. Requires the document ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "doc_id":   {"type": "string", "description": "The Firestore document ID of the expense to update."},
                        "amount":   {"type": "number", "description": "New amount in INR."},
                        "category": {"type": "string", "description": "New category."},
                        "date":     {"type": "string", "description": "New date YYYY-MM-DD."},
                        "note":     {"type": "string", "description": "New note."},
                    },
                    "required": ["doc_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_expense",
                "description": "Permanently delete an expense record. Only call after explicit user confirmation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "doc_id": {"type": "string", "description": "The Firestore document ID of the expense to delete."},
                    },
                    "required": ["doc_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_income",
                "description": "Create a new income record in the user's Quanta account.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "amount": {"type": "number", "description": "Income amount in INR."},
                        "source": {"type": "string", "description": "One of: salary, freelance, scholarship, allowance, gift, investment, other."},
                        "date":   {"type": "string", "description": "Date in YYYY-MM-DD format."},
                        "note":   {"type": "string", "description": "Optional note."},
                    },
                    "required": ["amount", "source", "date"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_income",
                "description": "Update an existing income record. Requires the document ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "doc_id": {"type": "string", "description": "Firestore document ID."},
                        "amount": {"type": "number", "description": "New amount."},
                        "source": {"type": "string", "description": "New source."},
                        "date":   {"type": "string", "description": "New date YYYY-MM-DD."},
                        "note":   {"type": "string", "description": "New note."},
                    },
                    "required": ["doc_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_income",
                "description": "Permanently delete an income record. Only call after explicit user confirmation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "doc_id": {"type": "string", "description": "Firestore document ID."},
                    },
                    "required": ["doc_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_study_analysis",
                "description": "Get study consistency metrics for the last 30 days plus the 7-day ML-predicted study hours and trend.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_study_sessions",
                "description": "Retrieve a list of recent study sessions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "days":  {"type": "integer", "description": "Days to look back (default 14)."},
                        "limit": {"type": "integer", "description": "Max sessions to return (default 20)."},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_study_session",
                "description": "Log a study session.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subject":          {"type": "string", "description": "Subject or topic studied."},
                        "duration_minutes": {"type": "number", "description": "Duration in minutes."},
                        "date":             {"type": "string", "description": "Date YYYY-MM-DD."},
                        "note":             {"type": "string", "description": "Optional note."},
                    },
                    "required": ["subject", "duration_minutes", "date"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_study_session",
                "description": "Update an existing study session.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "doc_id":           {"type": "string", "description": "Firestore document ID."},
                        "subject":          {"type": "string", "description": "New subject."},
                        "duration_minutes": {"type": "number", "description": "New duration in minutes."},
                        "date":             {"type": "string", "description": "New date YYYY-MM-DD."},
                        "note":             {"type": "string", "description": "New note."},
                    },
                    "required": ["doc_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_study_session",
                "description": "Permanently delete a study session. Only call after explicit user confirmation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "doc_id": {"type": "string", "description": "Firestore document ID."},
                    },
                    "required": ["doc_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_habit_analysis",
                "description": "Get all active habits with ML-calculated churn risk scores, current streaks, and personalized recommendations. Sorted by risk.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_habits",
                "description": "Retrieve all habits (active and inactive) without ML analysis.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_habit",
                "description": "Create a new habit.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name":      {"type": "string", "description": "Habit name."},
                        "category":  {"type": "string", "description": "One of: health, wellness, productivity, learning, social, other."},
                        "frequency": {"type": "string", "description": "daily, weekly, or monthly (default daily)."},
                        "note":      {"type": "string", "description": "Optional description."},
                    },
                    "required": ["name", "category"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_habit",
                "description": "Update an existing habit.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "doc_id":    {"type": "string",  "description": "Firestore document ID."},
                        "name":      {"type": "string",  "description": "New name."},
                        "category":  {"type": "string",  "description": "New category."},
                        "frequency": {"type": "string",  "description": "New frequency."},
                        "is_active": {"type": "boolean", "description": "Active status."},
                        "note":      {"type": "string",  "description": "New note."},
                    },
                    "required": ["doc_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_habit",
                "description": "Permanently delete a habit. Only call after explicit user confirmation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "doc_id": {"type": "string", "description": "Firestore document ID."},
                    },
                    "required": ["doc_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_goal_summary",
                "description": "Retrieve the user's financial and personal goals with their status and progress.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_activity_summary",
                "description": "Retrieve recent activity history (logs of user actions in Quanta).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max records (default 15)."},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_productivity_analysis",
                "description": "Analyse the user's study sessions by day of week and subject to identify peak productivity days and patterns.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
    ]


def dispatch_tool(tool_name: str, uid: str, args: dict) -> dict:
    """
    Execute a tool by name with the given arguments.
    All tools receive uid as the first argument to enforce data isolation.
    Returns the tool result as a plain dict.
    """
    fn = TOOL_FUNCTIONS.get(tool_name)
    if fn is None:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        result = fn(uid=uid, **args)
        return result if isinstance(result, dict) else {"result": result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": f"Tool '{tool_name}' failed: {str(e)}"}


TOOL_FUNCTIONS = {
    "get_user_profile":          get_user_profile,
    "get_financial_summary":     get_financial_summary,
    "get_recent_transactions":   get_recent_transactions,
    "get_financial_forecast":    get_financial_forecast,
    "create_expense":            create_expense,
    "update_expense":            update_expense,
    "delete_expense":            delete_expense,
    "create_savings":            create_savings,
    "update_savings":            update_savings,
    "delete_savings":            delete_savings,
    "create_income":             create_income,
    "update_income":             update_income,
    "delete_income":             delete_income,
    "get_study_analysis":        get_study_analysis,
    "get_study_sessions":        get_study_sessions,
    "create_study_session":      create_study_session,
    "update_study_session":      update_study_session,
    "delete_study_session":      delete_study_session,
    "get_habit_analysis":        get_habit_analysis,
    "get_habits":                get_habits,
    "create_habit":              create_habit,
    "update_habit":              update_habit,
    "delete_habit":              delete_habit,
    "complete_habit":            complete_habit,
    "create_goal":               create_goal,
    "get_goal_summary":          get_goal_summary,
    "get_activity_summary":      get_activity_summary,
    "get_productivity_analysis": get_productivity_analysis,
}
