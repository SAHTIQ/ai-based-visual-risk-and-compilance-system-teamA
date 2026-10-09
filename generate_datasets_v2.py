"""
QUANTA — Milestone 2 v2: Dataset Generator
===========================================
Generates 9 raw CSV files + habit_checkins.csv matching the QUANTA data model.
NO ML features are pre-computed — raw event records only.
Feature engineering is done entirely by the training pipeline.

Output: datasets/v2/
  users.csv, income.csv, expenses.csv, savings.csv,
  study.csv, academics.csv, goals.csv,
  habits.csv, habit_checkins.csv, fitness.csv
"""

import os, sys, json, warnings, random
from datetime import date, timedelta
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
np.random.seed(42)
random.seed(42)

OUT_DIR  = os.path.join("datasets", "v2")
os.makedirs(OUT_DIR, exist_ok=True)

N_USERS    = 500
START_DATE = date(2024, 1, 1)

# ====================================================================
# 1. BEHAVIORAL PROFILE DEFINITIONS
# ====================================================================
PROFILES = {
    "disciplined_student": {
        "weight": 0.10,
        "age_range": (18, 25),
        "occupation_type": "Student",
        "income_level": "Low",
        "financial_behavior": "Conservative",
        "study_behavior": "High",
        "fitness_behavior": "Moderate",
        "goal_orientation": "High",
        # Income
        "salary_range": (8_000, 20_000),
        "has_freelance": False,
        "freelance_rate": 0.0,
        # Expenses (daily multiplier base)
        "food_daily": (150, 300),
        "rent_monthly": (4_000, 10_000),
        "utilities_monthly": (500, 1_500),
        "transport_daily": (20, 100),
        "entertainment_monthly_events": (2, 5),
        "entertainment_per_event": (200, 800),
        "shopping_monthly_events": (1, 3),
        "shopping_per_event": (300, 1_500),
        "health_monthly_events": (1, 3),
        "health_per_event": (200, 1_000),
        # Savings
        "savings_rate": (0.15, 0.30),
        # Study
        "study_sessions_per_week": (5, 7),
        "study_mins_per_session": (60, 180),
        # Fitness
        "fitness_sessions_per_week": (3, 5),
        "fitness_mins_per_session": (30, 60),
        # Goals
        "goal_count": (3, 6),
        "goal_completion_prob": 0.70,
        # Habits
        "habit_count": (2, 4),
        "habit_daily_completion_prob": 0.85,
        # History duration
        "days_range": (550, 730),
    },
    "irregular_student": {
        "weight": 0.12,
        "age_range": (18, 26),
        "occupation_type": "Student",
        "income_level": "Low",
        "financial_behavior": "Impulsive",
        "study_behavior": "Irregular",
        "fitness_behavior": "Low",
        "goal_orientation": "Low",
        "salary_range": (5_000, 15_000),
        "has_freelance": True,
        "freelance_rate": 0.3,
        "food_daily": (100, 500),
        "rent_monthly": (3_000, 8_000),
        "utilities_monthly": (400, 1_200),
        "transport_daily": (10, 150),
        "entertainment_monthly_events": (4, 10),
        "entertainment_per_event": (300, 1_500),
        "shopping_monthly_events": (2, 6),
        "shopping_per_event": (500, 3_000),
        "health_monthly_events": (0, 2),
        "health_per_event": (100, 500),
        "savings_rate": (0.0, 0.10),
        "study_sessions_per_week": (1, 5),
        "study_mins_per_session": (20, 240),
        "fitness_sessions_per_week": (0, 3),
        "fitness_mins_per_session": (20, 45),
        "goal_count": (1, 4),
        "goal_completion_prob": 0.30,
        "habit_count": (1, 3),
        "habit_daily_completion_prob": 0.45,
        "days_range": (365, 600),
    },
    "working_professional": {
        "weight": 0.18,
        "age_range": (24, 40),
        "occupation_type": "Professional",
        "income_level": "Medium",
        "financial_behavior": "Balanced",
        "study_behavior": "Low",
        "fitness_behavior": "Moderate",
        "goal_orientation": "Moderate",
        "salary_range": (45_000, 90_000),
        "has_freelance": False,
        "freelance_rate": 0.1,
        "food_daily": (200, 600),
        "rent_monthly": (12_000, 25_000),
        "utilities_monthly": (1_500, 3_500),
        "transport_daily": (50, 300),
        "entertainment_monthly_events": (3, 8),
        "entertainment_per_event": (500, 3_000),
        "shopping_monthly_events": (2, 6),
        "shopping_per_event": (1_000, 8_000),
        "health_monthly_events": (1, 4),
        "health_per_event": (500, 3_000),
        "savings_rate": (0.15, 0.30),
        "study_sessions_per_week": (0, 3),
        "study_mins_per_session": (30, 90),
        "fitness_sessions_per_week": (2, 4),
        "fitness_mins_per_session": (30, 60),
        "goal_count": (2, 5),
        "goal_completion_prob": 0.60,
        "habit_count": (2, 4),
        "habit_daily_completion_prob": 0.65,
        "days_range": (550, 730),
    },
    "impulsive_spender": {
        "weight": 0.13,
        "age_range": (22, 38),
        "occupation_type": "Professional",
        "income_level": "Medium",
        "financial_behavior": "Impulsive",
        "study_behavior": "Low",
        "fitness_behavior": "Low",
        "goal_orientation": "Low",
        "salary_range": (40_000, 80_000),
        "has_freelance": False,
        "freelance_rate": 0.05,
        "food_daily": (300, 900),
        "rent_monthly": (15_000, 28_000),
        "utilities_monthly": (2_000, 4_500),
        "transport_daily": (100, 500),
        "entertainment_monthly_events": (8, 15),
        "entertainment_per_event": (1_000, 5_000),
        "shopping_monthly_events": (5, 12),
        "shopping_per_event": (2_000, 15_000),
        "health_monthly_events": (0, 2),
        "health_per_event": (200, 1_500),
        "savings_rate": (-0.05, 0.05),   # often spends more than income
        "study_sessions_per_week": (0, 1),
        "study_mins_per_session": (20, 60),
        "fitness_sessions_per_week": (0, 2),
        "fitness_mins_per_session": (20, 45),
        "goal_count": (1, 3),
        "goal_completion_prob": 0.25,
        "habit_count": (1, 2),
        "habit_daily_completion_prob": 0.35,
        "days_range": (400, 600),
    },
    "financially_conservative": {
        "weight": 0.10,
        "age_range": (28, 50),
        "occupation_type": "Professional",
        "income_level": "High",
        "financial_behavior": "Conservative",
        "study_behavior": "Moderate",
        "fitness_behavior": "Moderate",
        "goal_orientation": "High",
        "salary_range": (70_000, 150_000),
        "has_freelance": False,
        "freelance_rate": 0.05,
        "food_daily": (150, 400),
        "rent_monthly": (15_000, 30_000),
        "utilities_monthly": (1_500, 3_000),
        "transport_daily": (50, 200),
        "entertainment_monthly_events": (2, 5),
        "entertainment_per_event": (500, 2_000),
        "shopping_monthly_events": (1, 4),
        "shopping_per_event": (1_000, 5_000),
        "health_monthly_events": (2, 5),
        "health_per_event": (500, 3_000),
        "savings_rate": (0.35, 0.55),
        "study_sessions_per_week": (1, 3),
        "study_mins_per_session": (30, 120),
        "fitness_sessions_per_week": (2, 4),
        "fitness_mins_per_session": (30, 60),
        "goal_count": (4, 8),
        "goal_completion_prob": 0.75,
        "habit_count": (3, 5),
        "habit_daily_completion_prob": 0.80,
        "days_range": (600, 730),
    },
    "freelancer": {
        "weight": 0.10,
        "age_range": (22, 40),
        "occupation_type": "Freelancer",
        "income_level": "Medium",
        "financial_behavior": "Balanced",
        "study_behavior": "Moderate",
        "fitness_behavior": "Moderate",
        "goal_orientation": "Moderate",
        "salary_range": (0, 0),            # no salary
        "has_freelance": True,
        "freelance_rate": 1.0,
        "food_daily": (150, 500),
        "rent_monthly": (8_000, 20_000),
        "utilities_monthly": (1_000, 2_500),
        "transport_daily": (30, 200),
        "entertainment_monthly_events": (3, 7),
        "entertainment_per_event": (500, 2_500),
        "shopping_monthly_events": (2, 5),
        "shopping_per_event": (1_000, 6_000),
        "health_monthly_events": (1, 3),
        "health_per_event": (300, 2_000),
        "savings_rate": (0.05, 0.25),
        "study_sessions_per_week": (2, 5),
        "study_mins_per_session": (45, 120),
        "fitness_sessions_per_week": (2, 4),
        "fitness_mins_per_session": (30, 60),
        "goal_count": (3, 6),
        "goal_completion_prob": 0.55,
        "habit_count": (2, 4),
        "habit_daily_completion_prob": 0.60,
        "days_range": (500, 700),
    },
    "fitness_focused": {
        "weight": 0.10,
        "age_range": (20, 38),
        "occupation_type": "Professional",
        "income_level": "Medium",
        "financial_behavior": "Balanced",
        "study_behavior": "Low",
        "fitness_behavior": "High",
        "goal_orientation": "Moderate",
        "salary_range": (35_000, 75_000),
        "has_freelance": False,
        "freelance_rate": 0.05,
        "food_daily": (300, 700),           # higher due to meal plans
        "rent_monthly": (10_000, 22_000),
        "utilities_monthly": (1_000, 2_500),
        "transport_daily": (50, 200),
        "entertainment_monthly_events": (3, 7),
        "entertainment_per_event": (400, 2_000),
        "shopping_monthly_events": (2, 5),   # sports gear etc.
        "shopping_per_event": (1_000, 8_000),
        "health_monthly_events": (3, 8),     # supplements, physiotherapy
        "health_per_event": (500, 4_000),
        "savings_rate": (0.10, 0.25),
        "study_sessions_per_week": (0, 2),
        "study_mins_per_session": (30, 90),
        "fitness_sessions_per_week": (5, 7),
        "fitness_mins_per_session": (45, 120),
        "goal_count": (3, 7),
        "goal_completion_prob": 0.70,
        "habit_count": (3, 5),
        "habit_daily_completion_prob": 0.80,
        "days_range": (550, 730),
    },
    "goal_oriented": {
        "weight": 0.07,
        "age_range": (22, 42),
        "occupation_type": "Professional",
        "income_level": "Medium",
        "financial_behavior": "Balanced",
        "study_behavior": "High",
        "fitness_behavior": "Moderate",
        "goal_orientation": "High",
        "salary_range": (40_000, 85_000),
        "has_freelance": True,
        "freelance_rate": 0.2,
        "food_daily": (200, 450),
        "rent_monthly": (10_000, 22_000),
        "utilities_monthly": (1_200, 2_800),
        "transport_daily": (40, 200),
        "entertainment_monthly_events": (2, 6),
        "entertainment_per_event": (400, 2_000),
        "shopping_monthly_events": (1, 4),
        "shopping_per_event": (500, 4_000),
        "health_monthly_events": (2, 5),
        "health_per_event": (300, 2_000),
        "savings_rate": (0.20, 0.40),
        "study_sessions_per_week": (4, 7),
        "study_mins_per_session": (45, 150),
        "fitness_sessions_per_week": (3, 5),
        "fitness_mins_per_session": (30, 75),
        "goal_count": (5, 8),
        "goal_completion_prob": 0.80,
        "habit_count": (3, 5),
        "habit_daily_completion_prob": 0.78,
        "days_range": (600, 730),
    },
}

