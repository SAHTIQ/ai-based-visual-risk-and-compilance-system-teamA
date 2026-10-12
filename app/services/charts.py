"""
QUANTA — Chart & Generative-UI Spec Builders
============================================
Pure functions that turn real tool output into compact, renderable widget specs.
The LLM NEVER produces chart data — every number here comes from Firestore or
the ML service. The client (``chat.js``) switches on ``widget["type"]``.

Widget types produced:
  line_chart          history + ML forecast series (finance / study)
  bar_chart           category or day-of-week breakdown
  habit_risk          churn-risk bars per habit
  goal_progress       progress bars per goal
  fan_chart           Monte Carlo percentile fan (p5..p95)
  productivity_snapshot  KPI card (existing contract)
  insight_card        highlighted insight (existing contract)
"""


# ──────────────────────────────────────────────────────────────────────────────
# Line chart — history + forecast
# ──────────────────────────────────────────────────────────────────────────────

def build_line_chart(*, title, history, forecast, kind="currency", insight=None,
                     view_url="/dashboard"):
    """
    Build a line-chart spec joining a historical series to a forecast series.

    Args:
        history: list[{date, amount}] actual values (chronological).
        forecast: list[{date, amount}] projected values (chronological).
    """
    history = history or []
    forecast = forecast or []
    if not history and not forecast:
        return None

    return {
        "type": "line_chart",
        "payload": {
            "title": title,
            "kind": kind,                      # currency | minutes | hours | count
            "history": history[-60:],
            "forecast": forecast[:30],
            "insight": insight,
            "view_url": view_url,
        },
    }


def finance_line_chart(finance_result):
    """Line chart for the 30-day expense projection."""
    if not finance_result:
        return None
    return build_line_chart(
        title="30-day expense forecast",
        history=finance_result.get("history") or [],
        forecast=finance_result.get("forecast") or [],
        kind="currency",
        insight=finance_result.get("insight"),
        view_url="/expenses",
    )


