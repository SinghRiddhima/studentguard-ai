"""Private self-service profile and student access to SOS."""
from io import BytesIO

import streamlit as st
from PIL import Image, ImageOps, UnidentifiedImageError

import config
from views import student_dashboard

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
                st.text(f"Student ID · {student['student_id']}")
                st.text(f"Programme · {student['program']}")
                st.text(f"Year · {student['year']}")
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
            upload = st.file_uploader("Profile photo", type=["jpg", "jpeg", "png", "webp"])
            remove = st.checkbox("Remove current photo") if avatar else False
            if st.form_submit_button("Save profile", type="primary"):
                try:
                    image = normalise_avatar(upload) if upload else None
                    db.update_own_profile(user, display_name, image, remove)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.session_state["sg_profile_saved"] = True
                    st.rerun()

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
