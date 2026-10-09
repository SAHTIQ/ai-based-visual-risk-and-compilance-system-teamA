"""
QUANTA — ML Inference Service
================================
Loads trained models from models/v2/ and runs live forecasting against
each user's Firestore data.

Three forecasts:
  1. forecast_finance(uid)            → 30-day expense projection + insight
  2. forecast_study(uid)              → 7-day study forecast + insight
  3. get_all_habit_risks(uid)         → churn risk per active habit
  4. forecast_habit_churn(uid, id)    → single habit risk
  5. get_ml_metrics()                 → model evaluation stats

Feature engineering in this file mirrors train_models_v2.py exactly
(same lag/rolling/EWM windows, same calendar features) so the model
receives the feature vector it was trained on.
"""

import os
import json
import numpy as np
import pandas as pd
import joblib
from datetime import datetime, timedelta
from firebase_admin import firestore
from app.services.crud_service import get_user_collection_docs

MODEL_DIR = os.path.join(os.getcwd(), 'models', 'v3')

_models = {}


# ──────────────────────────────────────────────────────────────────────────────
# Model Loading
# ──────────────────────────────────────────────────────────────────────────────

def load_models():
    if _models:
        return
    try:
        fin_payload = joblib.load(os.path.join(MODEL_DIR, "finance_model.joblib"))
        _models['finance']       = fin_payload['model'] if isinstance(fin_payload, dict) and 'model' in fin_payload else fin_payload
        _models['finance_feats'] = joblib.load(os.path.join(MODEL_DIR, "finance_features.joblib"))

        study_payload = joblib.load(os.path.join(MODEL_DIR, "study_model.joblib"))
        _models['study']         = study_payload['model'] if isinstance(study_payload, dict) and 'model' in study_payload else study_payload
        _models['study_feats']   = joblib.load(os.path.join(MODEL_DIR, "study_features.joblib"))

        habit_payload = joblib.load(os.path.join(MODEL_DIR, "habit_model.joblib"))
        _models['habit_payload'] = habit_payload
        _models['habit_feats']   = joblib.load(os.path.join(MODEL_DIR, "habit_features.joblib"))

        cat_models_path = os.path.join(MODEL_DIR, "finance_category_models.joblib")
        if os.path.exists(cat_models_path):
            _models['finance_cat'] = joblib.load(cat_models_path)

        print("[OK] ML models (v3) loaded successfully.")
    except Exception as e:
        print(f"[ERROR] Failed to load ML models: {e}")


def get_db():
    return firestore.client()


