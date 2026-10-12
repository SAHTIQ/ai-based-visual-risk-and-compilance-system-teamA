"""
QUANTA — Grounded Tool-Using Agent
==================================
Implements the reference chatbot architecture:

    1. PLAN   — a fast router model picks which data tools to run and returns
                ``{"tools": [{"name": ..., "args": {...}}]}``.
    2. EXECUTE — the selected tools read the user's *real* Firestore records and
                the ML service. Numbers come from the database, never the model.
    3. COMPOSE — a writer model turns the tool results (JSON) into a friendly
                answer, instructed to use ONLY the numbers it was given.

Chart specs are produced by the tools themselves (``_chart`` / ``_widgets``),
never by the LLM. If the router fails, a sensible default tool set runs; if the
writer fails, a deterministic summary still returns the real numbers.
"""

import json
import os
import re
import requests

from app.services import charts
from app.services import chat_tools as ct
from app.services.llm_client import (
    chat_complete, extract_json, llm_enabled, resolve_config,
)
from app.services.ml_service import forecast_finance, forecast_study, get_all_habit_risks

MAX_TOOLS_PER_TURN = 3
MAX_WIDGETS_PER_TURN = 3
MAX_HISTORY_MESSAGES = 6

# Human-readable data sources reported to the client (traceability).
SOURCE_LABELS = {
    "get_financial_summary": "Financial records",
    "get_financial_forecast": "Expense ML projection model",
    "get_expense_breakdown": "Expense categorisation",
    "get_recent_transactions": "Transaction ledger",
    "get_study_analysis": "Study records",
    "get_study_forecast": "Study forecast model",
    "get_productivity_analysis": "Weekly productivity analysis",
    "get_habit_analysis": "Habit churn model",
    "get_goal_summary": "Goal tracker",
    "get_activity_summary": "Activity history",
    "get_user_profile": "User profile",
    "run_finance_simulation": "Monte Carlo simulation engine",
    "web_search": "Live Web Search",
    "create_expense": "Expense ledger (write)",
    "create_income": "Income ledger (write)",
    "create_savings": "Savings ledger (write)",
    "create_study_session": "Study records (write)",
    "create_habit": "Habit tracker (write)",
    "create_goal": "Goal tracker (write)",
    "complete_habit": "Habit check-in & streak engine",
}

TOOLS = {}


def _tool(name, description, params, run, kind="read"):
    """Register a tool in the global registry."""
    TOOLS[name] = {
        "name": name,
        "description": description,
        "params": params or {},
        "run": run,
        "kind": kind,
    }


def _extract_internals(result):
    """
    Split a tool result into (compact_llm_view, widgets).

    Tools may attach ``_chart`` (single widget) or ``_widgets`` (list). These are
    removed from the view handed to the writer so prompts stay small.
    """
    if not isinstance(result, dict):
        return {"value": result}, []

    view = {k: v for k, v in result.items() if not k.startswith("_")}
    widgets = []
    if result.get("_chart"):
        widgets.append(result["_chart"])
    if result.get("_widgets"):
        widgets.extend(result["_widgets"])
    return view, [w for w in widgets if w]


def _summarize(view):
    """Build a short, human-readable badge summary from a tool result."""
    if not isinstance(view, dict):
        return "data retrieved"
    if view.get("error"):
        return f"error: {view['error']}"
    for key in ("status", "note", "insight"):
        if isinstance(view.get(key), str) and view[key]:
            return view[key][:90]
    scalar_bits = []
    for key, value in view.items():
        if isinstance(value, (int, float, str)) and not isinstance(value, bool):
            scalar_bits.append(f"{key}={value}")
        if len(scalar_bits) >= 3:
            break
    return ", ".join(scalar_bits) if scalar_bits else "data retrieved"


# ──────────────────────────────────────────────────────────────────────────────
# READ TOOLS
# ──────────────────────────────────────────────────────────────────────────────

def _run_financial_summary(uid, args):
    days = int(args.get("days", 30) or 30)
    summary = ct.get_financial_summary(uid, days=days)
    chart = charts.expense_breakdown_chart(summary.get("top_expense_categories"))
    if chart:
        summary["_chart"] = chart
    return summary


