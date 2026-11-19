"""Student view: own profile, monthly check-in, progress, SOS counselling and feedback."""
import streamlit as st
import config
from src import survey
from src.database import CheckInTooSoon
from views import ui


def _checkin_tab(ctx):
    db, user = ctx.db, ctx.user
    status = db.checkin_status(user)
    if st.session_state.get("checkin_done"):
        d = st.session_state["checkin_done"]
        st.success("✅ Thank you — your check-in was saved and your snapshot has been updated.")
        ui.render_assessment(d, audience="student")
        if d.get("assumed"):
            st.caption("Some answers were 'not sure / prefer not to say', so neutral values were used for those.")
        return
    if not status["available"]:
        st.info(f"You completed your check-in on {status['last'][:10]}. To keep this short and useful, check-ins open once every "
                f"{config.CHECKIN_INTERVAL_DAYS} days — the next one opens on **{status['available_on']:%d %b %Y}**. "
                "You can request counselling at any time.")
        return
    st.write("A 5-minute monthly check-in. There are no right or wrong answers. Your answers help your institution offer the right "
             "support — they do **not** affect your marks, and you can still ask for counselling whatever you answer.")
    with st.form("checkin_form"):
        answers, section = {}, None
        for q in survey.QUESTIONS:
            if q["section"] != section:
                section = q["section"]
                st.markdown(f"##### {survey.SECTIONS[section]}")
            key = f"ci_{q['id']}"
            if q["kind"] == "multi":
                answers[q["id"]] = st.multiselect(q["text"], q["options"], max_selections=q["max_choices"], key=key)
            else:
                answers[q["id"]] = st.radio(q["text"], q["options"], index=None, horizontal=(q["kind"] == "scale"), key=key)
        consent = st.checkbox("I understand my answers will be visible to authorised counsellors, who decide any support — "
                              "nothing happens automatically.", key="ci_consent")
        go = st.form_submit_button("Submit check-in", type="primary")
    if go:
        try:
            res = survey.submit_checkin(db, user, answers, ctx.bundle, consent)
            st.session_state["checkin_done"] = res
            st.rerun()
        except CheckInTooSoon as e:
            st.error(str(e))
        except ValueError as e:
            st.error(str(e))


def _feedback_form(db, user, r):
    with st.form(f"fb_{r['request_id']}"):
        st.markdown("**How was the support you received?** (1 = poor, 5 = excellent)")
        vals = {k: st.slider(label, 1, 5, 4, key=f"fb_{k}_{r['request_id']}") for k, label in config.FEEDBACK_ASPECTS.items()}
        comment = st.text_area("Anything else? (optional)", max_chars=1500, key=f"fbc_{r['request_id']}")
        if st.form_submit_button("Send feedback"):
            try:
                db.submit_feedback(user, r["request_id"], vals["overall"], vals["timeliness"], vals["helpfulness"], vals["respected"], comment)
                st.success("Thank you for your feedback.")
                st.rerun()
            except (ValueError, PermissionError) as e:
                st.error(str(e))


def render_sos(ctx, expanded=False):
    user, db = ctx.user, ctx.db
    st.markdown("### 🆘 Need to talk to someone?")
    st.write("Counselling is available to every student, whatever any assessment says.")
    if not expanded and st.button("🆘 SOS — Request counselling", type="primary", width="stretch"):
        st.session_state["sos_open"] = True
    ui.emergency_note()
    if expanded or st.session_state.get("sos_open"):
        with st.form("sos_form", clear_on_submit=True):
            st.markdown("#### Counselling request")
            cat = st.selectbox("What kind of support do you need?", config.SOS_CATEGORIES)
            msg = st.text_area("Message (optional, visible only to authorised counsellors)", max_chars=2000)
            cm = st.selectbox("Preferred contact method (if supported)", config.SOS_CONTACT_METHODS)
            c1, c2 = st.columns(2)
            go = c1.form_submit_button("Submit request", type="primary")
            cancel = c2.form_submit_button("Cancel")
        if cancel:
            st.session_state["sg_profile_sos"] = False
            st.session_state["sos_open"] = False
            st.rerun()
        if go:
            try:
                rid = db.create_sos_request(user, cat, msg, cm)
                st.session_state["sg_profile_sos"] = False
                st.session_state["sos_open"] = False
                st.session_state["sos_confirm"] = rid
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    if st.session_state.get("sos_confirm"):
        st.success(f"✅ Your request was saved. Request ID: **{st.session_state['sos_confirm']}**. "
                   "A counsellor can view it in their dashboard — you will not get an automatic email/SMS in this prototype; "
                   "check the status in My Dashboard.")


def render(ctx):
    user, db = ctx.user, ctx.db
    profile = db.get_student(user, user["student_id"])
    st.subheader(f"Welcome, {user['display_name']}")
    if profile and profile["is_synthetic"]:
        st.info("This is a SYNTHETIC demo student profile — not a real person.")

    render_sos(ctx)

    tabs = st.tabs(["Monthly check-in", "My progress", "My support requests", "My wellbeing snapshot", "Privacy"])
    with tabs[0]:
        _checkin_tab(ctx)
    assessments = db.get_assessments(user, user["student_id"])
    with tabs[1]:
        prog = db.progression(user, user["student_id"])
        if not assessments:
            st.info("Your progress will appear after your first check-in.")
        else:
            st.caption("Lower is better. Your counsellor and you can use this to see how things are changing over time.")
            ui.timeline_chart(prog, db.get_thresholds(), key="stud_tl")
            st.write(ui.progress_sentence(prog))
            if prog["first_support_at"]:
                st.caption(ui.CAUSAL_CAVEAT)
            st.markdown("**Your snapshots**")
            for a in assessments:
                st.write(f"• {a['assessed_at'][:10]} — {config.ZONES[a['zone']]['short']}")
    with tabs[2]:
        reqs = db.my_sos_requests(user)
        if not reqs:
            st.caption("You have not submitted any requests yet.")
        for r in reqs:
            with st.container(border=True):
                st.write(f"**{r['request_id']}** · {r['category']} · Status: **{r['status']}**")
                st.caption(f"Submitted {r['created_at']} · Last update {r['updated_at']} · Contact: {r['contact_method']}")
                for h in r["history"]:
                    extra = f" (session: {h['scheduled_for']})" if h.get("scheduled_for") else ""
                    st.write(f"• {h['created_at']} — {h['status_after']}{extra}")
                if r["status"] == "Resolved":
                    if r["feedback"]:
                        f = r["feedback"]
                        st.success(f"Your feedback: overall {f['overall']}/5 — thank you.")
                    else:
                        _feedback_form(db, user, r)
    with tabs[3]:
        if not assessments:
            st.info("No assessment is available for you yet. Complete the monthly check-in.")
        else:
            st.caption("An advisory snapshot to help your institution offer support. It is not a prediction that you will leave, "
                       "and it does not affect your access to counselling.")
            ui.render_assessment(assessments[0], audience="student")
    with tabs[4]:
        st.markdown("""
- You can only see **your own** records. Other students cannot see yours.
- Your SOS message and check-in answers are visible to authorised counsellors only — not to unrelated faculty, and only as counts in admin reports.
- Check-ins open once every 30 days. Answers like "not sure" are allowed.
- Assessments are advisory; **a human counsellor makes every intervention decision**. Nothing happens automatically (no penalties, no restrictions).
- Indicators are self-reported patterns, not diagnoses.
- Feedback you give about services is seen by counsellors; administrators see only averages.
- Prototype limitation: demo login, local database, no external notifications.""")
