"""Explanations. Two real methods only (nothing is invented):

1. RULE_WEIGHTS – exact per-indicator points of the transparent demonstration score.
2. SHAP – TreeExplainer on the saved Random Forest, only when `shap` is installed and works.
Both describe associations in the data/rules, not causes."""
import numpy as np
import pandas as pd
import config
from src import risk_zones

CAUSAL_NOTE = ("These factors describe patterns associated with the assessment. They are not proven causes "
               "and are not a diagnosis of any condition.")


def _display(f, v):
    opts = f.get("options")
    return opts.get(int(v), str(v)) if opts else f"{v:g}"


def rule_explanation(features: dict) -> list:
    """Exact contribution (score points) of each indicator in the demonstration rule score."""
    sc = risk_zones.score_features(features)
    rows = []
    for f in config.FEATURES:
        k = f["key"]
        pts = sc["points"][k]
        rows.append(dict(feature=k, label=f["label"], value=features.get(k), display=_display(f, features.get(k)),
                         contribution=round(pts, 2), concern_level=round(sc["levels"][k], 2),
                         direction="raises concern" if sc["levels"][k] >= config.CONCERN_TRIGGER
                         else ("slightly raises concern" if pts > 0.5 else "no notable concern"),
                         method="RULE_WEIGHTS"))
    return sorted(rows, key=lambda r: -r["contribution"])


def shap_explanation(bundle: dict, features: dict):
    """Per-feature SHAP values (log-odds/probability units of the model, positive class) or None."""
    try:
        import shap
        pipe = bundle["pipeline"]
        X = pd.DataFrame([{k: features.get(k) for k in config.FEATURE_KEYS}])
        Xt = pipe.named_steps["prep"].transform(X)
        sv = shap.TreeExplainer(pipe.named_steps["model"]).shap_values(Xt)
        sv = np.asarray(sv[1] if isinstance(sv, list) else sv)
        sv = sv[0, :, 1] if sv.ndim == 3 else sv[0]
        rows = []
        for f, v in zip(config.FEATURES, sv):
            rows.append(dict(feature=f["key"], label=f["label"], value=features.get(f["key"]),
                             display=_display(f, features.get(f["key"])), contribution=round(float(v), 4),
                             direction="raises model output" if v > 0 else "lowers model output", method="SHAP"))
        return sorted(rows, key=lambda r: -abs(r["contribution"]))
    except Exception:  # noqa: BLE001 - SHAP missing/incompatible: caller falls back, never fabricates
        return None


def top_factors(rows: list, n=5) -> list:
    return [r for r in rows if r["contribution"] > 0][:n]