def _run_financial_forecast(uid, args):
    result = forecast_finance(uid)
    if not result:
        return {"status": "error", "note": "Finance ML model unavailable."}
    compact = {
        "projected_30d_expenses": result.get("projected_30d_expenses"),
        "current_monthly_income": result.get("current_monthly_income"),
        "expense_trend": result.get("expense_trend"),
        "top_categories": [
            {"category": c.get("category"), "total": c.get("total")}
            for c in (result.get("category_breakdown") or [])[:5]
        ],
        "insight": result.get("insight"),
    }
    line = charts.finance_line_chart(result)
    if line:
        compact["_chart"] = line
    return compact


def _run_expense_breakdown(uid, args):
    days = int(args.get("days", 30) or 30)
    summary = ct.get_financial_summary(uid, days=days)
    breakdown = summary.get("top_expense_categories") or []
    if not breakdown:
        return {"status": "insufficient_data",
                "note": "No expenses recorded in this period."}
    result = {
        "period_days": days,
        "total_expenses": summary.get("expenses"),
        "categories": breakdown,
    }
    chart = charts.expense_breakdown_chart(breakdown)
    if chart:
        result["_chart"] = chart
    return result


def _run_recent_transactions(uid, args):
    return ct.get_recent_transactions(
        uid,
        days=int(args.get("days", 14) or 14),
        type=args.get("type", "all") or "all",
        limit=int(args.get("limit", 15) or 15),
    )


def _run_study_analysis(uid, args):
    analysis = ct.get_study_analysis(uid)
    if analysis.get("error"):
        return analysis
    last30 = analysis.get("last_30_days", {})
    total_hours = float(last30.get("total_hours", 0) or 0)
    days_studied = int(last30.get("days_studied", 0) or 0)
    analysis["_widgets"] = [
        charts.productivity_snapshot(
            focus_hours=total_hours,
            focus_days=days_studied,
            sessions=int(last30.get("total_sessions", 0) or 0),
            peak_day=f"{last30.get('sessions_per_week', 0)} sessions/week",
            view_url="/study",
        )
    ]
    return analysis


def _run_study_forecast(uid, args):
    result = forecast_study(uid)
    if not result:
        return {"status": "error", "note": "Study ML model unavailable."}
    compact = {
        "projected_7d_hours": result.get("projected_7d_study_hrs"),
        "study_trend": result.get("study_trend"),
        "insight": result.get("insight"),
    }
    line = charts.study_line_chart(result)
    if line:
        compact["_chart"] = line
    return compact


def _run_productivity_analysis(uid, args):
    analysis = ct.get_productivity_analysis(uid)
    if analysis.get("note") or analysis.get("error"):
        return analysis
    chart = charts.productivity_day_chart(analysis.get("by_day_of_week"))
    if chart:
        analysis["_chart"] = chart
    return analysis


def _run_habit_analysis(uid, args):
    risks = get_all_habit_risks(uid)
    if risks is None:
        return {"status": "error", "note": "Habit churn model unavailable."}
    if not risks:
        return {"status": "insufficient_data",
                "note": "No active habits are being tracked yet."}
    result = {
        "habit_count": len(risks),
        "high_risk_count": sum(1 for h in risks if h.get("risk_level") == "High"),
        "habits": [
            {
                "name": h.get("name"),
                "risk_level": h.get("risk_level"),
                "churn_probability": h.get("churn_probability"),
                "current_streak": h.get("current_streak"),
                "recommendation": h.get("recommendation"),
            }
            for h in risks[:6]
        ],
    }
    chart = charts.habit_risk_chart(risks)
    if chart:
        result["_chart"] = chart
    return result


def _run_goal_summary(uid, args):
    summary = ct.get_goal_summary(uid)
    active = summary.get("active_goals") or []
    widget = charts.goal_progress_widget(active)
    if widget:
        summary["_chart"] = widget
    return summary


def _run_activity_summary(uid, args):
    return ct.get_activity_summary(uid, limit=int(args.get("limit", 12) or 12))


def _run_user_profile(uid, args):
    return ct.get_user_profile(uid)


