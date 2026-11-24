"""Public welcome and prototype sign-in."""
import streamlit as st

import config

from views import ui

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
                        st.session_state["user"] = user
                        st.rerun()
                    st.error("Invalid username or password.")
        with signup:
            st.caption("Create a student account. An invite code is optional.")
            with st.form("register"):
                code = st.text_input("Invite code (optional)", type="password", help="Leave blank if you do not have a code.")
                name = st.text_input("Display name")
                username = st.text_input("Choose a username")
                password = st.text_input("Choose a password (at least 8 characters)", type="password")
                program = st.selectbox("Programme / course", options=config.PROGRAMS)
                year = st.number_input("Year of study", min_value=1, max_value=8, step=1)
                if st.form_submit_button("Create student account", type="primary"):
                    try:
                        user = db.register_student(code, username, password, name, program, year)
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state["user"] = user
                        st.rerun()
