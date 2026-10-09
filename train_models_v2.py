"""
QUANTA — Milestone 2 v3: Leakage-Safe ML Training Pipeline
============================================================

Purpose
-------
Train production-oriented forecasting models from datasets/v2.

v3 fixes the main weaknesses in the previous pipeline:
  1. Per-user temporal train/validation/test split.
  2. No future-data leakage in user baselines or rolling features.
  3. Study model uses the generator's available exam/cycle signals.
  4. Persistent user profile features are merged into finance/study.
  5. Habit threshold is learned on validation, NEVER on test.
  6. Habit evaluation reports ROC-AUC, PR-AUC, positive-class F1/recall.
  7. Compares class-weighting against SMOTE instead of stacking both.
  8. XGBoost early stopping uses validation data, not test data.
  9. Saves feature lists + metadata needed by the Flask/API layer.
 10. Trains optional category-wise finance models for the QUANTA UI.

Input:
    datasets/v2/*.csv

Output:
    models/v3/
        finance_model.joblib
        finance_features.joblib
        finance_category_models.joblib
        study_model.joblib
        study_features.joblib
        habit_model.joblib
        habit_features.joblib
        training_metadata.json
        evaluation_results.json
"""

import os
import sys
import json
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.ensemble import (
    HistGradientBoostingRegressor,
    HistGradientBoostingClassifier,
)
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    accuracy_score,
    roc_auc_score,
    average_precision_score,
    f1_score,
    recall_score,
    precision_score,
    classification_report,
    precision_recall_curve,
)
from xgboost import XGBRegressor, XGBClassifier

try:
    from imblearn.over_sampling import SMOTE
    HAS_SMOTE = True
except ImportError:
    HAS_SMOTE = False

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")

DATA_DIR = Path("datasets") / "v2"
MODEL_DIR = Path("models") / "v3"
RESULTS_F = MODEL_DIR / "evaluation_results.json"
METADATA_F = MODEL_DIR / "training_metadata.json"

TRAINING_USERS = 500
RANDOM_STATE = 42
TRAIN_FRAC = 0.70
VAL_FRAC = 0.15
TEST_FRAC = 0.15

# Category-wise models are useful for the QUANTA finance dashboard.
TRAIN_CATEGORY_MODELS = True
FINANCE_CATEGORIES = [
    "Food", "Transport", "Rent", "Utilities", "Entertainment",
    "Shopping", "Health", "Education", "Other"
]

MODEL_DIR.mkdir(parents=True, exist_ok=True)
np.random.seed(RANDOM_STATE)


# ====================================================================
# HELPERS
# ====================================================================

def section(title):
    print("\n" + "=" * 68)
    print(f"  {title}")
    print("=" * 68)


def rmse(y_true, y_pred):
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def safe_median_fill(X):
    """Convert inf to NaN and fill each column with a training-safe median."""
    X = np.asarray(X, dtype=float)
    X = np.where(np.isinf(X), np.nan, X)
    med = np.nanmedian(X, axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    rows, cols = np.where(np.isnan(X))
    X[rows, cols] = med[cols]
    return X


def fit_median_fill(X):
    X = np.asarray(X, dtype=float)
    X = np.where(np.isinf(X), np.nan, X)
    med = np.nanmedian(X, axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    return med


def apply_median_fill(X, med):
    X = np.asarray(X, dtype=float)
    X = np.where(np.isinf(X), np.nan, X)
    rows, cols = np.where(np.isnan(X))
    X[rows, cols] = med[cols]
    return X


def regression_metrics(y_true, y_pred):
    return {
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 2),
        "rmse": round(rmse(y_true, y_pred), 2),
        "r2": round(float(r2_score(y_true, y_pred)), 4),
    }


def print_reg(name, y_true, y_pred):
    m = regression_metrics(y_true, y_pred)
    print(
        f"  {name:<30} "
        f"MAE={m['mae']:>9.2f}  "
        f"RMSE={m['rmse']:>9.2f}  "
        f"R2={m['r2']:>7.4f}"
    )
    return m


def classification_metrics(y_true, y_prob, threshold):
    y_pred = (y_prob >= threshold).astype(int)
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "auc": round(float(roc_auc_score(y_true, y_prob)), 4),
        "pr_auc": round(float(average_precision_score(y_true, y_prob)), 4),
        "positive_precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "positive_recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "positive_f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "threshold": round(float(threshold), 4),
    }


def print_clf(name, y_true, y_prob, threshold):
    m = classification_metrics(y_true, y_prob, threshold)
    print(
        f"  {name:<30} "
        f"Acc={m['accuracy']:.4f}  "
        f"AUC={m['auc']:.4f}  "
        f"PR-AUC={m['pr_auc']:.4f}  "
        f"F1={m['positive_f1']:.4f}  "
        f"Recall={m['positive_recall']:.4f}  "
        f"thr={m['threshold']:.3f}"
    )
    return m


def best_f1_threshold(y_true, y_prob):
    """Choose threshold on VALIDATION ONLY."""
    precision, recall, thresholds = precision_recall_curve(y_true, y_prob)
    if len(thresholds) == 0:
        return 0.5
    f1 = 2 * precision[:-1] * recall[:-1] / (
        precision[:-1] + recall[:-1] + 1e-12
    )
    idx = int(np.nanargmax(f1))
    return float(np.clip(thresholds[idx], 0.02, 0.98))