def _run_finance_simulation(uid, args):
    scenario = args.get("scenario", "expected") or "expected"
    horizon = int(args.get("horizon_days", 90) or 90)
    try:
        from app.services.simulation_service import run_simulation
    except Exception as exc:  # e.g. scipy not installed
        return {"status": "error", "note": f"Simulation engine unavailable: {exc}"}
    try:
        sim = run_simulation(uid, scenario=scenario, horizon_days=horizon,
                             n_monte_carlo=400)
    except Exception as exc:
        return {"status": "error", "note": f"Simulation failed: {exc}"}

    finance = sim.get("finance", {})
    mc = finance.get("monte_carlo", {})
    cash = finance.get("cashflow", {})
    compact = {
        "scenario": scenario,
        "horizon_days": horizon,
        "projected_net_change": cash.get("net_change"),
        "prob_shortfall_pct": round(float(mc.get("prob_shortfall", 0)) * 100, 1),
        "prob_goal_achieved_pct": round(float(mc.get("prob_goal_achieved", 0)) * 100, 1),
    }
    widget = charts.cashflow_fan_widget(mc)
    if widget:
        compact["_chart"] = widget
    return compact


def _run_web_search(uid, args):
    query = (args.get("query") or "").strip()
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return {"status": "disabled", "note": "Live web search requires TAVILY_API_KEY in .env."}
    try:
        res = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "search_depth": "basic", "max_results": 3},
            timeout=10,
        )
        if res.status_code == 200:
            data = res.json()
            return {
                "query": query,
                "results": [
                    {"title": r.get("title"), "url": r.get("url"), "snippet": (r.get("content") or "")[:200]}
                    for r in data.get("results", [])[:3]
                ],
            }
        return {"status": "error", "note": f"Search provider returned HTTP {res.status_code}"}
    except Exception as exc:
        return {"status": "error", "note": f"Web search failed: {exc}"}

# ──────────────────────────────────────────────────────────────────────────────
# WRITE TOOLS (create records on the user's behalf)
# ──────────────────────────────────────────────────────────────────────────────

def _run_create_expense(uid, args):
    return ct.create_expense(
        uid,
        amount=args.get("amount"),
        category=args.get("category"),
        date=args.get("date"),
        note=args.get("note", ""),
    )


def _run_create_income(uid, args):
    return ct.create_income(
        uid,
        amount=args.get("amount"),
        source=args.get("source"),
        date=args.get("date"),
        note=args.get("note", ""),
    )


def _run_create_study_session(uid, args):
    return ct.create_study_session(
        uid,
        subject=args.get("subject"),
        duration_minutes=args.get("duration_minutes"),
        date=args.get("date"),
        note=args.get("note", ""),
    )


def _run_create_habit(uid, args):
    return ct.create_habit(
        uid,
        name=args.get("name"),
        category=args.get("category", "other"),
        frequency=args.get("frequency", "daily"),
        target_count=args.get("target_count", 1),
        note=args.get("note", ""),
    )


def _run_complete_habit(uid, args):
    return ct.complete_habit(
        uid,
        habit_name=args.get("habit_name"),
        doc_id=args.get("doc_id"),
    )


def _run_create_savings(uid, args):
    return ct.create_savings(
        uid,
        amount=args.get("amount"),
        type=args.get("type", "investment"),
        date=args.get("date"),
        target_amount=args.get("target_amount"),
        note=args.get("note", ""),
    )


def _run_create_goal(uid, args):
    return ct.create_goal(
        uid,
        title=args.get("title"),
        target_amount=args.get("target_amount"),
        category=args.get("category", "financial"),
        target_date=args.get("target_date"),
        note=args.get("note", ""),
    )


# ──────────────────────────────────────────────────────────────────────────────
# TOOL REGISTRATION
# ──────────────────────────────────────────────────────────────────────────────