def study_line_chart(study_result):
    """Line chart for the 7-day study-hours projection."""
    if not study_result:
        return None
    return build_line_chart(
        title="7-day study forecast",
        history=study_result.get("history") or [],
        forecast=study_result.get("forecast") or [],
        kind="minutes",
        insight=study_result.get("insight"),
        view_url="/study",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Bar chart — category / weekday breakdown
# ──────────────────────────────────────────────────────────────────────────────

def build_bar_chart(*, title, labels, values, kind="currency", view_url="/dashboard"):
    """Build a horizontal bar-chart spec from parallel label/value lists."""
    pairs = [
        (str(label), float(value))
        for label, value in zip(labels or [], values or [])
        if value is not None
    ]
    if not pairs:
        return None
    pairs.sort(key=lambda item: item[1], reverse=True)
    return {
        "type": "bar_chart",
        "payload": {
            "title": title,
            "kind": kind,
            "labels": [p[0] for p in pairs][:8],
            "values": [round(p[1], 2) for p in pairs][:8],
            "view_url": view_url,
        },
    }


def expense_breakdown_chart(breakdown, title="Spending by category"):
    """Bar chart from ``finance_summary['top_expense_categories']``."""
    if not breakdown:
        return None
    labels = [row.get("category", "other") for row in breakdown]
    values = [row.get("amount", 0) for row in breakdown]
    return build_bar_chart(
        title=title, labels=labels, values=values,
        kind="currency", view_url="/expenses",
    )


def ml_category_chart(category_breakdown, title="Spending by category (30d)"):
    """Bar chart from the ML service ``category_breakdown`` list."""
    if not category_breakdown:
        return None
    labels = [row.get("category", "other") for row in category_breakdown]
    values = [row.get("total", 0) for row in category_breakdown]
    return build_bar_chart(
        title=title, labels=labels, values=values,
        kind="currency", view_url="/expenses",
    )


def productivity_day_chart(day_analysis, title="Study minutes by weekday"):
    """Bar chart from ``get_productivity_analysis['by_day_of_week']``."""
    if not day_analysis:
        return None
    labels = [row.get("day", "") for row in day_analysis]
    values = [row.get("total_minutes", 0) for row in day_analysis]
    return build_bar_chart(
        title=title, labels=labels, values=values,
        kind="minutes", view_url="/study",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Habit churn risk
# ──────────────────────────────────────────────────────────────────────────────

def habit_risk_chart(risks, title="Habit churn risk"):
    """Bar chart of churn probability per active habit (highest risk first)."""
    if not risks:
        return None
    habits = [
        {
            "name": row.get("name", "Habit"),
            "churn_probability": round(float(row.get("churn_probability", 0)) * 100, 1),
            "risk_level": row.get("risk_level", "Low"),
            "current_streak": int(row.get("current_streak", 0)),
        }
        for row in risks
    ]
    return {
        "type": "habit_risk",
        "payload": {"title": title, "habits": habits[:8], "view_url": "/habits"},
    }


# ──────────────────────────────────────────────────────────────────────────────
# Goal progress
# ──────────────────────────────────────────────────────────────────────────────

def goal_progress_widget(goals, title="Goal progress"):
    """Progress bars for the user's active goals."""
    if not goals:
        return None
    items = []
    for goal in goals[:8]:
        items.append({
            "title": goal.get("title") or goal.get("name") or "Goal",
            "progress_percentage": round(float(goal.get("progress_percentage", 0) or 0), 1),
            "status": goal.get("status", "active"),
            "target_date": str(goal.get("target_date") or ""),
        })
    if not items:
        return None
    return {
        "type": "goal_progress",
        "payload": {"title": title, "goals": items, "view_url": "/goals"},
    }


# ──────────────────────────────────────────────────────────────────────────────
# Monte Carlo fan
# ──────────────────────────────────────────────────────────────────────────────

def cashflow_fan_widget(mc_result, title="Balance projection (Monte Carlo)"):
    """Percentile fan chart from ``FinanceSimulator.run_monte_carlo`` output."""
    if not mc_result or not mc_result.get("dates"):
        return None
    return {
        "type": "fan_chart",
        "payload": {
            "title": title,
            "dates": mc_result.get("dates", [])[:90],
            "p5": [round(float(v), 2) for v in mc_result.get("p5", [])[:90]],
            "p25": [round(float(v), 2) for v in mc_result.get("p25", [])[:90]],
            "p50": [round(float(v), 2) for v in mc_result.get("p50", [])[:90]],
            "p75": [round(float(v), 2) for v in mc_result.get("p75", [])[:90]],
            "p95": [round(float(v), 2) for v in mc_result.get("p95", [])[:90]],
            "prob_shortfall": round(float(mc_result.get("prob_shortfall", 0)) * 100, 1),
            "view_url": "/simulation",
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# Productivity snapshot (existing contract, computed from real data)
# ──────────────────────────────────────────────────────────────────────────────

def productivity_snapshot(*, focus_hours, focus_days, sessions, avg_streak=0,
                          peak_day=None, view_url="/dashboard"):
    """
    KPI card backed entirely by measured values — no fabricated percentages.
    """
    score = min(100, int((focus_hours / 40.0) * 60 + (avg_streak / 30.0) * 40))
    consistency = round(min(100.0, (focus_days / 30.0) * 100), 1)
    return {
        "type": "productivity_snapshot",
        "payload": {
            "title": "Productivity snapshot",
            "trend_text": f"{sessions} sessions logged",
            "score": score,
            "focus_time_hrs": round(focus_hours, 1),
            "focus_label": "deep work (30d)",
            "consistency_pct": consistency,
            "consistency_label": f"{focus_days} of 30 days",
            "peak_window": peak_day or "Not enough data",
            "view_url": view_url,
        },
    }


def insight_card(*, heading, why_it_matters, view_url="/dashboard"):
    """Highlighted insight card."""
    if not heading:
        return None
    return {
        "type": "insight_card",
        "payload": {
            "heading": heading,
            "why_it_matters": why_it_matters or "",
            "view_url": view_url,
        },
    }
