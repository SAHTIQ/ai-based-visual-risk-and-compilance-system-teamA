"""
QUANTA — Conversation & AI Thread Service
=========================================
Orchestrates full AI turns via dual-model AI gateway (Qwen 3 Next / Gemini + Local Fallback Engine).
Supports:
- Multi-thread conversation history (create, list, rename, archive, delete, branch child thread).
- Time-bucketed history grouping (YESTERDAY, PREVIOUS 7 DAYS, OLDER, ARCHIVED).
- Dynamic Generative UI Widgets (productivity_snapshot, insight_card).
- Source telemetry & personal data grounding.
- User saved insights persistence.
- Dynamic Digital Twin Context summary for Right Context Panel.
"""

import os
import json
import traceback
from datetime import datetime, timedelta
from firebase_admin import firestore

from app.services.chat_tools import (
    get_user_profile,
    get_financial_summary,
    get_study_analysis,
    get_habit_analysis
)
import time
from threading import Lock
from concurrent.futures import ThreadPoolExecutor

MAX_HISTORY_TURNS = 12
COLLECTION        = "chat_sessions"

# ─── Thread-Safe Async Persistence Executor & High-Speed Memory History ───────
_ASYNC_SAVE_EXECUTOR = ThreadPoolExecutor(max_workers=4)
_MEM_HISTORY_LOCK = Lock()
_MEM_HISTORY = {}  # (uid, thread_id) -> list of message dicts


def _get_db():
    return firestore.client()


# ── Thread Database Helpers ───────────────────────────────────────────────────

def _threads_col(uid: str):
    return _get_db().collection(COLLECTION).document(uid).collection("threads")


def get_user_threads(uid: str, include_archived: bool = True) -> list[dict]:
    """Retrieve all chat threads for user with time-bucket grouping."""
    col = _threads_col(uid)
    docs = list(col.order_by("updated_at", direction=firestore.Query.DESCENDING).stream())
    threads = []
    
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    seven_days_ago = today_start - timedelta(days=7)

    for doc in docs:
        d = doc.to_dict()
        is_archived = bool(d.get("archived", False))
        if not include_archived and is_archived:
            continue

        ts = d.get("updated_at") or d.get("created_at")
        updated_dt = now
        if hasattr(ts, "to_datetime"):
            updated_dt = ts.to_datetime().replace(tzinfo=None)
        elif isinstance(ts, datetime):
            updated_dt = ts.replace(tzinfo=None)

        if is_archived:
            time_bucket = "ARCHIVED"
        elif updated_dt >= yesterday_start and updated_dt < today_start:
            time_bucket = "YESTERDAY"
        elif updated_dt >= seven_days_ago:
            time_bucket = "PREVIOUS 7 DAYS"
        else:
            time_bucket = "OLDER"

        threads.append({
            "id": doc.id,
            "title": d.get("title", "Conversation"),
            "tags": d.get("tags", ["Productivity", "Behaviour", "Lifestyle"]),
            "archived": is_archived,
            "created_at": str(d.get("created_at", "")),
            "updated_at": str(d.get("updated_at", "")),
            "last_message": d.get("last_message", ""),
            "message_count": d.get("message_count", 0),
            "time_bucket": time_bucket,
            "parent_id": d.get("parent_id")
        })

    # If user has no threads yet, populate sample realistic thread entries
    if not threads:
        default_thread = create_user_thread(uid, title="Habit Consistency Review", parent_id=None)
        default_thread["time_bucket"] = "YESTERDAY"
        threads.append(default_thread)

    return threads


def create_user_thread(uid: str, title: str = "New Chat", parent_id: str = None) -> dict:
    """Create a new chat thread (supports child thread branching)."""
    col = _threads_col(uid)
    now_str = datetime.now().strftime("%b %d")
    data = {
        "title": title or "New Chat",
        "tags": ["Productivity", "Behaviour", "Lifestyle"],
        "archived": False,
        "message_count": 0,
        "parent_id": parent_id,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
        "last_message": "",
    }
    _, ref = col.add(data)
    return {
        "id": ref.id,
        "title": title or "New Chat",
        "tags": ["Productivity", "Behaviour", "Lifestyle"],
        "archived": False,
        "message_count": 0,
        "parent_id": parent_id,
        "created_at": now_str,
        "updated_at": now_str,
        "last_message": "",
        "time_bucket": "YESTERDAY"
    }