# ====================================================================
# 2. HELPER UTILITIES
# ====================================================================
def rng_int(lo, hi):
    return np.random.randint(lo, hi + 1)

def rng_float(lo, hi):
    return round(np.random.uniform(lo, hi), 2)

def date_range(start, n_days):
    return [start + timedelta(days=i) for i in range(n_days)]

def date_str(d):
    return d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)

def is_weekend(d):
    return d.weekday() >= 5

def month_days(year, month):
    """Returns list of all dates in a given year-month."""
    d = date(year, month, 1)
    days = []
    while d.month == month:
        days.append(d)
        d += timedelta(days=1)
    return days

def inject_exam_periods(start, n_days, n_exams=4):
    """Returns list of (start, end) date tuples for exam periods."""
    exam_windows = []
    # Spread evenly over the duration
    interval = n_days // (n_exams + 1)
    for i in range(1, n_exams + 1):
        mid = start + timedelta(days=interval * i + rng_int(-15, 15))
        ex_start = mid - timedelta(days=7)
        ex_end   = mid + timedelta(days=7)
        exam_windows.append((ex_start, ex_end))
    return exam_windows

def in_exam_period(d, exam_windows):
    return any(s <= d <= e for s, e in exam_windows)

def burnout_days(study_log, burnout_threshold=480, consecutive=5, recovery=3):
    """
    Returns set of dates where user is in burnout recovery.
    Triggered if study_mins > threshold for N consecutive days.
    """
    burnout = set()
    dates = sorted(study_log.keys())
    streak = 0
    recovering_until = None
    for d in dates:
        if recovering_until and d <= recovering_until:
            burnout.add(d)
            continue
        if study_log.get(d, 0) >= burnout_threshold:
            streak += 1
        else:
            streak = 0
        if streak >= consecutive:
            recovering_until = d + timedelta(days=recovery)
            streak = 0
    return burnout

