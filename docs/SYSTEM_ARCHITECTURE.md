# 🌌 QUANTA — Personal Digital Twin Platform
## Comprehensive Technical Documentation & Architecture Reference

**System:** QUANTA (Digital Twin AI)  
**Version:** 3.2.0 (Production Core)  
**Stack:** Python 3.9+ / Flask 3.1 / Firebase Firestore / XGBoost & Scikit-Learn (v3) / Bootstrap 5 & Chart.js  

---

## 1. Executive Summary

**QUANTA** is an advanced personal digital twin platform. Rather than merely logging past events like conventional tracking software, QUANTA constructs an active computational replica of the user across five life dimensions:

1. **Finance & Wealth**: Incomes, expenses, savings runway, and cash flow simulations.
2. **Habits & Behavior**: Daily habit tracking, streaks, gamification XP, and ML churn prediction.
3. **Productivity & Study**: Deep work sessions, cognitive output, and 7-day trajectory forecasting.
4. **Academics**: Course enrollments, grades, credits, and SGPA/CGPA calculations.
5. **Fitness & Physical Health**: Exercise sessions, workout duration, and health scores.

By coupling a **NoSQL data layer** with **machine learning regression/classification**, **Monte Carlo simulations**, and an **autonomous conversational AI agent**, QUANTA delivers actionable personal foresight.

---

## 2. Architecture & Request Pipeline

```
[Browser / Mobile Client]
         │  (HTTPS / JWT Cookie / Auth Header)
         ▼
[Flask Web Server (run.py / app)]
   ├── Middleware: @require_auth (Firebase Admin SDK)
   ├── Template Engine: Jinja2 + Bootstrap 5 + Quanta Dark UI
   ├── Page Routes (13 Dashboards: /dashboard, /expenses, /habits, etc.)
   └── REST API Endpoints (/api/*)
         │
         ├──► [Sub-Millisecond Read Cache (_USER_CACHE / _ML_CACHE)]
         │          │ (Cache Miss)
         │          ▼
         │    [Google Cloud Firestore (11 Collections)]
         │
         ├──► [ML Inference Engine (ml_service.py - v3 Models)]
         │      ├── Finance 30-Day Expense Projection (XGBoost)
         │      ├── Study 7-Day Output Projection (XGBoost)
         │      └── Habit Churn Risk Classifier (Calibrated Ensemble)
         │
         ├──► [Simulation Lab (simulation_service.py)]
         │      ├── 300-Run Vectorized Monte Carlo Cash Flow
         │      └── Markov Chain Habit Transition Evolution
         │
         ├──► [Streak & Gamification Engine (streak_service.py)]
         │      ├── Daily Check-in & XP Accumulation (+10 XP)
         │      └── Streak Shields (Micro-Tasks) & XP Freezes
         │
         └──► [Autonomous Conversational Agent (agent.py)]
                ├── Fast Regex Intent Matcher (Instant Tool Bypass)
                ├── Router LLM (_plan)
                ├── 23 Data Tools Registry (chat_tools.py)
                └── Composer LLM (_compose) ──► Rich In-Chat UI Widgets
```

---

## 3. Technology Inventory

| Component | Technology | Role |
|---|---|---|
| **Backend Framework** | Flask 3.1 / Python 3.9+ | REST API, Jinja2 rendering, routing, middleware |
| **Authentication** | Firebase Auth (Client & Admin SDK) | Secure JWT-based user identity & tenant isolation |
| **Database** | Google Cloud Firestore | NoSQL document storage across 11 collections |
| **Machine Learning** | XGBoost 2.0+, Scikit-Learn, Joblib | Time-series regression & churn classification (v3) |
| **Simulation Engine** | NumPy & SciPy | Vectorized Monte Carlo & Markov state models |
| **LLM Gateway** | Native HTTP (Groq, HF Inference, OpenAI) | Dual-model router/composer agentic chat pipeline |
| **Performance Cache**| Thread-safe in-memory cache | Sub-millisecond response latency (<1ms) |
| **Frontend UI** | Bootstrap 5.3, Bootstrap Icons, CSS3 | Glassmorphic dark UI, mobile drawer sidebar |
| **Charts & Widgets** | Chart.js 4.x + In-Chat Dynamic Cards | Multi-axis lines, radars, donuts, progress widgets |

---

## 4. Firestore Data Model & Schema

Every document is strictly isolated by `uid`:

