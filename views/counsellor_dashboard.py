"""Counsellor views: overview, student directory, intervention centre (human-in-the-loop decisions)."""
from datetime import date, timedelta
import pandas as pd
import streamlit as st
import config
from src import intervention_engine
from views import ui


def render_overview(ctx):
    db, user = ctx.db, ctx.user
    st.subheader("Overview")
    dist = db.zone_distribution(user)
    ui.zone_metrics(dist)
    c1, c2 = st.columns([2, 3])
    with c1:
        st.markdown("**Risk-zone distribution (latest assessment per student)**")
        if sum(dist.values()):
            ui.zone_pie(dist)
        else:
            st.caption("No assessments yet. Use *Student Risk Assessment* to add one.")
    with c2:
        sos = db.sos_stats(user)
        st.markdown("**Counselling requests by status**")
        st.bar_chart(pd.Series(sos["by_status"]))
        pending = sos["by_status"]["Submitted"]
        st.write(f"**{pending}** request(s) awaiting acknowledgement.")
        ist = db.intervention_stats(user)
        st.write("**Human decisions on AI suggestions:** " +
                 ", ".join(f"{k}: {v}" for k, v in ist["by_decision"].items()))
    st.markdown("**Students for priority review** (Red zone first — a review prompt, not a verdict)")
    df = pd.DataFrame(db.list_students(user))
    if not df.empty:
        top = df[df["zone"].isin(["RED", "YELLOW"])].sort_values("risk_value", ascending=False).head(8)
        st.dataframe(top[["student_id", "alias", "program", "year", "zone", "risk_value", "assessed_at"]],
                     hide_index=True, width="stretch")
        flagged = df[df["intent_flag"] == 1]
        if len(flagged):
            st.write(f"**Priority follow-up:** {len(flagged)} student(s) self-reported serious consideration of discontinuing in their latest check-in "
                       "(see Progress & Trends → Check-in participation). This is a self-report prompt, not a label or a score input.")


def render_directory(ctx):
    db, user = ctx.db, ctx.user
    st.subheader("Student Directory")
    df = pd.DataFrame(db.list_students(user))
    if df.empty:
        st.caption("No students found.")
        return
    f1, f2, f3, f4 = st.columns(4)
    q = f1.text_input("Search ID / name")
    zones = f2.multiselect("Zone", list(config.ZONES), default=list(config.ZONES))
    progs = f3.multiselect("Program", sorted(df["program"].dropna().unique()))
    years = f4.multiselect("Year", sorted(df["year"].dropna().unique()))
    view = df.copy()
    view["Student ID"] = view["college_id"].fillna(view["student_id"])
    view["zone"] = view["zone"].fillna("NONE")
    if q:
        view = view[view["Student ID"].str.contains(q, case=False, regex=False)
                    | view["alias"].str.contains(q, case=False, regex=False)]
    view = view[view["zone"].isin(zones + ["NONE"])]
    if progs:
        view = view[view["program"].isin(progs)]
    if years:
        view = view[view["year"].isin(years)]
    view["synthetic"] = view["is_synthetic"].map({1: "SYNTHETIC", 0: "real"})
    view["self-report flag"] = view["intent_flag"].map({1: "⚑", 0: ""}).fillna("")
    st.caption(f"{len(view)} of {len(df)} students")
    st.dataframe(view[["Student ID", "alias", "program", "year", "zone", "risk_value", "assessed_at", "self-report flag", "synthetic"]],
                 hide_index=True, width="stretch")
    if view.empty:
        st.caption("No students match these filters.")
        return
    labels = dict(zip(view["student_id"], view["Student ID"] + " — " + view["alias"]))
    sid = st.selectbox("Open student profile", list(labels), format_func=labels.get)
    hist = db.get_assessments(user, sid)
    if not hist:
        st.caption("This student has no assessment yet.")
        return
    ui.render_assessment(hist[0])
    checks = db.get_checkins(user, sid)
    with st.expander("Latest self-report check-in", expanded=bool(checks and checks[0]["intent_flag"])):
        ui.checkin_context(checks[0] if checks else None)
    with st.expander("Assessment history"):
        st.dataframe(pd.DataFrame([{k: a[k] for k in ("assessed_at", "zone", "risk_value", "mode")} for a in hist]),
                     hide_index=True, width="stretch")
    if st.button("➡️ Review in Intervention Centre", key="go_ic"):
        st.session_state["selected_student"] = sid
        st.success("Student selected — open **Intervention Centre** from the sidebar.")