_tool(
    "get_financial_summary",
    "Total income, expenses, net balance, savings rate and top spending categories "
    "for a period. Use for 'how much did I spend', 'what is my savings rate'.",
    {"days": "int, look-back window (default 30)"},
    _run_financial_summary,
)
_tool(
    "get_financial_forecast",
    "ML projection of the next 30 days of expenses with a trend and a chart. "
    "Use for 'what will I spend', 'forecast my spending'.",
    {},
    _run_financial_forecast,
)
_tool(
    "get_expense_breakdown",
    "Spending grouped by category for a period, with a bar chart.",
    {"days": "int, look-back window (default 30)"},
    _run_expense_breakdown,
)
_tool(
    "get_recent_transactions",
    "List the most recent income and/or expense transactions.",
    {"days": "int", "type": "'income'|'expenses'|'all'", "limit": "int"},
    _run_recent_transactions,
)
_tool(
    "get_study_analysis",
    "Study consistency over 30 days: total hours, sessions, streak, consistency %.",
    {},
    _run_study_analysis,
)
_tool(
    "get_study_forecast",
    "ML forecast of study hours for the next 7 days with a trend and chart.",
    {},
    _run_study_forecast,
)
_tool(
    "get_productivity_analysis",
    "Study patterns by weekday and subject to find the most productive day.",
    {},
    _run_productivity_analysis,
)
_tool(
    "get_habit_analysis",
    "Active habits with ML churn-risk scores, streaks and recommendations.",
    {},
    _run_habit_analysis,
)
_tool(
    "get_goal_summary",
    "The user's goals with status and progress percentage.",
    {},
    _run_goal_summary,
)
_tool(
    "get_activity_summary",
    "Recent user activity history inside Quanta.",
    {"limit": "int"},
    _run_activity_summary,
)
_tool(
    "get_user_profile",
    "The user's profile (name, occupation and other attributes).",
    {},
    _run_user_profile,
)
_tool(
    "run_finance_simulation",
    "Monte Carlo financial scenario simulation (probability of shortfall, net change).",
    {"scenario": "'current'|'expected'|'best'|'risk'", "horizon_days": "int"},
    _run_finance_simulation,
)
_tool(
    "web_search",
    "Live external web search for real-world facts, benchmarks, or definitions outside user records.",
    {"query": "string search query"},
    _run_web_search,
)
_tool(
    "create_expense",
    "Log a new expense. Only call when the user explicitly asks to record one.",
    {"amount": "number", "category": "string", "date": "YYYY-MM-DD", "note": "string"},
    _run_create_expense,
    kind="write",
)
_tool(
    "create_income",
    "Log a new income entry. Only when the user explicitly asks to record one.",
    {"amount": "number", "source": "string", "date": "YYYY-MM-DD", "note": "string"},
    _run_create_income,
    kind="write",
)
_tool(
    "create_study_session",
    "Log a study session. Only when the user explicitly asks to record one.",
    {"subject": "string", "duration_minutes": "number", "date": "YYYY-MM-DD"},
    _run_create_study_session,
    kind="write",
)
_tool(
    "create_habit",
    "Create a new habit or routine (including financial, business, health, productivity). Use when the user asks to start/track/add a habit.",
    {"name": "string", "category": "'health'|'wellness'|'productivity'|'learning'|'social'|'finance'|'business'|'other'", "frequency": "'daily'|'weekly'|'monthly'"},
    _run_create_habit,
    kind="write",
)
_tool(
    "create_savings",
    "Record a new savings, deposit, investment, or emergency fund entry. Use when user says 'add to savings', 'save X', 'invest X in business/stocks/funds'.",
    {"amount": "number", "type": "'bank'|'investment'|'emergency'|'crypto'|'retirement'|'other'", "date": "YYYY-MM-DD", "note": "string"},
    _run_create_savings,
    kind="write",
)
_tool(
    "create_goal",
    "Create a new personal or financial goal. Use when the user asks to set a target or goal.",
    {"title": "string", "category": "'financial'|'academic'|'fitness'|'career'|'personal'", "target_amount": "number", "target_date": "YYYY-MM-DD"},
    _run_create_goal,
    kind="write",
)
_tool(
    "complete_habit",
    "Mark a habit as completed for today (check off habit) and advance the user's daily platform streak (+XP). "
    "Use when user says 'I have completed this habit', 'done with my workout/reading/habit today', 'mark my habit completed', 'finished my habit', etc.",
    {"habit_name": "string (name or keywords of the habit, e.g. 'reading', 'workout', or empty to infer)"},
    _run_complete_habit,
    kind="write",
)


def tool_catalog():
    """Render the registered tools as a compact catalogue for the router prompt."""
    lines = []
    for name, spec in TOOLS.items():
        param_txt = ", ".join(f"{k} ({v})" for k, v in spec["params"].items()) or "no args"
        lines.append(f"- {name}({param_txt}): {spec['description']}")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# PROMPTS
# ──────────────────────────────────────────────────────────────────────────────

