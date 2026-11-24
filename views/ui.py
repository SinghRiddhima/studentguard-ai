"""Shared Streamlit UI components (styling, banners, zone badges, explanation charts)."""
import html
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import config
from views.theme import PALETTES

CSS = """
<style>
.block-container {padding-top: 1.6rem; max-width: 1200px;}
.sg-hero {background: linear-gradient(120deg,#4338ca,#6366f1 55%,#0ea5e9); color:#fff; padding:20px 26px;
          border-radius:16px; margin-bottom:14px;}
.sg-hero h1 {color:#fff; margin:0; font-size:1.9rem;} .sg-hero p {margin:2px 0 0; opacity:.92;}
.sg-card {background:var(--sg-surface,#fff); border:1px solid var(--sg-border,#e2e8f0); border-radius:14px; padding:16px 18px; margin-bottom:12px;
          box-shadow:0 1px 2px rgba(15,23,42,.05);}
.sg-zone {display:inline-block; padding:5px 14px; border-radius:999px; font-weight:700; font-size:.95rem;}
.sg-banner-demo {background:#fef3c7; border:1px solid #f59e0b; color:#78350f; padding:9px 14px; border-radius:10px;
                 font-weight:600; margin-bottom:8px;}
.sg-banner-ok {background:#e0f2fe; border:1px solid #38bdf8; color:#0c4a6e; padding:9px 14px; border-radius:10px;
               font-weight:600; margin-bottom:8px;}
.sg-advisory {background:#eef2ff; border-left:5px solid #4f46e5; color:#312e81; padding:9px 14px;
              border-radius:8px; font-size:.9rem; margin-bottom:10px;}
.sg-emergency {background:#fff7ed; border:1px solid #fdba74; color:#7c2d12; padding:10px 14px; border-radius:10px;
               font-size:.88rem; margin:8px 0;}
.sg-metric {text-align:center;} .sg-metric .n {font-size:2rem; font-weight:800;} .sg-metric .l {color:var(--sg-muted,#475569); font-size:.85rem;}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def hero():
    st.markdown(f"<div class='sg-hero'><h1>🛡️ {config.APP_TITLE}</h1><p>{config.APP_SUBTITLE}</p></div>",
                unsafe_allow_html=True)


def about(mode: str):
    """Keep model context available without recurring dashboard banners."""
    st.caption(config.DEMO_BANNER if mode == "DEMONSTRATION" else
               "Trained model mode. See Model Performance for validation details and limits.")
    st.caption(config.ADVISORY_NOTICE)
    st.caption("Privacy: access is role-based; private messages are visible only to authorised counsellors.")


def mode_banner(mode: str):
    if mode == "DEMONSTRATION":
        st.markdown(f"<div class='sg-banner-demo'>⚠️ {html.escape(config.DEMO_BANNER)}</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='sg-banner-ok'>TRAINED MODEL MODE — advisory only. See Model Performance for "
                    "validation details and limits.</div>", unsafe_allow_html=True)


def advisory():
    st.markdown(f"<div class='sg-advisory'>🧑‍⚕️ {html.escape(config.ADVISORY_NOTICE)}</div>", unsafe_allow_html=True)


def emergency_note():
    st.caption(config.EMERGENCY_NOTE)


def zone_badge(zone: str, short=False) -> str:
    z = config.ZONES[zone]
    return (f"<span class='sg-zone' style='background:{z['bg']};color:{z['color']};border:1px solid {z['color']}'>"
            f"{html.escape(z['short'] if short else z['label'])}</span>")


def metric_card(label, value, color="var(--sg-text,#0f172a)"):
    st.markdown(f"<div class='sg-card sg-metric'><div class='n' style='color:{color}'>{value}</div>"
                f"<div class='l'>{html.escape(label)}</div></div>", unsafe_allow_html=True)


def zone_metrics(dist: dict):
    cols = st.columns(4)
    with cols[0]:
        metric_card("Students assessed", sum(dist.values()))
    for col, z in zip(cols[1:], ["GREEN", "YELLOW", "RED"]):
        with col:
            metric_card(config.ZONES[z]["label"].split(" — ")[0] + " · " + config.ZONES[z]["short"], dist.get(z, 0), config.ZONES[z]["color"])


def plotly_chart(figure, **options):
    appearance = st.session_state.get("sg_theme", "dark")
    bg, _, border, text, _, violet, cyan, magenta = PALETTES[appearance]
    figure.update_layout(
        template="plotly_dark" if appearance == "dark" else "plotly_white",
        paper_bgcolor=bg, plot_bgcolor=bg, font_color=text, font_size=15 if appearance == "light" else 12,
        colorway=[violet, cyan, magenta, "#64748b"],
        xaxis_gridcolor=border, yaxis_gridcolor=border,
    )
    st.plotly_chart(figure, theme=None, **options)


def zone_pie(dist: dict):
    df = pd.DataFrame({"zone": list(dist.keys()), "n": list(dist.values())})
    fig = px.pie(df, names="zone", values="n", hole=0.55, color="zone",
                 color_discrete_map={z: config.ZONES[z]["color"] for z in config.ZONES})
    fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=300, legend_title_text="")
    plotly_chart(fig, width="stretch")


def contributions_chart(rows: list, top=8):
    method = rows[0]["method"]
    sub = rows[:top]
    df = pd.DataFrame(sub).iloc[::-1]
    colors = ["#ef4444" if v > 0 else "#22c55e" for v in df["contribution"]]
    fig = go.Figure(go.Bar(x=df["contribution"], y=df["label"], orientation="h", marker_color=colors,
                           customdata=df["display"], hovertemplate="%{y}: %{customdata}<br>contribution %{x}<extra></extra>"))
    fig.update_layout(height=340, margin=dict(t=10, b=10, l=10, r=10),
                      xaxis_title="Score points (rule weights)" if method == "RULE_WEIGHTS" else "SHAP value (model units)")
    plotly_chart(fig, width="stretch")


def render_assessment(r: dict, audience="counsellor"):
    """Common rendering of an assessment result dict (live result or DB row)."""
    st.markdown(f"<div class='sg-card'>{zone_badge(r['zone'])}", unsafe_allow_html=True)
    st.caption(f"Assessed: {r['assessed_at']}  ·  Mode: **{r['mode']}**")
    if audience == "counsellor":
        label = r.get("risk_value_label") or ("Model probability" if r["mode"] == "TRAINED_MODEL" else "Demonstration rule score")
        st.write(f"**Output:** {r['risk_value']}  — _{label}_")
        t = r.get("thresholds", {})
        if t:
            st.caption(f"Zone thresholds used (illustrative unless validated): Yellow ≥ {t.get('yellow')}, Red ≥ {t.get('red')}")
        if r.get("demo_model_output") is not None:
            st.caption(f"Synthetic-trained model output (illustrative only, not used for the zone): {r['demo_model_output']:.2f}")
    st.markdown("</div>", unsafe_allow_html=True)
    contribs = r["contributions"]
    if audience == "counsellor":
        c1, c2 = st.columns([3, 2])
        with c1:
            st.markdown(f"**Contributing indicators** — method: `{r.get('explanation_method', contribs[0]['method'])}`")
            contributions_chart(contribs)
        with c2:
            st.markdown("**Co-occurring patterns**")
            for p in r["patterns"] or ["No co-occurring pattern detected."]:
                st.write("• " + p)
            st.markdown("**Top factors**")
            for row in [x for x in contribs if x["contribution"] > 0][:4]:
                st.write(f"• {row['label']}: {row['display']} ({row['direction']})")
        st.caption(config.ADVISORY_NOTICE + " Factors are associations, not proven causes; no diagnosis is made.")
    else:
        top = [x for x in contribs if x["contribution"] > 0][:3]
        if top and r["zone"] != "GREEN":
            st.write("Areas where extra support might help:")
            for row in top:
                st.write(f"• {row['label']}")
        else:
            st.write("No major areas of concern were identified in this snapshot. Support is always available if you need it.")
    st.markdown("**Suggested support options** (advisory — a counsellor decides what is offered)")
    for rec in r["recommendations"]:
        with st.container(border=True):
            st.write(f"**{rec['concern']}**")
            st.write("Support: " + ", ".join(rec["support"]))
            if audience == "counsellor":
                st.caption(f"Why: {rec['reason']}  ·  Status: {rec.get('decision_status', 'Pending human review')}")


ZONE_ORDER = ["GREEN", "YELLOW", "RED"]


def timeline_chart(prog: dict, thresholds: dict, key: str, height=340):
    """Concern-score timeline with zone bands and support/counselling events marked."""
    tl = prog["timeline"]
    if not tl:
        st.info("No assessments yet.")
        return
    df = pd.DataFrame(tl)
    df["date"] = pd.to_datetime(df["assessed_at"])
    demo = all(m == "DEMONSTRATION" for m in df["mode"])
    fig = go.Figure()
    if demo:
        top = 100
        for lo, hi, z in ((0, thresholds["yellow"], "GREEN"), (thresholds["yellow"], thresholds["red"], "YELLOW"), (thresholds["red"], top, "RED")):
            fig.add_hrect(y0=lo, y1=hi, fillcolor=config.ZONES[z]["bg"], opacity=0.55, line_width=0)
    fig.add_trace(go.Scatter(x=df["date"], y=df["risk_value"], mode="lines+markers", name="Assessment",
                             line=dict(color="#475569"), marker=dict(size=13, color=[config.ZONES[z]["color"] for z in df["zone"]],
                                                                      line=dict(width=1, color="white")),
                             customdata=df["zone"], hovertemplate="%{x|%d %b %Y}<br>%{customdata}<br>value %{y}<extra></extra>"))
    ev = prog["support_events"]
    if ev:
        fig.add_trace(go.Scatter(x=pd.to_datetime([e["at"] for e in ev]), y=[4] * len(ev), mode="markers", name="Support / counselling event",
                                 marker=dict(symbol="diamond", size=12, color="#4f46e5"), text=[e["label"] for e in ev],
                                 hovertemplate="%{x|%d %b %Y}<br>%{text}<extra></extra>"))
    fig.update_layout(height=height, margin=dict(t=10, b=10, l=10, r=10), yaxis=dict(range=[0, 100] if demo else None, title="Concern score (0–100, demo)" if demo else "Model output"),
                      legend=dict(orientation="h", y=-0.2))
    plotly_chart(fig, width="stretch", key=key)


ARROW = {"Improved": "🟢 Improved", "Same zone": "⚪ Same zone", "Higher concern": "🟠 Higher concern"}


def progress_sentence(prog: dict) -> str:
    if not prog["first_support_at"]:
        return "No counselling or intervention recorded yet."
    if prog["zone_before"] and prog["zone_after"]:
        b, a = config.ZONES[prog["zone_before"]]["short"], config.ZONES[prog["zone_after"]]["short"]
        return (f"Support began {prog['first_support_at'][:10]}. Zone before: **{b}** → latest: **{a}** "
                f"(value {prog['score_before']} → {prog['score_after']}). Outcome: {prog['outcome']}.")
    return f"Support began {prog['first_support_at'][:10]}. {prog['outcome']}."


CAUSAL_CAVEAT = ("A zone change after support is an observation, not proof that the support caused it. Other things change over time too "
                 "(exams, season, regression to the mean, self-report mood).")


def checkin_context(c: dict):
    """Show a student's latest check-in context to counsellors."""
    if not c:
        st.caption("No monthly check-in submitted yet.")
        return
    e = c["extras"]
    st.markdown(f"**Latest check-in:** {c['submitted_at']}" + ("  ·  _SYNTHETIC_" if c["is_synthetic"] else ""))
    if c["intent_flag"]:
        st.warning("Student self-reports serious consideration of discontinuing (or a likelihood ≥ 4/5). This is a self-report, not a label "
                   "and not part of the score — consider a private, supportive check-in.")
    st.write(f"• Considered discontinuing: **{e.get('discontinuation_consideration')}** · likelihood next 12 months: **{e.get('likelihood_12m')}/5**\n\n"
             f"• Main factor they named: **{e.get('main_factor')}** · motivation change: {e.get('motivation_change')}\n\n"
             f"• Support they think would help: {', '.join(e.get('preferred_support', []))}")
    if c["assumed"]:
        labels = [config.FEATURE_BY_KEY[k]["label"] for k in c["assumed"] if k in config.FEATURE_BY_KEY]
        st.caption("Not answered / derived, so a neutral default was used: " + ", ".join(labels))