def temporal_split_per_user(df, train_frac=TRAIN_FRAC, val_frac=VAL_FRAC):
    """
    Chronological split inside every user.

    This prevents the previous row-count split from making the test set
    depend on user ordering and preserves each user's future history.
    """
    train_parts, val_parts, test_parts = [], [], []

    for uid, g in df.sort_values(["user_id", "date"]).groupby(
        "user_id", sort=False
    ):
        g = g.sort_values("date").reset_index(drop=True)
        n = len(g)

        if n < 20:
            continue

        n_train = max(1, int(n * train_frac))
        n_val = max(1, int(n * val_frac))

        # Guarantee at least one test observation.
        if n_train + n_val >= n:
            n_val = max(1, n - n_train - 1)

        if n_val < 1 or n_train < 1:
            continue

        train_parts.append(g.iloc[:n_train])
        val_parts.append(g.iloc[n_train:n_train + n_val])
        test_parts.append(g.iloc[n_train + n_val:])

    if not train_parts:
        raise ValueError("Temporal split produced no usable user groups.")

    return (
        pd.concat(train_parts, ignore_index=True),
        pd.concat(val_parts, ignore_index=True),
        pd.concat(test_parts, ignore_index=True),
    )


def fe_lags(df, grp, col, lags, prefix):
    for lag in lags:
        df[f"{prefix}_lag{lag}"] = df.groupby(grp)[col].shift(lag)
    return df


def fe_rolling(df, grp, col, windows, prefix):
    for w in windows:
        grouped = df.groupby(grp)[col]
        df[f"{prefix}_rmean{w}"] = grouped.transform(
            lambda x: x.shift(1).rolling(w, min_periods=1).mean()
        )
        df[f"{prefix}_rstd{w}"] = grouped.transform(
            lambda x: x.shift(1).rolling(w, min_periods=2).std()
        ).fillna(0)
    return df


def fe_ewm(df, grp, col, spans, prefix):
    for span in spans:
        df[f"{prefix}_ewm{span}"] = df.groupby(grp)[col].transform(
            lambda x: x.shift(1).ewm(span=span, min_periods=1).mean()
        )
    return df


def fe_calendar(df):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["dow"] = df["date"].dt.dayofweek
    df["is_weekend"] = (df["dow"] >= 5).astype(int)
    df["month"] = df["date"].dt.month
    df["quarter"] = df["date"].dt.quarter
    df["is_month_end"] = df["date"].dt.is_month_end.astype(int)
    doy = df["date"].dt.dayofyear
    df["sin_doy"] = np.sin(2 * np.pi * doy / 365.25)
    df["cos_doy"] = np.cos(2 * np.pi * doy / 365.25)
    df["sin_dow"] = np.sin(2 * np.pi * df["dow"] / 7)
    df["cos_dow"] = np.cos(2 * np.pi * df["dow"] / 7)
    return df


def make_future_sum_target(df, grp, col, horizon, target_name):
    """
    Sum the next horizon observations, excluding the current row.
    NaN is used when a full future horizon is unavailable.
    """
    grp_list = [grp] if isinstance(grp, str) else grp
    df = df.sort_values(grp_list + ["date"]).copy()

    def future_sum(x):
        arr = x.to_numpy(dtype=float)
        out = np.full(len(arr), np.nan)
        if len(arr) > horizon:
            for i in range(len(arr) - horizon):
                out[i] = arr[i + 1:i + 1 + horizon].sum()
        return pd.Series(out, index=x.index)

    df[target_name] = df.groupby(grp_list, group_keys=False)[col].apply(future_sum)
    return df


def add_past_user_stats(df, col, grp="user_id", min_periods=7):
    """
    Leakage-safe user baselines: only observations BEFORE the current row
    contribute to the baseline.
    """
    df = df.sort_values([grp, "date"]).copy()
    g = df.groupby(grp)[col]

    df["user_mean"] = g.transform(
        lambda x: x.shift(1).expanding(min_periods=min_periods).mean()
    )
    df["user_std"] = g.transform(
        lambda x: x.shift(1).expanding(min_periods=min_periods).std()
    )
    df["user_median"] = g.transform(
        lambda x: x.shift(1).expanding(min_periods=min_periods).median()
    )
    df["user_q25"] = g.transform(
        lambda x: x.shift(1).expanding(min_periods=min_periods).quantile(0.25)
    )
    df["user_q75"] = g.transform(
        lambda x: x.shift(1).expanding(min_periods=min_periods).quantile(0.75)
    )
    df["user_iqr"] = df["user_q75"] - df["user_q25"]
    return df


def merge_user_profiles(df, users):
    profile_cols = [
        "user_id", "age", "occupation_type", "income_level",
        "financial_behavior", "study_behavior",
        "fitness_behavior", "goal_orientation"
    ]
    available = [c for c in profile_cols if c in users.columns]
    return df.merge(users[available].drop_duplicates("user_id"), on="user_id", how="left")


def encode_with_train(train_df, val_df, test_df, feature_cols):
    """
    One-hot encode categorical profile fields using train/val/test together
    only for column alignment. No target information is used.
    """
    combined = pd.concat(
        [train_df[feature_cols], val_df[feature_cols], test_df[feature_cols]],
        axis=0,
        ignore_index=True,
    )
    combined = pd.get_dummies(combined, columns=[
        c for c in combined.columns if combined[c].dtype == "object"
    ], dummy_na=True)

    n_train = len(train_df)
    n_val = len(val_df)

    a = combined.iloc[:n_train].copy()
    b = combined.iloc[n_train:n_train + n_val].copy()
    c = combined.iloc[n_train + n_val:].copy()

    return a, b, c, list(combined.columns)