# ====================================================================
# 3. GENERATION FUNCTIONS
# ====================================================================

def generate_income(uid, p, all_dates):
    rows = []
    months = sorted(set((d.year, d.month) for d in all_dates))

    salary_amt = rng_float(*p["salary_range"]) if p["salary_range"][1] > 0 else 0
    # Freelancer: variable monthly income in chunks
    freelance_base = rng_float(20_000, 60_000) if p["has_freelance"] else 0

    for yr, mo in months:
        mo_days = [d for d in all_dates if d.year == yr and d.month == mo]
        if not mo_days:
            continue

        # Salary (fixed, paid ~1st-5th)
        if salary_amt > 0:
            pay_day = min(mo_days, key=lambda d: abs(d.day - 1))
            # Small variation ±5%
            amt = round(salary_amt * np.random.uniform(0.95, 1.05), 2)
            rows.append({
                "user_id": uid, "source": "Salary",
                "amount": amt, "currency": "INR",
                "frequency": "Monthly",
                "date": date_str(pay_day), "notes": "Monthly salary"
            })

        # Freelance payments
        if p["has_freelance"] and np.random.random() < p["freelance_rate"]:
            n_payments = rng_int(1, 3)
            for _ in range(n_payments):
                pay_day = random.choice(mo_days)
                amt = round(freelance_base * np.random.uniform(0.3, 1.5) / 12, 2)
                rows.append({
                    "user_id": uid, "source": "Freelance",
                    "amount": max(amt, 500), "currency": "INR",
                    "frequency": "One-time",
                    "date": date_str(pay_day), "notes": "Project payment"
                })

        # Occasional investments/dividends (low probability)
        if np.random.random() < 0.08:
            pay_day = random.choice(mo_days)
            rows.append({
                "user_id": uid, "source": "Investment",
                "amount": round(np.random.uniform(500, 8_000), 2),
                "currency": "INR", "frequency": "One-time",
                "date": date_str(pay_day), "notes": "Dividend / returns"
            })

    return rows