PLANNER_SYSTEM = """You are the ROUTER for a personal "Digital Twin" assistant.
Decide which data tools must run to answer the user's question or fulfill the user's request. You do NOT answer
the question yourself — you only choose tools.

Available tools:
{CATALOG}

Rules:
- Output ONLY minified JSON: {{"tools":[{{"name":"<tool>","args":{{}}}}]}}
- Choose at most {MAX} tools. Prefer the single most relevant tool.
- Use "write" tools whenever the user asks to add, record, create, track, complete, or save something:
  * To mark a habit as done, finished, or completed for today -> call "complete_habit" (extract habit_name if mentioned)
  * To save money, log savings, or record an investment -> call "create_savings"
  * To track a habit (including business or financial habits) -> call "create_habit"
  * To log an expense/spending -> call "create_expense"
  * To log income/earnings -> call "create_income"
  * To set a goal/target -> call "create_goal"
  * To log study time -> call "create_study_session"
- Extract amounts (numbers only), names, categories, and notes directly from the user request.
- Never invent a tool name that is not listed in Available tools.
- For greetings or general questions with no data need, return {{"tools":[]}}."""


COMPOSER_SYSTEM = """You are QUANTA's assistant — a warm, concise personal analyst.
You are given TOOL RESULTS (JSON) containing the outcome of data actions and queries.

Rules:
- When a write tool succeeds (returns "success": true):
  * For complete_habit: enthusiastically celebrate their consistency! State the habit name, the new habit streak (e.g. 🔥 **3 days**), the updated daily platform streak, and XP gained (+10 XP). Highlight that their daily streak is safe and advancing.
  * For other creations: confirm the creation warmly and state the exact recorded values (amount, name, category, date).
- If a write tool returns an error or asks for selection, guide the user politely.
- Use ONLY values present in TOOL RESULTS. Never invent or estimate numbers.
- Currency is Indian Rupees (INR / Rs.); format large numbers readably (e.g. Rs. 20,000, Rs. 300,000).
- Be conversational and specific; reference the user's real figures.
- Use short markdown: **bold** for key numbers, "-" bullets for lists.
- If a result has status "insufficient_data" or "error", say plainly that there isn't enough recorded data yet and suggest what to log. Do not fabricate.
- Predictions are probabilities/chances, not certainties.
- At most one sentence may be general advice, prefixed "General tip:".
- Resolve pronouns ("it", "those", "this habit") using the conversation history.
- Keep the whole answer under ~180 words unless the user asks for detail."""


# ──────────────────────────────────────────────────────────────────────────────
# PLANNING
# ──────────────────────────────────────────────────────────────────────────────

def _sanitize_history(history):
    """Keep only valid recent user/assistant turns."""
    cleaned = []
    for msg in (history or []):
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            cleaned.append({"role": role, "content": content.strip()})
    return cleaned[-MAX_HISTORY_MESSAGES:]


_GREETING_MAP = {
    "greeting": "Hello! I'm QUANTA, your personal Digital Twin analyst. I'm connected to your live financial records, habits, study sessions, and forecasting models. How can I help you today?",
    "thanks": "You're very welcome! Let me know anytime you want to check your progress, log new entries, or run simulations.",
    "identity": "I am QUANTA — your AI Digital Twin. I track and analyze your real personal data across finances, habits, productivity, and fitness to deliver grounded predictions and behavioral insights.",
}

def maybe_quick_reply(question):
    """Instant 0ms response for simple conversational greetings and pleasantries."""
    q = (question or "").strip()
    if re.match(r"^(hi|hello|hey|greetings|good morning|good afternoon|good evening|yo)\b[!.? ]*$", q, re.I):
        return {"reply": _GREETING_MAP["greeting"], "tool_calls": [], "widgets": [], "sources_used": [], "model_used": "quanta-fast-path", "fallback_used": False, "status": "completed"}
    if re.match(r"^(thank you|thanks|thx|appreciate it|awesome thanks|many thanks)\b.*", q, re.I):
        return {"reply": _GREETING_MAP["thanks"], "tool_calls": [], "widgets": [], "sources_used": [], "model_used": "quanta-fast-path", "fallback_used": False, "status": "completed"}
    if re.match(r"^(who are you|what are you|what is quanta)\??$", q, re.I):
        return {"reply": _GREETING_MAP["identity"], "tool_calls": [], "widgets": [], "sources_used": [], "model_used": "quanta-fast-path", "fallback_used": False, "status": "completed"}
    return None


