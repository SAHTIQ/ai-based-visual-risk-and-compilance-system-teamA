"""
QUANTA — Demo Data Seeder Route
=================================
POST /api/seed-demo   →  Seeds 90 days of realistic mock data for the
                          authenticated user so ML forecasting activates.

Seeded collections:
  expenses       — 90 days of daily categorised spending
  income         — 3 monthly salary + 4 freelance entries
  study_records  — 70 study sessions (varied subjects & durations)
  fitness_records— 60 workout sessions
  habits         — 5 active habits with realistic streaks
  goals          — 3 goals (1 completed)

All existing documents for this user are cleared first (idempotent).
Realistic Indian rupee values, realistic patterns (weekends less study,
month-end rent, gradual streak build-up).

REMOVE OR DISABLE THIS ROUTE BEFORE GOING TO PRODUCTION.
"""

import random
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, g
from firebase_admin import firestore
from app.middleware.auth import require_auth

seed_bp = Blueprint('seed_bp', __name__, url_prefix='/api')


# ─── helpers ──────────────────────────────────────────────────────────────────

def _days_ago(n):
    return (datetime.now() - timedelta(days=n)).strftime('%Y-%m-%d')


def _batch_delete(db, collection, uid):
    """Delete all docs for this uid in the given collection."""
    docs = db.collection(collection).where('uid', '==', uid).stream()
    batch = db.batch()
    count = 0
    for doc in docs:
        batch.delete(doc.reference)
        count += 1
        if count >= 400:          # Firestore batch limit = 500
            batch.commit()
            batch = db.batch()
            count = 0
    if count:
        batch.commit()


# ─── route ────────────────────────────────────────────────────────────────────