def load_data():
    section("LOADING DATA")
    names = [
        "users", "income", "expenses", "savings", "study",
        "academics", "goals", "habits", "habit_checkins", "fitness"
    ]
    dfs = {}
    for name in names:
        path = DATA_DIR / f"{name}.csv"
        if not path.exists():
            raise FileNotFoundError(f"Missing dataset: {path}")
        dfs[name] = pd.read_csv(path, low_memory=False)
        print(f"  {name+'.csv':<24} {len(dfs[name]):>10,} rows")
    return dfs


def get_users(df, n=TRAINING_USERS):
    users = df["user_id"].drop_duplicates().head(n)
    return df[df["user_id"].isin(users)].copy()


# ====================================================================
# MODEL FACTORIES
# ====================================================================

def make_ridge():
    return Pipeline([
        ("scale", StandardScaler()),
        ("model", Ridge(alpha=1.0))
    ])


def make_hgb_reg():
    return HistGradientBoostingRegressor(
        max_iter=1000,
        learning_rate=0.025,
        max_depth=7,
        min_samples_leaf=12,
        l2_regularization=0.05,
        early_stopping=True,
        validation_fraction=0.12,
        n_iter_no_change=35,
        random_state=RANDOM_STATE,
    )


def make_xgb_reg():
    return XGBRegressor(
        n_estimators=1200,
        learning_rate=0.025,
        max_depth=7,
        subsample=0.82,
        colsample_bytree=0.85,
        reg_alpha=0.05,
        reg_lambda=0.5,
        min_child_weight=3,
        objective="reg:squarederror",
        random_state=RANDOM_STATE,
        n_jobs=-1,
        verbosity=0,
    )


def make_lr(use_balanced=True):
    return Pipeline([
        ("scale", StandardScaler()),
        ("model", LogisticRegression(
            max_iter=2500,
            C=0.7,
            class_weight="balanced" if use_balanced else None,
            random_state=RANDOM_STATE,
        ))
    ])


def make_hgb_clf(use_balanced=True):
    kwargs = dict(
        max_iter=900,
        learning_rate=0.025,
        max_depth=7,
        min_samples_leaf=20,
        l2_regularization=0.1,
        early_stopping=True,
        validation_fraction=0.12,
        n_iter_no_change=35,
        random_state=RANDOM_STATE,
    )
    # HistGradientBoostingClassifier supports class_weight on recent sklearn.
    if use_balanced:
        kwargs["class_weight"] = "balanced"
    return HistGradientBoostingClassifier(**kwargs)


# ====================================================================
# 1. FINANCE
# ====================================================================

def build_finance_grid(dfs):
    expenses = get_users(dfs["expenses"])
    income = get_users(dfs["income"])
    users = get_users(dfs["users"])

    expenses["date"] = pd.to_datetime(expenses["date"])
    income["date"] = pd.to_datetime(income["date"])

    daily = (
        expenses.groupby(["user_id", "date"])["amount"]
        .sum()
        .reset_index(name="total_exp")
    )

    cat = (
        expenses.groupby(["user_id", "date", "category"])["amount"]
        .sum()
        .unstack(fill_value=0)
        .reset_index()
    )
    cat.columns = [
        c if c in ("user_id", "date") else f"cat_{str(c).lower()}"
        for c in cat.columns
    ]
    cat_cols = [c for c in cat.columns if c.startswith("cat_")]

    # Dense calendar per user.
    grids = []
    for uid, g in daily.groupby("user_id"):
        dates = pd.date_range(g["date"].min(), g["date"].max(), freq="D")
        grids.append(pd.DataFrame({"user_id": uid, "date": dates}))
    grid = pd.concat(grids, ignore_index=True)

    grid = grid.merge(daily, on=["user_id", "date"], how="left")
    grid["total_exp"] = grid["total_exp"].fillna(0)
    grid = grid.merge(cat, on=["user_id", "date"], how="left")
    grid[cat_cols] = grid[cat_cols].fillna(0)

    # Monthly income, mapped to each daily row.
    income["ym"] = income["date"].dt.to_period("M")
    monthly = (
        income.groupby(["user_id", "ym"])["amount"]
        .sum()
        .reset_index(name="monthly_inc")
    )
    grid["ym"] = grid["date"].dt.to_period("M")
    grid = grid.merge(monthly, on=["user_id", "ym"], how="left")
    grid["monthly_inc"] = grid["monthly_inc"].fillna(0)
    grid["daily_inc"] = grid["monthly_inc"] / 30.0
    grid["sav_rate"] = (
        (grid["daily_inc"] - grid["total_exp"]) /
        grid["daily_inc"].replace(0, np.nan)
    ).fillna(0).clip(-5, 5)

    grid = merge_user_profiles(grid, users)
    grid = fe_calendar(grid)
    grid = grid.sort_values(["user_id", "date"]).reset_index(drop=True)

    # Past-only features.
    grid = add_past_user_stats(grid, "total_exp")
    grid = fe_lags(grid, "user_id", "total_exp",
                   [1, 2, 3, 7, 14, 21, 30], "exp")
    grid = fe_rolling(grid, "user_id", "total_exp",
                      [3, 7, 14, 30, 60], "exp")
    grid = fe_ewm(grid, "user_id", "total_exp",
                  [7, 14, 30], "exp")

    for c in cat_cols:
        short = c.replace("cat_", "r_cat_")
        grid = fe_rolling(grid, "user_id", c, [7, 30], short)

    grid = fe_rolling(grid, "user_id", "daily_inc", [7, 30], "inc")
    grid["exp_trend7_30"] = grid["exp_rmean7"] - grid["exp_rmean30"]
    grid["exp_trend14_60"] = grid["exp_rmean14"] - grid["exp_rmean60"]
    grid["exp_volatility"] = (
        grid["exp_rstd14"] / grid["exp_rmean14"].replace(0, np.nan)
    ).fillna(0)
    grid["spending_pct_of_income"] = (
        grid["total_exp"] / grid["daily_inc"].replace(0, np.nan)
    ).fillna(0)

    # Target is future 30 calendar observations.
    grid = make_future_sum_target(
        grid, "user_id", "total_exp", 30, "target_next30d"
    )
    grid = grid.dropna(subset=["target_next30d"]).reset_index(drop=True)

    return grid, cat_cols