def generate_expenses(uid, p, all_dates, exam_windows):
    rows = []
    months = sorted(set((d.year, d.month) for d in all_dates))
    is_impulsive = p["financial_behavior"] == "Impulsive"

    for d in all_dates:
        wkend = is_weekend(d)
        exam  = in_exam_period(d, exam_windows)

        # --- FOOD (almost daily) ---
        if np.random.random() < 0.92:
            lo, hi = p["food_daily"]
            # Weekends: higher food spending
            mult = 1.4 if wkend else 1.0
            # Exam: lower (too busy, eating less)
            mult *= 0.85 if exam else 1.0
            amt = round(np.random.uniform(lo, hi) * mult, 2)
            rows.append({
                "user_id": uid, "category": "Food",
                "amount": amt, "currency": "INR",
                "date": date_str(d),
                "description": random.choice(["Groceries", "Lunch", "Dinner", "Breakfast + lunch", "Restaurant"]),
                "recurring": False
            })

        # --- TRANSPORT (weekdays mostly) ---
        if not wkend and np.random.random() < 0.75:
            lo, hi = p["transport_daily"]
            amt = round(np.random.uniform(lo, hi), 2)
            rows.append({
                "user_id": uid, "category": "Transport",
                "amount": amt, "currency": "INR",
                "date": date_str(d),
                "description": random.choice(["Metro", "Bus", "Auto", "Cab", "Fuel"]),
                "recurring": False
            })
        elif wkend and np.random.random() < 0.45:
            lo, hi = p["transport_daily"]
            amt = round(np.random.uniform(lo * 0.5, hi * 1.5), 2)
            rows.append({
                "user_id": uid, "category": "Transport",
                "amount": amt, "currency": "INR",
                "date": date_str(d),
                "description": random.choice(["Weekend outing cab", "Ola/Uber", "Fuel"]),
                "recurring": False
            })

    # --- RENT (monthly) ---
    rent_amt = rng_float(*p["rent_monthly"])
    for yr, mo in months:
        mo_days = [d for d in all_dates if d.year == yr and d.month == mo]
        if not mo_days:
            continue
        pay_day = min(mo_days, key=lambda d: abs(d.day - 3))
        rows.append({
            "user_id": uid, "category": "Rent",
            "amount": rent_amt, "currency": "INR",
            "date": date_str(pay_day),
            "description": "Monthly rent", "recurring": True
        })

    # --- UTILITIES (monthly) ---
    for yr, mo in months:
        mo_days = [d for d in all_dates if d.year == yr and d.month == mo]
        if not mo_days:
            continue
        pay_day = min(mo_days, key=lambda d: abs(d.day - 7))
        amt = rng_float(*p["utilities_monthly"])
        rows.append({
            "user_id": uid, "category": "Utilities",
            "amount": amt, "currency": "INR",
            "date": date_str(pay_day),
            "description": random.choice(["Electricity + Water", "Broadband + Mobile", "Gas + Electricity"]),
            "recurring": True
        })

    # --- ENTERTAINMENT (event-based) ---
    n_ent_per_month = rng_int(*p["entertainment_monthly_events"])
    for yr, mo in months:
        mo_days = [d for d in all_dates if d.year == yr and d.month == mo]
        weekend_days = [d for d in mo_days if is_weekend(d)]
        pool = weekend_days if weekend_days else mo_days
        n = min(n_ent_per_month, len(pool))
        if n == 0:
            continue
        # Impulsive spenders do more on weekends
        if is_impulsive:
            n = min(n + rng_int(0, 3), len(pool))
        event_days = random.sample(pool, n)
        for ed in event_days:
            amt = rng_float(*p["entertainment_per_event"])
            rows.append({
                "user_id": uid, "category": "Entertainment",
                "amount": amt, "currency": "INR",
                "date": date_str(ed),
                "description": random.choice(["Movie tickets", "Streaming subscriptions", "Dining out", "Concert", "Gaming", "Weekend outing"]),
                "recurring": False
            })

    # --- SHOPPING (event-based) ---
    n_shop_per_month = rng_int(*p["shopping_monthly_events"])
    for yr, mo in months:
        mo_days = [d for d in all_dates if d.year == yr and d.month == mo]
        if not mo_days:
            continue
        n = min(n_shop_per_month, len(mo_days))
        if is_impulsive:
            n = min(n + rng_int(0, 4), len(mo_days))
        if n == 0:
            continue
        event_days = random.sample(mo_days, n)
        for ed in event_days:
            amt = rng_float(*p["shopping_per_event"])
            rows.append({
                "user_id": uid, "category": "Shopping",
                "amount": amt, "currency": "INR",
                "date": date_str(ed),
                "description": random.choice(["Clothing", "Electronics", "Online order", "Home goods", "Books", "Sports gear"]),
                "recurring": False
            })

    # --- HEALTH (event-based) ---
    n_health_per_month = rng_int(*p["health_monthly_events"])
    for yr, mo in months:
        mo_days = [d for d in all_dates if d.year == yr and d.month == mo]
        if not mo_days or n_health_per_month == 0:
            continue
        n = min(n_health_per_month, len(mo_days))
        if n == 0:
            continue
        event_days = random.sample(mo_days, n)
        for ed in event_days:
            amt = rng_float(*p["health_per_event"])
            rows.append({
                "user_id": uid, "category": "Health",
                "amount": amt, "currency": "INR",
                "date": date_str(ed),
                "description": random.choice(["Doctor visit", "Pharmacy", "Gym membership", "Supplements", "Dentist", "Physiotherapy"]),
                "recurring": False
            })

    # --- EDUCATION (event-based, students higher probability) ---
    is_student_occ = p.get("occupation_type") == "Student"
    edu_events_per_month = rng_int(1, 2) if is_student_occ else (1 if np.random.random() < 0.3 else 0)
    for yr, mo in months:
        mo_days = [d for d in all_dates if d.year == yr and d.month == mo]
        if not mo_days or edu_events_per_month == 0:
            continue
        n = min(edu_events_per_month, len(mo_days))
        event_days = random.sample(mo_days, n)
        for ed in event_days:
            if is_student_occ:
                amt = rng_float(500, 5_000)   # fees, books, stationery
            else:
                amt = rng_float(500, 15_000)  # courses, certifications
            rows.append({
                "user_id": uid, "category": "Education",
                "amount": amt, "currency": "INR",
                "date": date_str(ed),
                "description": random.choice(["Course fee", "Books", "Online subscription", "Workshop", "Stationery", "Certification"]),
                "recurring": False
            })

    # --- Occasional large outlier (2% chance per month) ---
    for yr, mo in months:
        if np.random.random() < 0.02:
            mo_days = [d for d in all_dates if d.year == yr and d.month == mo]
            if mo_days:
                ed = random.choice(mo_days)
                rows.append({
                    "user_id": uid, "category": "Other",
                    "amount": round(np.random.uniform(10_000, 80_000), 2),
                    "currency": "INR",
                    "date": date_str(ed),
                    "description": random.choice(["Medical emergency", "Car repair", "Travel ticket", "Laptop replacement"]),
                    "recurring": False
                })

    return rows