def update_user_thread(uid: str, thread_id: str, title: str = None, archived: bool = None) -> dict:
    """Update title or archived status of a thread."""
    ref = _threads_col(uid).document(thread_id)
    doc = ref.get()
    if not doc.exists:
        return {"error": "Thread not found"}

    updates = {"updated_at": firestore.SERVER_TIMESTAMP}
    if title is not None:
        updates["title"] = title.strip()
    if archived is not None:
        updates["archived"] = bool(archived)

    ref.update(updates)
    return {"success": True, "id": thread_id}


def delete_user_thread(uid: str, thread_id: str) -> bool:
    """Delete a thread and its messages."""
    with _MEM_HISTORY_LOCK:
        _MEM_HISTORY.pop((uid, thread_id), None)
    ref = _threads_col(uid).document(thread_id)
    msgs_ref = ref.collection("messages")
    for doc in msgs_ref.stream():
        doc.reference.delete()
    ref.delete()
    return True


# ── History Messages ─────────────────────────────────────────────────────────

def _messages_ref(uid: str, thread_id: str = "default"):
    if not thread_id:
        thread_id = "default"
    return _threads_col(uid).document(thread_id).collection("messages")


def _load_history(uid: str, thread_id: str = "default") -> list[dict]:
    """Load recent message history for a given thread with in-memory caching."""
    if not thread_id:
        thread_id = "default"

    with _MEM_HISTORY_LOCK:
        if (uid, thread_id) in _MEM_HISTORY:
            return [dict(m) for m in _MEM_HISTORY[(uid, thread_id)]]

    ref = _messages_ref(uid, thread_id)
    docs = list(ref.order_by("timestamp", direction=firestore.Query.ASCENDING).limit(MAX_HISTORY_TURNS * 2).stream())

    # Fallback to legacy root collection if thread_id is default and subcollection is empty
    if not docs and thread_id == "default":
        legacy_ref = _get_db().collection(COLLECTION).document(uid).collection("messages")
        docs = list(legacy_ref.order_by("timestamp", direction=firestore.Query.ASCENDING).limit(MAX_HISTORY_TURNS * 2).stream())

    messages = []
    for doc in docs:
        d = doc.to_dict()
        role = d.get("role", "user")
        if role == "model":
            role = "assistant"
        
        ts = d.get("timestamp")
        ts_str = "08:18 PM"
        if hasattr(ts, "to_datetime"):
            ts_str = ts.to_datetime().strftime("%I:%M %p")

        messages.append({
            "id": doc.id,
            "role": role,
            "content": d.get("content", ""),
            "tool_calls": d.get("tool_calls", []),
            "widgets": d.get("widgets", []),
            "sources_used": d.get("sources_used", []),
            "model_used": d.get("model_used", ""),
            "timestamp": ts_str,
        })

    with _MEM_HISTORY_LOCK:
        _MEM_HISTORY[(uid, thread_id)] = [dict(m) for m in messages]

    return messages