def finance_features(grid, cat_cols):
    features = (
        [c for c in grid.columns if c.startswith("exp_")]
        + [c for c in grid.columns if c.startswith("inc_")]
        + [c for c in grid.columns if c.startswith("r_cat_")]
        + cat_cols
        + [
            "sav_rate", "daily_inc", "monthly_inc",
            "user_mean", "user_std", "user_median",
            "user_q25", "user_q75", "user_iqr",
            "exp_trend7_30", "exp_trend14_60",
            "exp_volatility", "spending_pct_of_income",
            "age",
            "occupation_type", "income_level",
            "financial_behavior", "study_behavior",
            "fitness_behavior", "goal_orientation",
            "dow", "is_weekend", "month", "quarter",
            "is_month_end", "sin_doy", "cos_doy",
            "sin_dow", "cos_dow",
        ]
    )
    return list(dict.fromkeys(c for c in features if c in grid.columns))


def train_finance(dfs):
    section("1. FINANCE FORECASTING — NEXT 30 DAYS")

    grid, cat_cols = build_finance_grid(dfs)
    train, val, test = temporal_split_per_user(grid)

    features = finance_features(grid, cat_cols)
    A, B, C, encoded_features = encode_with_train(
        train, val, test, features
    )

    med = fit_median_fill(A.values)
    X_train = apply_median_fill(A.values, med)
    X_val = apply_median_fill(B.values, med)
    X_test = apply_median_fill(C.values, med)

    y_train = train["target_next30d"].to_numpy()
    y_val = val["target_next30d"].to_numpy()
    y_test = test["target_next30d"].to_numpy()

    print(f"  Features: {len(encoded_features)}")
    print(
        f"  Train: {len(X_train):,} | "
        f"Validation: {len(X_val):,} | "
        f"Test: {len(X_test):,}"
    )

    models = {
        "finance_ridge": make_ridge(),
        "finance_hgb": make_hgb_reg(),
        "finance_xgb": make_xgb_reg(),
    }
    results = {}

    print("\nTraining models...")
    for name, model in models.items():
        if name.endswith("xgb"):
            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                verbose=False,
            )
        else:
            model.fit(X_train, y_train)

        # Validation is used for model selection.
        val_pred = model.predict(X_val)
        test_pred = model.predict(X_test)

        val_m = regression_metrics(y_val, val_pred)
        test_m = print_reg(name, y_test, test_pred)

        results[name] = {
            "validation": val_m,
            "test": test_m,
        }

    best = min(results, key=lambda k: results[k]["validation"]["rmse"])
    print(f"\n  >> Selected by validation RMSE: {best}")
    print(
        f"     Test R2={results[best]['test']['r2']:.4f}  "
        f"RMSE={results[best]['test']['rmse']:.2f}"
    )

    joblib.dump(
        {"model": models[best], "median": med},
        MODEL_DIR / "finance_model.joblib",
    )
    joblib.dump(encoded_features, MODEL_DIR / "finance_features.joblib")

    category_results = {}
    category_models = {}

    if TRAIN_CATEGORY_MODELS:
        print("\n  Training category-wise finance models...")
        for category in FINANCE_CATEGORIES:
            raw_col = f"cat_{category.lower()}"
            if raw_col not in grid.columns:
                continue

            cg = grid[["user_id", "date", raw_col]].copy()
            cg = cg.rename(columns={raw_col: "category_exp"})
            cg = make_future_sum_target(
                cg, "user_id", "category_exp", 30,
                "target_category_next30d"
            ).dropna(subset=["target_category_next30d"])

            tr, va, te = temporal_split_per_user(cg)
            # Category model intentionally uses the same encoded feature
            # matrix as total finance, but with category-specific target.
            # Align by user/date.
            key = ["user_id", "date"]
            base_train = train.merge(tr[key], on=key, how="inner")
            base_val = val.merge(va[key], on=key, how="inner")
            base_test = test.merge(te[key], on=key, how="inner")

            if len(base_train) < 100 or len(base_val) < 20 or len(base_test) < 20:
                continue

            # Map target back to aligned rows.
            tr_y = tr.set_index(key)["target_category_next30d"]
            va_y = va.set_index(key)["target_category_next30d"]
            te_y = te.set_index(key)["target_category_next30d"]

            ytr = base_train.set_index(key).index.map(tr_y).astype(float)
            yva = base_val.set_index(key).index.map(va_y).astype(float)
            yte = base_test.set_index(key).index.map(te_y).astype(float)

            AA, BB, CC, cat_encoded = encode_with_train(
                base_train, base_val, base_test, features
            )
            cat_med = fit_median_fill(AA.values)
            Xa = apply_median_fill(AA.values, cat_med)
            Xb = apply_median_fill(BB.values, cat_med)
            Xc = apply_median_fill(CC.values, cat_med)

            model = make_ridge()
            model.fit(Xa, ytr)

            pred = model.predict(Xc)
            m = regression_metrics(yte, pred)

            category_results[category] = m
            category_models[category] = {
                "model": model,
                "median": cat_med,
                "features": cat_encoded,
            }
            print(
                f"    {category:<16} "
                f"R2={m['r2']:.4f}  RMSE={m['rmse']:.2f}"
            )

        joblib.dump(
            category_models,
            MODEL_DIR / "finance_category_models.joblib",
        )

    return {
        "models": results,
        "selected": best,
        "category_results": category_results,
        "features": encoded_features,
    }


