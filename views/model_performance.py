"""Model evaluation page – shows ONLY metrics actually computed by src/train_model.py."""
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import config
from views import ui


def render(ctx):
    st.subheader("Model Performance")
    if not config.METRICS_PATH.exists():
        st.warning("No trained model or metrics found. The app still works using the transparent rule-based demonstration logic. "
                   "To create the demo model run:  `python -m src.generate_synthetic_data` then `python -m src.train_model`.")
        return
    m = json.loads(config.METRICS_PATH.read_text())
    if m["is_synthetic"]:
        st.error("⚠️ These metrics come from SYNTHETIC data whose labels are generated from the demo rules. They show that the "
                 "pipeline runs — they are NOT evidence that the system predicts real student dropout.")
    d, sp = m["dataset"], m["split"]
    st.markdown("#### Dataset inspection")
    c = st.columns(4)
    c[0].metric("Records", d["n_records"]); c[1].metric("Features", d["n_features_available"])
    c[2].metric("Duplicate rows", d["duplicate_rows"]); c[3].metric("Missing cells", sum(d["missing_values"].values()))
    st.write(f"Target: `{m['target']}` · class distribution: {d['class_distribution']} · one record per student: "
             f"{d.get('one_record_per_student')} · train/test: {sp['train']}/{sp['test']} "
             f"(test positives {sp['test_positive']}, negatives {sp['test_negative']}) · group-aware split: {sp['grouped']}")
    st.markdown("#### Model comparison (hold-out test set)")
    rows = []
    for name, r in m["results"].items():
        h = r["holdout"]
        row = dict(model=name, accuracy=h["accuracy"], precision=h["precision"], recall=h["recall"], f1=h["f1"], roc_auc=h["roc_auc"], brier=h["brier"])
        if r["cv"]:
            row["cv_f1 (mean±sd)"] = f"{r['cv']['f1']['mean']:.3f} ± {r['cv']['f1']['std']:.3f}"
        rows.append(row)
    df = pd.DataFrame(rows)
    st.dataframe(df.round(3), hide_index=True, width="stretch")
    st.info("Why accuracy alone is not enough: with imbalanced classes a model that never flags anyone still scores high accuracy "
            "(see the majority-class baseline row). Precision, recall and F1 on the flagged class matter more.")
    long = df.melt(id_vars="model", value_vars=["accuracy", "precision", "recall", "f1"])
    ui.plotly_chart(px.bar(long, x="model", y="value", color="variable", barmode="group").update_layout(height=340), width="stretch")
    st.markdown(f"#### Deployed model: {m['deployed_model']}")
    cm = m["results"][m["deployed_model"]]["holdout"]["confusion_matrix"]
    a, b = st.columns(2)
    with a:
        fig = go.Figure(go.Heatmap(z=cm, x=["Pred 0", "Pred 1"], y=["Actual 0", "Actual 1"], text=cm, texttemplate="%{text}",
                                   colorscale="Blues", showscale=False))
        fig.update_layout(title="Confusion matrix", height=320, yaxis_autorange="reversed")
        ui.plotly_chart(fig, width="stretch")
    with b:
        fi = pd.Series(m["feature_importance"]).sort_values()
        fi.index = [config.FEATURE_BY_KEY[k]["label"] for k in fi.index]
        ui.plotly_chart(px.bar(fi, orientation="h", title="Random Forest feature importance (global, not causal)").update_layout(
            height=320, showlegend=False), width="stretch")
    cc = m["calibration_curve"]
    fig = go.Figure([go.Scatter(x=cc["mean_predicted"], y=cc["fraction_positive"], mode="lines+markers", name="Model"),
                     go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="Perfect calibration", line=dict(dash="dash"))])
    fig.update_layout(title="Reliability curve (not verified as calibrated)", height=320, xaxis_title="Mean predicted", yaxis_title="Observed fraction")
    ui.plotly_chart(fig, width="stretch")
    st.caption(m["calibration_note"])
    st.markdown("#### Limitations")
    for l in m["limitations"]:
        st.write("• " + l)
    st.caption(f"Trained at {m['trained_at']}.")
