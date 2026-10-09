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
    return firestore.client()


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


def create_expense(uid, amount, category, date, note="", **_):
    """Create a new expense record."""
    if category not in EXPENSE_CATEGORIES:
        return {"error": f"Invalid category '{category}'. Valid: {EXPENSE_CATEGORIES}"}
    return _create_doc('expenses', uid, {
        "amount": float(amount), "category": category, "date": date, "note": note
    })


def update_expense(uid, doc_id, amount=None, category=None, date=None, note=None, **_):
    """Update an existing expense record."""
    data = {}
    if amount is not None:
        data['amount'] = float(amount)
    if category is not None:
        if category not in EXPENSE_CATEGORIES:
            return {"error": f"Invalid category '{category}'."}
        data['category'] = category
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


INCOME_SOURCES = ['salary', 'freelance', 'scholarship', 'allowance', 'gift', 'investment', 'other']


def create_income(uid, amount, source, date, note="", **_):
    """Create a new income record."""
    if source not in INCOME_SOURCES:
        return {"error": f"Invalid source '{source}'. Valid: {INCOME_SOURCES}"}
    return _create_doc('income', uid, {
        "amount": float(amount), "source": source, "date": date, "note": note
    })


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


HABIT_CATEGORIES = ['health', 'wellness', 'productivity', 'learning', 'social', 'other']
HABIT_FREQUENCIES = ['daily', 'weekly', 'monthly']


def create_habit(uid, name, category, frequency="daily", note="", **_):
    """Create a new habit."""
    if category not in HABIT_CATEGORIES:
        return {"error": f"Invalid category '{category}'. Valid: {HABIT_CATEGORIES}"}
    if frequency not in HABIT_FREQUENCIES:
        return {"error": f"Invalid frequency. Valid: {HABIT_FREQUENCIES}"}
    return _create_doc('habits', uid, {
        "name": name, "category": category,
        "frequency": frequency, "note": note,
        "is_active": True, "current_streak": 0,
    })


def update_habit(uid, doc_id, name=None, category=None, frequency=None,
                 is_active=None, note=None, **_):
    """Update a habit."""
    data = {}
    if name is not None:
        data['name'] = name
    if category is not None:
        if category not in HABIT_CATEGORIES:
            return {"error": f"Invalid category '{category}'."}
        data['category'] = category
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
    "get_goal_summary":          get_goal_summary,
    "get_activity_summary":      get_activity_summary,
    "get_productivity_analysis": get_productivity_analysis,
}
