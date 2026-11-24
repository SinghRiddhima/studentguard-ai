"""Administrator view: AGGREGATE statistics only – no student records, no counselling messages."""
import json
import pandas as pd
import streamlit as st
import config
from views import counsellor_dashboard, progress_trends, ui


def render(ctx):
    db, user = ctx.db, ctx.user
    st.subheader("Administrator Overview")
    st.caption("Aggregate view. Individual risk profiles and counselling messages are not available to administrators.")
    counts = db.admin_counts(user)
    c = st.columns(4)
    with c[0]: ui.metric_card("Students in database", counts["students"])
    with c[1]: ui.metric_card("…of which synthetic", counts["synthetic_students"])
    with c[2]: ui.metric_card("Assessments stored", counts["assessments"])
    with c[3]: ui.metric_card("Active counsellors", counts["counsellors"])
    dist = db.zone_distribution(user)
    a, b = st.columns(2)
    with a:
        st.markdown("**Risk-zone distribution**")
        ui.zone_pie(dist) if sum(dist.values()) else st.caption("No assessments yet.")
    with b:
        sos = db.sos_stats(user)
        st.markdown("**Counselling requests by status** (counts only)")
        st.bar_chart(pd.Series(sos["by_status"]))
        st.markdown("**By category**")
        st.bar_chart(pd.Series(sos["by_category"])) if sos["by_category"] else st.caption("No requests yet.")
    ist = db.intervention_stats(user)
    x, y = st.columns(2)
    with x:
        st.markdown("**Human decisions on AI suggestions**")
        st.bar_chart(pd.Series(ist["by_decision"]))
    with y:
        st.markdown("**Intervention status**")
        st.bar_chart(pd.Series(ist["by_status"]))
    st.markdown("### Progress after support (aggregate)")
    st.caption(ui.CAUSAL_CAVEAT)
    progress_trends.outcome_charts(db.progression_summary(user), "ad")
    st.markdown("### Student feedback on services (averages only — no comments or identities)")
    progress_trends.feedback_charts(db.feedback_stats(user), "ad_fb")
    cs = db.checkin_stats(user)
    st.markdown(f"### Monthly check-ins\n{cs['students_recent']} of {cs['students']} students checked in during the last "
                f"{config.CHECKIN_INTERVAL_DAYS} days ({cs['total_checkins']} check-ins in total).")
    st.markdown("### Dataset quality summary")
    if config.METRICS_PATH.exists():
        m = json.loads(config.METRICS_PATH.read_text())
        d = m["dataset"]
        st.write(f"Training data: **{d['n_records']} records**, {d['n_features_available']} features, "
                 f"{d['duplicate_rows']} duplicate rows, missing values: {sum(d['missing_values'].values())}. "
                 f"{'**SYNTHETIC** — not real students.' if m['is_synthetic'] else 'Validated labels declared by the trainer.'}")
    else:
        st.caption("No training summary yet. Run `python -m src.train_model`.")
    with st.expander("Audit trail (all roles)"):
        counsellor_dashboard.render_audit(ctx)


def render_settings(ctx):
    db, user = ctx.db, ctx.user
    st.subheader("Settings")
    st.markdown("#### Risk-zone thresholds (demonstration rule score, 0–100)")
    t = db.get_thresholds()
    st.caption("ILLUSTRATIVE thresholds — not validated on real outcome data. Changing them affects new assessments only; "
               "each stored assessment keeps the thresholds used at the time.")
    with st.form("thr"):
        yl = st.number_input("Yellow zone starts at", 1.0, 99.0, float(t["yellow"]), 1.0)
        rd = st.number_input("Red zone starts at", 2.0, 100.0, float(t["red"]), 1.0)
        if st.form_submit_button("Save thresholds"):
            try:
                db.set_thresholds(user, yl, rd)
                st.success("Thresholds saved and logged.")
            except ValueError as e:
                st.error(str(e))
    st.markdown("#### Counsellor accounts")
    st.dataframe(pd.DataFrame(db.list_users(user)), hide_index=True, width="stretch")
    with st.form("newuser", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        un = c1.text_input("Username")
        dn = c2.text_input("Display name")
        pw = c3.text_input("Password (min 8 chars)", type="password")
        if st.form_submit_button("Create counsellor account"):
            try:
                db.create_user(user, un, pw, "counsellor", dn)
                st.success("Counsellor account created.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    st.markdown("#### Student invitations")
    st.caption("Each code can register one demo student and expires after 24 hours.")
    if st.button("Generate student invite"):
        st.code(db.create_student_invite(user))
    st.markdown("#### Original research survey (Google Form)")
    st.write(f"[Open the research form]({config.RESEARCH_FORM_URL}) — it is anonymous research and is **not connected** to student accounts. "
             "Its responses cannot flow into this app automatically; students use the in-app monthly check-in instead "
             "(same questions Q3–Q19, one per account per 30 days).")
    st.markdown("#### Prototype security limitations")
    st.markdown("- Demo login only (no lockout, MFA, reset, session expiry, HTTPS). \n- Local unencrypted SQLite file.\n"
                "- No email/SMS integration: counsellors are **not** notified automatically.\n- Not an emergency service.")
