"""StudentGuard AI – Streamlit entry point. Run:  streamlit run app.py"""
import json
import os
from types import SimpleNamespace

import streamlit as st

import config
from src import predict, seed
from src.data_preprocessing import DatasetError
from src.database import Database

st.set_page_config(page_title=config.APP_TITLE, page_icon="🛡️", layout="wide")

from views import (academic_model, administrator_dashboard, counselling_requests, counsellor_dashboard,  # noqa: E402
                   model_performance, profile, progress_trends, risk_assessment, student_dashboard, theme, ui, welcome)


@st.cache_resource
def get_db(path):
    db = Database(path)
    return db


@st.cache_resource
def get_bundle():
    return predict.load_bundle()


def bootstrap():
    db, bundle = get_db(os.environ.get("STUDENTGUARD_DB", str(config.DB_PATH))), get_bundle()
    if db.user_count() == 0:
        try:
            seed.seed_demo_data(db, bundle)
        except DatasetError as e:
            st.error(f"Could not load demo data: {e}")
    if config.METRICS_PATH.exists():
        try:
            db.record_model_metadata(json.loads(config.METRICS_PATH.read_text()))
        except Exception:  # noqa: BLE001
            pass
    return db, bundle


def main():
    theme.apply()
    ui.inject_css()
    db, bundle = bootstrap()
    mode = predict.mode_of(bundle)
    signed_in = st.session_state.get("user")
    user = db.active_user(signed_in["user_id"]) if signed_in else None
    if not user:
        st.session_state.pop("user", None)
        brand, appearance = st.columns([4, 1])
        brand.html('<div class="sg-wordmark">STUDENTGUARD AI</div>')
        with appearance:
            theme.toggle()
        with st.expander("About StudentGuard"):
            ui.about(mode)
        if st.session_state.get("sg_screen") == "auth":
            welcome.authentication(db)
        else:
            welcome.landing()
        return
    st.session_state["user"] = user
    ctx = SimpleNamespace(db=db, bundle=bundle, user=user, mode=mode)

    def page(fn, name):
        def _p():
            fn(ctx)
        _p.__name__ = name
        return _p

    role = user["role"]
    if role == "student":
        pages = [st.Page(page(student_dashboard.render, "my_dashboard"), title="My Dashboard", icon="🏠", url_path="my_dashboard")]
    elif role == "counsellor":
        pages = [
            st.Page(page(counsellor_dashboard.render_overview, "overview"), title="Overview", icon="📊", url_path="overview"),
            st.Page(page(risk_assessment.render, "assessment"), title="Student Risk Assessment", icon="🧭", url_path="assessment"),
            st.Page(page(counsellor_dashboard.render_directory, "directory"), title="Student Directory", icon="👥", url_path="directory"),
            st.Page(page(counsellor_dashboard.render_intervention_centre, "interventions"), title="Intervention Centre", icon="🤝", url_path="interventions"),
            st.Page(page(progress_trends.render, "trends"), title="Progress & Trends", icon="📈", url_path="trends"),
            st.Page(page(counselling_requests.render, "sos"), title="SOS Counselling Requests", icon="🆘", url_path="sos"),
            st.Page(page(model_performance.render, "model"), title="Model Performance", icon="🧪", url_path="model"),
        ]
    else:
        pages = [
            st.Page(page(administrator_dashboard.render, "admin_overview"), title="Overview", icon="📊", url_path="admin_overview"),
            st.Page(page(model_performance.render, "model"), title="Model Performance", icon="📈", url_path="model"),
            st.Page(page(administrator_dashboard.render_settings, "settings"), title="Settings", icon="⚙️", url_path="settings"),
        ]
    if role in ("counsellor", "administrator", "admin"):
        pages.append(st.Page(page(academic_model.render, "academic_lab"),
                             title="Academic Model Lab", icon="🎓", url_path="academic_lab"))
    pages.insert(0, st.Page(page(profile.render, "my_profile"), title="My Profile", icon=":material/person:", default=True))
    nav = st.navigation(pages)
    if st.session_state["sg_theme"] != "dark" and "theme" not in st.query_params:
        st.query_params["theme"] = st.session_state["sg_theme"]
    with st.sidebar:
        st.html('<div class="sg-wordmark">STUDENTGUARD AI</div>')
        st.text(user["display_name"])
        st.caption(profile.ROLE_LABELS[role])
        theme.toggle()
        if st.button("Sign out"):
            appearance = st.session_state["sg_theme"]
            st.session_state.clear()
            st.session_state["sg_theme"] = appearance
            st.rerun()
        st.divider()
        with st.expander("About StudentGuard"):
            ui.about(mode)
    nav.run()


main()
