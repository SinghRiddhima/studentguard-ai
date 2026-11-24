"""Private self-service profile and student access to SOS."""
from io import BytesIO

import streamlit as st
from PIL import Image, ImageOps, UnidentifiedImageError

import config
from src.contact_verification import LABELS, VerificationError, VerifyService, normalise_contact
from views import contact_verification, student_dashboard

ROLE_LABELS = {"student": "Student", "counsellor": "Counsellor", "admin": "Administrator"}


def normalise_avatar(upload):
    if upload.size > 2 * 1024 * 1024:
        raise ValueError("Choose an image under 2 MB.")
    try:
        with Image.open(upload) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"} or max(source.size) > 4096:
                raise ValueError("Choose a JPG, PNG or WebP image up to 4096 pixels on each side.")
            avatar = ImageOps.exif_transpose(source).convert("RGB")
            avatar.thumbnail((320, 320))
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ValueError("That image could not be opened.") from exc
    output = BytesIO()
    avatar.save(output, format="JPEG", quality=86)
    return output.getvalue()


def render(ctx):
    user, db = ctx.user, ctx.db
    is_student = user["role"] == "student"
    student = db.get_student(user, user["student_id"]) if is_student else None
    avatar = db.own_avatar(user)
    contacts = db.own_contacts(user)

    st.title("My profile")
    portrait, identity = st.columns([1, 4], vertical_alignment="center")
    with portrait:
        if avatar:
            st.image(avatar, width=116)
        else:
            initials = "".join(part[0].upper() for part in user["display_name"].split()[:2])
            st.badge(initials or "SG", icon=":material/person:", color="violet")
    with identity:
        st.text(user["display_name"])
        st.caption(ROLE_LABELS[user["role"]])

    if st.session_state.pop("sg_profile_saved", False):
        st.success("Profile saved.")

    details, activity = st.columns(2)
    with details:
        with st.container(border=True):
            st.subheader("Account details")
            st.text(f"Username · {user['username']}")
            if student:
                st.text(f"College student ID · {student['college_id'] or 'Not added'}")
                st.text(f"Programme · {student['program']}")
                st.text(f"Year · {student['year']}")
            for channel, label in LABELS.items():
                contact = contacts.get(channel)
                if contact:
                    status = "Verified" if contact["verified_at"] else "Unverified"
                    st.text(f"{label} · {contact['destination']} · {status}")
                else:
                    st.text(f"{label} · Not added")
    with activity:
        with st.container(border=True):
            st.subheader("Check-in" if is_student else "Workspace")
            if is_student:
                status = db.checkin_status(user)
                st.write("Your check-in is available." if status["available"] else
                         f"Next check-in opens {status['available_on']:%d %b %Y}.")
                st.caption("Open My Dashboard to check in or review your progress.")
            else:
                st.write("Use the sidebar to open your role’s tools.")

    with st.expander("Edit profile"):
        with st.form("edit_profile"):
            display_name = st.text_input("Display name", value=user["display_name"], max_chars=80)
            username = st.text_input("Username", value=user["username"], max_chars=40)
            college_id = program = year = None
            if student:
                college_id = st.text_input("College student ID", value=student["college_id"] or "", max_chars=40)
                current_program = student["program"]
                programmes = list(config.PROGRAMS)
                if current_program and current_program not in programmes:
                    programmes.insert(0, current_program)
                index = programmes.index(current_program) if current_program else None
                program = st.selectbox("Programme / course", programmes, index=index)
                year = st.number_input("Year of study", min_value=1, max_value=8, value=student["year"], step=1)
            upload = st.file_uploader("Profile photo", type=["jpg", "jpeg", "png", "webp"])
            remove = st.checkbox("Remove current photo") if avatar else False
            if st.form_submit_button("Save profile", type="primary"):
                try:
                    image = normalise_avatar(upload) if upload else None
                    db.update_own_profile(
                        user, display_name, image, remove, username=username,
                        college_id=college_id if college_id or (student and student["college_id"]) else None,
                        program=program if student and program != student["program"] else None,
                        year=year if student and year != student["year"] else None,
                    )
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.session_state["sg_profile_saved"] = True
                    st.rerun()

    with st.expander("Edit and verify contact details"):
        render_contacts(db, user, contacts)

    with st.expander("Change password"):
        with st.form("change_password", clear_on_submit=True):
            current = st.text_input("Current password", type="password", max_chars=128)
            password = st.text_input("New password", type="password", max_chars=128)
            confirm = st.text_input("Confirm new password", type="password", max_chars=128)
            if st.form_submit_button("Update password"):
                try:
                    if password != confirm:
                        raise ValueError("The new passwords must match.")
                    db.change_own_password(user, current, password)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.success("Password updated.")

    if is_student:
        if st.button("SOS Counselling", type="primary"):
            st.session_state["sg_profile_sos"] = True
        if st.session_state.get("sg_profile_sos") or st.session_state.get("sos_confirm"):
            if st.session_state.get("sg_profile_sos"):
                student_dashboard.render_sos(ctx, expanded=True)
            else:
                st.success(f"Counselling request saved. Request ID: {st.session_state['sos_confirm']}")
        with st.expander("Privacy and support"):
            st.caption("Your counselling message is available to authorised counsellors and to you.")
            st.caption(config.EMERGENCY_NOTE)


def render_contacts(db, user, contacts):
    try:
        service = VerifyService.configured()
    except VerificationError as exc:
        st.error(str(exc))
        return
    if service is None:
        st.caption("Use fictional contact details in demo mode. Email and SMS codes are unavailable.")
    for channel, label in LABELS.items():
        current = contacts.get(channel, {})
        previous = current.get("destination")
        key = f"sg_contact_{user['user_id']}_{channel}"
        pending = st.session_state.get(key)
        if pending and service:
            if st.button(f"Cancel {label.lower()} change", key=f"{key}_cancel"):
                st.session_state.pop(key)
                st.rerun()
            if contact_verification.confirm_code(service, channel, pending["destination"], pending["code"], key):
                st.session_state.pop(key)
                try:
                    db.save_own_contact(user, channel, pending["destination"], True, pending["previous"])
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.session_state["sg_profile_saved"] = True
                    st.rerun()
            continue
        with st.form(f"{key}_edit"):
            value = st.text_input(label, value=previous or "", max_chars=254 if channel == "email" else 24)
            if st.form_submit_button(f"{'Verify' if service else 'Save'} {label.lower()}"):
                try:
                    destination = normalise_contact(channel, value)
                    if destination == previous and current.get("verified_at"):
                        st.caption("This contact is already verified.")
                    elif service:
                        st.session_state[key] = dict(destination=destination, previous=previous, code={})
                        st.rerun()
                    else:
                        db.save_own_contact(user, channel, destination, False, previous)
                        st.session_state["sg_profile_saved"] = True
                        st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