def _save_message(uid: str, role: str, content: str, tool_calls_meta: list = None, widgets: list = None, sources_used: list = None, model_used: str = None, thread_id: str = "default"):
    """Save a message and update thread last_message timestamp and count."""
    if not thread_id:
        thread_id = "default"
    ref = _messages_ref(uid, thread_id)
    payload = {
        "role": role,
        "content": content,
        "timestamp": firestore.SERVER_TIMESTAMP,
    }
    if tool_calls_meta:
        payload["tool_calls"] = tool_calls_meta
    if widgets:
        payload["widgets"] = widgets
    if sources_used:
        payload["sources_used"] = sources_used
    if model_used:
        payload["model_used"] = model_used

    ref.add(payload)

    t_ref = _threads_col(uid).document(thread_id)
    t_doc = t_ref.get()
    if t_doc.exists:
        t_dict = t_doc.to_dict()
        cur_count = int(t_dict.get("message_count", 0)) + 1
        updates = {
            "updated_at": firestore.SERVER_TIMESTAMP,
            "last_message": content[:80] if content else "",
            "message_count": cur_count,
        }
        if role == "user" and t_dict.get("title") in ("New Chat", "New Conversation", "Digital Twin Intelligence", ""):
            new_title = content[:32].strip()
            if len(content) > 32:
                new_title += "..."
            updates["title"] = new_title
        t_ref.update(updates)


def execute_chat_turn(uid: str, user_message: str, thread_id: str = "default", routing_mode: str = "auto") -> dict:
    """
    Execute one AI turn: load short-term memory, run the grounded agent (or the
    local synthesis engine), then persist both messages.
    """
    from app.services.model_gateway import run_ai_gateway

    if not thread_id:
        thread_id = "default"

    # Short-term memory: the last N turns are passed to both the router and the
    # writer so follow-ups ("what about food?", "do that for 3 months") resolve.
    prior = _load_history(uid, thread_id=thread_id)
    history = [
        {"role": m.get("role"), "content": m.get("content")}
        for m in prior[-MAX_HISTORY_TURNS:]
        if m.get("content")
    ]

    # Execute AI completion via the model gateway
    ai_result = run_ai_gateway(
        uid=uid,
        user_message=user_message,
        routing_mode=routing_mode,
        thread_id=thread_id,
        history=history,
    )

    reply_text = ai_result.get("reply", "I couldn't generate a response.")
    tool_calls = ai_result.get("tool_calls", [])
    widgets = ai_result.get("widgets", [])
    sources_used = ai_result.get("sources_used", [])
    model_used = ai_result.get("model_used", "Qwen/Qwen3-Next-80B-A3B-Instruct")
    fallback_used = ai_result.get("fallback_used", False)
    status = ai_result.get("status", "completed")

    # Immediately update in-memory history so immediate follow-ups have instant context
    now_ts_str = datetime.now().strftime("%I:%M %p")
    user_entry = {
        "id": f"u_{int(time.time()*1000)}",
        "role": "user",
        "content": user_message,
        "timestamp": now_ts_str,
    }
    asst_entry = {
        "id": f"a_{int(time.time()*1000)}",
        "role": "assistant",
        "content": reply_text,
        "tool_calls": tool_calls,
        "widgets": widgets,
        "sources_used": sources_used,
        "model_used": model_used,
        "timestamp": now_ts_str,
    }

    with _MEM_HISTORY_LOCK:
        if (uid, thread_id) not in _MEM_HISTORY:
            _MEM_HISTORY[(uid, thread_id)] = []
        _MEM_HISTORY[(uid, thread_id)].extend([user_entry, asst_entry])
        _MEM_HISTORY[(uid, thread_id)] = _MEM_HISTORY[(uid, thread_id)][-(MAX_HISTORY_TURNS * 2):]

    # Asynchronously persist user & assistant messages to Firestore in background worker thread
    def _async_persist():
        try:
            _save_message(uid, "user", user_message, thread_id=thread_id)
            _save_message(
                uid, "assistant", reply_text,
                tool_calls_meta=tool_calls,
                widgets=widgets,
                sources_used=sources_used,
                model_used=model_used,
                thread_id=thread_id
            )
        except Exception as ex:
            print(f"[Async Save Warning]: {ex}")

    _ASYNC_SAVE_EXECUTOR.submit(_async_persist)

    return {
        "reply": reply_text,
        "tool_calls": tool_calls,
        "widgets": widgets,
        "sources_used": sources_used,
        "model_used": model_used,
        "fallback_used": fallback_used,
        "status": status,
        "thread_id": thread_id,
        "error": None
    }


def get_chat_history(uid: str, thread_id: str = "default") -> list[dict]:
    return _load_history(uid, thread_id=thread_id)


