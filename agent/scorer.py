"""Detective: the ML recovery-probability scorer.

Trains a real classifier on historical_data.csv (labeled, resolved cases) and
applies it to current_batch.csv (unresolved, at-risk cases). This is what
turns "recovery probability" from a hardcoded lookup table into an actual
learned, evaluable number — the model's own held-out AUC/Brier score is saved
alongside it so the confidence claim is itself checkable, not asserted.
"""
from __future__ import annotations

import json
import os
import sys

import joblib
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent import features  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_HERE, "model.pkl")
METRICS_PATH = os.path.join(_HERE, "..", "reports", "training_metrics.json")


def train(historical_csv: str, save: bool = True):
    df = pd.read_csv(historical_csv)
    X = features.build_feature_frame(df)
    y = df["recovered"].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    model = GradientBoostingClassifier(random_state=42, n_estimators=150, max_depth=3)
    model.fit(X_train, y_train)

    proba_test = model.predict_proba(X_test)[:, 1]
    metrics = {
        "roc_auc": float(roc_auc_score(y_test, proba_test)),
        "brier_score": float(brier_score_loss(y_test, proba_test)),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "base_rate_recovered": float(y.mean()),
        "feature_importance": dict(
            sorted(
                zip(features.FEATURE_COLUMNS, model.feature_importances_.tolist()),
                key=lambda kv: -kv[1],
            )
        ),
    }

    if save:
        joblib.dump(model, MODEL_PATH)
        os.makedirs(os.path.dirname(METRICS_PATH), exist_ok=True)
        with open(METRICS_PATH, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)

    return model, metrics


def load_model():
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            "No trained model found at agent/model.pkl — run `python agent/scorer.py` "
            "(or agent.scorer.train(...)) first."
        )
    return joblib.load(MODEL_PATH)


def score(df: pd.DataFrame, model=None) -> pd.DataFrame:
    """Adds a `recovery_probability` column (the model's P(recovered) under
    each row's case-type DEFAULT_ACTION — see schema.DEFAULT_ACTION_FOR_CASE).
    The decision engine rescales this per-candidate-action; see decision_engine.py."""
    if model is None:
        model = load_model()
    X = features.build_feature_frame(df)
    proba = model.predict_proba(X)[:, 1]
    out = df.copy()
    out["recovery_probability"] = proba
    return out


if __name__ == "__main__":
    hist_path = os.path.join(_HERE, "..", "data", "historical_data.csv")
    _, metrics = train(hist_path)
    print("Trained Detective model on", metrics["n_train"] + metrics["n_test"], "historical cases")
    print(f"Held-out ROC-AUC: {metrics['roc_auc']:.3f}  |  Brier score: {metrics['brier_score']:.3f}")
    print("Top features:", list(metrics["feature_importance"].items())[:5])