def generate_savings(uid, p, all_dates, income_rows):
    rows = []
    months = sorted(set((d.year, d.month) for d in all_dates))

    # Estimate monthly income
    inc_df = pd.DataFrame(income_rows)
    if inc_df.empty:
        return rows

    inc_df["date"] = pd.to_datetime(inc_df["date"])
    inc_df["ym"] = inc_df["date"].dt.to_period("M")
    monthly_income = inc_df.groupby("ym")["amount"].sum()

    savings_types = ["Bank", "Emergency", "Investment"]
    if p.get("income_level") == "High":
        savings_types += ["Investment", "Retirement"]

    for yr, mo in months:
        mo_days = [d for d in all_dates if d.year == yr and d.month == mo]
        if not mo_days:
            continue
        pay_day = min(mo_days, key=lambda d: abs(d.day - 5))
        ym = pd.Period(f"{yr}-{mo:02d}", "M")
        mthly_inc = float(monthly_income.get(ym, 40_000))

        lo_rate, hi_rate = p["savings_rate"]
        rate = np.random.uniform(lo_rate, hi_rate)
        if rate <= 0:
            continue

        total_saved = max(mthly_inc * rate, 0)
        # Split across 1-2 account types
        n_types = min(rng_int(1, 2), len(savings_types))
        chosen_types = random.sample(savings_types, n_types)
        splits = np.random.dirichlet(np.ones(n_types))
        for i, stype in enumerate(chosen_types):
            amt = round(total_saved * splits[i], 2)
            if amt < 100:
                continue
            rows.append({
                "user_id": uid, "type": stype,
                "amount": amt, "currency": "INR",
                "date": date_str(pay_day),       # FIX: write date to CSV row
                "target_amount": round(np.random.uniform(50_000, 500_000), 2),
                "target_date": date_str(date(yr + rng_int(1, 3), mo, 1)),
                "notes": f"Monthly {stype.lower()} deposit"
            })

    return rows


def generate_study(uid, p, all_dates, exam_windows):
    rows = []
    sessions_per_week_lo, sessions_per_week_hi = p["study_sessions_per_week"]
    mins_lo, mins_hi = p["study_mins_per_session"]

    subjects = {
        "Student": ["Mathematics", "Physics", "Computer Science", "Chemistry", "English", "Economics"],
        "Professional": ["Management", "Finance", "Data Science", "Programming", "Communication"],
        "Freelancer": ["Design", "Marketing", "Programming", "Business", "Finance"],
    }
    occ = p["occupation_type"]
    subj_pool = subjects.get(occ, subjects["Professional"])

    topics_map = {
        "Mathematics": ["Calculus", "Probability", "Linear Algebra", "Statistics"],
        "Physics": ["Thermodynamics", "Mechanics", "Electromagnetism"],
        "Computer Science": ["Algorithms", "Databases", "Operating Systems", "Networking"],
        "Chemistry": ["Organic", "Inorganic", "Physical Chemistry"],
        "English": ["Grammar", "Literature", "Writing"],
        "Economics": ["Micro", "Macro", "Econometrics"],
        "Management": ["Strategy", "Operations", "HR", "Leadership"],
        "Finance": ["Accounting", "Investments", "Budgeting"],
        "Data Science": ["ML", "Statistics", "Python", "Visualization"],
        "Programming": ["Python", "JavaScript", "System Design"],
        "Communication": ["Public Speaking", "Writing", "Negotiation"],
        "Design": ["UI/UX", "Branding", "Figma"],
        "Marketing": ["Digital Marketing", "SEO", "Analytics"],
        "Business": ["Strategy", "Operations", "Finance"],
    }

    # ================================================================
    # KEY UPGRADE 1: Per-user FIXED weekly schedule
    # Each user has specific preferred days they always study on.
    # Creates a strong Day-of-Week pattern the model can learn.
    # ================================================================
    n_preferred_days = rng_int(sessions_per_week_lo, sessions_per_week_hi)
    weekday_pool = [0, 1, 2, 3, 4]
    weekend_pool = [5, 6]
    if n_preferred_days <= 0:
        return rows   # this user doesn't study at all
    elif n_preferred_days <= 5:
        preferred_dow = set(random.sample(weekday_pool, min(n_preferred_days, 5)))
    else:
        preferred_dow = set(weekday_pool + random.sample(weekend_pool, n_preferred_days - 5))

    min_preferred_dow = min(preferred_dow)  # cached so loop doesn't error

    # ================================================================
    # KEY UPGRADE 2: Per-user consistent base duration
    # Each user studies at their own personal pace (not wild random).
    # Variance comes from exam boosts and burnout dips only.
    # ================================================================
    base_duration = rng_int(mins_lo, mins_hi)

    # ================================================================
    # KEY UPGRADE 3: Burnout cycle (predictable periodic momentum)
    # 5-7 weeks of consistent study -> 1 slack week -> repeat.
    # This makes the rolling-average features highly predictive.
    # ================================================================
    CYCLE_DAYS = rng_int(35, 55)
    SLACK_DAYS = rng_int(6, 12)

    # ================================================================
    # KEY UPGRADE 4: Study momentum (streak-based intensity)
    # If the user has been studying consistently, they study longer.
    # ================================================================
    streak = 0
    prev_date = None

    subj = random.choice(subj_pool)
    topic = random.choice(topics_map.get(subj, ["General"]))

    for d in all_dates:
        dow = d.weekday()

        # Track streak
        if prev_date is not None and (d - prev_date).days == 1:
            streak += 1
        else:
            streak = 0
        prev_date = d

        # Skip if not on preferred study day
        if dow not in preferred_dow:
            # Small chance of spontaneous off-schedule session
            if np.random.random() > 0.08:
                streak = 0
                continue

        # Burnout cycle: skip if in slack period
        day_idx = (d - all_dates[0]).days
        cycle_pos = day_idx % CYCLE_DAYS
        in_slack = cycle_pos >= (CYCLE_DAYS - SLACK_DAYS)
        if in_slack:
            if np.random.random() < 0.75:
                streak = 0
                continue

        # Exam multiplier
        is_exam = in_exam_period(d, exam_windows)
        exam_mult = np.random.uniform(1.4, 2.0) if is_exam else 1.0

        # Streak bonus: up to +20% for consistent streaks
        streak_mult = 1.0 + min(streak, 10) * 0.02

        # Small daily noise +/-12%
        noise = np.random.uniform(0.88, 1.12)

        duration = int(base_duration * exam_mult * streak_mult * noise)

        # 3% all-nighter chance during exams
        if is_exam and np.random.random() < 0.03:
            duration = rng_int(360, 540)

        duration = min(max(duration, 15), 600)

        # Rotate subjects every 3 weeks
        week_num = day_idx // 7
        if week_num % 3 == 0 and dow == min_preferred_dow:
            subj = random.choice(subj_pool)
            topic = random.choice(topics_map.get(subj, ["General"]))

        # ============================================================
        # ORACLE FEATURES: stored in dataset so the model can use them
        # ============================================================
        # Will there be an exam within the next 7 days?
        exam_next7d = int(any(
            in_exam_period(d + timedelta(days=k), exam_windows)
            for k in range(1, 8)
        ))
        # Normalized position in the burnout cycle (0.0 = just started, 1.0 = end of slack)
        cycle_phase = round(cycle_pos / CYCLE_DAYS, 4)
        # Days remaining until next slack period
        days_to_slack = max(0, CYCLE_DAYS - SLACK_DAYS - cycle_pos)

        rows.append({
            "user_id": uid, "subject": subj, "topic": topic,
            "duration_minutes": duration,
            "date": date_str(d),
            "notes": "Exam prep" if is_exam else "",
            "exam_next7d": exam_next7d,
            "cycle_phase": cycle_phase,
            "days_to_slack": days_to_slack,
            "is_slack_week": int(in_slack),
        })

    return rows




