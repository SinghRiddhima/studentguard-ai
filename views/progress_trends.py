"""Counsellor view: progression after support, check-in participation, and service feedback."""
import pandas as pd
import plotly.express as px
import streamlit as st
import config
from views import ui


def outcome_charts(summary: dict, key: str):
    if not summary["n_with_support"]:
        st.caption("No students with recorded support and follow-up assessments yet.")
        return
    c1, c2 = st.columns(2)
    with c1:
        o = pd.Series(summary["outcomes"]).rename_axis("outcome").reset_index(name="students")
        fig = px.bar(o, x="outcome", y="students", color="outcome", color_discrete_map={
            "Improved": "#16a34a", "Same zone": "#94a3b8", "Higher concern": "#f59e0b"})
        fig.update_layout(height=300, showlegend=False, margin=dict(t=10, b=10))
        ui.plotly_chart(fig, width="stretch", key=f"{key}_o")
    with c2:
        t = pd.Series(summary["transitions"]).rename_axis("transition").reset_index(name="students")
        if len(t):
            ui.plotly_chart(px.bar(t, x="transition", y="students").update_layout(height=300, margin=dict(t=10, b=10)),
                            width="stretch", key=f"{key}_t")


def feedback_charts(stats: dict, key: str):
    if not stats["n"]:
        st.caption("No service feedback yet.")
        return
    st.write(f"**{stats['n']}** feedback response(s) from **{stats['resolved_requests']}** resolved request(s).")
    a = stats["averages"]
    cols = st.columns(4)
    for col, (k, label) in zip(cols, config.FEEDBACK_ASPECTS.items()):
        with col:
            ui.metric_card(label, f"{a[k]}/5")
    if stats["by_category"]:
        df = pd.DataFrame(stats["by_category"])
        ui.plotly_chart(px.bar(df, x="category", y="overall", text="n", range_y=[0, 5]).update_layout(
            height=300, margin=dict(t=10, b=10), yaxis_title="Average overall rating"), width="stretch", key=f"{key}_c")
        st.caption("Bar labels show the number of responses; small numbers make averages unreliable.")


def render(ctx):
    db, user = ctx.db, ctx.user
    st.subheader("Progress & Trends")
    tab1, tab2, tab3, tab4 = st.tabs(["Progress after support", "Student timeline", "Check-in participation", "Service feedback"])
    with tab1:
        summary = db.progression_summary(user)
        c = st.columns(4)
        o = summary["outcomes"]
        with c[0]: ui.metric_card("Students with support recorded", summary["n_with_support"])
        with c[1]: ui.metric_card("Improved zone", o.get("Improved", 0), "#16a34a")
        with c[2]: ui.metric_card("Same zone", o.get("Same zone", 0), "#64748b")
        with c[3]: ui.metric_card("Higher concern", o.get("Higher concern", 0), "#b45309")
        st.caption(ui.CAUSAL_CAVEAT + " 'Before' = last assessment before support began; 'after' = latest assessment since.")
        outcome_charts(summary, "ct")
        rows = db.progression_rows(user)
        if rows:
            df = pd.DataFrame(rows)
            pick = st.multiselect("Filter outcome", sorted(df["outcome"].unique()), default=sorted(df["outcome"].unique()))
            st.dataframe(df[df["outcome"].isin(pick)], hide_index=True, width="stretch")
    with tab2:
        students = [s for s in db.list_students(user) if s["zone"]]
        names = {s["student_id"]: s["alias"] for s in students}
        default = list(names).index(st.session_state["selected_student"]) if st.session_state.get("selected_student") in names else 0
        sid = st.selectbox("Student", list(names), index=default, format_func=lambda s: f"{s} — {names[s]}", key="pt_student")
        prog = db.progression(user, sid)
        ui.timeline_chart(prog, db.get_thresholds(), key="cn_tl")
        st.write(ui.progress_sentence(prog))
        if prog["support_events"]:
            st.dataframe(pd.DataFrame(prog["support_events"])[["at", "type", "label"]], hide_index=True, width="stretch")
        checks = db.get_checkins(user, sid)
        ui.checkin_context(checks[0] if checks else None)
        for r in [x for x in db.list_sos_requests(user) if x["student_id"] == sid and x["feedback"]]:
            f = r["feedback"]
            st.write(f"💬 Feedback on {r['request_id']}: overall {f['overall']}/5, helpful {f['helpfulness']}/5"
                     + (f" — “{f['comment']}”" if f["comment"] else ""))
    with tab3:
        s = db.checkin_stats(user)
        c = st.columns(4)
        with c[0]: ui.metric_card("Students", s["students"])
        with c[1]: ui.metric_card(f"Checked in (last {config.CHECKIN_INTERVAL_DAYS} days)", s["students_recent"])
        with c[2]: ui.metric_card("Total check-ins", s["total_checkins"])
        with c[3]: ui.metric_card("Self-reported intention flags", s["flagged_latest"], "#b45309")
        rate = (s["students_recent"] / s["students"] * 100) if s["students"] else 0
        st.write(f"Participation this window: **{rate:.0f}%**. Students are limited to one check-in per {config.CHECKIN_INTERVAL_DAYS} days.")
        flagged = [x for x in db.list_students(user) if x.get("intent_flag")]
        if flagged:
            st.markdown("**Students whose latest check-in self-reports serious consideration of discontinuing** "
                        "(a prompt for a private, supportive check-in — not a verdict):")
            st.dataframe(pd.DataFrame(flagged)[["student_id", "alias", "program", "year", "zone"]], hide_index=True, width="stretch")
    with tab4:
        feedback_charts(db.feedback_stats(user), "cn_fb")
        fb = db.list_feedback(user)
        if fb:
            st.markdown("**Comments** (confidential to counsellors)")
            for f in fb:
                if f["comment"]:
                    st.write(f"• {f['request_id']} · {f['category']} · {f['overall']}/5 — {f['comment']}")
