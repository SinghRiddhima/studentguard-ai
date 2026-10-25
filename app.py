"""StudentGuard AI – Streamlit entry point. Run:  streamlit run app.py"""
import json
from types import SimpleNamespace

import streamlit as st

import config
from src import predict, seed
from src.data_preprocessing import DatasetError
from src.database import Database

st.set_page_config(page_title=config.APP_TITLE, page_icon="🛡️", layout="wide")

from views import (administrator_dashboard, counselling_requests, counsellor_dashboard,  # noqa: E402
                   model_performance, progress_trends, risk_assessment, student_dashboard, ui)


@st.cache_resource
def get_db():
    db = Database()
    return db


@st.cache_resource
def get_bundle():
    return predict.load_bundle()


def bootstrap():
    db, bundle = get_db(), get_bundle()
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


def login_screen(db):
    ui.hero()
    st.warning("Prototype with DEMO authentication — do not enter real student data. See README for limitations.")
    c1, c2 = st.columns([1, 1])
    with c1:
        with st.form("login"):
            st.markdown("### Sign in")
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("Sign in", type="primary"):
                user = db.authenticate(u, p)
                if user:
                    st.session_state["user"] = user
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
    with c2:
        st.markdown("### Demo accounts (synthetic data)")
        st.table({"Role": ["Student", "Counsellor", "Administrator"],
                  "Username": ["student1 (also student2, student3)", "counsellor", "admin"],
                  "Password": ["student123", "counsel123", "admin123"]})
        st.caption("Shown only because this is a classroom demo.")
    ui.emergency_note()


def main():
    ui.inject_css()
    db, bundle = bootstrap()
    user = st.session_state.get("user")
    if not user:
        login_screen(db)
        return
    ctx = SimpleNamespace(db=db, bundle=bundle, user=user, mode=predict.mode_of(bundle))

    def page(fn, name):
        def _p():
            ui.hero()
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
    nav = st.navigation(pages)
    with st.sidebar:
        st.markdown(f"**{user['display_name']}**  \n_{role}_")
        if st.button("Sign out"):
            st.session_state.clear()
            st.rerun()
        st.divider()
        st.caption(config.ADVISORY_NOTICE)
        st.caption("Privacy: access is role-based; private messages are visible only to authorised counsellors.")
    nav.run()


main()
