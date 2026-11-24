"""Shared code entry for student registration and contact changes."""
from time import monotonic

import streamlit as st

from src.contact_verification import VerificationError


def confirm_code(service, channel, destination, state, key):
    method = "email" if channel == "email" else "SMS"
    if st.button(f"Send {method} code", key=f"{key}_send"):
        try:
            if state and monotonic() - state["sent_at"] < 60:
                raise VerificationError("Wait one minute before requesting another code.")
            sid = service.send(channel, destination)
            state.update(sid=sid, sent_at=monotonic())
        except VerificationError as exc:
            st.error(str(exc))
    if not state:
        return False
    st.caption(f"Code requested for {destination}.")
    with st.form(f"{key}_code", clear_on_submit=True):
        code = st.text_input(f"{method} verification code", max_chars=10, type="password")
        submitted = st.form_submit_button(f"Verify {method} code")
    if submitted:
        try:
            service.check(channel, destination, state["sid"], code)
        except VerificationError as exc:
            st.error(str(exc))
        else:
            return True
    return False
