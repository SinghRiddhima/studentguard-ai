"""Counsellor-run assessment form: validate -> assess -> save -> explain -> human decision."""
import streamlit as st
import config
from src import predict
from src.validation import validate_assessment
from views import counsellor_dashboard, ui


def _widget(f, key):
    if f.get("kind") == "percent":
        return st.slider(f["label"], 0, 100, int(f["default"]), help=f["help"], key=key)
    if f.get("options"):
        codes = list(f["options"])
        return st.select_slider(f["label"], options=codes, value=f["default"], help=f["help"], key=key,
                                format_func=lambda c: f["options"][c]) if len(codes) > 2 else \
            st.radio(f["label"], codes, index=codes.index(f["default"]), horizontal=True, help=f["help"], key=key,
                     format_func=lambda c: f["options"][c])
    return st.number_input(f["label"], f["min"], f["max"], f["default"], key=key)


def render(ctx):
    db, user = ctx.db, ctx.user
    st.subheader("Student Risk Assessment")
    students = db.list_students(user)
    names = {s["student_id"]: s["alias"] for s in students}
    sid = st.selectbox("Student", list(names), format_func=lambda s: f"{s} — {names[s]}")
    prof = db.get_student(user, sid)
    if prof and not prof["consent_to_assessment"]:
        st.warning("This student has not consented to assessment. Do not proceed.")
        return
    st.caption("Scales follow the survey: Likert 1–5 / frequency answers; categories are mapped to ordinal codes (see README).")
    with st.form("assessment_form"):
        vals = {}
        cols = st.columns(2)
        for i, f in enumerate(config.FEATURES):
            with cols[i % 2]:
                vals[f["key"]] = _widget(f, f"in_{f['key']}")
        submit = st.form_submit_button("Run assessment & save", type="primary")
    if submit:
        clean, errs = validate_assessment(vals)
        if errs:
            for e in errs:
                st.error(e)
            return
        result = predict.assess(sid, clean, ctx.bundle, db.get_thresholds())
        aid = db.save_assessment(user, result, synthetic=bool(prof["is_synthetic"]))
        st.session_state["last_assessment"] = (sid, aid)
        st.session_state["selected_student"] = sid
        st.success(f"Assessment saved (#{aid}) at {result['assessed_at']}.")
    last = st.session_state.get("last_assessment")
    if last and last[0] == sid:
        a = next((x for x in db.get_assessments(user, sid) if x["assessment_id"] == last[1]), None)
        if a:
            ui.render_assessment(a)
            counsellor_dashboard.render_decision_form(ctx, sid, a)