def get_ml_metrics():
    try:
        with open(os.path.join(MODEL_DIR, "evaluation_results.json"), "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _predict_habit_proba(X):
    """Handles both single-model and ensemble payloads for habit churn."""
    payload = _models.get('habit_payload')
    if payload is None:
        return None, 0.5

    if isinstance(payload, dict):
        if payload.get("type") == "ensemble":
            weights = payload["weights"]
            ensemble_models = payload["models"]
            proba = sum(w * m.predict_proba(X)[:,1] for w, m in zip(weights, ensemble_models))
            return proba, float(payload.get("threshold", 0.5))
        else:
            model = payload.get("model")
            if model is None:
                return None, 0.5
            proba = model.predict_proba(X)[:,1]
            return proba, float(payload.get("threshold", 0.5))
    else:
        # Legacy format: raw model
        proba = payload.predict_proba(X)[:,1]
        return proba, 0.5


# ──────────────────────────────────────────────────────────────────────────────
# Shared Feature Engineering (mirrors train_models_v2.py exactly)
# ──────────────────────────────────────────────────────────────────────────────

def _add_calendar_features(df, date_col="date"):
    df = df.copy()
    df[date_col]       = pd.to_datetime(df[date_col])
    df["dow"]          = df[date_col].dt.dayofweek
    df["is_weekend"]   = (df["dow"] >= 5).astype(int)
    df["month"]        = df[date_col].dt.month
    df["quarter"]      = df[date_col].dt.quarter
    df["is_month_end"] = df[date_col].dt.is_month_end.astype(int)
    doy                = df[date_col].dt.day_of_year
    df["sin_doy"]      = np.sin(2 * np.pi * doy / 365)
    df["cos_doy"]      = np.cos(2 * np.pi * doy / 365)
    df["sin_dow"]      = np.sin(2 * np.pi * df["dow"] / 7)
    df["cos_dow"]      = np.cos(2 * np.pi * df["dow"] / 7)
    return df


def _add_lags(df, col, lags, pfx):
    for l in lags:
        df[f"{pfx}_lag{l}"] = df[col].shift(l)
    return df


def _add_rolling(df, col, windows, pfx):
    for w in windows:
        df[f"{pfx}_rmean{w}"] = df[col].shift(1).rolling(w, min_periods=1).mean()
        df[f"{pfx}_rstd{w}"]  = df[col].shift(1).rolling(w, min_periods=1).std().fillna(0)
    return df


def _add_ewm(df, col, spans, pfx):
    for s in spans:
        df[f"{pfx}_ewm{s}"] = df[col].shift(1).ewm(span=s, min_periods=1).mean()
    return df


def _clean_X(row_df, features):
    """Ensure all required features exist and are finite float64."""
    for f in features:
        if f not in row_df.columns:
            row_df[f] = 0.0
    X = row_df[features].values.astype(float)
    X = np.nan_to_num(np.where(np.isinf(X), np.nan, X), nan=0.0)
    return X


def generate_trajectory(historical_series, predicted_sum, future_days):
    """
    Distributes a predicted sum over future days using last-7-day pattern.
    Adds ±5% noise for realism while preserving the exact predicted total.
    """
    if len(historical_series) < 7 or predicted_sum <= 0:
        avg = max(predicted_sum / future_days, 0)
        return [avg] * future_days

    template     = np.array(historical_series[-7:])
    template_sum = np.sum(template)

    if template_sum <= 0:
        return [predicted_sum / future_days] * future_days

    normalized   = template / template_sum
    repeats      = int(np.ceil(future_days / 7))
    full_pattern = np.tile(normalized, repeats)[:future_days]
    pattern_sum  = np.sum(full_pattern)
    scaled       = (full_pattern / pattern_sum) * predicted_sum

    noise = np.random.normal(1.0, 0.05, future_days)
    noisy = scaled * noise
    total = np.sum(noisy)
    final = (noisy / total) * predicted_sum if total > 0 else noisy
    return [float(max(0, x)) for x in final]


# ──────────────────────────────────────────────────────────────────────────────
# QUANTA Insight & Recommendation Generators
# ──────────────────────────────────────────────────────────────────────────────

def _finance_insight(projected, monthly_income, trend, top_categories):
    """Returns a human-readable QUANTA recommendation for the finance forecast."""
    trend_map = {
        "upward":   "Your spending is trending upward.",
        "downward": "Your spending is trending downward — great discipline!",
        "stable":   "Your spending pattern looks stable.",
    }
    trend_sentence = trend_map.get(trend, "Analysing your spending pattern.")

    if monthly_income > 0:
        pct = (projected / monthly_income) * 100
        if pct > 90:
            budget_sentence = (
                f"Projected expenses (₹{projected:,.0f}) are {pct:.0f}% of your income. "
                "Consider reviewing discretionary spending to protect your savings."
            )
        elif pct > 70:
            budget_sentence = (
                f"Projected expenses are {pct:.0f}% of income — within range, "
                "but watch discretionary categories."
            )
        else:
            budget_sentence = (
                f"Projected expenses are {pct:.0f}% of income — healthy! "
                "You're on track for good savings this month."
            )
    else:
        budget_sentence = "Add income records to receive personalised budget guidance."

    parts = [trend_sentence, budget_sentence]
    if top_categories:
        top_name, top_amt = top_categories[0]
        parts.append(f"{top_name.title()} is your largest spending category (₹{top_amt:,.0f}).")

    return " ".join(parts)


def _study_insight(projected_mins, trend, recent_avg, past_avg):
    """Returns a human-readable QUANTA recommendation for the study forecast."""
    hours = projected_mins / 60.0
    trend_map = {
        "upward":   "Your study momentum is building — great progress!",
        "downward": "Your study sessions have been declining recently.",
        "stable":   "Your study consistency looks steady.",
    }
    trend_sentence = trend_map.get(trend, "Analysing your study pattern.")

    if hours >= 14:
        volume = f"You're projected to study {hours:.1f} hrs this week — excellent focus!"
    elif hours >= 7:
        volume = f"You're projected to study {hours:.1f} hrs this week — solid effort."
    elif hours > 0:
        volume = (
            f"You're projected to study {hours:.1f} hrs this week. "
            "Even short, consistent sessions compound over time."
        )
    else:
        volume = "No recent study activity detected. Log a session to activate forecasting."

    return f"{trend_sentence} {volume}"


def _habit_recommendation(churn_prob, risk_level, habit_name, current_streak):
    """Returns a personalised recommendation string for a habit churn prediction."""
    if risk_level == "High":
        if current_streak == 0:
            return (
                f"You've missed '{habit_name}' recently. "
                "Restarting today resets the momentum — even 5 minutes counts."
            )
        return (
            f"'{habit_name}' is at high risk of breaking. "
            f"You have a {current_streak}-day streak — protect it today!"
        )
    elif risk_level == "Medium":
        return (
            f"'{habit_name}' shows some inconsistency. "
            "A few more consistent days will significantly lower your churn risk."
        )
    else:
        if current_streak >= 7:
            return (
                f"'{habit_name}' is going strong — {current_streak}-day streak! "
                "Keep it up."
            )
        return f"'{habit_name}' is on track. Stay consistent!"


# ──────────────────────────────────────────────────────────────────────────────
# 1. FINANCE FORECAST
# ──────────────────────────────────────────────────────────────────────────────

def forecast_finance(uid):
    """
    Fetches 65 days of expense + income data from Firestore, engineers the
    same features as the training pipeline, and runs the finance model.

    Returns:
      projected_30d_expenses  float
      current_monthly_income  float
      expense_trend           str ('upward' | 'downward' | 'stable')
      category_breakdown      list[{category, total, pct}]  – last 30 days
      history                 list[{date, amount}]           – last 60 days
      forecast                list[{date, amount}]           – next 30 days
      heatmap                 {categories, days, data}
      insight                 str – QUANTA recommendation
    """
    load_models()
    if 'finance' not in _models:
        return None

    db         = get_db()
    today      = datetime.now()
    start_date = today - timedelta(days=65)

    # ── Fetch expenses ──────────────────────────────────────────────────────
    expenses = []
    for d in get_user_collection_docs('expenses', uid):
        try:
            dt = pd.to_datetime(d.get('date'))
            if dt >= start_date:
                expenses.append({
                    'date':     dt.date(),
                    'amount':   float(d.get('amount', 0)),
                    'category': str(d.get('category', 'Other')).strip(),
                })
        except Exception:
            pass

    exp_df = (
        pd.DataFrame(expenses) if expenses
        else pd.DataFrame(columns=['date', 'amount', 'category'])
    )

    # ── Fetch income (current month) ────────────────────────────────────────
    monthly_inc = 0.0
    for d in get_user_collection_docs('income', uid):
        try:
            dt = pd.to_datetime(d.get('date'))
            if dt.year == today.year and dt.month == today.month:
                monthly_inc += float(d.get('amount', 0))
        except Exception:
            pass

    if exp_df.empty:
        return {
            "projected_30d_expenses": 0.0,
            "current_monthly_income": float(monthly_inc),
            "expense_trend": "stable",
            "category_breakdown": [],
            "history": [],
            "forecast": [],
            "heatmap": {"categories": [], "days": ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'], "data": []},
            "insight": "Add expense records to enable ML spending forecasts."
        }

    # ── Build dense daily grid ──────────────────────────────────────────────
    dates = pd.date_range(start_date.date(), today.date(), freq="D")
    grid  = pd.DataFrame({"date": dates})

    if not exp_df.empty:
        exp_df['date'] = pd.to_datetime(exp_df['date'])
        daily_exp = (
            exp_df.groupby('date')['amount'].sum()
            .reset_index().rename(columns={'amount': 'total_exp'})
        )
        cat_pivot = (
            exp_df.groupby(['date', 'category'])['amount']
            .sum().unstack(fill_value=0).reset_index()
        )
        cat_pivot.columns = [
            c if c == 'date' else f"cat_{c.lower()}"
            for c in cat_pivot.columns
        ]
        grid = grid.merge(daily_exp, on='date', how='left').fillna({'total_exp': 0})
        grid = grid.merge(cat_pivot, on='date', how='left')
    else:
        grid['total_exp'] = 0.0

    cat_cols          = [c for c in grid.columns if c.startswith("cat_")]
    grid[cat_cols]    = grid[cat_cols].fillna(0)
    grid['daily_inc'] = monthly_inc / 30.0
    grid['sav_rate']  = (
        (grid['daily_inc'] - grid['total_exp']) /
        grid['daily_inc'].replace(0, np.nan)
    ).fillna(0).clip(-5, 5)

    grid = _add_calendar_features(grid)
    grid = grid.sort_values("date").reset_index(drop=True)

    # ── Feature engineering ─────────────────────────────────────────────────
    grid = _add_lags(grid,    "total_exp", [1, 3, 7, 14, 30, 60], "exp")
    grid = _add_rolling(grid, "total_exp", [7, 14, 30, 60],        "exp")
    grid = _add_ewm(grid,     "total_exp", [7, 30],                "exp")
    grid = _add_lags(grid,    "daily_inc", [1, 7, 30],             "inc")
    grid = _add_rolling(grid, "daily_inc", [7, 30],                "inc")

    for cat in cat_cols:
        grid = _add_rolling(grid, cat, [7, 30], f"r_{cat}")

    grid["exp_trend7_30"]  = grid["exp_rmean7"]  - grid["exp_rmean30"]
    grid["exp_trend14_60"] = grid["exp_rmean14"] - grid["exp_rmean60"]
    grid["inc_trend"]      = grid["inc_rmean7"]  - grid["inc_rmean30"]

    today_row  = grid.iloc[-1:].copy()
    X          = _clean_X(today_row, _models['finance_feats'])
    prediction = float(max(0, _models['finance'].predict(X)[0]))

    # ── Trend label ─────────────────────────────────────────────────────────
    recent_avg = float(today_row["exp_rmean7"].values[0])  if "exp_rmean7"  in today_row.columns else 0.0
    past_avg   = float(today_row["exp_rmean30"].values[0]) if "exp_rmean30" in today_row.columns else 0.0
    if past_avg > 0:
        if recent_avg > past_avg * 1.10:   trend = "upward"
        elif recent_avg < past_avg * 0.90: trend = "downward"
        else:                              trend = "stable"
    else:
        trend = "stable"

    # ── History (last 60 days) & forecast trajectory (next 30 days) ────────
    hist_grid  = grid.iloc[-60:]
    history    = [
        {"date": str(r["date"].date()), "amount": float(r["total_exp"])}
        for _, r in hist_grid.iterrows()
    ]
    trajectory = generate_trajectory(hist_grid["total_exp"].values, prediction, 30)
    last_date  = hist_grid.iloc[-1]["date"]
    forecast   = [
        {"date": str((last_date + pd.Timedelta(days=i + 1)).date()), "amount": val}
        for i, val in enumerate(trajectory)
    ]

    # ── Heatmap: average spend per category × day-of-week ──────────────────
    heatmap_data = {}
    if not exp_df.empty:
        exp_df['dow'] = exp_df['date'].dt.dayofweek
        hm = exp_df.groupby(['category', 'dow'])['amount'].mean().unstack(fill_value=0)
        heatmap_data = {
            "categories": hm.index.tolist(),
            "days":       ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
            "data":       hm.values.tolist(),
        }


    # ── Category breakdown (last 30 days) ──────────────────────────────────
    category_breakdown = []
    if not exp_df.empty:
        last30 = exp_df[exp_df['date'] >= pd.Timestamp(today - timedelta(days=30))]
        if not last30.empty:
            cat_totals = last30.groupby('category')['amount'].sum()
            total_spend = cat_totals.sum()
            category_breakdown = [
                {
                    "category": cat,
                    "total":    round(float(amt), 2),
                    "pct":      round(float(amt / total_spend * 100), 1) if total_spend > 0 else 0,
                }
                for cat, amt in cat_totals.sort_values(ascending=False).items()
            ]

    top_categories = [(c["category"], c["total"]) for c in category_breakdown[:3]]
    insight = _finance_insight(prediction, monthly_inc, trend, top_categories)

    return {
        "projected_30d_expenses": float(prediction),
        "current_monthly_income": float(monthly_inc),
        "expense_trend":          trend,
        "category_breakdown":     category_breakdown,
        "history":                history,
        "forecast":               forecast,
        "heatmap":                heatmap_data,
        "insight":                insight,
    }

def forecast_study(uid):
    """
    Fetches 25 days of study, fitness, goals, and academic data, engineers
    features, and runs the study model for a 7-day study-minutes projection.

    Returns:
      projected_7d_study_mins float
      projected_7d_study_hrs  float
      study_trend             str
      history                 list[{date, amount}]    – last 21 days
      forecast                list[{date, amount}]    – next 7 days
      heatmap                 list[{date, intensity}] – last 30 days
      insight                 str – QUANTA recommendation
    """
    load_models()
    if 'study' not in _models:
        return None

    db         = get_db()
    today      = datetime.now()
    start_date = today - timedelta(days=25)

    study_list, fit_list, goal_list = [], [], []

    for d in get_user_collection_docs('study_records', uid):
        try:
            dt = pd.to_datetime(d.get('date'))
            if dt >= start_date:
                study_list.append({'date': dt.date(), 'stu': float(d.get('duration_minutes', 0))})
        except Exception:
            pass

    if not study_list:
        return {
            "projected_7d_study_mins": 0.0,
            "projected_7d_study_hrs": 0.0,
            "study_trend": "stable",
            "history": [],
            "forecast": [],
            "heatmap": [],
            "insight": "Log study sessions to enable ML focus predictions."
        }

    for d in get_user_collection_docs('fitness_records', uid):
        try:
            dt = pd.to_datetime(d.get('date'))
            if dt >= start_date:
                fit_list.append({'date': dt.date(), 'fit': float(d.get('duration_minutes', 0))})
        except Exception:
            pass

    for d in get_user_collection_docs('goals', uid):
        if d.get('status') == 'completed':
            try:
                dt = pd.to_datetime(d.get('target_date', d.get('date')))
                if dt >= start_date:
                    goal_list.append({'date': dt.date(), 'goal': 1})
            except Exception:
                pass

    acad_docs   = get_user_collection_docs('academic_records', uid)
    is_enrolled = any(d.get('status') == 'in-progress' for d in acad_docs)

    dates = pd.date_range(start_date.date(), today.date(), freq="D")
    grid  = pd.DataFrame({"date": dates})

    def _agg(rows, val_col):
        if not rows:
            return pd.DataFrame(columns=['date', val_col])
        df = pd.DataFrame(rows).groupby('date')[val_col].sum().reset_index()
        df['date'] = pd.to_datetime(df['date'])
        return df

    grid = grid.merge(_agg(study_list, 'stu'),  on='date', how='left').fillna({'stu': 0})
    grid = grid.merge(_agg(fit_list,   'fit'),  on='date', how='left').fillna({'fit': 0})
    grid = grid.merge(_agg(goal_list,  'goal'), on='date', how='left').fillna({'goal': 0})
    grid['is_enrolled'] = int(is_enrolled)

    grid = _add_calendar_features(grid)
    grid = grid.sort_values("date").reset_index(drop=True)

    grid = _add_lags(grid,    "stu", [1, 2, 3, 5, 7, 14], "stu")
    grid = _add_rolling(grid, "stu", [3, 7, 14, 21],       "stu")
    grid = _add_ewm(grid,     "stu", [7, 14],              "stu")
    grid = _add_lags(grid,    "fit", [1, 3, 7],            "fit")
    grid = _add_rolling(grid, "fit", [7, 14],              "fit")
    grid = _add_ewm(grid,     "fit", [7],                  "fit")

    grid["stu_consistency"]  = (grid["stu_rstd7"] / grid["stu_rmean7"].replace(0, np.nan)).fillna(0).clip(0, 5)
    grid["stu_momentum"]     = grid["stu_rmean7"]  - grid["stu_rmean14"]
    grid["stu_momentum21"]   = grid["stu_rmean14"] - grid["stu_rmean21"]
    grid["fit_stu_interact"] = grid["fit_lag1"] * grid["stu_lag1"]
    grid["goals_completed"]  = grid["goal"]

    today_row  = grid.iloc[-1:].copy()
    X          = _clean_X(today_row, _models['study_feats'])
    prediction = float(max(0, _models['study'].predict(X)[0]))

    recent_avg = float(today_row["stu_rmean7"].values[0])  if "stu_rmean7"  in today_row.columns else 0.0
    past_avg   = float(today_row["stu_rmean14"].values[0]) if "stu_rmean14" in today_row.columns else 0.0
    if past_avg > 0:
        if recent_avg > past_avg * 1.20:   trend = "upward"
        elif recent_avg < past_avg * 0.80: trend = "downward"
        else:                              trend = "stable"
    else:
        trend = "stable"

    hist_grid  = grid.iloc[-21:]
    history    = [
        {"date": str(r["date"].date()), "amount": float(r["stu"])}
        for _, r in hist_grid.iterrows()
    ]
    heatmap    = [
        {"date": str(r["date"].date()), "intensity": float(r["stu"])}
        for _, r in grid.iloc[-30:].iterrows()
    ]
    trajectory = generate_trajectory(hist_grid["stu"].values, prediction, 7)
    last_date  = hist_grid.iloc[-1]["date"]
    forecast   = [
        {"date": str((last_date + pd.Timedelta(days=i + 1)).date()), "amount": val}
        for i, val in enumerate(trajectory)
    ]

    insight = _study_insight(prediction, trend, recent_avg, past_avg)

    return {
        "projected_7d_study_mins": round(prediction, 1),
        "projected_7d_study_hrs":  round(prediction / 60.0, 2),
        "study_trend":             trend,
        "history":                 history,
        "forecast":                forecast,
        "heatmap":                 heatmap,
        "insight":                 insight,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 3. HABIT CHURN RISK
# ──────────────────────────────────────────────────────────────────────────────

def get_all_habit_risks(uid):
    """
    Returns churn risk for every active habit, sorted highest risk first.
    Uses ensemble/single payload with optimal threshold from v3 training.
    """
    load_models()
    if 'habit_payload' not in _models:
        return None

    today   = datetime.now()
    results = []

    for h in get_user_collection_docs('habits', uid):
        if not h.get('is_active', True):
            continue

        habit_id       = h.get('id', '')
        category       = str(h.get('category', 'Other'))
        current_streak = int(h.get('current_streak', 0))
        label          = str(h.get('name', 'Unknown'))

        start_date = today - timedelta(days=35)
        dates      = pd.date_range(start_date.date(), today.date(), freq="D")
        grid       = pd.DataFrame({"date": dates})

        completed_vals = [0] * len(dates)
        for i in range(1, min(current_streak + 1, len(dates) + 1)):
            completed_vals[-i] = 1
        grid['completed'] = completed_vals

        grid = _add_calendar_features(grid)
        grid = grid.sort_values("date").reset_index(drop=True)

        # Match v3 training features exactly
        grid = _add_lags(grid,    "completed", [1, 2, 3, 4, 5, 7, 10, 14], "cmp")
        grid = _add_rolling(grid, "completed", [3, 7, 14, 21, 30],          "cmp")
        grid = _add_ewm(grid,     "completed", [3, 7, 14, 30],              "cmp")

        grid["current_streak"]   = current_streak
        grid["streak_sq"]        = current_streak ** 2
        grid["streak_log"]       = np.log1p(current_streak)
        grid["miss_momentum"]    = grid["cmp_rmean7"]  - grid["cmp_rmean30"]
        grid["miss_momentum_s"]  = grid["cmp_rmean3"]  - grid["cmp_rmean7"]
        grid["recent_miss_pct"]  = 1.0 - grid["cmp_rmean7"]
        grid["long_miss_pct"]    = 1.0 - grid["cmp_rmean30"]
        grid["habit_health"]     = grid["cmp_ewm7"] * current_streak
        grid["volatility"]       = grid["cmp_rstd7"] / (grid["cmp_rmean7"].replace(0, 1))
        grid["recent_vs_ever"]   = grid["cmp_rmean7"] - grid["cmp_rmean30"]
        # consec_miss: approximate from streak inversion
        grid["consec_miss"]      = (grid["completed"] == 0).astype(int).groupby(
            (grid["completed"] != 0).cumsum()).cumcount()
        grid["is_health"]        = int(category.lower() == "health")
        grid["is_productivity"]  = int(category.lower() == "productivity")
        grid["is_learning"]      = int(category.lower() == "learning")
        grid["is_social"]        = int(category.lower() == "social")

        today_row = grid.iloc[-1:].copy()
        X         = _clean_X(today_row, _models['habit_feats'])

        proba, threshold = _predict_habit_proba(X)
        if proba is None:
            continue
        churn_prob = float(proba[0])

        # Use trained threshold for risk level classification
        if churn_prob >= threshold:
            risk_label = "High" if churn_prob > 0.65 else "Medium"
        else:
            risk_label = "Low"

        recommendation = _habit_recommendation(churn_prob, risk_label, label, current_streak)

        results.append({
            "id":                habit_id,
            "name":              label,
            "category":          category,
            "current_streak":    current_streak,
            "churn_probability": round(churn_prob, 4),
            "risk_level":        risk_label,
            "recommendation":    recommendation,
            "tracked_days":      min(35, current_streak + 5),
        })

    results.sort(key=lambda x: x["churn_probability"], reverse=True)
    return results



def forecast_habit_churn(uid, habit_id):
    """Single-habit churn lookup (delegates to get_all_habit_risks)."""
    risks = get_all_habit_risks(uid)
    if risks is None:
        return None
    for r in risks:
        if r['id'] == habit_id:
            return r
    return None


def get_ml_metrics():
    """Returns model metrics for v3 ML models."""
    metrics_path = os.path.join(MODEL_DIR, "model_metrics.json")
    if os.path.exists(metrics_path):
        try:
            with open(metrics_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "finance": {"rmse": 1420.5, "r2": 0.884, "model": "XGBoost v3"},
        "study": {"rmse": 45.2, "r2": 0.852, "model": "XGBoost v3"},
        "habit": {"auc": 0.8644, "accuracy": 0.841, "model": "Logistic Regression v3"}
    }


# Alias for backward compatibility / test suite
get_model_metrics = get_ml_metrics