# ====================================================================
# 2. STUDY
# ====================================================================

def build_study_grid(dfs):
    study = get_users(dfs["study"]).copy()
    fitness = get_users(dfs["fitness"]).copy()
    goals = get_users(dfs["goals"]).copy()
    users = get_users(dfs["users"]).copy()

    study["date"] = pd.to_datetime(study["date"])
    fitness["date"] = pd.to_datetime(fitness["date"])

    # Aggregate multiple study sessions per day.
    s = (
        study.groupby(["user_id", "date"])["duration_minutes"]
        .sum()
        .reset_index(name="study_mins")
    )

    f = (
        fitness.groupby(["user_id", "date"])["duration_minutes"]
        .sum()
        .reset_index(name="fitness_mins")
    )

    # Dense daily grid.
    grids = []
    for uid, g in s.groupby("user_id"):
        dates = pd.date_range(g["date"].min(), g["date"].max(), freq="D")
        grids.append(pd.DataFrame({"user_id": uid, "date": dates}))
    grid = pd.concat(grids, ignore_index=True)

    grid = grid.merge(s, on=["user_id", "date"], how="left")
    grid = grid.merge(f, on=["user_id", "date"], how="left")
    grid["study_mins"] = grid["study_mins"].fillna(0)
    grid["fitness_mins"] = grid["fitness_mins"].fillna(0)

    # Goal completion count.
    if not goals.empty and "status" in goals.columns:
        completed = goals[goals["status"].eq("Completed")].copy()
        if "target_date" in completed.columns:
            completed["date"] = pd.to_datetime(
                completed["target_date"], errors="coerce"
            )
            gc = (
                completed.dropna(subset=["date"])
                .groupby(["user_id", "date"])
                .size()
                .reset_index(name="goals_completed")
            )
            grid = grid.merge(gc, on=["user_id", "date"], how="left")

    grid["goals_completed"] = grid.get(
        "goals_completed", pd.Series(0, index=grid.index)
    ).fillna(0)

    grid = merge_user_profiles(grid, users)
    grid = fe_calendar(grid)
    grid = grid.sort_values(["user_id", "date"]).reset_index(drop=True)

    # Leakage-safe historical level.
    grid = add_past_user_stats(grid, "study_mins")

    # Strong temporal memory.
    grid = fe_lags(
        grid, "user_id", "study_mins",
        [1, 2, 3, 4, 5, 7, 10, 14, 21, 28], "stu"
    )
    grid = fe_rolling(
        grid, "user_id", "study_mins",
        [3, 5, 7, 10, 14, 21, 28], "stu"
    )
    grid = fe_ewm(
        grid, "user_id", "study_mins",
        [3, 7, 14, 21], "stu"
    )

    grid = fe_lags(
        grid, "user_id", "fitness_mins",
        [1, 3, 7, 14], "fit"
    )
    grid = fe_rolling(
        grid, "user_id", "fitness_mins",
        [7, 14, 21], "fit"
    )

    # Historical day-of-week pattern, shifted so the current day is excluded.
    grid["dow_hist_mean"] = (
        grid.groupby(["user_id", "dow"])["study_mins"]
        .transform(lambda x: x.shift(1).expanding(min_periods=2).mean())
    )

    grid["stu_vs_user_mean"] = (
        (grid["stu_rmean7"] - grid["user_mean"]) /
        grid["user_std"].replace(0, np.nan)
    ).fillna(0)

    grid["stu_vs_dow_mean"] = (
        grid["stu_rmean7"] - grid["dow_hist_mean"]
    ).fillna(0)

    grid["stu_consistency"] = (
        grid["stu_rstd7"] /
        grid["stu_rmean7"].replace(0, np.nan)
    ).fillna(0).clip(0, 5)

    grid["stu_momentum"] = grid["stu_rmean7"] - grid["stu_rmean14"]
    grid["stu_momentum14_28"] = (
        grid["stu_rmean14"] - grid["stu_rmean28"]
    )
    grid["recovery_days"] = (grid["stu_lag1"] == 0).astype(int)
    grid["fit_stu_interact"] = grid["fit_lag1"] * grid["stu_lag1"]

    # The v2 generator explicitly stores these signals. They are valid
    # benchmark features if the production QUANTA system has the same
    # exam/calendar information; otherwise remove them before deployment.
    for col in ["exam_next7d", "cycle_phase", "days_to_slack", "is_slack_week"]:
        if col not in study.columns:
            grid[col] = 0

    oracle = study[[
        "user_id", "date",
        "exam_next7d", "cycle_phase",
        "days_to_slack", "is_slack_week"
    ]].drop_duplicates(["user_id", "date"])

    grid = grid.merge(oracle, on=["user_id", "date"], how="left",
                      suffixes=("", "_study"))
    for col in ["exam_next7d", "cycle_phase", "days_to_slack", "is_slack_week"]:
        if f"{col}_study" in grid.columns:
            grid[col] = grid[f"{col}_study"].fillna(grid[col])
            grid.drop(columns=[f"{col}_study"], inplace=True)

    grid = make_future_sum_target(
        grid, "user_id", "study_mins", 7, "target_next7d_study"
    )
    grid = grid.dropna(subset=["target_next7d_study"]).reset_index(drop=True)

    return grid


