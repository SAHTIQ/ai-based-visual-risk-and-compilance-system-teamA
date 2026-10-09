# 🌌 QUANTA — Personal Digital Twin Platform
### *AI-Powered Personal Life Intelligence, ML Forecasting & Monte Carlo Simulation Laboratory*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![Framework: Flask](https://img.shields.io/badge/Framework-Flask%203.1-green.svg)](https://flask.palletsprojects.com/)
[![Database: Firebase](https://img.shields.io/badge/Database-Firebase%20Firestore-orange.svg)](https://firebase.google.com/)
[![ML: XGBoost & Scikit--Learn](https://img.shields.io/badge/ML-XGBoost%20%7C%20Scikit--Learn-red.svg)](https://xgboost.readthedocs.io/)

---

## 📌 Abstract

**Quanta** is an AI-powered personal digital twin platform designed to help individuals understand, forecast, and optimize life decisions across five core domains: **Finance, Academics/Study, Habits, Physical Fitness, and Personal Goal Tracking**.

Unlike standard tracking applications that only log past events, Quanta creates a dynamic computational replica of the user — a **Digital Twin**. It continuously learns from past behaviour, projects future trajectories using machine learning models (XGBoost, Random Forest), conducts probabilistic Monte Carlo simulations of future scenarios, and provides interactive guidance via an integrated AI Assistant.

---

## ✨ Key Features

- **📊 Unified Personal Data Hub**: Complete CRUD lifecycle management across 11 structured Firestore collections covering income, expenses, savings, study records, academic courses, habits, fitness logs, and long-term goals.
- **📈 Machine Learning Forecasting Engine**:
  - **30-Day Expense Projection**: Powered by **XGBoost Regressor**, trained on rolling statistical features, exponential moving averages, and cyclical date encodings.
  - **7-Day Study Hour Forecast**: Powered by **Random Forest Regressor**, analyzing daily study momentum and time-series patterns.
  - **Habit Churn Risk Classifier**: **Random Forest / Logistic Regression** predicting habit abandonments before they occur.
- **🧪 Multi-Domain Scenario Simulation Laboratory**:
  - **Monte Carlo Financial Engine**: Vectorized 300-run simulation testing financial resilience, savings trajectories, and expense shock scenarios.
  - **Markov Chain Habit Evolution**: Probabilistic multi-state transition modeling predicting long-term habit adherence.
  - **Scenario Comparison**: Side-by-side evaluation of 4 trajectories (*Current Path*, *Normal Trajectory*, *Best Case*, *Risk Event Shock*).
- **💬 Quanta AI Assistant**:
  - Conversational AI powered by **Gemini / Qwen 27B** via OpenAI-compatible endpoints.
  - Equipped with **23 Firestore tools** enabling natural language querying, log creation, data analysis, and plain-English recommendations.
- **🛡️ Enterprise Privacy & Security**:
  - Full document-level UID isolation backed by Firebase Authentication.
  - Secure environment variable key management (`.env`) preventing secret leaks.

---

## 🏗 System Architecture

```
                       +-----------------------------------+
                       |         User Interface           |
                       | Bootstrap 5 + Chart.js + Jinja2   |
                       +-----------------------------------+
                                         |
                                         v
                       +-----------------------------------+
                       |        Flask Application          |
                       | Application Factory + Blueprints |
                       +-----------------------------------+
                                   /     |     \
                                  /      |      \
                                 v       v       v
           +-----------------------+  +----+  +-----------------------+
           | Firebase Admin SDK    |  | ML |  | Quanta AI Assistant   |
           | Firestore Data Engine |  | Engine| | Gemini AI + 23 Tools  |
           +-----------------------+  +----+  +-----------------------+
```

---

## 📁 Repository Structure

```
digital-twin-ai/
├── app/                          # Flask Backend Application
│   ├── __init__.py               # Application factory & Blueprint registration
│   ├── config.py                 # Configuration loader (.env binding)
│   ├── middleware/
│   │   └── auth.py               # Firebase token authentication decorator
│   ├── routes/                   # API & Page Blueprints (13 modules)
│   ├── services/                 # Firestore CRUD & AI Assistant Tool Services
│   └── utils/                    # Data validators & JSON serializers
├── datasets/                     # Synthetic & Processed Datasets (Parquet/CSV)
├── docs/                         # Comprehensive Documentation & Architecture Guides
│   ├── quanta_documentation.md   # Full project documentation & thesis specification
│   └── QUANTA_MODELS.txt         # ML model definitions & metrics
├── models/                       # Trained Machine Learning Model Artifacts (.joblib)
├── notebooks/                    # Colab / Jupyter Exploration Notebooks
├── scripts/                      # Utility, Diagnostic, & Testing Scripts
├── static/                       # Static Assets (CSS, JavaScript, Chart.js)
├── templates/                    # Jinja2 HTML Templates
├── .env.example                  # Environment Variables Template
├── .gitignore                    # Comprehensive Security & Build Exclusions
├── firebase.json                 # Firebase Hosting & Emulators Config
├── firestore.rules               # Firestore Security & Access Rules
├── generate_datasets_v2.py       # High-fidelity dataset synthesis generator
├── train_models_v2.py            # ML Model Training & Evaluation Pipeline
├── requirements.txt              # Python Dependencies
├── run.py                        # Main Application Launch Entrypoint
├── LICENSE                       # MIT Open Source License
└── README.md                     # Project Overview
```

---

## 🚀 Quick Start Guide

### Prerequisites

- **Python 3.9+** installed.
- A **Firebase Project** with:
  - **Firebase Authentication** enabled (Email/Password).
  - **Cloud Firestore Database** initialized.
  - A downloaded **Service Account Key** (`serviceAccountKey.json`).
- A **Gemini API Key** (or OpenAI-compatible key).

### 1. Clone & Set Up Environment

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/quanta.git
cd quanta

# Create virtual environment
python -m venv venv

# Activate Virtual Environment
# On Windows PowerShell:
.\venv\Scripts\Activate.ps1
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Credentials & `.env`

1. Copy the `.env.example` file to create `.env`:
   ```bash
   cp .env.example .env
   ```

2. Move your downloaded Firebase service account key into the project root as `serviceAccountKey.json`.

3. Update `.env` with your actual keys:
   ```env
   FLASK_SECRET_KEY=your-custom-super-secret-key
   FLASK_DEBUG=true

   FIREBASE_CREDENTIALS_PATH=serviceAccountKey.json
   FIREBASE_PROJECT_ID=your-firebase-project-id

   FIREBASE_API_KEY=your-firebase-api-key
   FIREBASE_AUTH_DOMAIN=your-firebase-project.firebaseapp.com
   FIREBASE_STORAGE_BUCKET=your-firebase-project.firebasestorage.app
   FIREBASE_MESSAGING_SENDER_ID=your-sender-id
   FIREBASE_APP_ID=your-app-id

   GEMINI_API_KEY=your-gemini-api-key
   GEMINI_MODEL=gemini-3.1-flash-lite
   ```

### 3. Generate Datasets & Train ML Models (Optional / First-time setup)

To generate dataset files and train the Machine Learning forecasting models:

```bash
# Generate high-fidelity synthetic datasets
python generate_datasets_v2.py

# Train XGBoost and Random Forest ML models
python train_models_v2.py
```

### 4. Run the Application

```bash
python run.py
```

Open your browser and navigate to: **`http://127.0.0.1:5000`**

---

## 🔒 Security & Privacy

> [!IMPORTANT]
> **Never commit your `.env` or `serviceAccountKey.json` to GitHub!**

This repository is pre-configured with a strict `.gitignore` that automatically excludes:
- `serviceAccountKey.json` and any private credential JSONs.
- `.env` and local environment files.
- Python `venv/` environments and `__pycache__` artifacts.
- Local IDE configs (`.vscode/`, `.idea/`).

---

## 📖 Documentation

For detailed architectural specs, mathematical foundations of Monte Carlo & Markov simulations, and feature documentation, check the [docs/quanta_documentation.md](docs/quanta_documentation.md) file.

---

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.
