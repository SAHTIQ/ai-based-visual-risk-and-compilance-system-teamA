import os
import json
import warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, date
from firebase_admin import firestore
from scipy.optimize import linprog

warnings.filterwarnings('ignore')

# ──────────────────────────────────────────────────────────────────────────────
# 1. DATA FETCHER
# ──────────────────────────────────────────────────────────────────────────────

def _get_db():
    """Helper to get firestore client."""
    return firestore.client()

def _generate_fallback_expenses(days=90):
    today = datetime.now().date()
    expenses = []
    for d in range(days):
        dt_str = str(today - timedelta(days=d))
        expenses.append({'date': dt_str, 'amount': 250.0, 'category': 'food'})
        if d % 2 == 0:
            expenses.append({'date': dt_str, 'amount': 120.0, 'category': 'transport'})
        if d % 7 == 0:
            expenses.append({'date': dt_str, 'amount': 1500.0, 'category': 'shopping'})
        if d % 30 == 0:
            expenses.append({'date': dt_str, 'amount': 22000.0, 'category': 'rent'})
    return expenses

def _generate_fallback_income(days=90):
    today = datetime.now().date()
    income = []
    for m in range(max(1, days // 30 + 1)):
        dt_str = str(today - timedelta(days=m * 30))
        income.append({'date': dt_str, 'amount': 85000.0, 'source': 'Salary'})
    return income

def _generate_fallback_habits():
    return [
        {'id': 'h1', 'name': 'Morning Meditation', 'category': 'wellness', 'current_streak': 23, 'is_active': True, 'frequency': 'daily'},
        {'id': 'h2', 'name': 'Read 30 mins', 'category': 'learning', 'current_streak': 14, 'is_active': True, 'frequency': 'daily'},
        {'id': 'h3', 'name': 'Evening Run', 'category': 'health', 'current_streak': 7, 'is_active': True, 'frequency': 'daily'},
        {'id': 'h4', 'name': 'No Sugar', 'category': 'health', 'current_streak': 2, 'is_active': True, 'frequency': 'daily'},
        {'id': 'h5', 'name': 'Code Daily', 'category': 'productivity', 'current_streak': 31, 'is_active': True, 'frequency': 'daily'},
    ]

def _generate_fallback_study(days=60):
    today = datetime.now().date()
    study = []
    for d in range(days):
        dt_str = str(today - timedelta(days=d))
        study.append({'date': dt_str, 'duration_minutes': 120})
    return study

def _fetch_expenses(uid, days=90):
    """Returns list of {date: str, amount: float, category: str} dicts"""
    try:
        db = _get_db()
        start_date = datetime.now() - timedelta(days=days)
        expenses = []
        for doc in db.collection('expenses').where('uid', '==', uid).stream():
            d = doc.to_dict()
            try:
                dt = pd.to_datetime(d.get('date'))
                if dt >= start_date:
                    expenses.append({
                        'date': str(dt.date()),
                        'amount': float(d.get('amount', 0)),
                        'category': str(d.get('category', 'Other')).strip()
                    })
            except Exception:
                pass
        return expenses
    except Exception as e:
        print(f"[Firestore Error] _fetch_expenses: {e}")
        return []

def _fetch_income(uid, days=90):
    """Returns list of {date: str, amount: float, source: str} dicts"""
    try:
        db = _get_db()
        start_date = datetime.now() - timedelta(days=days)
        income = []
        for doc in db.collection('income').where('uid', '==', uid).stream():
            d = doc.to_dict()
            try:
                dt = pd.to_datetime(d.get('date'))
                if dt >= start_date:
                    income.append({
                        'date': str(dt.date()),
                        'amount': float(d.get('amount', 0)),
                        'source': str(d.get('source', 'Other')).strip()
                    })
            except Exception:
                pass
        return income
    except Exception as e:
        print(f"[Firestore Error] _fetch_income: {e}")
        return []

def _fetch_savings(uid):
    """Returns list of {type, amount, target_amount, target_date} dicts"""
    try:
        db = _get_db()
        savings = []
        for doc in db.collection('savings').where('uid', '==', uid).stream():
            d = doc.to_dict()
            savings.append({
                'type': d.get('type', 'Other'),
                'amount': float(d.get('amount', 0)),
                'target_amount': float(d.get('target_amount', 0)),
                'target_date': str(d.get('target_date', ''))
            })
        return savings
    except Exception as e:
        print(f"[Firestore Error] _fetch_savings: {e}")
        return []

def _fetch_study(uid, days=60):
    """Returns list of {date: str, duration_minutes: int} dicts"""
    try:
        db = _get_db()
        start_date = datetime.now() - timedelta(days=days)
        study = []
        for doc in db.collection('study_records').where('uid', '==', uid).stream():
            d = doc.to_dict()
            try:
                dt = pd.to_datetime(d.get('date'))
                if dt >= start_date:
                    study.append({
                        'date': str(dt.date()),
                        'duration_minutes': int(d.get('duration_minutes', 0))
                    })
            except Exception:
                pass
        return study
    except Exception as e:
        print(f"[Firestore Error] _fetch_study: {e}")
        return []

def _fetch_fitness(uid, days=60):
    """Returns list of {date: str, duration_minutes: int, activity_type: str} dicts"""
    try:
        db = _get_db()
        start_date = datetime.now() - timedelta(days=days)
        fitness = []
        for doc in db.collection('fitness_records').where('uid', '==', uid).stream():
            d = doc.to_dict()
            try:
                dt = pd.to_datetime(d.get('date'))
                if dt >= start_date:
                    fitness.append({
                        'date': str(dt.date()),
                        'duration_minutes': int(d.get('duration_minutes', 0)),
                        'activity_type': str(d.get('activity_type', 'Other'))
                    })
            except Exception:
                pass
        return fitness
    except Exception as e:
        print(f"[Firestore Error] _fetch_fitness: {e}")
        return []

def _fetch_habits(uid):
    """Returns list of {id, name, category, current_streak, is_active, frequency} dicts"""
    try:
        db = _get_db()
        habits = []
        for doc in db.collection('habits').where('uid', '==', uid).stream():
            d = doc.to_dict()
            habits.append({
                'id': doc.id,
                'name': str(d.get('name', '')),
                'category': str(d.get('category', 'Other')),
                'current_streak': int(d.get('current_streak', 0)),
                'is_active': bool(d.get('is_active', True)),
                'frequency': str(d.get('frequency', 'daily'))
            })
        return habits
    except Exception as e:
        print(f"[Firestore Error] _fetch_habits: {e}")
        return []

def _fetch_goals(uid):
    """Returns list of {title, category, status, priority, target_date, progress_percentage} dicts"""
    try:
        db = _get_db()
        goals = []
        for doc in db.collection('goals').where('uid', '==', uid).stream():
            d = doc.to_dict()
            goals.append({
                'title': str(d.get('title', '')),
                'category': str(d.get('category', 'Other')),
                'status': str(d.get('status', 'active')),
                'priority': str(d.get('priority', 'medium')),
                'target_date': str(d.get('target_date', '')),
                'progress_percentage': float(d.get('progress_percentage', 0))
            })
        return goals
    except Exception as e:
        print(f"[Firestore Quota Warning] _fetch_goals falling back: {e}")
        return []



def _fetch_user_profile(uid):
    """Returns dict with occupation, date_of_birth keys"""
    try:
        db = _get_db()
        doc = db.collection('users').document(uid).get()
        if doc.exists:
            d = doc.to_dict()
            return {'occupation': d.get('occupation', 'unknown'), 'date_of_birth': d.get('date_of_birth', '')}
    except Exception as e:
        print(f"[Firestore Quota Warning] _fetch_user_profile falling back: {e}")
    return {'occupation': 'unknown', 'date_of_birth': ''}


# ──────────────────────────────────────────────────────────────────────────────
# 2. FINANCE SIMULATOR
# ──────────────────────────────────────────────────────────────────────────────

class FinanceSimulator:
    def __init__(self, expenses: list, income: list, savings: list, scenario_delta: dict = None):
        self.expenses = expenses
        self.income = income
        self.savings = savings
        self.scenario_delta = scenario_delta or {}
        
        # Scenario deltas
        self.income_delta_pct = self.scenario_delta.get('income_delta_pct', 0.0)
        self.expense_category_deltas = self.scenario_delta.get('expense_category_deltas', {})
        self.one_time_shock = self.scenario_delta.get('one_time_shock', 0.0)
        self.shock_day = self.scenario_delta.get('shock_day', 30)

        # Baseline stats
        self._monthly_income = self._calculate_monthly_income()
        self._category_avgs = self._monthly_avg_by_category()
        
    def _calculate_monthly_income(self):
        if not self.income: return 0.0
        df = pd.DataFrame(self.income)
        df['date'] = pd.to_datetime(df['date'])
        days = (df['date'].max() - df['date'].min()).days
        days = max(days, 30)
        return (df['amount'].sum() / days) * 30.0

    def _monthly_avg_by_category(self):
        """Returns dict {category: avg_monthly_amount}"""
        if not self.expenses: return {}
        df = pd.DataFrame(self.expenses)
        df['date'] = pd.to_datetime(df['date'])
        days = (df['date'].max() - df['date'].min()).days
        days = max(days, 30)
        
        cat_sums = df.groupby('category')['amount'].sum()
        return {cat: float((total / days) * 30.0) for cat, total in cat_sums.items()}
        
    def _current_balance(self):
        """Estimate current balance = total_income - total_expense"""
        inc_sum = sum(i['amount'] for i in self.income)
        exp_sum = sum(e['amount'] for e in self.expenses)
        return inc_sum - exp_sum

    def run_cashflow(self, horizon_days=90):
        """Deterministic cash-flow simulation."""
        # Calculate daily averages
        base_daily_income = self._monthly_income / 30.0
        scenario_daily_income = base_daily_income * (1.0 + self.income_delta_pct)
        
        scenario_daily_expenses = 0.0
        category_breakdown = {}
        for cat, amt in self._category_avgs.items():
            delta = self.expense_category_deltas.get(cat, 0.0)
            cat_daily = (amt * (1.0 + delta)) / 30.0
            scenario_daily_expenses += cat_daily
            category_breakdown[cat] = round(cat_daily * horizon_days, 2)

        daily_balance_history = []
        current_bal = self._current_balance()
        today = datetime.now().date()
        
        total_income_sim = 0.0
        total_expense_sim = 0.0

        # Run day-by-day
        for day_idx in range(horizon_days):
            inc = scenario_daily_income
            exp = scenario_daily_expenses
            
            if day_idx == self.shock_day:
                exp -= self.one_time_shock # one_time_shock is usually negative, so -(-x) = +x expense
                
            current_bal += inc - exp
            total_income_sim += inc
            total_expense_sim += exp
            
            date_str = str(today + timedelta(days=day_idx))
            daily_balance_history.append({
                'date': date_str,
                'balance': current_bal,
                'income': inc,
                'expense': exp
            })
            
        # Target hit
        target_hit = False
        target_date = None
        
        target_amount = sum(s['target_amount'] for s in self.savings if 'target_amount' in s)
        if target_amount > 0:
            for day_data in daily_balance_history:
                if day_data['balance'] >= target_amount:
                    target_hit = True
                    target_date = day_data['date']
                    break

        return {
            'daily_balance': daily_balance_history,
            'total_income': total_income_sim,
            'total_expense': total_expense_sim,
            'net_change': total_income_sim - total_expense_sim,
            'category_breakdown': category_breakdown,
            'savings_target_hit': target_hit,
            'savings_target_date': target_date
        }


    def run_monte_carlo(self, horizon_days=90, n_runs=1000):
        """Monte Carlo simulation."""
        if not self.expenses:
            return {
                'dates': [str(datetime.now().date() + timedelta(days=i)) for i in range(horizon_days)],
                'p5': [0]*horizon_days, 'p25': [0]*horizon_days, 'p50': [0]*horizon_days, 
                'p75': [0]*horizon_days, 'p95': [0]*horizon_days,
                'prob_shortfall': 0.0, 'prob_goal_achieved': 0.0
            }
            
        # Compute daily stats
        df = pd.DataFrame(self.expenses)
        df['date'] = pd.to_datetime(df['date'])
        daily_sums = df.groupby('date')['amount'].sum()
        
        base_mu = daily_sums.mean() if not daily_sums.empty else 0.0
        base_sigma = daily_sums.std() if not daily_sums.empty and len(daily_sums)>1 else (base_mu * 0.2)
        
        # Apply scenario deltas to mu
        avg_delta = np.mean(list(self.expense_category_deltas.values())) if self.expense_category_deltas else 0.0
        mu = base_mu * (1.0 + avg_delta)
        sigma = base_sigma

        # Vectorized simulation: shape (n_runs, horizon_days)
        sim_expenses = np.random.normal(loc=mu, scale=max(sigma, 1.0), size=(n_runs, horizon_days))
        sim_expenses = np.maximum(sim_expenses, 0)  # No negative expenses
        
        # Apply shock
        if self.one_time_shock != 0 and 0 <= self.shock_day < horizon_days:
            sim_expenses[:, self.shock_day] -= self.one_time_shock

        base_daily_income = self._monthly_income / 30.0
        scenario_daily_income = base_daily_income * (1.0 + self.income_delta_pct)
        sim_income = np.full((n_runs, horizon_days), scenario_daily_income)

        # Net daily change
        net_daily = sim_income - sim_expenses
        
        # Cumulative balance
        current_bal = self._current_balance()
        balances = current_bal + np.cumsum(net_daily, axis=1)

        # Calculate percentiles
        p5 = np.percentile(balances, 5, axis=0)
        p25 = np.percentile(balances, 25, axis=0)
        p50 = np.percentile(balances, 50, axis=0)
        p75 = np.percentile(balances, 75, axis=0)
        p95 = np.percentile(balances, 95, axis=0)
        
        # Realistic Shortfall Risk:
        # Evaluates 3 distinct dimensions of personal financial risk:
        # 1. Monthly Operating Deficit: spending exceeds income in any 30-day window (requires burning savings/borrowing)
        # 2. Capital Drawdown / Net Wealth Drain: ending balance drops below starting balance (net deficit over horizon)
        # 3. Liquidity Safety Reserve Breach: balances dip below emergency reserve threshold or suffer insolvency
        n_windows = max(1, horizon_days // 30)
        has_monthly_deficit = np.zeros(n_runs, dtype=bool)
        for w in range(n_windows):
            w_start = w * 30
            w_end = min((w + 1) * 30, horizon_days)
            w_exp = np.sum(sim_expenses[:, w_start:w_end], axis=1)
            w_inc = np.sum(sim_income[:, w_start:w_end], axis=1)
            has_monthly_deficit |= (w_exp > w_inc)

        monthly_exp = max(20000.0, float(np.mean(sim_expenses) * 30.0))
        emergency_buffer = min(current_bal * 0.75, monthly_exp)

        buffer_breached = np.any(balances < emergency_buffer, axis=1)
        insolvent = np.any(balances < 0, axis=1)
        net_drain = (balances[:, -1] < current_bal)

        prob_deficit = float(np.mean(has_monthly_deficit))
        prob_drain = float(np.mean(net_drain))
        prob_buffer_breach = float(np.mean(buffer_breached))
        prob_insolvency = float(np.mean(insolvent))

        # Composite Shortfall Probability
        prob_shortfall = float(np.clip(
            prob_insolvency * 1.0 +
            (1.0 - prob_insolvency) * (prob_deficit * 0.60 + prob_buffer_breach * 0.20 + prob_drain * 0.20),
            0.0, 1.0
        ))
        
        target_amount = sum(s['target_amount'] for s in self.savings if 'target_amount' in s)
        prob_goal_achieved = 0.0
        if target_amount > 0:
            prob_goal_achieved = np.mean(np.any(balances >= target_amount, axis=1))

        dates = [str(datetime.now().date() + timedelta(days=i)) for i in range(horizon_days)]

        # Sample cloud points for dispersion scatter plot (40 runs sampled across 6 milestone days)
        sample_days = [int(d) for d in np.linspace(max(1, horizon_days // 6), horizon_days - 1, 6)]
        cloud_points = []
        sample_run_indices = np.linspace(0, n_runs - 1, 40, dtype=int)
        for r_idx in sample_run_indices:
            for d_idx in sample_days:
                val = round(float(balances[r_idx, d_idx]), 2)
                cloud_points.append({
                    'x': int(d_idx + 1),
                    'y': val,
                    'is_negative': bool(val < emergency_buffer)
                })

        return {
            'dates': dates,
            'p5': p5.tolist(),
            'p25': p25.tolist(),
            'p50': p50.tolist(),
            'p75': p75.tolist(),
            'p95': p95.tolist(),
            'prob_shortfall': float(prob_shortfall),
            'prob_goal_achieved': float(prob_goal_achieved),
            'sample_cloud': cloud_points
        }


# ──────────────────────────────────────────────────────────────────────────────
# 3. PRODUCTIVITY SIMULATOR
# ──────────────────────────────────────────────────────────────────────────────

class ProductivitySimulator:
    def __init__(self, study: list, fitness: list, user_profile: dict, scenario_delta: dict = None):
        self.study = study
        self.fitness = fitness
        self.user_profile = user_profile
        self.scenario_delta = scenario_delta or {}
        
        self.study_delta_mins = self.scenario_delta.get('study_delta_mins_per_day', 0)
        self.fitness_delta_mins = self.scenario_delta.get('fitness_delta_mins_per_day', 0)
        self.sleep_hours = self.scenario_delta.get('sleep_hours', 7)
        
        default_work = 0 if user_profile.get('occupation', '').lower() == 'student' else 8
        self.work_hours = self.scenario_delta.get('work_hours', default_work)

    def _avg_daily_study(self, days=14):
        if not self.study: return 0.0
        df = pd.DataFrame(self.study)
        df['date'] = pd.to_datetime(df['date'])
        cutoff = df['date'].max() - pd.Timedelta(days=days)
        recent = df[df['date'] > cutoff]
        if recent.empty: return 0.0
        return recent['duration_minutes'].sum() / days

    def _avg_daily_fitness(self, days=14):
        if not self.fitness: return 0.0
        df = pd.DataFrame(self.fitness)
        df['date'] = pd.to_datetime(df['date'])
        cutoff = df['date'].max() - pd.Timedelta(days=days)
        recent = df[df['date'] > cutoff]
        if recent.empty: return 0.0
        return recent['duration_minutes'].sum() / days

    def run_time_budget(self):
        """Compute daily time allocation."""
        total_minutes = 1440
        meals_commute_mins = 90 + 60
        fixed_minutes = (self.sleep_hours * 60) + (self.work_hours * 60) + meals_commute_mins
        available_minutes = total_minutes - fixed_minutes
        
        current_study_mins = self._avg_daily_study(days=7)
        current_fitness_mins = self._avg_daily_fitness(days=7)
        
        scenario_study_mins = current_study_mins + self.study_delta_mins
        scenario_fitness_mins = current_fitness_mins + self.fitness_delta_mins
        
        allocated = scenario_study_mins + scenario_fitness_mins
        leisure_minutes = available_minutes - allocated
        
        is_feasible = leisure_minutes >= 0
        overload_minutes = int(abs(leisure_minutes)) if not is_feasible else 0
        
        return {
            'total_minutes': total_minutes,
            'fixed_minutes': int(fixed_minutes),
            'available_minutes': int(available_minutes),
            'current_study_mins': float(current_study_mins),
            'current_fitness_mins': float(current_fitness_mins),
            'scenario_study_mins': float(scenario_study_mins),
            'scenario_fitness_mins': float(scenario_fitness_mins),
            'leisure_minutes': float(leisure_minutes),
            'is_feasible': bool(is_feasible),
            'overload_minutes': int(overload_minutes)
        }

    def run_constraint_optimization(self):
        """scipy.optimize.linprog: find optimal study+fitness allocation."""
        fixed_mins = (self.sleep_hours * 60) + (self.work_hours * 60) + 150 # meals+commute
        available = 1440 - fixed_mins
        
        # maximize: study + fitness -> minimize: -study - fitness
        c = [-1, -1]
        
        # A_ub * x <= b_ub
        # study + fitness <= available
        A_ub = [[1, 1]]
        b_ub = [available]
        
        # Bounds: study <= 360, fitness <= 120
        x0_bounds = (0, 360)
        x1_bounds = (0, 120)
        
        res = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=[x0_bounds, x1_bounds])
        
        opt_study = float(res.x[0]) if res.success else 0.0
        opt_fitness = float(res.x[1]) if res.success else 0.0
        opt_leisure = float(available - opt_study - opt_fitness)
        
        return {
            'optimal_study_mins': float(opt_study),
            'optimal_fitness_mins': float(opt_fitness),
            'optimal_leisure_mins': float(opt_leisure),
            'max_achievable_study_hrs': float(opt_study / 60.0)
        }

    def run_forecast(self, horizon_days=90):
        """Project weekly study hours over horizon."""
        current_study_mins = self._avg_daily_study(days=7)
        scenario_study_mins = current_study_mins + self.study_delta_mins
        
        weeks = horizon_days // 7
        dates = [str(datetime.now().date() + timedelta(days=i*7)) for i in range(weeks)]
        
        baseline_hrs = [(current_study_mins * 7) / 60.0] * weeks
        
        # Add slight seasonality/improvement trend
        trend = np.linspace(1.0, 1.1, weeks)
        scenario_hrs = [((scenario_study_mins * 7) / 60.0) * t for t in trend]
        
        weekly_gain = scenario_hrs[-1] - baseline_hrs[-1] if weeks > 0 else 0.0
        
        return {
            'dates': dates,
            'baseline_hrs': [float(x) for x in baseline_hrs],
            'scenario_hrs': [float(x) for x in scenario_hrs],
            'weekly_gain_hrs': float(weekly_gain),
            'hours_to_goal': None
        }


# ──────────────────────────────────────────────────────────────────────────────
# 4. HABIT SIMULATOR
# ──────────────────────────────────────────────────────────────────────────────

class HabitSimulator:
    STATES = ['MISSED', 'OCCASIONAL', 'REGULAR', 'CONSISTENT']
    
    def __init__(self, habits: list, scenario_delta: dict = None):
        self.habits = habits
        self.scenario_delta = scenario_delta or {}
        
    def _estimate_state(self, habit: dict) -> int:
        """Estimate current state index (0-3) from current_streak."""
        streak = habit.get('current_streak', 0)
        if streak == 0: return 0
        if 1 <= streak <= 3: return 1
        if 4 <= streak <= 10: return 2
        return 3

    def _build_transition_matrix(self, habit: dict, intervention: str = 'none', discipline_delta: float = 0.0) -> np.ndarray:
        """Build 4x4 row-stochastic transition matrix with intervention and discipline modifiers."""
        # Base
        P = np.array([
            [0.60, 0.30, 0.08, 0.02],
            [0.25, 0.45, 0.25, 0.05],
            [0.05, 0.20, 0.55, 0.20],
            [0.02, 0.05, 0.18, 0.75]
        ])
        
        # Interventions boost transition to higher habit consistency states
        boost = 0.0
        if intervention == 'reminder': boost = 0.14
        elif intervention == 'partner': boost = 0.22
        elif intervention == 'stacking': boost = 0.28
        
        total_effect = boost + discipline_delta
        if total_effect > 0:
            b = min(0.40, total_effect)
            P[0, 1] += b * 0.5
            P[0, 2] += b * 0.3
            P[0, 3] += b * 0.2
            P[0, 0] = max(0.05, P[0, 0] - b)
            
            P[1, 2] += b * 0.5
            P[1, 3] += b * 0.3
            P[1, 1] = max(0.05, P[1, 1] - b * 0.6)
            P[1, 0] = max(0.05, P[1, 0] - b * 0.2)
            
            P[2, 3] += b * 0.6
            P[2, 2] = max(0.1, P[2, 2] - b * 0.4)
            P[2, 1] = max(0.05, P[2, 1] - b * 0.2)
            
            P[3, 3] = min(0.96, P[3, 3] + b * 0.2)
            P[3, 2] = max(0.03, P[3, 2] - b * 0.1)
        elif total_effect < 0:
            p = min(0.40, abs(total_effect))
            P[3, 3] = max(0.35, P[3, 3] - p * 0.6)
            P[3, 1] += p * 0.4
            P[3, 0] += p * 0.2
            
            P[2, 3] = max(0.05, P[2, 3] - p * 0.5)
            P[2, 1] += p * 0.3
            P[2, 0] += p * 0.3
            P[2, 2] = max(0.15, P[2, 2] - p * 0.1)
            
            P[1, 0] = min(0.70, P[1, 0] + p * 0.4)
            P[1, 2] = max(0.05, P[1, 2] - p * 0.3)
            
        # Normalize rows to guarantee valid probabilities
        P = P / P.sum(axis=1, keepdims=True)
        return P

    def run_markov_forecast(self, habit: dict, horizon_days=90, n_runs=300) -> dict:
        """
        Vectorized Monte Carlo over Markov Chain.
        All n_runs simulated simultaneously using numpy array ops — no Python loop over runs.
        ~40-60x faster than sequential version, same accuracy at n_runs=300.
        """
        start_state = self._estimate_state(habit)
        interventions = self.scenario_delta.get('habit_interventions', {})
        default_intervention = self.scenario_delta.get('habit_intervention_default', 'none')
        intervention = interventions.get(habit.get('id'), default_intervention)
        discipline_delta = float(self.scenario_delta.get('habit_discipline_delta', 0.0))

        P = self._build_transition_matrix(habit, intervention, discipline_delta=discipline_delta)
        cum_P = np.cumsum(P, axis=1)  # (4,4) cumulative — for fast random state lookup

        # ── Vectorized streak simulation ───────────────────────────────────
        # Pre-generate ALL random numbers at once: shape (n_runs, horizon_days)
        rand_nums = np.random.random((n_runs, horizon_days))

        states  = np.full(n_runs, start_state, dtype=np.int8)
        streaks = np.full(n_runs, habit.get('current_streak', 0), dtype=np.int32)
        streaks_30 = np.zeros(n_runs, dtype=np.int32)
        streaks_90 = np.zeros(n_runs, dtype=np.int32)

        for day in range(horizon_days):
            # cum_P[states] picks the right row per run: shape (n_runs, 4)
            thresholds = cum_P[states]                              # (n_runs, 4)
            rands      = rand_nums[:, day:day+1]                   # (n_runs, 1)
            states     = (rands < thresholds).argmax(axis=1).astype(np.int8)

            streaks = np.where(states > 0, streaks + 1, 0)

            if day == 29: streaks_30 = streaks.copy()
            if day == 89: streaks_90 = streaks.copy()

        # ── State distribution via matrix power (exact, instant) ───────────
        weeks = horizon_days // 7
        dates = [str(datetime.now().date() + timedelta(days=i*7)) for i in range(weeks)]
        P7 = np.linalg.matrix_power(P, 7)   # 1-week transition

        p_consistent = []
        p_missed     = []
        dist = np.zeros(4)
        dist[start_state] = 1.0
        for _ in range(weeks):
            dist = dist @ P7
            p_missed.append(float(dist[0]))
            p_consistent.append(float(dist[3]))

        prob_habit_formed = p_consistent[-1] if p_consistent else 0.0

        return {
            'habit_id':              habit.get('id', 'new'),
            'habit_name':            habit.get('name', 'New Habit'),
            'current_state':         self.STATES[start_state],
            'current_streak':        habit.get('current_streak', 0),
            'dates':                 dates,
            'p_consistent':          p_consistent,
            'p_missed':              p_missed,
            'expected_streak_day30': float(np.mean(streaks_30)) if len(streaks_30) else 0.0,
            'expected_streak_day90': float(np.mean(streaks_90)) if len(streaks_90) else 0.0,
            'prob_habit_formed':     float(prob_habit_formed),
            'days_to_consistent':    30.0 if prob_habit_formed > 0.5 else None,
        }


    def run_all_habits(self, horizon_days=90) -> list:
        results = []
        for h in self.habits:
            if h.get('is_active', True):
                results.append(self.run_markov_forecast(h, horizon_days))
        return results

    def simulate_new_habit(self, frequency: str = 'daily', intervention: str = 'reminder') -> dict:
        habit = {
            'id': 'new_simulated',
            'name': 'Simulated New Habit',
            'current_streak': 0,
            'frequency': frequency
        }
        self.scenario_delta['habit_interventions'] = {'new_simulated': intervention}
        return self.run_markov_forecast(habit)


# ──────────────────────────────────────────────────────────────────────────────
# 5. CROSS-DOMAIN COUPLER
# ──────────────────────────────────────────────────────────────────────────────

class CrossDomainCoupler:
    def __init__(self, finance_sim: FinanceSimulator, productivity_sim: ProductivitySimulator, habit_sim: HabitSimulator):
        self.finance_sim = finance_sim
        self.productivity_sim = productivity_sim
        self.habit_sim = habit_sim

    def compute_financial_stress_score(self) -> float:
        """stress = std(last30d_expenses) / mean(monthly_income)"""
        expenses = self.finance_sim.expenses
        if not expenses: return 0.0
        df = pd.DataFrame(expenses)
        df['date'] = pd.to_datetime(df['date'])
        recent = df[df['date'] > pd.Timestamp.now() - pd.Timedelta(days=30)]
        if recent.empty: return 0.0
        
        daily = recent.groupby('date')['amount'].sum()
        std_exp = daily.std() if len(daily) > 1 else 0.0
        
        monthly_inc = self.finance_sim._monthly_income
        if monthly_inc <= 0: return 1.0
        
        stress = std_exp / (monthly_inc / 30.0)
        return float(np.clip(stress, 0.0, 1.0))

    def compute_free_time_hours(self) -> float:
        """Free time = 24 - sleep - work - avg_study_hrs - avg_fitness_hrs"""
        tb = self.productivity_sim.run_time_budget()
        return tb['leisure_minutes'] / 60.0

    def compute_coupling_adjustments(self) -> dict:
        stress = self.compute_financial_stress_score()
        free_time = self.compute_free_time_hours()
        
        adj = {
            'study_capacity_multiplier': 1.0,
            'habit_churn_adjustment': 0.0,
            'financial_habit_feasibility': 1.0
        }
        
        if stress > 0.7:
            adj['study_capacity_multiplier'] = 0.75
            adj['habit_churn_adjustment'] += 0.15
        elif stress > 0.4:
            adj['study_capacity_multiplier'] = 0.90
            adj['habit_churn_adjustment'] += 0.05
            
        if free_time < 2.0:
            adj['habit_churn_adjustment'] += 0.10
            
        return adj

    def compute_life_balance_score(self, finance_result: dict, productivity_result: dict, habit_results: list) -> dict:
        # Financial Health
        shortfall_prob = finance_result.get('monte_carlo', {}).get('prob_shortfall', 0.0)
        net_change = finance_result.get('cashflow', {}).get('net_change', 0.0)
        fin_score = 100 * (1.0 - shortfall_prob)
        if net_change < 0: fin_score *= 0.8
        
        # Productivity
        forecast = productivity_result.get('forecast', {})
        weekly_study_hrs = forecast.get('scenario_hrs', [0])[-1] if forecast.get('scenario_hrs') else 0
        prod_score = min(100.0, (weekly_study_hrs / 14.0) * 100.0)
        
        # Habit Consistency
        if habit_results:
            avg_prob = np.mean([h.get('prob_habit_formed', 0) for h in habit_results])
            habit_score = avg_prob * 100.0
        else:
            habit_score = 0.0
            
        # Physical Fitness
        tb = productivity_result.get('time_budget', {})
        fit_mins = tb.get('scenario_fitness_mins', 0.0)
        fit_score = min(100.0, (fit_mins / 60.0) * 100.0)
        
        scores = [float(fin_score), float(prod_score), float(habit_score), float(fit_score)]
        
        return {
            'labels': ['Financial Health', 'Productivity', 'Habit Consistency', 'Physical Fitness'],
            'baseline': scores,
            'scenario': scores
        }


# ──────────────────────────────────────────────────────────────────────────────
# 6. RECOMMENDATION ENGINE
# ──────────────────────────────────────────────────────────────────────────────

class RecommendationEngine:
    def __init__(self, finance_result: dict, productivity_result: dict, 
                 habit_results: list, coupling: dict, goals: list,
                 data_quality: dict):
        self.finance_result = finance_result
        self.productivity_result = productivity_result
        self.habit_results = habit_results
        self.coupling = coupling
        self.goals = goals
        self.data_quality = data_quality

    def _confidence_from_history_days(self, days: int) -> tuple:
        if days >= 90: return ('high', '90+ days of data')
        if days >= 30: return ('medium', '30-89 days of data')
        return ('low', 'Less than 30 days of data')

    def generate_recommendations(self) -> list:
        recs = []
        
        if not self.data_quality.get('has_user_data', True):
            recs.append({
                'id': 'onboard_1', 'domain': 'setup',
                'title': 'Initialize Your Digital Twin',
                'description': 'Log your income, expenses, study hours, or habits to calculate personalized simulations.',
                'impact': 'high', 'confidence': 'low', 'confidence_reason': 'No personal data recorded yet',
                'priority_score': 1.0, 'action_url': '/dashboard'
            })

        # Finance Rules
        mc = self.finance_result.get('monte_carlo', {})
        cf = self.finance_result.get('cashflow', {})
        conf_str, conf_reason = self._confidence_from_history_days(self.data_quality['expense_days'])
        
        if mc.get('prob_shortfall', 0) > 0.3:
            recs.append({
                'id': 'fin_1', 'domain': 'finance',
                'title': 'High Risk of Shortfall',
                'description': 'Reduce discretionary spending immediately to avoid negative balance.',
                'impact': 'high', 'confidence': conf_str, 'confidence_reason': conf_reason,
                'priority_score': 0.9, 'action_url': '/expenses'
            })
            
        if cf.get('net_change', 0) < 0:
            recs.append({
                'id': 'fin_2', 'domain': 'finance',
                'title': 'Negative Cashflow Trend',
                'description': 'Your projected expenses exceed income over the simulation horizon.',
                'impact': 'high', 'confidence': conf_str, 'confidence_reason': conf_reason,
                'priority_score': 0.8, 'action_url': '/expenses'
            })
            
        if cf.get('savings_target_hit'):
            recs.append({
                'id': 'fin_3', 'domain': 'finance',
                'title': 'Savings Target on Track',
                'description': f"You are projected to hit your savings target by {cf['savings_target_date']}.",
                'impact': 'medium', 'confidence': conf_str, 'confidence_reason': conf_reason,
                'priority_score': 0.5, 'action_url': '/savings'
            })
            
        # Study Rules
        tb = self.productivity_result.get('time_budget', {})
        fc = self.productivity_result.get('forecast', {})
        conf_str, conf_reason = self._confidence_from_history_days(self.data_quality['study_days'])
        
        if fc.get('weekly_gain_hrs', 0) < 0:
            recs.append({
                'id': 'stu_1', 'domain': 'study',
                'title': 'Declining Study Trend',
                'description': 'Your study hours are projected to drop. Consider schedule adjustments.',
                'impact': 'medium', 'confidence': conf_str, 'confidence_reason': conf_reason,
                'priority_score': 0.7, 'action_url': '/study'
            })
            
        if not tb.get('is_feasible', True):
            recs.append({
                'id': 'stu_2', 'domain': 'study',
                'title': 'Infeasible Schedule',
                'description': f"You are overloaded by {tb.get('overload_minutes', 0)} mins. Reallocate time.",
                'impact': 'high', 'confidence': conf_str, 'confidence_reason': conf_reason,
                'priority_score': 0.85, 'action_url': '/study'
            })
            
        # Habit Rules
        conf_str, conf_reason = self._confidence_from_history_days(self.data_quality.get('habit_count', 0)*10)
        for h in self.habit_results:
            if h.get('prob_habit_formed', 1.0) < 0.3:
                recs.append({
                    'id': f"hab_{h['habit_id']}", 'domain': 'habit',
                    'title': f"Habit Risk: {h['habit_name']}",
                    'description': 'Low probability of habit formation. Add a reminder or stack with another habit.',
                    'impact': 'medium', 'confidence': conf_str, 'confidence_reason': conf_reason,
                    'priority_score': 0.75, 'action_url': '/habits'
                })
                
        # Cross-Domain Rules
        stress = self.coupling.get('financial_stress_score', 0)
        free_time = self.coupling.get('free_time_hours', 24)
        
        if stress > 0.7 and fc.get('weekly_gain_hrs', 0) < 0:
            recs.append({
                'id': 'cross_1', 'domain': 'cross-domain',
                'title': 'Financial Stress Impacting Focus',
                'description': 'High financial stress correlates with declining study. Address finances to improve focus.',
                'impact': 'high', 'confidence': 'medium', 'confidence_reason': 'Cross-domain correlation',
                'priority_score': 0.95, 'action_url': '/dashboard'
            })
            
        if free_time < 2.0:
            recs.append({
                'id': 'cross_2', 'domain': 'cross-domain',
                'title': 'Schedule Overload Warning',
                'description': 'Less than 2 hours of free time daily increases habit churn risk.',
                'impact': 'medium', 'confidence': 'high', 'confidence_reason': 'Time budget analysis',
                'priority_score': 0.7, 'action_url': '/dashboard'
            })

        recs.sort(key=lambda x: x['priority_score'], reverse=True)
        return recs

    def score_scenarios(self, scenarios: list, weights: dict = None) -> list:
        weights = weights or {'finance': 0.4, 'study': 0.3, 'habits': 0.3}
        
        for s in scenarios:
            fin_score = s['finance_result'].get('cashflow', {}).get('net_change', 0)
            fin_score = min(1.0, max(0.0, fin_score / 10000.0)) # Normalize roughly
            
            stu_score = s['productivity_result'].get('forecast', {}).get('scenario_hrs', [0])[-1]
            stu_score = min(1.0, stu_score / 20.0) # Normalize roughly
            
            hab_score = np.mean([h.get('prob_habit_formed', 0) for h in s['habit_results']]) if s['habit_results'] else 0.0
            
            s['composite_score'] = (fin_score * weights['finance']) + \
                                   (stu_score * weights['study']) + \
                                   (hab_score * weights['habits'])
                                   
        scenarios.sort(key=lambda x: x.get('composite_score', 0), reverse=True)
        return scenarios


# ──────────────────────────────────────────────────────────────────────────────
# 7. MAIN ORCHESTRATOR
# ──────────────────────────────────────────────────────────────────────────────

_user_data_cache = {}

def fetch_all_user_data(uid: str, horizon_days: int = 90) -> dict:
    """
    Fetch all Firestore user documents in PARALLEL, cached for 15 seconds.
    Uses ThreadPoolExecutor so all 8 collections are queried concurrently.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    now = datetime.now()
    cache_key = f"{uid}_{horizon_days}"
    if cache_key in _user_data_cache:
        cached_time, cached_val = _user_data_cache[cache_key]
        if (now - cached_time).total_seconds() < 15:
            return cached_val

    fetch_tasks = {
        'expenses': lambda: _fetch_expenses(uid, days=max(90, horizon_days)),
        'income':   lambda: _fetch_income(uid, days=max(90, horizon_days)),
        'savings':  lambda: _fetch_savings(uid),
        'study':    lambda: _fetch_study(uid, days=60),
        'fitness':  lambda: _fetch_fitness(uid, days=60),
        'habits':   lambda: _fetch_habits(uid),
        'goals':    lambda: _fetch_goals(uid),
        'profile':  lambda: _fetch_user_profile(uid),
    }

    data = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fn): key for key, fn in fetch_tasks.items()}
        for future in as_completed(futures):
            key = futures[future]
            try:
                data[key] = future.result()
            except Exception as e:
                print(f"[Fetch error] {key}: {e}")
                data[key] = []

    _user_data_cache[cache_key] = (now, data)
    return data


def run_simulation(uid: str, scenario: str = 'current', scenario_delta: dict = None,
                   horizon_days: int = 90, n_monte_carlo: int = 1000, fetched_data: dict = None) -> dict:
    """
    Main entry point. Fetches data, runs all simulators, returns complete result.
    """
    delta = {}
    if scenario == 'expected':
        # Normal Path: modest improvement — slightly more disciplined, +15 mins study/day
        delta = {
            'expense_category_deltas':   {'Other': 0.15},
            'study_delta_mins_per_day':  15,
            'habit_discipline_delta':    0.12,
            'habit_intervention_default': 'reminder',
        }
    elif scenario == 'best':
        # Best Case: everything improves — +30 mins study, higher income, lower spend
        delta = {
            'income_delta_pct':          0.05,
            'expense_category_deltas':   {'Other': -0.10},
            'study_delta_mins_per_day':  30,
            'habit_discipline_delta':    0.35,
            'habit_intervention_default': 'stacking',
        }
    elif scenario == 'risk':
        # Risk Event: financial shock → stress → -45 mins study, habits suffer
        delta = {
            'one_time_shock':            -50000,
            'shock_day':                 30,
            'income_delta_pct':          -0.25,
            'study_delta_mins_per_day':  -45,
            'habit_discipline_delta':    -0.30,
            'habit_intervention_default': 'none',
        }
        
    # Allow scenario_delta to be passed positionally or as dict safely
    if isinstance(scenario_delta, int) and (horizon_days == 90 or not horizon_days):
        horizon_days = scenario_delta
        scenario_delta = {}

    if isinstance(scenario_delta, dict) and scenario_delta:
        delta.update(scenario_delta)

    # Fetch data (or use cached fetched_data)
    user_data = fetched_data or fetch_all_user_data(uid, horizon_days)
    expenses = user_data['expenses']
    income = user_data['income']
    savings = user_data['savings']
    study = user_data['study']
    fitness = user_data['fitness']
    habits = user_data['habits']
    goals = user_data['goals']
    profile = user_data['profile']

    
    has_user_data = bool(expenses or income or study or fitness or habits or goals)
    dq = {
        'has_user_data': has_user_data,
        'expense_days': len(set(e['date'] for e in expenses)),
        'income_days': len(set(i['date'] for i in income)),
        'study_days': len(set(s['date'] for s in study)),
        'fitness_days': len(set(f['date'] for f in fitness)),
        'habit_count': len(habits),
        'overall_confidence': 'high' if (len(expenses) > 10 or len(study) > 5) else ('low' if not has_user_data else 'medium')
    }

    # Run simulators
    f_sim = FinanceSimulator(expenses, income, savings, scenario_delta=delta)
    f_cash = f_sim.run_cashflow(horizon_days=horizon_days)
    f_mc = f_sim.run_monte_carlo(horizon_days=horizon_days, n_runs=n_monte_carlo)
    finance_result = {'cashflow': f_cash, 'monte_carlo': f_mc}
    
    p_sim = ProductivitySimulator(study, fitness, profile, scenario_delta=delta)
    productivity_result = {
        'time_budget': p_sim.run_time_budget(),
        'forecast': p_sim.run_forecast(horizon_days=horizon_days),
        'optimization': p_sim.run_constraint_optimization()
    }
    
    h_sim = HabitSimulator(habits, scenario_delta=delta)
    habit_results = h_sim.run_all_habits(horizon_days=horizon_days)
    
    # Coupler
    coupler = CrossDomainCoupler(f_sim, p_sim, h_sim)
    cross_domain = {
        'financial_stress_score': coupler.compute_financial_stress_score(),
        'free_time_hours': coupler.compute_free_time_hours(),
        'coupling_adjustments': coupler.compute_coupling_adjustments(),
        'life_balance_score': coupler.compute_life_balance_score(finance_result, productivity_result, habit_results)
    }
    
    # Recommendations
    rec_engine = RecommendationEngine(finance_result, productivity_result, habit_results, cross_domain, goals, dq)
    recommendations = rec_engine.generate_recommendations()
    
    return {
        'scenario': scenario,
        'horizon_days': horizon_days,
        'generated_at': datetime.now().isoformat(),
        'finance': finance_result,
        'productivity': productivity_result,
        'habits': habit_results,
        'cross_domain': cross_domain,
        'recommendations': recommendations,
        'data_quality': dq
    }

def compare_scenarios(uid: str, scenarios: list = None, horizon_days: int = 90) -> dict:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if not scenarios:
        scenarios = ['current', 'expected', 'best', 'risk']

    # Fetch data ONCE, shared across all scenario runs
    user_data = fetch_all_user_data(uid, horizon_days)

    # Run all scenarios in PARALLEL
    def _run(s):
        return s, run_simulation(uid, scenario=s, scenario_delta=None,
                                 horizon_days=horizon_days, fetched_data=user_data)

    results = {}
    with ThreadPoolExecutor(max_workers=len(scenarios)) as pool:
        futures = {pool.submit(_run, s): s for s in scenarios}
        for future in as_completed(futures):
            s, res = future.result()
            results[s] = res

    fin_net  = {s: results[s]['finance']['cashflow'].get('net_change', 0) for s in scenarios}
    stu_hrs  = {s: results[s]['productivity']['forecast'].get('scenario_hrs', [0])[-1] for s in scenarios}
    hab_con  = {s: np.mean([h.get('prob_habit_formed', 0) for h in results[s]['habits']]) if results[s]['habits'] else 0.0 for s in scenarios}
    life_bal = {s: results[s]['cross_domain']['life_balance_score'].get('scenario', [0,0,0,0]) for s in scenarios}

    scen_objects = [
        {
            'name': s,
            'finance_result': results[s]['finance'],
            'productivity_result': results[s]['productivity'],
            'habit_results': results[s]['habits'],
        }
        for s in scenarios
    ]

    engine = RecommendationEngine({}, {}, [], {}, [], {})
    ranked = engine.score_scenarios(scen_objects)

    fin_shortfall = {
        s: round(float(results[s]['finance']['monte_carlo'].get('prob_shortfall', 0.0)) * 100, 1)
        for s in scenarios
    }

    return {
        'scenarios': results,
        'comparison': {
            'finance_net_change': fin_net,
            'study_weekly_hrs':   stu_hrs,
            'habit_consistency':  hab_con,
            'life_balance':       life_bal,
            'shortfall_risk':     fin_shortfall,
        },
        'ranked_scenarios': [r['name'] for r in ranked],
        'best_scenario':    ranked[0]['name'] if ranked else None,
    }