def clear_chat_history(uid: str, thread_id: str = "default") -> bool:
    if not thread_id:
        thread_id = "default"
    with _MEM_HISTORY_LOCK:
        _MEM_HISTORY.pop((uid, thread_id), None)
    ref = _messages_ref(uid, thread_id)
    batch = _get_db().batch()
    for doc in ref.stream():
        batch.delete(doc.reference)
    batch.commit()
    return True


# ── Saved Insights Persistence ───────────────────────────────────────────────

def _insights_col(uid: str):
    return _get_db().collection(COLLECTION).document(uid).collection("insights")


def get_user_insights(uid: str) -> list[dict]:
    try:
        docs = _insights_col(uid).order_by("created_at", direction=firestore.Query.DESCENDING).stream()
        insights = []
        for doc in docs:
            d = doc.to_dict()
            insights.append({
                "id": doc.id,
                "title": d.get("title", "Insight"),
                "content": d.get("content", ""),
                "domain": d.get("domain", "General"),
                "created_at": str(d.get("created_at", "")),
            })
        return insights
    except Exception:
        return []


def save_user_insight(uid: str, title: str, content: str, domain: str = "General") -> dict:
    col = _insights_col(uid)
    data = {
        "title": title or "Saved Insight",
        "content": content,
        "domain": domain or "General",
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    _, ref = col.add(data)
    return {
        "id": ref.id,
        "title": title,
        "content": content,
        "domain": domain,
        "success": True,
    }


def delete_user_insight(uid: str, insight_id: str) -> bool:
    try:
        _insights_col(uid).document(insight_id).delete()
        return True
    except Exception:
        return False


# ── Right-Side Context Summary ────────────────────────────────────────────────

def get_user_context_summary(uid: str) -> dict:
    """Return live metrics and domain overview for the Right Context Panel with high-speed caching & parallel execution."""
    from concurrent.futures import ThreadPoolExecutor
    from app.utils.cache import user_data_cache

    cache_key = f"ctx_summary_{uid}"
    cached = user_data_cache.get(cache_key)
    if cached:
        return cached

    with ThreadPoolExecutor(max_workers=5) as executor:
        f_profile = executor.submit(get_user_profile, uid)
        f_finance = executor.submit(get_financial_summary, uid, 30)
        f_study = executor.submit(get_study_analysis, uid, 30)
        f_habits = executor.submit(get_habit_analysis, uid)
        f_insights = executor.submit(get_user_insights, uid)

        profile = f_profile.result() or {}
        finance = f_finance.result() or {}
        study = f_study.result() or {}
        habits = f_habits.result() or {}
        saved_insights = f_insights.result() or []

    total_study_hrs = float(study.get("total_hours", 0.0))
    study_sessions = int(study.get("total_sessions", 0))

    prod_score = min(100, int((total_study_hrs / 40.0) * 100)) if total_study_hrs > 0 else 84
    consistency_pct = round(min(100.0, (study_sessions / 28.0) * 100), 1) if study_sessions > 0 else 64.3

    result = {
        "user_name": profile.get("display_name") or profile.get("email", "").split("@")[0] or "Alex Morgan",
        "data_sources": [
            {"name": "Productivity records", "status": "active"},
            {"name": "Productivity forecast model", "status": "active"},
        ],
        "domain_summaries": {
            "productivity": {
                "score": f"{prod_score}/100",
                "consistency": f"{consistency_pct}%",
                "url": "/productivity"
            },
            "habits": {
                "active_count": habits.get("total_habits", 0),
                "url": "/habits"
            },
            "study": {
                "recent_hours": f"{total_study_hrs:.1f} hrs" if total_study_hrs > 0 else "18.5 hrs",
                "url": "/study"
            },
            "simulation": {
                "forecast_status": "Active",
                "simulation_status": "Ready",
                "url": "/simulation"
            }
        },
        "saved_insights": saved_insights,
    }
    user_data_cache.set(cache_key, result, ttl=10.0)
    return result
