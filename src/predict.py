"""Risk assessment module: returns a structured result and always states the assessment mode."""
from datetime import datetime
import joblib
import pandas as pd
import config
from src import explainability, intervention_engine, risk_zones

MODE_DEMO = "DEMONSTRATION"
MODE_TRAINED = "TRAINED_MODEL"


def load_bundle(path=None):
    """Load the saved model; returns None (and the app keeps working in rule-based demo mode) if unavailable."""
    path = path or config.MODEL_PATH
    try:
        b = joblib.load(path)
        if not isinstance(b, dict) or "pipeline" not in b:
            return None
        return b
    except Exception:  # noqa: BLE001
        return None


def mode_of(bundle) -> str:
    """TRAINED_MODEL only when the model was trained on verified, non-synthetic labels."""
    if bundle and bundle.get("validated_labels") and not bundle.get("is_synthetic"):
        return MODE_TRAINED
    return MODE_DEMO


def model_probability(bundle, features: dict):
    if not bundle:
        return None
    try:
        X = pd.DataFrame([{k: features.get(k) for k in config.FEATURE_KEYS}])
        return float(bundle["pipeline"].predict_proba(X)[0, 1])
    except Exception:  # noqa: BLE001
        return None


def assess(student_id: str, features: dict, bundle=None, thresholds: dict = None, prob_thresholds: dict = None) -> dict:
    mode = mode_of(bundle)
    sc = risk_zones.score_features(features)
    prob = model_probability(bundle, features)
    contributions, method_note = None, None
    if mode == MODE_TRAINED and prob is not None:
        pt = prob_thresholds or config.DEFAULT_PROB_THRESHOLDS
        zone, risk_value, thr = risk_zones.map_zone(prob, pt), prob, pt
        contributions = explainability.shap_explanation(bundle, features)
        method_note = ("Zone from model probability using configured thresholds"
                       + ("" if bundle.get("calibrated") else " (probabilities NOT verified as calibrated)") + ".")
        output_label = "Model-estimated probability of the trained target (not a certainty)"
    else:
        thr = thresholds or config.DEFAULT_SCORE_THRESHOLDS
        zone, risk_value = risk_zones.map_zone(sc["score"], thr), sc["score"]
        method_note = "Zone from the transparent demonstration rule score (0–100) with illustrative thresholds."
        output_label = "Demonstration rule score (0–100), not a probability"
    if contributions is None:
        contributions = explainability.rule_explanation(features)
    recs = intervention_engine.recommend(features)
    demo_model_output = None
    if mode == MODE_DEMO and prob is not None:
        demo_model_output = prob   # synthetic-trained model: shown only as illustrative
    return dict(student_id=student_id, zone=zone, assessed_at=datetime.now().replace(microsecond=0).isoformat(sep=" "),
                mode=mode, risk_value=round(risk_value, 4), risk_value_label=output_label,
                rule_score=sc["score"], model_output=prob, demo_model_output=demo_model_output,
                contributions=contributions, explanation_method=contributions[0]["method"],
                patterns=sc["patterns"], recommendations=recs, suggested_next_steps=intervention_engine.flat_support(recs),
                thresholds=thr, method_note=method_note, features=features,
                banner=config.DEMO_BANNER if mode == MODE_DEMO else
                "TRAINED MODEL MODE — advisory only; see Model Performance for validation limits.",
                causal_note=explainability.CAUSAL_NOTE)
