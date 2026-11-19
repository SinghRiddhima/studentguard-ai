"""Train and evaluate models. Usage:

    python -m src.train_model                                  # synthetic demo data
    python -m src.train_model --data my.csv --target dropped_out --validated-labels

Without --validated-labels (or if a data_source column says SYNTHETIC) the saved model is flagged
`is_synthetic=True` and the app stays in DEMONSTRATION MODE. Pass --validated-labels ONLY if the
target column holds verified historical outcomes.
"""
import argparse
import json
from datetime import datetime

import joblib
import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, brier_score_loss, confusion_matrix, f1_score,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import (GroupShuffleSplit, StratifiedGroupKFold, StratifiedKFold,
                                     cross_validate, train_test_split)
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeClassifier

import config
from src import data_preprocessing as dp

DEFAULT_TARGET = "synthetic_concern_label"


def make_models(seed=42):
    return {
        "Logistic Regression": LogisticRegression(max_iter=1000, class_weight="balanced"),
        "Decision Tree": DecisionTreeClassifier(max_depth=5, class_weight="balanced", random_state=seed),
        "Random Forest": RandomForestClassifier(n_estimators=200, min_samples_leaf=3,
                                                class_weight="balanced_subsample", random_state=seed, n_jobs=1),
    }


def _metrics(y_true, y_pred, y_prob):
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    out = dict(accuracy=accuracy_score(y_true, y_pred),
               precision=precision_score(y_true, y_pred, zero_division=0),
               recall=recall_score(y_true, y_pred, zero_division=0),
               f1=f1_score(y_true, y_pred, zero_division=0),
               confusion_matrix=cm.tolist(), brier=brier_score_loss(y_true, y_prob))
    out["roc_auc"] = float(roc_auc_score(y_true, y_prob)) if len(set(y_true)) == 2 else None
    return {k: (float(v) if isinstance(v, (float, np.floating)) else v) for k, v in out.items()}


def train(data_path=config.SYNTHETIC_TRAINING_CSV, target=DEFAULT_TARGET, validated_labels=False,
          seed=42, save=True):
    raw = dp.load_dataset(data_path)
    df = dp.encode_survey_labels(raw)
    dp.check_columns(df)
    df, n_oor = dp.clip_out_of_range(df)
    inspection = dp.inspect_dataset(df, target)
    inspection["out_of_range_values_set_to_missing"] = n_oor
    ok, msgs = dp.validate_target(df, target)
    if not ok:
        raise dp.DatasetError("No valid supervised target: " + " ".join(msgs) +
                              " The app will keep running in DEMONSTRATION MODE without a trained model.")
    df = df[df[target].notna()].reset_index(drop=True)

    synthetic = (not validated_labels) or ("data_source" in df.columns
                                           and df["data_source"].astype(str).str.upper().eq("SYNTHETIC").any())
    X, y = df[config.FEATURE_KEYS], df[target].astype(int)
    groups = df["student_id"] if "student_id" in df.columns else None
    grouped = groups is not None and groups.nunique() < len(df)   # repeat students -> group-aware splits

    if grouped:
        tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed).split(X, y, groups))
        cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed)
    else:
        tr, te = train_test_split(np.arange(len(df)), test_size=0.2, stratify=y, random_state=seed)
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    Xtr, Xte, ytr, yte = X.iloc[tr], X.iloc[te], y.iloc[tr], y.iloc[te]
    cv_groups = groups.iloc[tr] if grouped else None

    results, pipes = {}, {}
    base = DummyClassifier(strategy="most_frequent").fit(Xtr, ytr)
    results["Majority-class baseline"] = dict(
        holdout=_metrics(yte, base.predict(Xte), base.predict_proba(Xte)[:, 1]), cv=None)
    for name, est in make_models(seed).items():
        pipe = Pipeline([("prep", dp.build_preprocessor()), ("model", est)])
        cvres = cross_validate(pipe, Xtr, ytr, cv=cv, groups=cv_groups, n_jobs=1,
                               scoring=["accuracy", "precision", "recall", "f1"])
        pipe.fit(Xtr, ytr)
        results[name] = dict(
            holdout=_metrics(yte, pipe.predict(Xte), pipe.predict_proba(Xte)[:, 1]),
            cv={m: dict(mean=float(np.mean(cvres[f"test_{m}"])), std=float(np.std(cvres[f"test_{m}"])))
                for m in ["accuracy", "precision", "recall", "f1"]})
        pipes[name] = pipe

    deployed = pipes["Random Forest"]          # Random Forest baseline is the deployed model
    prob = deployed.predict_proba(Xte)[:, 1]
    frac_pos, mean_pred = calibration_curve(yte, prob, n_bins=5, strategy="quantile")
    importances = deployed.named_steps["model"].feature_importances_
    metrics = dict(
        trained_at=datetime.now().isoformat(timespec="seconds"), deployed_model="Random Forest",
        target=target, is_synthetic=bool(synthetic), validated_labels=bool(validated_labels and not synthetic),
        calibrated=False,
        calibration_note="Probabilities were NOT calibrated/verified for decision thresholds. "
                         "Brier score and a reliability curve are reported for inspection only.",
        dataset=inspection, split=dict(train=int(len(tr)), test=int(len(te)), grouped=bool(grouped),
                                        test_positive=int(yte.sum()), test_negative=int((1 - yte).sum())),
        results=results,
        calibration_curve=dict(mean_predicted=mean_pred.tolist(), fraction_positive=frac_pos.tolist()),
        feature_importance=dict(sorted(zip(config.FEATURE_KEYS, map(float, importances)), key=lambda kv: -kv[1])),
        limitations=[
            "Evaluation uses one hold-out split plus 5-fold CV; with a small dataset these estimates are noisy.",
            "Accuracy alone is misleading on imbalanced classes – compare with the majority-class baseline; "
            "see precision, recall and F1 for the flagged class.",
            "No claim of generalisation to other colleges or student populations is made.",
        ] + (["SYNTHETIC DATA: the label is generated from the transparent rule score plus noise. "
              "Good scores only show the pipeline works; they are NOT evidence of real-world dropout prediction."]
             if synthetic else []))
    if save:
        config.MODEL_DIR.mkdir(exist_ok=True)
        joblib.dump(dict(pipeline=deployed, feature_names=config.FEATURE_KEYS, target=target,
                         is_synthetic=bool(synthetic), validated_labels=metrics["validated_labels"],
                         calibrated=False, trained_at=metrics["trained_at"], model_name="Random Forest"),
                    config.MODEL_PATH)
        config.METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    return metrics


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(config.SYNTHETIC_TRAINING_CSV))
    ap.add_argument("--target", default=DEFAULT_TARGET)
    ap.add_argument("--validated-labels", action="store_true",
                    help="Target holds verified historical outcomes (otherwise model is flagged synthetic/demo)")
    a = ap.parse_args()
    try:
        m = train(a.data, a.target, a.validated_labels)
    except dp.DatasetError as e:
        raise SystemExit(f"[ERROR] {e}")
    print(f"Saved {config.MODEL_PATH.name} and {config.METRICS_PATH.name} (synthetic={m['is_synthetic']})")
    for name, r in m["results"].items():
        h = r["holdout"]
        print(f"{name:26s} acc={h['accuracy']:.3f} prec={h['precision']:.3f} rec={h['recall']:.3f} f1={h['f1']:.3f}")
    if m["is_synthetic"]:
        print("NOTE: metrics are on SYNTHETIC data – they demonstrate mechanics only.")


if __name__ == "__main__":
    main()