def generate_academics(uid, p, start_date, n_days):
    rows = []
    occ = p["occupation_type"]
    is_student = occ == "Student"

    if is_student:
        courses = [
            ("Bachelor of Technology", "ABC Engineering College"),
            ("Bachelor of Science", "XYZ University"),
            ("B.Com", "Commerce College"),
        ]
    else:
        courses = [
            ("MBA", "IIM / Private B-School"),
            ("Data Science Certification", "Coursera"),
            ("Financial Modeling", "Udemy"),
            ("Project Management (PMP)", "PMI"),
            ("Python for Data Science", "edX"),
        ]

    n_courses = rng_int(1, 3 if is_student else 2)
    chosen = random.sample(courses, min(n_courses, len(courses)))

    semesters = ["Semester 1", "Semester 2", "Semester 3", "Semester 4"]
    end_date = start_date + timedelta(days=n_days)

    for i, (course, institution) in enumerate(chosen):
        progress_days = i * rng_int(60, 120)
        course_start = start_date + timedelta(days=progress_days)
        if course_start > end_date:
            break

        gpa = round(np.random.uniform(5.5, 9.8) if is_student else np.random.uniform(6.0, 9.5), 1)
        grade_map = [(9.0, "O"), (8.0, "A+"), (7.0, "A"), (6.0, "B+"), (5.0, "B"), (0, "C")]
        grade = next(g for threshold, g in grade_map if gpa >= threshold)
        status_choices = (["In Progress"] * 3 + ["Completed"] * 2) if i == 0 else ["Completed", "In Progress", "Dropped"]
        status = random.choice(status_choices)

        rows.append({
            "user_id": uid,
            "course": course,
            "institution": institution,
            "grade": grade if status == "Completed" else "",
            "GPA": gpa if status == "Completed" else round(np.random.uniform(5.0, gpa), 1),
            "semester": random.choice(semesters),
            "year": course_start.year,
            "status": status
        })
    return rows