def _plan(question, history):
    """Ask the router model which tools to run. Returns a validated list."""
    cfg = resolve_config()
    raw = chat_complete(
        [
            {"role": "system",
             "content": PLANNER_SYSTEM.format(CATALOG=tool_catalog(),
                                              MAX=MAX_TOOLS_PER_TURN)},
            *history,
            {"role": "user", "content": question},
        ],
        model=cfg["planner_model"],
        temperature=0.0,
        max_tokens=180,
        timeout=15,
    )
    plan = extract_json(raw)
    calls = plan.get("tools") if isinstance(plan, dict) else None
    if not isinstance(calls, list):
        return []

    validated = []
    for call in calls:
        if not isinstance(call, dict):
            continue
        name = call.get("name")
        if not isinstance(name, str) or name not in TOOLS:
            continue
        args = call.get("args") if isinstance(call.get("args"), dict) else {}
        validated.append({"name": name, "args": args})
    return validated[:MAX_TOOLS_PER_TURN]


def _is_habit_completion_query(question):
    """Detect if the user is asking to complete or check in a habit (typo-tolerant)."""
    q = (question or "").lower().strip()
    has_completion = bool(re.search(r'\b(comp?l[eai]?t[ed]*|finish[ed]*|done|checked?|checked\s+in|check\s+off|did)\b', q))
    if not has_completion:
        return False
    has_habit_word = bool(re.search(r'\b(habit|habits|routine|streak|today|day|daily|box|reading|read|bok|book|walk|workout|gym|exercise|meditat|water|run|study)\b', q))
    return has_habit_word


def _default_calls(question):
    """Sensible grounded defaults when routing yields nothing usable."""
    q = (question or "").lower()
    if _is_habit_completion_query(question):
        return [{"name": "complete_habit", "args": {"habit_name": question}}]
    if any(w in q for w in ("save", "saving", "savings", "budget")):
        return [{"name": "get_financial_summary", "args": {"days": 30}},
                {"name": "get_goal_summary", "args": {}}]
    if any(w in q for w in ("habit", "routine", "streak")):
        return [{"name": "get_habit_analysis", "args": {}}]
    if any(w in q for w in ("study", "focus", "productiv", "learn")):
        return [{"name": "get_study_analysis", "args": {}},
                {"name": "get_study_forecast", "args": {}}]
    if any(w in q for w in ("spend", "expense", "money", "financ", "income")):
        return [{"name": "get_financial_summary", "args": {"days": 30}}]
    return [
        {"name": "get_study_analysis", "args": {}},
        {"name": "get_habit_analysis", "args": {}},
        {"name": "get_financial_summary", "args": {"days": 30}},
    ]
# ──────────────────────────────────────────────────────────────────────────────
# COMPOSING
# ──────────────────────────────────────────────────────────────────────────────

def _widget_types(widgets):
    return sorted({w.get("type") for w in widgets if isinstance(w, dict) and w.get("type")})


def _compose(question, results, history, widgets):
    """Ask the writer model to turn tool results into prose. Returns text or None."""
    chart_note = ""
    types = _widget_types(widgets)
    if types:
        chart_note = (
            f"\n\nA visual ({', '.join(types)}) is shown beneath your answer. "
            "Refer to it in one short sentence without inventing its values."
        )

    user_block = (
        f'Question: "{question}"\n\n'
        f"TOOL RESULTS (JSON):\n{json.dumps(results, default=str)}"
        f"{chart_note}\n\nWrite the answer now."
    )

    return chat_complete(
        [
            {"role": "system", "content": COMPOSER_SYSTEM},
            *history,
            {"role": "user", "content": user_block},
        ],
        temperature=0.3,
        max_tokens=450,
        timeout=25,
    )