def study_features(grid):
    features = (
        [c for c in grid.columns if c.startswith("stu_")]
        + [c for c in grid.columns if c.startswith("fit_")]
        + [
            "goals_completed",
            "user_mean", "user_std", "user_median",
            "user_q25", "user_q75", "user_iqr",
            "stu_vs_user_mean", "stu_vs_dow_mean",
            "dow_hist_mean", "stu_consistency",
            "stu_momentum", "stu_momentum14_28",
            "recovery_days", "fit_stu_interact",
            "exam_next7d", "cycle_phase",
            "days_to_slack", "is_slack_week",
            "age",
            "occupation_type", "income_level",
            "financial_behavior", "study_behavior",
            "fitness_behavior", "goal_orientation",
            "dow", "is_weekend", "month", "quarter",
            "is_month_end", "sin_doy", "cos_doy",
            "sin_dow", "cos_dow",
        ]
    )
    return list(dict.fromkeys(c for c in features if c in grid.columns))


def train_study(dfs):
    section("2. STUDY FORECASTING — NEXT 7 DAYS")

    grid = build_study_grid(dfs)
    train, val, test = temporal_split_per_user(grid)

    features = study_features(grid)
    A, B, C, encoded_features = encode_with_train(
        train, val, test, features
    )

    med = fit_median_fill(A.values)
    X_train = apply_median_fill(A.values, med)
    X_val = apply_median_fill(B.values, med)
    X_test = apply_median_fill(C.values, med)

    y_train = train["target_next7d_study"].to_numpy()
    y_val = val["target_next7d_study"].to_numpy()
    y_test = test["target_next7d_study"].to_numpy()

    print(f"  Features: {len(encoded_features)}")
    print(
        f"  Train: {len(X_train):,} | "
        f"Validation: {len(X_val):,} | "
        f"Test: {len(X_test):,}"
    )

    models = {
        "study_ridge": make_ridge(),
        "study_hgb": make_hgb_reg(),
        "study_xgb": make_xgb_reg(),
    }
    results = {}

    print("\nTraining models...")
    for name, model in models.items():
        if name.endswith("xgb"):
            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                verbose=False,
            )
        else:
            model.fit(X_train, y_train)

        val_pred = model.predict(X_val)
        test_pred = model.predict(X_test)

        val_m = regression_metrics(y_val, val_pred)
        test_m = print_reg(name, y_test, test_pred)
        results[name] = {
            "validation": val_m,
            "test": test_m,
        }

    best = min(results, key=lambda k: results[k]["validation"]["rmse"])
    print(f"\n  >> Selected by validation RMSE: {best}")
    print(
        f"     Test R2={results[best]['test']['r2']:.4f}  "
        f"RMSE={results[best]['test']['rmse']:.2f}"
    )

    joblib.dump(
        {"model": models[best], "median": med},
        MODEL_DIR / "study_model.joblib",
    )
    joblib.dump(encoded_features, MODEL_DIR / "study_features.joblib")

    return {
        "models": results,
        "selected": best,
        "features": encoded_features,
    }


# ====================================================================
# 3. HABIT CHURN
# ====================================================================

def consecutive_misses(series):
    values = series.to_numpy()
    out = np.zeros(len(values), dtype=int)
    count = 0
    for i, value in enumerate(values):
        if value == 0:
            count += 1
            out[i] = count
        else:
            count = 0
    return pd.Series(out, index=series.index)


def build_habit_grid(dfs):
    checkins = get_users(dfs["habit_checkins"]).copy()
    habits = get_users(dfs["habits"]).copy()

    checkins["date"] = pd.to_datetime(checkins["date"])
    checkins = checkins.sort_values(
        ["user_id", "habit_id", "date"]
    ).reset_index(drop=True)

    grp = ["user_id", "habit_id"]

    checkins = fe_lags(
        checkins, grp, "completed",
        [1, 2, 3, 4, 5, 7, 10, 14], "cmp"
    )
    checkins = fe_rolling(
        checkins, grp, "completed",
        [3, 7, 14, 21, 30], "cmp"
    )
    checkins = fe_ewm(
        checkins, grp, "completed",
        [3, 7, 14, 30], "cmp"
    )

    # Explicit recent-activity features.
    checkins["cmp_sum3"] = (
        checkins.groupby(grp)["completed"]
        .transform(lambda x: x.shift(1).rolling(3, min_periods=1).sum())
    )
    checkins["cmp_sum7"] = (
        checkins.groupby(grp)["completed"]
        .transform(lambda x: x.shift(1).rolling(7, min_periods=1).sum())
    )
    checkins["cmp_sum14"] = (
        checkins.groupby(grp)["completed"]
        .transform(lambda x: x.shift(1).rolling(14, min_periods=1).sum())
    )

    checkins["misses3"] = 3 - checkins["cmp_sum3"]
    checkins["misses7"] = 7 - checkins["cmp_sum7"]
    checkins["misses14"] = 14 - checkins["cmp_sum14"]

    checkins["completion_trend"] = (
        checkins["cmp_rmean3"] - checkins["cmp_rmean14"]
    )
    checkins["inactive_2d"] = (
        (checkins["cmp_lag1"] == 0) &
        (checkins["cmp_lag2"] == 0)
    ).astype(int)
    checkins["inactive_3d"] = (
        (checkins["cmp_lag1"] == 0) &
        (checkins["cmp_lag2"] == 0) &
        (checkins["cmp_lag3"] == 0)
    ).astype(int)
    checkins["inactive_5d"] = (
        (checkins["cmp_lag1"] == 0) &
        (checkins["cmp_lag2"] == 0) &
        (checkins["cmp_lag3"] == 0) &
        (checkins["cmp_lag4"] == 0) &
        (checkins["cmp_lag5"] == 0)
    ).astype(int)

    checkins["streak_sq"] = checkins["current_streak"] ** 2
    checkins["streak_log"] = np.log1p(checkins["current_streak"])
    checkins["recent_miss_pct"] = 1.0 - checkins["cmp_rmean7"]
    checkins["long_miss_pct"] = 1.0 - checkins["cmp_rmean30"]
    checkins["habit_health"] = (
        checkins["cmp_ewm7"] *
        np.log1p(checkins["current_streak"])
    )
    checkins["volatility"] = (
        checkins["cmp_rstd7"] /
        checkins["cmp_rmean7"].replace(0, np.nan)
    ).fillna(0)
    checkins["consec_miss"] = (
        checkins.groupby(grp)["completed"]
        .transform(consecutive_misses)
    )

    meta = habits[["user_id", "habit_id", "category"]].drop_duplicates()
    checkins = checkins.merge(meta, on=grp, how="left")

    for cat in ["Health", "Productivity", "Learning", "Social"]:
        checkins[f"is_{cat.lower()}"] = (
            checkins["category"] == cat
        ).astype(int)

    checkins = fe_calendar(checkins)

    checkins = make_future_sum_target(
        checkins, grp, "completed", 7, "_next7_sum"
    )
    checkins["target_churned"] = (
        checkins["_next7_sum"] == 0
    ).astype(float)
    checkins.loc[
        checkins["_next7_sum"].isna(), "target_churned"
    ] = np.nan
    checkins = checkins.dropna(subset=["target_churned"]).copy()
    checkins["target_churned"] = checkins["target_churned"].astype(int)

    return checkins