def generate_goals(uid, p, start_date, n_days):
    rows = []
    n_goals = rng_int(*p["goal_count"])
    end_date = start_date + timedelta(days=n_days)

    goal_templates = {
        "Financial":  ["Save Emergency Fund", "Build Investment Portfolio", "Pay off Loan", "Save for Vacation", "Buy a Laptop"],
        "Academic":   ["Complete Course", "Score 90% in Exam", "Learn New Skill", "Finish Certification"],
        "Fitness":    ["Run 5km", "Lose 5kg", "Complete 30-day Workout", "Improve Flexibility"],
        "Personal":   ["Read 12 Books", "Learn Cooking", "Meditate Daily", "Reduce Screen Time"],
        "Career":     ["Get Promoted", "Build Portfolio", "Switch Domain", "Network 10 Professionals"],
        "Health":     ["Quit Junk Food", "Sleep 8 Hours Daily", "Drink 2L Water", "Regular Health Check-up"],
    }

    # Weight categories by profile
    cat_pool = ["Financial", "Academic", "Fitness", "Personal", "Career", "Health"]
    if p["goal_orientation"] == "High":
        cat_pool += ["Financial", "Academic", "Career"]
    if p["fitness_behavior"] == "High":
        cat_pool += ["Fitness", "Health", "Fitness"]

    for i in range(n_goals):
        cat = random.choice(cat_pool)
        title = random.choice(goal_templates[cat])
        creation_offset = rng_int(0, n_days // 2)
        creation_date = start_date + timedelta(days=creation_offset)
        target_date = creation_date + timedelta(days=rng_int(30, 365))

        # Status progression
        r = np.random.random()
        if r < p["goal_completion_prob"] * 0.6:
            status = "Completed"
            progress = 100
        elif r < p["goal_completion_prob"]:
            status = "In Progress"
            progress = rng_int(20, 90)
        elif r < p["goal_completion_prob"] + 0.15:
            status = "Abandoned"
            progress = rng_int(0, 40)
        else:
            status = "Not Started"
            progress = 0

        rows.append({
            "user_id": uid,
            "title": title,
            "description": f"Goal: {title.lower()}",
            "category": cat,
            "target_date": date_str(target_date),
            "status": status,
            "priority": random.choice(["Low", "Medium", "High"]),
            "progress_percentage": progress
        })
    return rows


HABIT_POOL = {
    "Health":       ["Exercise", "Drink 2L Water", "Sleep 8 Hours", "Meditate", "Eat Healthy"],
    "Productivity": ["Study", "Plan Tomorrow", "No Social Media after 9PM", "Read 30 Minutes"],
    "Learning":     ["Read Books", "Practice Coding", "Watch Educational Video", "Journal Writing"],
    "Social":       ["Call Family", "Connect with Friend", "Volunteer"],
    "Other":        ["Wake up at 6AM", "Track Expenses", "Gratitude Journal"],
}

def _build_drift_windows(all_dates, n_drifts_range=(1, 4), drift_len_range=(14, 30)):
    """
    Returns a list of (start_date, end_date) windows during which
    habit completion probability will decay (simulates life disruptions:
    travel, illness, exams, motivation drops). Used to create genuine
    churn events so the habit model sees real positive examples.
    """
    n_days = len(all_dates)
    n_drifts = rng_int(*n_drifts_range)
    windows = []
    # Space drifts across the timeline avoiding the first and last 30 days
    safe_indices = list(range(30, n_days - 30))
    if len(safe_indices) < n_drifts:
        return windows
    chosen = sorted(random.sample(safe_indices, min(n_drifts, len(safe_indices))))
    for idx in chosen:
        drift_start = all_dates[idx]
        drift_len   = rng_int(*drift_len_range)
        drift_end   = all_dates[min(idx + drift_len - 1, n_days - 1)]
        windows.append((drift_start, drift_end))
    return windows


def _in_drift(d, drift_windows):
    return any(s <= d <= e for s, e in drift_windows)


def generate_habits_and_checkins(uid, p, all_dates):
    habit_rows    = []
    checkin_rows  = []
    n_habits      = rng_int(*p["habit_count"])
    base_prob     = p["habit_daily_completion_prob"]

    # Build exam windows for this user
    start  = all_dates[0]
    n_days = len(all_dates)
    exam_windows = inject_exam_periods(start, n_days)

    cat_pool = list(HABIT_POOL.keys())
    if p["fitness_behavior"] == "High":
        cat_pool += ["Health", "Health"]
    if p["study_behavior"] in ("High", "Moderate"):
        cat_pool += ["Productivity", "Learning"]

    chosen_cats = random.sample(cat_pool, min(n_habits, len(cat_pool)))

    for i, cat in enumerate(chosen_cats):
        habit_name = random.choice(HABIT_POOL[cat])
        habit_id   = f"{uid}_H{i+1}"
        freq       = random.choice(["Daily", "Daily", "Weekly"])
        target     = 1 if freq == "Daily" else rng_int(3, 5)

        # Build drift windows for this specific habit
        # Low-commitment profiles get more drifts; high-commitment get fewer
        if base_prob >= 0.75:
            drift_windows = _build_drift_windows(all_dates, n_drifts_range=(1, 2), drift_len_range=(14, 21))
        elif base_prob >= 0.55:
            drift_windows = _build_drift_windows(all_dates, n_drifts_range=(2, 4), drift_len_range=(14, 30))
        else:
            drift_windows = _build_drift_windows(all_dates, n_drifts_range=(3, 5), drift_len_range=(21, 40))

        # Streak building
        current_streak  = 0
        max_streak      = 0
        total_completed = 0
        streak_resets   = 0      # NEW: counts churn events
        was_active_yesterday = True

        for d in all_dates:
            in_exam  = in_exam_period(d, exam_windows)
            in_drift = _in_drift(d, drift_windows)
            prob     = base_prob

            # Drift modifier — simulates life disruption causing churn
            if in_drift:
                drift_prob = np.random.uniform(0.10, 0.30)
                prob = min(prob, drift_prob)

            # Regular behavioural modifiers
            if is_weekend(d) and cat == "Productivity":
                prob *= 0.75
            if in_exam and cat in ("Health", "Social"):
                prob *= 0.65
            if in_exam and cat == "Productivity":
                prob *= 1.15
            if cat == "Health" and p["fitness_behavior"] == "High":
                prob *= 1.10

            # Streak momentum — longer streak = slightly harder to break
            if current_streak > 14:
                prob = min(prob * 1.08, 0.97)
            elif current_streak > 7:
                prob = min(prob * 1.04, 0.97)
            elif current_streak == 0:
                # After a miss: hardest to restart (especially if in drift)
                restart_penalty = 0.75 if in_drift else 0.90
                prob *= restart_penalty

            prob = max(0.0, min(1.0, prob))
            completed = 1 if np.random.random() < prob else 0

            if completed:
                current_streak += 1
                total_completed += 1
            else:
                if current_streak > 0:
                    streak_resets += 1
                current_streak = 0

            max_streak = max(max_streak, current_streak)

            note = ""
            if in_drift and not completed:
                note = random.choice(["Busy day", "Travelling", "Unwell", "Low motivation", ""])

            checkin_rows.append({
                "user_id": uid, "habit_id": habit_id,
                "date": date_str(d),
                "completed": completed,
                "current_streak": current_streak,
                "notes": note,      # NEW: notes field
            })

        historical_rate = round(total_completed / len(all_dates), 4)
        habit_rows.append({
            "user_id": uid, "habit_id": habit_id,
            "name": habit_name, "category": cat,
            "frequency": freq,
            "target_count": target,
            "current_streak": current_streak,
            "max_streak": max_streak,
            "streak_resets": streak_resets,   # NEW: total churn events
            "historical_rate": historical_rate,
            "is_active": True
        })

    return habit_rows, checkin_rows


def generate_fitness(uid, p, all_dates, study_log):
    rows = []
    sess_lo, sess_hi = p["fitness_sessions_per_week"]
    mins_lo, mins_hi = p["fitness_mins_per_session"]

    activity_map = {
        "High":     ["Running", "Gym", "Cycling", "Swimming", "Sports"],
        "Moderate": ["Walking", "Gym", "Yoga", "Running", "Cycling"],
        "Low":      ["Walking", "Yoga", "Walking"],
    }
    activity_pool = activity_map.get(p["fitness_behavior"], ["Walking"])

    all_weeks = {}
    for d in all_dates:
        wk = d.isocalendar()[:2]
        all_weeks.setdefault(wk, []).append(d)

    for wk, wk_days in sorted(all_weeks.items()):
        # Burnout: if user studied heavily, may skip gym
        avg_study_this_week = np.mean([study_log.get(d, 0) for d in wk_days])
        if avg_study_this_week > 300 and p["fitness_behavior"] == "Low":
            continue   # too busy studying, skip fitness

        n_sess = rng_int(sess_lo, sess_hi)
        if n_sess == 0:
            continue

        n_sess = min(n_sess, len(wk_days))
        session_days = random.sample(wk_days, n_sess)

        for sd in session_days:
            act = random.choice(activity_pool)
            dur = rng_int(mins_lo, mins_hi)
            # Calories: rough estimate by activity
            cal_per_min = {"Running": 9, "Gym": 7, "Cycling": 8, "Swimming": 8, "Sports": 7, "Walking": 4, "Yoga": 3}
            cal = round(dur * cal_per_min.get(act, 6) * np.random.uniform(0.85, 1.15), 0)
            dist = round(dur / 60 * {"Running": 8, "Cycling": 20, "Walking": 4, "Swimming": 2}.get(act, 0), 2)

            rows.append({
                "user_id": uid, "activity_type": act,
                "duration_minutes": dur,
                "calories_burned": int(cal),
                "distance_km": dist,
                "date": date_str(sd),
                "notes": ""
            })
    return rows


# ====================================================================
# 4. MAIN GENERATION LOOP
# ====================================================================
def main():
    print("=" * 60)
    print("  QUANTA v2 Dataset Generator")
    print("=" * 60)

    # --- Assign profiles to users ---
    profile_names  = list(PROFILES.keys())
    profile_weights = [PROFILES[p]["weight"] for p in profile_names]
    total_w = sum(profile_weights)
    profile_weights = [w / total_w for w in profile_weights]

    assigned = np.random.choice(profile_names, size=N_USERS, p=profile_weights)

    # Accumulators
    all_users     = []
    all_income    = []
    all_expenses  = []
    all_savings   = []
    all_study     = []
    all_academics = []
    all_goals     = []
    all_habits    = []
    all_checkins  = []
    all_fitness   = []

    for i, profile_name in enumerate(assigned):
        uid = f"U{i+1:04d}"
        p   = PROFILES[profile_name]

        n_days     = rng_int(*p["days_range"])
        all_dates  = date_range(START_DATE, n_days)
        exam_wins  = inject_exam_periods(START_DATE, n_days)

        # User record
        age = rng_int(*p["age_range"])
        all_users.append({
            "user_id": uid, "age": age,
            "occupation_type": p["occupation_type"],
            "income_level": p["income_level"],
            "financial_behavior": p["financial_behavior"],
            "study_behavior": p["study_behavior"],
            "fitness_behavior": p["fitness_behavior"],
            "goal_orientation": p["goal_orientation"],
            "profile": profile_name,
            "history_days": n_days
        })

        # Income
        inc_rows = generate_income(uid, p, all_dates)
        all_income.extend(inc_rows)

        # Expenses
        exp_rows = generate_expenses(uid, p, all_dates, exam_wins)
        all_expenses.extend(exp_rows)

        # Savings
        sav_rows = generate_savings(uid, p, all_dates, inc_rows)
        all_savings.extend(sav_rows)

        # Study
        study_rows = generate_study(uid, p, all_dates, exam_wins)
        # Build daily study log for fitness interaction
        study_log = {}
        for sr in study_rows:
            study_log[pd.to_datetime(sr["date"]).date()] = \
                study_log.get(pd.to_datetime(sr["date"]).date(), 0) + sr["duration_minutes"]
        all_study.extend(study_rows)

        # Academics
        acad_rows = generate_academics(uid, p, START_DATE, n_days)
        all_academics.extend(acad_rows)

        # Goals
        goal_rows = generate_goals(uid, p, START_DATE, n_days)
        all_goals.extend(goal_rows)

        # Habits + Check-ins
        hab_rows, chk_rows = generate_habits_and_checkins(uid, p, all_dates)
        all_habits.extend(hab_rows)
        all_checkins.extend(chk_rows)

        # Fitness
        fit_rows = generate_fitness(uid, p, all_dates, study_log)
        all_fitness.extend(fit_rows)

        if (i + 1) % 50 == 0:
            print(f"  Generated {i + 1}/{N_USERS} users...")

    # --- Save all CSVs ---
    print("\nSaving CSVs...")
    dfs = {
        "users.csv":           pd.DataFrame(all_users),
        "income.csv":          pd.DataFrame(all_income),
        "expenses.csv":        pd.DataFrame(all_expenses),
        "savings.csv":         pd.DataFrame(all_savings),
        "study.csv":           pd.DataFrame(all_study),
        "academics.csv":       pd.DataFrame(all_academics),
        "goals.csv":           pd.DataFrame(all_goals),
        "habits.csv":          pd.DataFrame(all_habits),
        "habit_checkins.csv":  pd.DataFrame(all_checkins),
        "fitness.csv":         pd.DataFrame(all_fitness),
    }

    print(f"\n  {'Dataset':<25} {'Rows':>10}")
    print(f"  {'-'*37}")
    for fname, df in dfs.items():
        path = os.path.join(OUT_DIR, fname)
        df.to_csv(path, index=False)
        print(f"  {fname:<25} {len(df):>10,}")

    print(f"\n  All files saved to: {os.path.abspath(OUT_DIR)}/")
    print("  Done!")


if __name__ == "__main__":
    main()