- `expenses`: `amount` (float), `category` (string), `date` (YYYY-MM-DD), `note` (string), `currency` (INR).
- `income`: `amount` (float), `source` (string), `date` (YYYY-MM-DD), `note` (string).
- `savings`: `amount` (float), `type` (investment/emergency/bank), `target_amount` (float), `date` (YYYY-MM-DD).
- `habits`: `name` (string), `category` (string), `frequency` (daily/weekly), `current_streak` (int), `last_completed` (YYYY-MM-DD), `streak_protected` (bool), `is_active` (bool).
- `study_records`: `subject` (string), `duration_minutes` (float), `date` (YYYY-MM-DD), `note` (string).
- `academic_courses`: `course_name` (string), `credits` (int), `grade` (string), `semester` (int).
- `fitness_records`: `activity_type` (string), `duration_minutes` (float), `calories_burned` (float), `date` (YYYY-MM-DD).
- `goals`: `title` (string), `category` (string), `status` (in-progress/completed), `target` (float), `current` (float), `progress_percentage` (float), `target_date` (YYYY-MM-DD).
- `user_streaks`: `streak_count` (int), `xp` (int), `level_title` (string), `last_checkin_date` (YYYY-MM-DD), `streak_frozen` (bool).
- `activity_history`: `action` (string), `entity_type` (string), `entity_id` (string), `summary` (string), `timestamp` (server timestamp).
- `chat_threads` & `chat_messages`: `thread_id`, `role`, `content`, `tool_calls`, `widgets`, `created_at`.

---

## 5. Machine Learning (v3 Architecture)

Located in `app/services/ml_service.py` with serialized models in `models/v3/`:

1. **Finance Forecast (`forecast_finance`)**:
   - 65-day historical expense analysis.
   - Generates lag features (1, 2, 3, 7, 14, 30 days), rolling statistics (means, standard deviations), exponential moving averages, and cyclical date features.
   - Outputs 30-day projected spending, category breakdown, trend direction, and human-readable advice.
2. **Study Momentum (`forecast_study`)**:
   - Time-series study analysis predicting upcoming 7-day study output.
   - Evaluates weekday study momentum and consistency.
3. **Habit Churn Classifier (`get_all_habit_risks`)**:
   - Predicts churn probability for active habits.
   - **Today's Completion Protection**: Habits completed today (`last_completed == today`) or shielded are automatically assigned **Low Risk** (`prob <= 0.09`), eliminating false alarms.
   - **New Habit Window**: Habits created within the past 7 days are evaluated against their actual lifetime rather than penalized with 34 artificial zero-days.

---

## 6. Monte Carlo & Scenario Simulation Laboratory

Located in `app/services/simulation_service.py`:
- Simulates 300 to 400 parallel trajectories over 30 to 180 days.
- **Scenarios**:
  - *Current Path*: Historical drift and empirical standard deviation.
  - *Normal Path*: Expected baseline trajectory.
  - *Best Case*: Enhanced savings (+15% income discipline, -10% discretionary spending).
  - *Risk Event*: Shock event testing unexpected financial liabilities.
- **Metrics Computed**: Probability of financial shortfall, probability of goal attainment, percentile fan charts (10th, 25th, 50th, 75th, 90th percentiles).

---

## 7. Autonomous Conversational AI ("Ask Your Data")

Located in `app/services/agent.py` and `app/services/chat_tools.py`:

- **Grounded Tool Architecture**: The AI is connected to 23 real-data tools. The composer LLM **never invents figures**; all numbers originate from live Firestore queries.
- **Fast Intent Routing**: Habit completions (`"i complted reading bok"`, `"done with workout"`) trigger instantaneous regex matching that bypasses the router LLM, ensuring zero-latency execution.
- **Typo Tolerance & Fuzzy Search**: Employs `difflib.get_close_matches` and token normalization so typos like `bok` resolve to `reading book`.
- **In-Chat UI Widgets**:
  - `habit_checkin_card`: Interactive confirmation showing streak flame, XP progress, and daily platform status.
  - `clarification_chips`: One-click domain pills when user queries are ambiguous.
  - `habit_risk_chart`: Visual churn distribution.
  - `cashflow_fan_widget`: Interactive Monte Carlo probability fan chart.
  - `goal_progress_widget`: Dynamic goal progress bars.
- **Mutual Exclusion**: Completing a habit automatically suppresses churn risk widgets in the same turn.

---

## 8. Gamification & Streak Mechanics

Located in `app/services/streak_service.py`:
- **Daily Check-in**: Completing habits or manual check-in advances the daily platform streak.
- **XP Progression**:
  - Level 1: *Rookie* (0–99 XP)
  - Level 2: *Explorer* (100–299 XP)
  - Level 3: *Consistent* (300–599 XP)
  - Level 4: *Achiever* (600–999 XP)
  - Level 5: *Master* (1000+ XP)
- **Shielding & Freezes**:
  - Micro-Task Shield: Perform a 2-minute micro-commitment to protect an at-risk habit.
  - Streak Freeze: Spend 30 XP to freeze an active streak for 24 hours.

---

## 9. Caching & Latency Optimization

Located in `app/services/crud_service.py`:
- In-memory thread-safe cache (`_USER_CACHE`, TTL: 90s) and ML cache (`_ML_CACHE`, TTL: 120s).
- Drops dashboard and page loading latencies from 5–20 seconds to `<1ms`.
- Automatic cache invalidation on any write (`create`, `update`, `delete`).

---

## 10. Execution & Setup Reference

```bash
# Activate environment
.\venv\Scripts\Activate.ps1

# Start Flask application with hot-reloading
python run.py
```
App is live on: `http://127.0.0.1:5000` (and `http://10.2.0.2:5000`).
