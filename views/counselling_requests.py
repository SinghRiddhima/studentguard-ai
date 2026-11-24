"""Counsellor SOS queue: view requests, update status, record follow-up."""
from datetime import date, datetime, time
import streamlit as st
import config
from views import ui


def render(ctx):
    db, user = ctx.db, ctx.user
    st.subheader("SOS Counselling Requests")
    st.caption("Requests are independent of AI risk zones. Updates appear in this queue; email/SMS notifications are not sent.")
    choice = st.multiselect("Filter by status", config.SOS_STATUSES, default=["Submitted", "Acknowledged", "Contact in progress", "Session scheduled"])
    reqs = db.list_sos_requests(user, choice or None)
    if not reqs:
        st.caption("No requests match this filter.")
        return
    st.write(f"{len(reqs)} request(s)")
    for r in reqs:
        label = f"{r['request_id']} · {r['alias']} · {r['category']} · {r['status']}"
        with st.expander(label, expanded=(r["status"] == "Submitted")):
            if r["is_synthetic"]:
                st.caption("SYNTHETIC demo request")
            st.write(f"**Submitted:** {r['created_at']}  ·  **Updated:** {r['updated_at']}  ·  **Preferred contact:** {r['contact_method']}")
            st.text_area("Student's message (confidential)", r["message"] or "(no message)", disabled=True, key=f"m_{r['request_id']}")
            for h in r["history"]:
                st.caption(f"{h['created_at']} → {h['status_after']} by {h.get('author') or 'student'}"
                           + (f" · session {h['scheduled_for']}" if h.get("scheduled_for") else "")
                           + (f" · note: {h['note']}" if h.get("note") else ""))
            with st.form(f"s_{r['request_id']}"):
                c1, c2 = st.columns(2)
                new = c1.selectbox("New status", config.SOS_STATUSES, index=config.SOS_STATUSES.index(r["status"]))
                note = c2.text_input("Follow-up note (private)")
                d1, d2 = st.columns(2)
                sd = d1.date_input("Session date (if scheduling)", value=date.today())
                stime = d2.time_input("Session time", value=time(11, 0))
                if st.form_submit_button("Update status"):
                    try:
                        when = datetime.combine(sd, stime).isoformat(sep=" ", timespec="minutes") if new == "Session scheduled" else None
                        db.update_sos_status(user, r["request_id"], new, note, when)
                        st.success("Status updated.")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
