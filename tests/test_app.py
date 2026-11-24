"""End-to-end UI tests using Streamlit's AppTest (each role, each page)."""
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest


def _view_script(view, fn, username, password, db_path):
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    sys.path.insert(0, str(Path.cwd()))
    import importlib
    from src import predict
    from src.database import Database
    from src.seed import seed_demo_data
    import streamlit as st
    db = Database(db_path)
    seed_demo_data(db, None)
    if "user" not in st.session_state:
        st.session_state["user"] = db.authenticate(username, password)
    ctx = SimpleNamespace(db=db, bundle=predict.load_bundle(), user=st.session_state["user"], mode="DEMONSTRATION")
    getattr(importlib.import_module(f"views.{view}"), fn)(ctx)


def run(view, fn, user, pw, path):
    at = AppTest.from_function(_view_script, args=(view, fn, user, pw, str(path)), default_timeout=90)
    return at.run()


def click(at, label):
    return next(button for button in at.button if button.label == label).click().run()


def open_app(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDENTGUARD_DB", str(tmp_path / "app.db"))
    return AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=90).run()


def test_app_launches_to_welcome(tmp_path, monkeypatch):
    at = open_app(tmp_path, monkeypatch)
    assert not at.exception
    assert any("Every Student Deserves a Chance to Continue." in element.value for element in at.get("html"))
    click(at, "Light mode")
    assert at.query_params["theme"] == "light"
    click(at, "Enter StudentGuard")
    assert not at.exception
    assert any("DEMO authentication" in w.value for w in at.caption)


@pytest.mark.parametrize("username,password", [
    ("student1", "student123"), ("counsellor", "counsel123"), ("admin", "admin123"),
])
def test_profile_is_the_first_page(tmp_path, monkeypatch, username, password):
    at = open_app(tmp_path, monkeypatch)
    click(at, "Enter StudentGuard")
    at.text_input[0].set_value(username)
    at.text_input[1].set_value(password)
    click(at, "Sign in")
    assert not at.exception
    assert any(element.value == "My profile" for element in at.title)
    if username == "student1":
        at.text_input[0].set_value("Demo Student")
        click(at, "Save profile")
        assert any(element.value == "Demo Student" for element in at.text)
        click(at, "SOS Counselling")
        click(at, "Submit request")
        assert any("Counselling request saved" in element.value for element in at.success)
    click(at, "Sign out")
    assert any(button.label == "Enter StudentGuard" for button in at.button)


def test_invite_signup_opens_profile(tmp_path, monkeypatch):
    from src.database import Database

    at = open_app(tmp_path, monkeypatch)
    db = Database(tmp_path / "app.db")
    admin = db.authenticate("admin", "admin123")
    code = db.create_student_invite(admin)
    click(at, "Enter StudentGuard")
    for label, value in {
        "Invite code (optional)": code, "Display name": "Demo Student",
        "Choose a username": "demo.student", "Choose a password (at least 8 characters)": "demoPass123",
    }.items():
        next(widget for widget in at.text_input if widget.label == label).set_value(value)
    next(w for w in at.selectbox if w.label == "Programme / course").select("Computer Engineering")
    click(at, "Create student account")
    assert not at.exception
    assert any(element.value == "My profile" for element in at.title)
    user = db.authenticate("demo.student", "demoPass123")
    assert user["role"] == "student"
    with pytest.raises(ValueError, match="already used"):
        db.register_student(code, "another.student", "demoPass123", "Another Demo", "Computer Engineering", 1)


@pytest.mark.parametrize("view,fn,user,pw", [
    ("student_dashboard", "render", "student1", "student123"),
    ("counsellor_dashboard", "render_overview", "counsellor", "counsel123"),
    ("counsellor_dashboard", "render_directory", "counsellor", "counsel123"),
    ("counsellor_dashboard", "render_intervention_centre", "counsellor", "counsel123"),
    ("risk_assessment", "render", "counsellor", "counsel123"),
    ("counselling_requests", "render", "counsellor", "counsel123"),
    ("model_performance", "render", "counsellor", "counsel123"),
    ("progress_trends", "render", "counsellor", "counsel123"),
    ("administrator_dashboard", "render", "admin", "admin123"),
    ("administrator_dashboard", "render_settings", "admin", "admin123"),
])
def test_every_page_renders(tmp_path, view, fn, user, pw):
    at = run(view, fn, user, pw, tmp_path / "p.db")
    assert not at.exception, at.exception


def test_student_sos_button_and_form(tmp_path):
    at = run("student_dashboard", "render", "student1", "student123", tmp_path / "s.db")
    at.button[0].click().run()
    assert not at.exception
    at.text_area[0].input("I need to talk").run()
    next(b for b in at.button if b.label == "Submit request").click().run()
    assert not at.exception
    assert any("Request ID" in s.value for s in at.success)


def test_assessment_form_saves_and_shows_decision(tmp_path):
    at = run("risk_assessment", "render", "counsellor", "counsel123", tmp_path / "r.db")
    at.button[0].click().run()
    assert not at.exception
    assert any("Assessment saved" in s.value for s in at.success)
    assert any("Your decision" in m.value for m in at.markdown)


def test_student_checkin_form_end_to_end(tmp_path):
    at = run("student_dashboard", "render", "student1", "student123", tmp_path / "c.db")
    assert not at.exception
    assert len(at.radio) == 16                                  # 16 single/scale questions + 1 multiselect (Q16)
    for r in at.radio:
        r.set_value(r.options[1])
    at.multiselect[0].set_value([at.multiselect[0].options[0]])
    at.checkbox[0].check()
    next(b for b in at.button if b.label == "Submit check-in").click().run()
    assert not at.exception, at.exception
    assert any("check-in was saved" in s.value for s in at.success)
    at.run()                                                      # reload -> monthly lock message is not shown only for done-state
    assert not at.exception


def test_checkin_lock_message_after_submit(tmp_path):
    from datetime import datetime
    from src import survey
    from src.database import Database
    from tests.test_survey import CALM
    db = Database(tmp_path / "l.db")
    from src.seed import seed_demo_data
    seed_demo_data(db, None)
    survey.submit_checkin(db, db.authenticate("student1", "student123"), CALM, None, True)
    at = run("student_dashboard", "render", "student1", "student123", tmp_path / "l.db")
    assert not at.exception
    assert any("check-ins open once every" in i.value for i in at.caption)
    assert len(at.radio) == 0                                   # form hidden while locked


def test_feedback_form_submits(tmp_path):
    at = run("student_dashboard", "render", "student1", "student123", tmp_path / "f.db")
    assert not at.exception
    next(b for b in at.button if b.label == "Send feedback").click().run()
    assert not at.exception, at.exception


def test_avatar_is_resized_and_removed(db, student):
    from io import BytesIO

    from PIL import Image
    from views.profile import normalise_avatar

    upload = BytesIO()
    Image.new("RGB", (640, 480), "violet").save(upload, format="PNG")
    upload.size = upload.tell()
    upload.seek(0)
    avatar = normalise_avatar(upload)
    with Image.open(BytesIO(avatar)) as image:
        assert image.format == "JPEG"
        assert image.size == (320, 240)
    db.update_own_profile(student, "Demo Student", avatar)
    assert db.own_avatar(student) == avatar
    db.update_own_profile(student, "Demo Student", remove_avatar=True)
    assert db.own_avatar(student) is None