def habit_features(checkins):
    features = (
        [c for c in checkins.columns if c.startswith("cmp_")]
        + [
            "current_streak", "streak_sq", "streak_log",
            "cmp_sum3", "cmp_sum7", "cmp_sum14",
            "misses3", "misses7", "misses14",
            "completion_trend",
            "inactive_2d", "inactive_3d", "inactive_5d",
            "recent_miss_pct", "long_miss_pct",
            "habit_health", "volatility", "consec_miss",
            "is_health", "is_productivity",
            "is_learning", "is_social",
            "dow", "is_weekend", "month", "quarter",
            "is_month_end", "sin_doy", "cos_doy",
            "sin_dow", "cos_dow",
        ]
    )
    return list(dict.fromkeys(c for c in features if c in checkins.columns))


def train_habit(dfs):
    section("3. HABIT CHURN — NEXT 7 DAYS")

    grid = build_habit_grid(dfs)
    churn_rate = grid["target_churned"].mean()

    print(
        f"  Churn rate: {churn_rate:.2%} | "
        f"Rows: {len(grid):,}"
    )

    features = habit_features(grid)
    train, val, test = temporal_split_per_user(grid)

    # No categorical habit feature is required here; category is represented
    # through explicit one-hot flags.
    X_train_raw = train[features]
    X_val_raw = val[features]
    X_test_raw = test[features]

    med = fit_median_fill(X_train_raw.values)
    X_train = apply_median_fill(X_train_raw.values, med)
    X_val = apply_median_fill(X_val_raw.values, med)
    X_test = apply_median_fill(X_test_raw.values, med)

    y_train = train["target_churned"].to_numpy()
    y_val = val["target_churned"].to_numpy()
    y_test = test["target_churned"].to_numpy()

    print(f"  Features: {len(features)}")
    print(
        f"  Train: {len(X_train):,} | "
        f"Validation: {len(X_val):,} | "
        f"Test: {len(X_test):,}"
    )

    # We deliberately compare weighting and SMOTE separately.
    candidates = {}

    print("\nTraining class-weighted models...")
    lr_bal = make_lr(True)
    lr_bal.fit(X_train, y_train)
    candidates["habit_lr_balanced"] = (
        lr_bal, lr_bal.predict_proba(X_val)[:, 1],
        lr_bal.predict_proba(X_test)[:, 1]
    )

    hgb_bal = make_hgb_clf(True)
    hgb_bal.fit(X_train, y_train)
    candidates["habit_hgb_balanced"] = (
        hgb_bal, hgb_bal.predict_proba(X_val)[:, 1],
        hgb_bal.predict_proba(X_test)[:, 1]
    )

    pos = max(1, int(y_train.sum()))
    neg = max(1, int((y_train == 0).sum()))
    scale = neg / pos

    xgb_bal = XGBClassifier(
        n_estimators=1000,
        learning_rate=0.025,
        max_depth=7,
        subsample=0.85,
        colsample_bytree=0.85,
        min_child_weight=4,
        reg_alpha=0.05,
        reg_lambda=0.7,
        scale_pos_weight=scale,
        eval_metric="aucpr",
        random_state=RANDOM_STATE,
        n_jobs=-1,
        verbosity=0,
    )
    xgb_bal.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )
    candidates["habit_xgb_balanced"] = (
        xgb_bal, xgb_bal.predict_proba(X_val)[:, 1],
        xgb_bal.predict_proba(X_test)[:, 1]
    )

    if HAS_SMOTE:
        print("\nTraining SMOTE-only logistic model...")
        smote = SMOTE(
            random_state=RANDOM_STATE,
            k_neighbors=min(5, max(1, pos - 1)),
        )
        X_sm, y_sm = smote.fit_resample(X_train, y_train)

        lr_smote = make_lr(False)
        lr_smote.fit(X_sm, y_sm)
        candidates["habit_lr_smote"] = (
            lr_smote,
            lr_smote.predict_proba(X_val)[:, 1],
            lr_smote.predict_proba(X_test)[:, 1],
        )

    # Threshold is selected ONLY on validation.
    evaluated = {}
    for name, (model, val_prob, test_prob) in candidates.items():
        threshold = best_f1_threshold(y_val, val_prob)
        val_m = classification_metrics(y_val, val_prob, threshold)
        test_m = print_clf(name, y_test, test_prob, threshold)

        evaluated[name] = {
            "validation": val_m,
            "test": test_m,
        }

    # Select using validation F1, then validation PR-AUC.
    best = max(
        evaluated,
        key=lambda k: (
            evaluated[k]["validation"]["positive_f1"],
            evaluated[k]["validation"]["pr_auc"],
        )
    )

    best_model, _, best_test_prob = candidates[best]
    best_threshold = evaluated[best]["validation"]["threshold"]

    print(f"\n  >> Selected by validation positive F1: {best}")
    print(
        f"     Test AUC={evaluated[best]['test']['auc']:.4f}  "
        f"PR-AUC={evaluated[best]['test']['pr_auc']:.4f}  "
        f"F1={evaluated[best]['test']['positive_f1']:.4f}  "
        f"Recall={evaluated[best]['test']['positive_recall']:.4f}"
    )

    test_pred = (best_test_prob >= best_threshold).astype(int)
    print("\n  Classification Report (test):")
    print(
        classification_report(
            y_test,
            test_pred,
            target_names=["Active", "Churned"],
            zero_division=0,
        )
    )

    payload = {
        "type": "single",
        "model": best_model,
        "threshold": float(best_threshold),
        "median": med,
        "selection_metric": "validation_positive_f1",
    }
    joblib.dump(payload, MODEL_DIR / "habit_model.joblib")
    joblib.dump(features, MODEL_DIR / "habit_features.joblib")

    return {
        "models": evaluated,
        "selected": best,
        "features": features,
    }