@seed_bp.route('/seed-demo', methods=['POST'])
@require_auth
def seed_demo():
    """Seed 90 days of realistic mock data for the logged-in user."""
    uid = g.uid
    db  = firestore.client()

    rng = random.Random(42)          # deterministic for reproducibility

    # ── 1. Clear existing data ───────────────────────────────────────────────
    for col in ('expenses', 'income', 'study_records', 'fitness_records', 'habits', 'goals'):
        _batch_delete(db, col, uid)

    today = datetime.now()
    batch = db.batch()
    count = 0

    def _add(collection, data):
        nonlocal count
        data['uid'] = uid
        ref = db.collection(collection).document()
        batch.set(ref, data)
        count += 1
        if count >= 450:
            batch.commit()
            # reset — Python trick: we need to rebind outer batch
            # Use a list to hold it so inner func can rebind
            pass   # handled below by manual flush

    docs_added = []

    def add_doc(collection, data):
        data['uid'] = uid
        data['created_at'] = firestore.SERVER_TIMESTAMP
        docs_added.append((collection, data))

    # ── 2. Income ────────────────────────────────────────────────────────────
    # 3 months of salary
    for m in range(3):
        day = (today.replace(day=1) - timedelta(days=m * 30)).strftime('%Y-%m-%d')
        add_doc('income', {
            'amount':   85000.0,
            'currency': 'INR',
            'source':   'Salary',
            'date':     day,
            'notes':    'Monthly salary',
        })
    # 4 freelance payments
    for i, (days, amt, src) in enumerate([
        (15, 12000, 'Freelance Design'),
        (38, 8500,  'Freelance Code Review'),
        (62, 15000, 'Consulting'),
        (75, 9000,  'Freelance Design'),
    ]):
        add_doc('income', {
            'amount':   float(amt),
            'currency': 'INR',
            'source':   src,
            'date':     _days_ago(days),
        })

    # ── 3. Expenses (90 days) ────────────────────────────────────────────────
    # Daily base patterns — realistic Bengaluru spending
    expense_templates = {
        'food':          (150, 350),    # daily food
        'transport':     (60,  200),    # commute
        'entertainment': (200, 800),    # weekends mostly
        'shopping':      (300, 3000),   # occasional
        'health':        (200, 1500),   # clinic / meds
        'utilities':     (800, 1200),   # monthly phone/internet
        'education':     (500, 2000),   # courses
    }

    for day_offset in range(90):
        date_str = _days_ago(day_offset)
        dt       = today - timedelta(days=day_offset)
        dow      = dt.weekday()   # 0=Mon … 6=Sun
        is_weekend = dow >= 5

        # Food — every day
        add_doc('expenses', {
            'category':     'food',
            'amount':       float(rng.randint(*expense_templates['food'])),
            'currency':     'INR',
            'date':         date_str,
            'description':  rng.choice(['Zomato order', 'Groceries', 'Restaurant', 'Swiggy', 'Canteen lunch', 'Home cooking supplies']),
            'is_recurring': False,
        })

        # Transport — weekdays
        if not is_weekend:
            add_doc('expenses', {
                'category':     'transport',
                'amount':       float(rng.randint(*expense_templates['transport'])),
                'currency':     'INR',
                'date':         date_str,
                'description':  rng.choice(['Ola ride', 'Uber', 'Metro', 'Petrol', 'Auto']),
                'is_recurring': False,
            })

        # Entertainment — mostly weekends + some weekdays
        if is_weekend or rng.random() < 0.2:
            add_doc('expenses', {
                'category':     'entertainment',
                'amount':       float(rng.randint(*expense_templates['entertainment'])),
                'currency':     'INR',
                'date':         date_str,
                'description':  rng.choice(['Movie tickets', 'Netflix/Prime', 'Gaming', 'Mall outing', 'Bowling', 'Museum']),
                'is_recurring': False,
            })

        # Shopping — 2–3× per month
        if rng.random() < 0.09:
            add_doc('expenses', {
                'category':     'shopping',
                'amount':       float(rng.randint(*expense_templates['shopping'])),
                'currency':     'INR',
                'date':         date_str,
                'description':  rng.choice(['Amazon', 'Flipkart', 'Clothes', 'Electronics', 'Books', 'Home decor']),
                'is_recurring': False,
            })

        # Health — twice a month
        if rng.random() < 0.07:
            add_doc('expenses', {
                'category':     'health',
                'amount':       float(rng.randint(*expense_templates['health'])),
                'currency':     'INR',
                'date':         date_str,
                'description':  rng.choice(['Doctor visit', 'Pharmacy', 'Gym', 'Vitamins', 'Dental']),
                'is_recurring': False,
            })

        # Utilities — 1st of each month
        if dt.day == 1:
            add_doc('expenses', {
                'category':     'utilities',
                'amount':       float(rng.randint(*expense_templates['utilities'])),
                'currency':     'INR',
                'date':         date_str,
                'description':  rng.choice(['Electricity bill', 'Internet', 'Mobile recharge']),
                'is_recurring': True,
            })

        # Rent — 5th of each month
        if dt.day == 5:
            add_doc('expenses', {
                'category':     'rent',
                'amount':       22000.0,
                'currency':     'INR',
                'date':         date_str,
                'description':  'Monthly rent',
                'is_recurring': True,
            })

        # Education — once a month
        if rng.random() < 0.04:
            add_doc('expenses', {
                'category':     'education',
                'amount':       float(rng.randint(*expense_templates['education'])),
                'currency':     'INR',
                'date':         date_str,
                'description':  rng.choice(['Udemy course', 'Book purchase', 'Workshop', 'Online certification']),
                'is_recurring': False,
            })

    # ── 4. Study Records (70 sessions over 60 days) ──────────────────────────
    subjects = ['Data Science', 'Python', 'System Design', 'DSA', 'Machine Learning',
                'Web Dev', 'Mathematics', 'English Writing', 'Cloud (AWS)']

    study_days = sorted(rng.sample(range(1, 60), 55))   # 55 days out of 60
    for day_offset in study_days:
        dt  = today - timedelta(days=day_offset)
        dow = dt.weekday()

        # Longer sessions on weekends, shorter on weekdays
        if dow >= 5:
            duration = rng.randint(90, 240)
        else:
            duration = rng.randint(25, 120)

        # Productivity builds over time (earlier = lower)
        base_prod = min(10, max(3, int(10 - (day_offset / 60) * 4 + rng.gauss(0, 1.5))))
        prod = max(1, min(10, base_prod))

        add_doc('study_records', {
            'date':               dt.strftime('%Y-%m-%d'),
            'subject':            rng.choice(subjects),
            'duration_minutes':   duration,
            'productivity_score': prod,
            'notes':              rng.choice([
                'Good focus today', 'Completed chapter', 'Practice problems',
                'Watched lecture', 'Code challenge', 'Revision', '',
                'Hard concepts — reviewed 3x', 'Felt tired but pushed through'
            ]),
        })

        # On high-productivity days, log a second short session
        if prod >= 8 and rng.random() < 0.4:
            add_doc('study_records', {
                'date':               dt.strftime('%Y-%m-%d'),
                'subject':            rng.choice(subjects),
                'duration_minutes':   rng.randint(20, 60),
                'productivity_score': rng.randint(6, 9),
                'notes':              'Evening revision',
            })

    # ── 5. Fitness Records (60 sessions over 70 days) ────────────────────────
    activities = ['Running', 'Gym', 'Yoga', 'Cycling', 'Swimming', 'HIIT', 'Walking']
    fitness_days = sorted(rng.sample(range(1, 70), 55))
    for day_offset in fitness_days:
        dt = today - timedelta(days=day_offset)
        add_doc('fitness_records', {
            'date':              dt.strftime('%Y-%m-%d'),
            'activity_type':     rng.choice(activities),
            'duration_minutes':  rng.randint(30, 90),
            'calories_burned':   rng.randint(200, 600),
            'notes':             rng.choice(['Great session', 'Easy day', 'PR today', 'Tough workout', '']),
        })

    # ── 6. Habits ────────────────────────────────────────────────────────────
    habit_configs = [
        { 'name': 'Morning Meditation', 'category': 'wellness',     'frequency': 'daily', 'target_count': 1, 'current_streak': 23 },
        { 'name': 'Read 30 mins',        'category': 'learning',     'frequency': 'daily', 'target_count': 1, 'current_streak': 14 },
        { 'name': 'Evening Run',         'category': 'health',       'frequency': 'daily', 'target_count': 1, 'current_streak': 7  },
        { 'name': 'No Sugar',            'category': 'health',       'frequency': 'daily', 'target_count': 1, 'current_streak': 2  },
        { 'name': 'Code Daily',          'category': 'productivity', 'frequency': 'daily', 'target_count': 1, 'current_streak': 31 },
    ]
    for h in habit_configs:
        add_doc('habits', {
            **h,
            'is_active': True,
            'best_streak': h['current_streak'] + rng.randint(0, 10),
        })

    # ── 7. Goals ─────────────────────────────────────────────────────────────
    add_doc('goals', {
        'title':            'Save ₹1,00,000 this year',
        'description':      'Build emergency fund',
        'status':           'in-progress',
        'progress_percent': 65,
        'target_date':      (today + timedelta(days=90)).strftime('%Y-%m-%d'),
        'category':         'finance',
    })
    add_doc('goals', {
        'title':            'Complete ML Specialization',
        'description':      'Finish Coursera ML course',
        'status':           'completed',
        'progress_percent': 100,
        'target_date':      _days_ago(10),
        'category':         'learning',
    })
    add_doc('goals', {
        'title':            'Run 5K in under 28 minutes',
        'description':      'Build running endurance',
        'status':           'in-progress',
        'progress_percent': 40,
        'target_date':      (today + timedelta(days=60)).strftime('%Y-%m-%d'),
        'category':         'fitness',
    })

    # ── 8. Commit all in batches ─────────────────────────────────────────────
    BATCH_SIZE = 450
    batches_written = 0
    for i in range(0, len(docs_added), BATCH_SIZE):
        chunk = docs_added[i:i + BATCH_SIZE]
        wb    = db.batch()
        for collection, data in chunk:
            ref = db.collection(collection).document()
            wb.set(ref, data)
        wb.commit()
        batches_written += 1

    totals = {}
    for col, _ in docs_added:
        totals[col] = totals.get(col, 0) + 1

    return jsonify({
        'success': True,
        'message': f'Demo data seeded for user {uid[:8]}…',
        'records_created': totals,
        'total': len(docs_added),
        'note': 'ML forecasts should now be available. Reload the Finance / Study / Habits pages.',
    })


@seed_bp.route('/clear-data', methods=['POST'])
@require_auth
def clear_user_data():
    """Clear all data for the authenticated user so they can start clean."""
    uid = g.uid
    db  = firestore.client()

    for col in ('expenses', 'income', 'study_records', 'fitness_records', 'habits', 'goals', 'activity_history'):
        _batch_delete(db, col, uid)

    return jsonify({
        'success': True,
        'message': 'All data cleared successfully. Dashboard is reset to zero.'
    })

