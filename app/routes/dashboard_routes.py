from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth
from app.services.crud_service import get_user_collection_docs
from app.utils.serializers import serialize_docs

dashboard_bp = Blueprint('dashboard_bp', __name__, url_prefix='/api/dashboard')

@dashboard_bp.route('/summary', methods=['GET'])
@require_auth
def get_summary():
    try:
        from datetime import datetime
        from concurrent.futures import ThreadPoolExecutor
        today = datetime.now()
        cur_month = today.strftime('%Y-%m')

        user_uid = g.uid

        def fetch_col(col_name, target_uid):
            try:
                return get_user_collection_docs(col_name, target_uid)
            except Exception as ex:
                print(f"[Dashboard Summary Warning] Failed fetching {col_name}: {ex}")
                return []

        cols = ['income', 'expenses', 'savings', 'study_records', 'goals', 'habits', 'fitness_records']
        docs_map = {}

        with ThreadPoolExecutor(max_workers=7) as executor:
            future_to_col = {executor.submit(fetch_col, c, user_uid): c for c in cols}
            for future in future_to_col:
                col_name = future_to_col[future]
                docs_map[col_name] = future.result()

        income_docs = docs_map.get('income', [])
        total_income = sum(doc.get('amount', 0) for doc in income_docs)
        income_month = sum(doc.get('amount', 0) for doc in income_docs if str(doc.get('date', '')).startswith(cur_month))

        expense_docs = docs_map.get('expenses', [])
        total_expenses = sum(doc.get('amount', 0) for doc in expense_docs)
        expenses_month = sum(doc.get('amount', 0) for doc in expense_docs if str(doc.get('date', '')).startswith(cur_month))

        net_savings = total_income - total_expenses
        net_savings_month = income_month - expenses_month

        savings_docs = docs_map.get('savings', [])
        total_savings = sum(doc.get('amount', 0) for doc in savings_docs)

        study_docs = docs_map.get('study_records', [])
        study_hours_total = sum(doc.get('duration_minutes', 0) for doc in study_docs) / 60.0
        study_hours_month = sum(doc.get('duration_minutes', 0) for doc in study_docs if str(doc.get('date', '')).startswith(cur_month)) / 60.0

        goal_docs = docs_map.get('goals', [])
        total_goals = len(goal_docs)
        active_goals = sum(1 for doc in goal_docs if doc.get('status') not in ['completed', 'abandoned'])
        completed_goals = sum(1 for doc in goal_docs if doc.get('status') == 'completed')

        habit_docs = docs_map.get('habits', [])
        active_habits = sum(1 for doc in habit_docs if doc.get('is_active', True))

        fitness_docs = docs_map.get('fitness_records', [])
        fitness_sessions_total = len(fitness_docs)
        fitness_sessions_month = sum(1 for doc in fitness_docs if str(doc.get('date', '')).startswith(cur_month))

        health_data = _compute_health_score_and_briefing(docs_map, cur_month)

        return jsonify({
            "success": True,
            "data": {
                "total_income": total_income,
                "income_month": income_month,
                "total_expenses": total_expenses,
                "expenses_month": expenses_month,
                "net_savings": net_savings,
                "net_savings_month": net_savings_month,
                "total_savings": total_savings,
                "study_hours": study_hours_total,
                "study_hours_month": study_hours_month,
                "total_goals": total_goals,
                "active_goals": active_goals,
                "completed_goals": completed_goals,
                "active_habits": active_habits,
                "fitness_sessions": fitness_sessions_total,
                "fitness_sessions_month": fitness_sessions_month,
                "health_score": health_data,
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def _compute_health_score_and_briefing(docs_map, cur_month):
    income_docs = docs_map.get('income', [])
    expense_docs = docs_map.get('expenses', [])
    habit_docs = docs_map.get('habits', [])
    study_docs = docs_map.get('study_records', [])
    goal_docs = docs_map.get('goals', [])
    fitness_docs = docs_map.get('fitness_records', [])

    total_records = len(income_docs) + len(expense_docs) + len(habit_docs) + len(study_docs) + len(goal_docs) + len(fitness_docs)

    # 1. Finance Score (0-25)
    inc_m = sum(d.get('amount', 0) for d in income_docs if str(d.get('date', '')).startswith(cur_month))
    exp_m = sum(d.get('amount', 0) for d in expense_docs if str(d.get('date', '')).startswith(cur_month))
    if inc_m > 0:
        savings_ratio = max(0.0, (inc_m - exp_m) / inc_m)
        fin_score = min(25, int(savings_ratio * 25))
    elif exp_m > 0:
        fin_score = 5
    else:
        fin_score = 0  # No financial records logged

    # 2. Habit Score (0-25)
    active_habits = [h for h in habit_docs if h.get('is_active', True)]
    if active_habits:
        avg_streak = sum(h.get('current_streak', h.get('streak', h.get('streak_count', 0))) for h in active_habits) / len(active_habits)
        habit_score = min(25, int(10 + min(15, avg_streak * 2.5)))
    else:
        habit_score = 0  # No active habits created

    # 3. Study Score (0-25)
    study_m = sum(d.get('duration_minutes', 0) for d in study_docs if str(d.get('date', '')).startswith(cur_month)) / 60.0
    study_score = min(25, int((study_m / 15.0) * 25)) if study_m > 0 else 0  # No study logged

    # 4. Goals & Fitness Score (0-25)
    tot_goals = len(goal_docs)
    comp_goals = sum(1 for g in goal_docs if g.get('status') == 'completed')
    fit_m = sum(1 for f in fitness_docs if str(f.get('date', '')).startswith(cur_month))

    goal_pts = (comp_goals / max(1, tot_goals)) * 15 if tot_goals > 0 else 0
    fit_pts = min(10, fit_m * 2.5) if fit_m > 0 else 0
    life_score = min(25, int(goal_pts + fit_pts))

    overall_score = min(100, max(0, fin_score + habit_score + study_score + life_score))

    if total_records == 0 or overall_score == 0:
        label = "New Digital Twin — Setup Needed"
        badge = "info"
    elif overall_score >= 85:
        label = "Optimal Twin State"
        badge = "success"
    elif overall_score >= 70:
        label = "Strong Progress"
        badge = "primary"
    elif overall_score >= 40:
        label = "Moderate Equilibrium"
        badge = "warning"
    else:
        label = "Needs Focus & Shielding"
        badge = "danger"

    # Morning Briefing Bullets
    briefing = []
    if inc_m > 0 and exp_m <= inc_m:
        sav_pct = round(((inc_m - exp_m) / inc_m) * 100, 1)
        briefing.append(f"💰 Financial Twin: Savings rate is at {sav_pct}% for this month. Target allocation maintained.")
    elif exp_m > inc_m and inc_m > 0:
        briefing.append(f"⚠️ Financial Alert: Monthly expenses exceeded income by ₹{int(exp_m - inc_m)}. Review non-essential spending.")
    elif exp_m > 0:
        briefing.append(f"💸 Financial Twin: Monthly expenses logged: ₹{int(exp_m)}. Add your income to unlock savings intelligence.")
    else:
        briefing.append("💡 Financial Twin: Record your income and expenses to unlock budget intelligence.")

    at_risk = [h for h in active_habits if h.get('risk_score', 0) > 0.4 or h.get('status') == 'at_risk']
    if at_risk:
        briefing.append(f"🛡️ Actionable Shield: {len(at_risk)} habit(s) flagged for potential churn today. Activate Habit Shield to preserve streak.")
    elif active_habits:
        briefing.append(f"⚡ Habit Momentum: You have {len(active_habits)} active habit streak(s) running cleanly.")
    else:
        briefing.append("🌱 Habit Twin: Create a daily habit to begin building your consistency shield.")

    if study_m > 0 or fit_m > 0:
        briefing.append(f"🎯 Productivity & Vitality: {study_m:.1f} hrs focused study and {fit_m} fitness session(s) logged this month.")
    else:
        briefing.append("📚 Daily Focus: Log a study session or workout today to boost your Health Score by up to +25 pts.")

    return {
        "score": overall_score,
        "label": label,
        "badge": badge,
        "breakdown": {
            "finance": fin_score,
            "habits": habit_score,
            "study": study_score,
            "goals_fitness": life_score
        },
        "morning_briefing": briefing
    }

@dashboard_bp.route('/expense-breakdown', methods=['GET'])
@require_auth
def expense_breakdown():
    try:
        docs = get_user_collection_docs('expenses', g.uid)
        breakdown = {}
        for doc in docs:
            cat = doc.get('category', 'other')
            breakdown[cat] = breakdown.get(cat, 0) + doc.get('amount', 0)
            
        return jsonify({"success": True, "data": breakdown})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@dashboard_bp.route('/income-trend', methods=['GET'])
@require_auth
def income_trend():
    try:
        docs = get_user_collection_docs('income', g.uid)
        trend = {}
        for doc in docs:
            date = str(doc.get('date', ''))[:7] # YYYY-MM
            if date:
                trend[date] = trend.get(date, 0) + doc.get('amount', 0)
                
        return jsonify({"success": True, "data": trend})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@dashboard_bp.route('/study-trend', methods=['GET'])
@require_auth
def study_trend():
    try:
        docs = get_user_collection_docs('study_records', g.uid)
        trend = {}
        for doc in docs:
            date = str(doc.get('date', ''))[:7] # YYYY-MM
            if date:
                trend[date] = trend.get(date, 0) + (doc.get('duration_minutes', 0) / 60.0)
                
        return jsonify({"success": True, "data": trend})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@dashboard_bp.route('/recent-activity', methods=['GET'])
@require_auth
def recent_activity():
    try:
        docs = get_user_collection_docs('activity_history', g.uid)
        docs.sort(key=lambda x: str(x.get('created_at', '')), reverse=True)
        return jsonify({"success": True, "data": serialize_docs(docs[:10])})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