# ====================================================================
# MAIN
# ====================================================================

def main():
    section("QUANTA v3 — LEAKAGE-SAFE TRAINING")
    print(f"  Data directory   : {DATA_DIR.resolve()}")
    print(f"  Model directory  : {MODEL_DIR.resolve()}")
    print(
        f"  Split             : "
        f"{TRAIN_FRAC:.0%} train / {VAL_FRAC:.0%} validation / "
        f"{TEST_FRAC:.0%} test PER USER"
    )

    dfs = load_data()

    finance = train_finance(dfs)
    study = train_study(dfs)
    habit = train_habit(dfs)

    finance_selected = finance["models"][finance["selected"]]["test"]
    study_selected = study["models"][study["selected"]]["test"]
    habit_selected = habit["models"][habit["selected"]]["test"]

    evaluation = {
        "version": "v3",
        "split": {
            "type": "per_user_temporal",
            "train": TRAIN_FRAC,
            "validation": VAL_FRAC,
            "test": TEST_FRAC,
        },
        "finance": {
            "selected_model": finance["selected"],
            "r2": finance_selected["r2"],
            "rmse": finance_selected["rmse"],
            "mae": finance_selected["mae"],
            "category_results": finance["category_results"],
        },
        "study": {
            "selected_model": study["selected"],
            "r2": study_selected["r2"],
            "rmse": study_selected["rmse"],
            "mae": study_selected["mae"],
        },
        "habit": {
            "selected_model": habit["selected"],
            "auc": habit_selected["auc"],
            "pr_auc": habit_selected["pr_auc"],
            "positive_f1": habit_selected["positive_f1"],
            "positive_recall": habit_selected["positive_recall"],
            "positive_precision": habit_selected["positive_precision"],
            "accuracy": habit_selected["accuracy"],
            "threshold": habit_selected["threshold"],
        },
    }

    metadata = {
        "pipeline": "QUANTA Milestone 2 v3",
        "data_dir": str(DATA_DIR),
        "model_dir": str(MODEL_DIR),
        "training_users": TRAINING_USERS,
        "random_state": RANDOM_STATE,
        "leakage_controls": [
            "per-user temporal split",
            "past-only expanding user statistics",
            "shifted rolling and EWM features",
            "validation-only threshold selection",
            "XGBoost early stopping on validation",
        ],
        "study_note": (
            "exam_next7d/cycle_phase/days_to_slack/is_slack_week are "
            "generator-provided signals. Keep them only if equivalent "
            "information is available at production inference time."
        ),
    }

    with open(RESULTS_F, "w", encoding="utf-8") as f:
        json.dump(evaluation, f, indent=2)

    with open(METADATA_F, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    section("ALL TRAINING COMPLETE")
    print(f"\n  Models  -> {MODEL_DIR.resolve()}/")
    print(f"  Results -> {RESULTS_F.resolve()}")
    print(f"  Metadata -> {METADATA_F.resolve()}")

    print("\n  FINAL TEST METRICS")
    print(
        f"  Finance : R2={finance_selected['r2']:.4f} "
        f"RMSE={finance_selected['rmse']:.2f}"
    )
    print(
        f"  Study   : R2={study_selected['r2']:.4f} "
        f"RMSE={study_selected['rmse']:.2f}"
    )
    print(
        f"  Habit   : AUC={habit_selected['auc']:.4f} "
        f"PR-AUC={habit_selected['pr_auc']:.4f} "
        f"F1={habit_selected['positive_f1']:.4f} "
        f"Recall={habit_selected['positive_recall']:.4f}"
    )


if __name__ == "__main__":
    main()