def render_decision_form(ctx, student_id: str, assessment: dict):
    """Accept / modify / reject the rule-based suggestion; reason is mandatory; everything is audited."""
    db, user = ctx.db, ctx.user
    suggestion = assessment["recommendations"]
    suggested = intervention_engine.flat_support(suggestion)
    st.markdown("#### Your decision (final authority rests with you)")
    with st.form(f"decision_{assessment['assessment_id']}"):
        decision = st.radio("Decision on the suggested support", config.DECISIONS, horizontal=True,
                            format_func=lambda d: {"accepted": "✅ Accept as suggested", "modified": "✏️ Modify",
                                                   "rejected": "⛔ Reject"}[d])
        st.caption("Suggested: " + ", ".join(suggested))
        chosen = st.multiselect("Final intervention(s) — used for 'Modify' (and as an alternative for 'Reject')",
                                config.INTERVENTION_CATALOGUE, default=[s for s in suggested if s in config.INTERVENTION_CATALOGUE])
        custom = st.text_input("Other intervention (free text, optional)")
        reason = st.text_area("Reason for your decision (required)")
        notes = st.text_area("Notes after contacting the student (private to counsellors)")
        set_fu = st.checkbox("Schedule a follow-up")
        fu = st.date_input("Follow-up date", value=date.today() + timedelta(days=14), min_value=date.today())
        ok = st.form_submit_button("Save decision", type="primary")
    if ok:
        if decision == "accepted":
            final = "; ".join(suggested)
        elif decision == "rejected":
            final = "; ".join(chosen + ([custom] if custom.strip() else [])) or "No intervention needed at this time"
        else:
            final = "; ".join(chosen + ([custom.strip()] if custom.strip() else []))
        try:
            iid = db.record_decision(user, student_id, assessment["assessment_id"], suggestion, decision, final,
                                     reason, notes, fu if set_fu else None)
            st.success(f"Decision recorded (intervention #{iid}) and written to the audit trail.")
        except ValueError as e:
            st.error(str(e))


def render_intervention_centre(ctx):
    db, user = ctx.db, ctx.user
    st.subheader("Intervention Centre")
    students = db.list_students(user)
    ids = [s["student_id"] for s in students if s["zone"]]
    if not ids:
        st.caption("No assessed students yet.")
        return
    default = ids.index(st.session_state["selected_student"]) if st.session_state.get("selected_student") in ids else 0
    names = {s["student_id"]: s["alias"] for s in students}
    sid = st.selectbox("Student", ids, index=default, format_func=lambda s: f"{s} — {names[s]}")
    st.session_state["selected_student"] = sid
    tab1, tab2, tab3 = st.tabs(["Review & decide", "Interventions & follow-up", "Audit trail"])
    with tab1:
        a = db.get_assessments(user, sid)[0]
        ui.render_assessment(a)
        checks = db.get_checkins(user, sid)
        with st.expander("Latest self-report check-in"):
            ui.checkin_context(checks[0] if checks else None)
        render_decision_form(ctx, sid, a)
    with tab2:
        rows = db.list_interventions(user, sid)
        if not rows:
            st.caption("No interventions recorded for this student yet.")
        for r in rows:
            with st.container(border=True):
                st.write(f"**#{r['intervention_id']}** · {r['decision'].upper()} · Status: **{r['status']}** · by {r['counsellor']}")
                st.write(f"Final: {r['final_intervention']}")
                st.caption(f"Reason: {r['reason']} · Follow-up: {r['follow_up_date'] or '—'} · Created {r['created_at']}")
                if r["counsellor_notes"]:
                    st.caption(f"Notes: {r['counsellor_notes']}")
                with st.form(f"upd_{r['intervention_id']}"):
                    c1, c2, c3 = st.columns([2, 3, 2])
                    s = c1.selectbox("Update status", config.INTERVENTION_STATUSES,
                                     index=config.INTERVENTION_STATUSES.index(r["status"]))
                    n = c2.text_input("Follow-up note")
                    fu = c3.date_input("Next follow-up", value=None)
                    if st.form_submit_button("Update"):
                        try:
                            db.update_intervention(user, r["intervention_id"], s, n, fu)
                            st.success("Updated.")
                            st.rerun()
                        except ValueError as e:
                            st.error(str(e))
        fu = db.list_follow_ups(user, sid)
        if fu:
            st.markdown("**Follow-up timeline**")
            st.dataframe(pd.DataFrame(fu)[["created_at", "kind", "status_after", "note", "scheduled_for", "author"]],
                         hide_index=True, width="stretch")
    with tab3:
        render_audit(ctx)


def render_audit(ctx, limit=100):
    rows = ctx.db.list_audit(ctx.user, limit)
    if not rows:
        st.caption("No audit entries yet.")
        return
    df = pd.DataFrame(rows)[["timestamp", "actor_role", "actor_user_id", "action", "entity_type", "entity_id", "details_json"]]
    st.dataframe(df, hide_index=True, width="stretch")
