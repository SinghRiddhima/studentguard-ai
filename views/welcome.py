"""Public welcome, sign-in and student registration."""
from time import monotonic

import streamlit as st

import config
from src.contact_verification import LABELS, VerificationError, VerifyService, normalise_contact
from views import contact_verification, ui

ORBITS = """
<div class="sg-orbit" aria-hidden="true">
  <div class="sg-orbit-ring" style="--tilt:-28deg"></div>
  <div class="sg-orbit-ring" style="--tilt:32deg"></div>
  <div class="sg-orbit-ring" style="--tilt:84deg"></div>
  <div class="sg-orbit-core"></div>
</div>
"""


def landing():
    st.html(f"""
    <section class="sg-landing">
      <div>
        <div class="sg-eyebrow">EARLY WARNING. HUMAN SUPPORT. BETTER OUTCOMES.</div>
        <h1>Every Student Deserves a Chance to Continue.</h1>
        <p>Identify where students may need support and connect them with a counsellor early.</p>
      </div>
      {ORBITS}
    </section>
    """)
    enter, discover = st.columns(2)
    if enter.button("Enter StudentGuard", type="primary", width="stretch"):
        st.session_state["sg_screen"] = "auth"
        st.rerun()
    if discover.button("Discover How It Works", width="stretch"):
        st.session_state["sg_discover"] = True
    features = [
        ("Explainable AI", "Review the indicators behind an assessment."),
        ("Intelligent Risk Zones", "Use Green, Yellow and Red to guide follow-up."),
        ("SOS Counselling", "Request support from any zone."),
        ("Human-Led Decisions", "Counsellors review recommendations and record their decisions."),
    ]
    for col, (title, description) in zip(st.columns(4), features):
        with col:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.caption(description)
    if st.session_state.get("sg_discover"):
        st.write("Students check in, the system highlights possible concerns, and a counsellor reviews suggested support. "
                "Students can also request counselling directly from their profile.")
    st.markdown("**AI supports the decision. People make the difference.**")
    ui.emergency_note()


def authentication(db):
    if st.button("Back to welcome"):
        st.session_state.pop("sg_pending_signup", None)
        st.session_state["sg_screen"] = "welcome"
        st.rerun()
    panel, forms = st.columns([1, 1], gap="large")
    with panel:
        st.html(f'<div class="sg-landing" style="grid-template-columns:1fr;min-height:unset">'
                f'<div><div class="sg-eyebrow">STUDENTGUARD AI</div><h2>Early support starts here.</h2></div>{ORBITS}</div>')
        with st.expander("Demo accounts"):
            st.caption("DEMO authentication. Use fictional information in this classroom prototype.")
            st.table({"Role": ["Student", "Counsellor", "Administrator"],
                      "Username": ["student1", "counsellor", "admin"],
                      "Password": ["student123", "counsel123", "admin123"]})
        ui.emergency_note()
    with forms:
        signin, signup = st.tabs(["Sign in", "Student sign-up"])
        with signin:
            with st.form("login"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                if st.form_submit_button("Sign in", type="primary"):
                    user = db.authenticate(username, password)
                    if user:
                        st.session_state.pop("sg_pending_signup", None)
                        st.session_state["user"] = user
                        st.rerun()
                    st.error("Invalid username or password.")
        with signup:
            render_signup(db)


def render_signup(db):
    try:
        service = VerifyService.configured()
    except VerificationError as exc:
        st.error(str(exc))
        return
    pending = st.session_state.get("sg_pending_signup")
    if pending and (service is None or monotonic() - pending["started"] >= 900):
        st.session_state.pop("sg_pending_signup")
        st.caption("Your verification session expired. Enter your details again.")
        pending = None
    if pending:
        st.subheader("Verify your contact details")
        if st.button("Start sign-up again"):
            st.session_state.pop("sg_pending_signup")
            st.rerun()
        for channel, destination in pending["contacts"].items():
            if channel in pending["verified"]:
                st.caption(f"{LABELS[channel]} verified.")
            elif contact_verification.confirm_code(service, channel, destination, pending["codes"][channel], f"signup_{channel}"):
                pending["verified"].add(channel)
                st.rerun()
        if pending["verified"] == set(LABELS) and st.button("Create student account", type="primary"):
            try:
                user = db.complete_registration(pending["registration"], pending["contacts"], pending["verified"])
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state.pop("sg_pending_signup")
                st.session_state["user"] = user
                st.rerun()
        return

    if service is None:
        st.caption("Demo sign-up uses fictional contact details. Email and SMS codes are unavailable.")
    with st.form("register"):
        code = st.text_input("Invite code (optional)", type="password")
        name = st.text_input("Display name", max_chars=80)
        username = st.text_input("Choose a username", max_chars=40)
        password = st.text_input("Choose a password (at least 8 characters)", type="password", max_chars=128)
        college_id = st.text_input("College student ID", max_chars=40)
        program = st.selectbox("Programme / course", options=config.PROGRAMS)
        year = st.number_input("Year of study", min_value=1, max_value=8, step=1)
        email = st.text_input("Email address", max_chars=254)
        phone = st.text_input("Phone number", placeholder="+91…", max_chars=24)
        label = "Continue to verification" if service else "Create student account"
        if st.form_submit_button(label, type="primary"):
            try:
                contacts = {"email": normalise_contact("email", email), "sms": normalise_contact("sms", phone)}
                registration = db.prepare_registration(code, username, password, name, program, year, college_id)
                if service:
                    st.session_state["sg_pending_signup"] = dict(registration=registration, contacts=contacts,
                                                                 started=monotonic(), verified=set(),
                                                                 codes={channel: {} for channel in contacts})
                else:
                    st.session_state["user"] = db.complete_registration(registration, contacts)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.rerun()