def _deterministic_summary(results):
    """
    Grounded prose built directly from tool results — used when the writer model
    is unavailable. Contains only real values.
    """
    lines = []
    for entry in results:
        view = entry.get("result", {})
        tool = entry.get("tool", "data")
        if not isinstance(view, dict):
            continue

        if view.get("status") in ("error", "insufficient_data") or view.get("error"):
            note = view.get("note") or view.get("error") or "not enough recorded data"
            lines.append(f"- {tool}: {note}.")
            continue

        if "income" in view and "expenses" in view:
            lines.append(
                f"- Finances: income ₹{view.get('income', 0):,.0f}, "
                f"expenses ₹{view.get('expenses', 0):,.0f}, "
                f"net ₹{view.get('net', 0):,.0f}, "
                f"savings rate {view.get('savings_rate_pct', 0)}%."
            )
        elif "projected_30d_expenses" in view:
            lines.append(
                f"- Expense forecast: about ₹{view.get('projected_30d_expenses', 0):,.0f} "
                f"over 30 days (trend: {view.get('expense_trend', 'stable')})."
            )
        elif "projected_7d_hours" in view:
            lines.append(
                f"- Study forecast: about {view.get('projected_7d_hours', 0)} hours "
                f"over the next 7 days (trend: {view.get('study_trend', 'stable')})."
            )
        elif "last_30_days" in view:
            last30 = view.get("last_30_days", {})
            lines.append(
                f"- Study: {last30.get('total_hours', 0)} hours across "
                f"{last30.get('total_sessions', 0)} sessions "
                f"({last30.get('consistency_pct', 0)}% consistency)."
            )
        elif "habit_streak" in view:
            lines.append(
                f"- Checked in habit '{view.get('habit_name')}': habit streak is now {view.get('habit_streak')} days! "
                f"Daily platform streak: {view.get('daily_streak')} days (+{view.get('xp_gained', 10)} XP, Level: {view.get('level', 'Rookie')})."
            )
        elif "habits" in view:
            lines.append(
                f"- Habits: {view.get('habit_count', 0)} active, "
                f"{view.get('high_risk_count', 0)} at high churn risk."
            )
        elif "active_goals" in view:
            lines.append(
                f"- Goals: {len(view.get('active_goals', []))} active, "
                f"{view.get('completed_count', 0)} completed."
            )
        elif "prob_shortfall_pct" in view:
            lines.append(
                f"- Simulation ({view.get('scenario', 'expected')}): "
                f"{view.get('prob_shortfall_pct', 0)}% chance of a shortfall, "
                f"projected net change ₹{view.get('projected_net_change', 0):,.0f}."
            )
        else:
            lines.append(f"- {tool}: data retrieved.")

    header = "Here's what your recorded data shows:"
    return header + "\n" + "\n".join(lines) if lines else header


# ──────────────────────────────────────────────────────────────────────────────
# AGENT ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

_VAGUE_PATTERNS = [
    re.compile(r"^(how am i doing\??)$", re.IGNORECASE),
    re.compile(r"^(what should i focus on\??)$", re.IGNORECASE),
    re.compile(r"^(how can i improve\??)$", re.IGNORECASE),
    re.compile(r"^(give me (advice|insights?|recommendations?)\??)$", re.IGNORECASE),
    re.compile(r"^(where do i stand\??)$", re.IGNORECASE),
    re.compile(r"^(overview\??)$", re.IGNORECASE),
    re.compile(r"^(help me\??)$", re.IGNORECASE),
    re.compile(r"^(analyze me\??)$", re.IGNORECASE),
    re.compile(r"^(what can you do\??)$", re.IGNORECASE),
]


def maybe_clarify(question):
    """
    Catch broad/unfocused questions before tool routing and invite the user
    to disambiguate with 1-click domain pills (matching the reference specification).
    """
    q = (question or "").strip()
    for pat in _VAGUE_PATTERNS:
        if pat.search(q):
            return {
                "reply": (
                    "I can analyze several dimensions of your personal data. "
                    "Which area would you like me to inspect right now?"
                ),
                "widgets": [{
                    "type": "clarification_chips",
                    "payload": {
                        "title": "Select a domain to inspect",
                        "options": [
                            {
                                "icon": "bi-credit-card-fill text-primary",
                                "label": "Financial Health & Forecast",
                                "prompt": "Analyze my 30-day spending breakdown and net savings rate."
                            },
                            {
                                "icon": "bi-book-fill text-info",
                                "label": "Productivity & Study Trajectory",
                                "prompt": "What is my 7-day study prediction based on my historical momentum?"
                            },
                            {
                                "icon": "bi-check2-circle text-warning",
                                "label": "Habit Consistency & Churn Risk",
                                "prompt": "Which of my active habits are at high risk of churn?"
                            },
                            {
                                "icon": "bi-diagram-3-fill text-success",
                                "label": "Scenario Simulation Lab",
                                "prompt": "Simulate saving 15% more income over the next 6 months."
                            }
                        ]
                    }
                }],
                "tool_calls": [],
                "sources_used": [],
                "model_used": "quanta-clarification-router",
                "fallback_used": False,
                "status": "clarification_requested"
            }
    return None


def _run_tool(uid, name, args):
    """Execute a tool defensively — never let a tool crash the turn."""
    try:
        return TOOLS[name]["run"](uid, args or {})
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return {"status": "error", "note": f"{name} failed: {exc}"}


def agent_answer(uid, question, history=None):
    """
    Run the full plan → execute → compose pipeline.

    Returns a dict matching the chat contract (``reply``, ``tool_calls``,
    ``widgets``, ``sources_used``, ``model_used``, ``fallback_used``, ``status``)
    or ``None`` when the LLM is disabled and no chart could be produced (the
    caller then uses the deterministic fallback engine).
    """
    quick = maybe_quick_reply(question)
    if quick:
        return quick

    clarification = maybe_clarify(question)
    if clarification:
        return clarification

    if not llm_enabled():
        return None

    history = _sanitize_history(history)

    if _is_habit_completion_query(question):
        calls = [{"name": "complete_habit", "args": {"habit_name": question}}]
    else:
        calls = _plan(question, history)
        if not calls:
            calls = _default_calls(question)

    calls = [c for c in calls if c.get("name") in TOOLS][:MAX_TOOLS_PER_TURN]
    if not calls:
        calls = _default_calls(question)

    # Mutual exclusion: If complete_habit is called, drop get_habit_analysis so no contradictory churn widget is attached
    if any(c.get("name") == "complete_habit" for c in calls):
        calls = [c for c in calls if c.get("name") != "get_habit_analysis"]

    def _exec_single(call):
        n = call["name"]
        a = call.get("args", {})
        raw_res = _run_tool(uid, n, a)
        v, prod = _extract_internals(raw_res)
        return n, a, v, prod

    from concurrent.futures import ThreadPoolExecutor

    executed = []
    if len(calls) > 1:
        with ThreadPoolExecutor(max_workers=min(4, len(calls))) as executor:
            futures = [executor.submit(_exec_single, c) for c in calls]
            for f in futures:
                try:
                    executed.append(f.result())
                except Exception as ex:
                    print(f"[Tool Execution Exception]: {ex}")
    elif len(calls) == 1:
        executed = [_exec_single(calls[0])]

    results, widgets, tool_calls, sources = [], [], [], []
    for name, args, view, produced in executed:
        for widget in produced:
            if len(widgets) < MAX_WIDGETS_PER_TURN and widget not in widgets:
                widgets.append(widget)

        results.append({"tool": name, "args": args, "result": view})
        tool_calls.append({
            "tool": name,
            "args": args,
            "result_summary": _summarize(view),
        })
        label = SOURCE_LABELS.get(name)
        if label and label not in sources:
            sources.append(label)

    sources_used = [{"name": s, "status": "accessed"} for s in sources]
    model_used = resolve_config()["model"]

    content = _compose(question, results, history, widgets)

    if not content:
        if not widgets:
            return None
        return {
            "reply": _deterministic_summary(results),
            "tool_calls": tool_calls,
            "widgets": widgets,
            "sources_used": sources_used,
            "model_used": model_used,
            "fallback_used": True,
            "status": "completed_without_writer",
        }

    insufficient = any(
        isinstance(r.get("result"), dict)
        and r["result"].get("status") in ("insufficient_data", "error")
        for r in results
    )

    return {
        "reply": content,
        "tool_calls": tool_calls,
        "widgets": widgets,
        "sources_used": sources_used,
        "model_used": model_used,
        "fallback_used": False,
        "status": "insufficient_evidence" if insufficient else "completed",
    }


def get_agent_status():
    """One-line status for the boot log."""
    from app.services.llm_client import provider_info
    return f"Chat AI: {provider_info()} · tools={len(TOOLS)}"
