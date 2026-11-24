"""Regression checks for signup and the UCI academic page."""
import config
import pytest
from streamlit.testing.v1 import AppTest
from tests.test_app import open_app, click, run


@pytest.mark.parametrize('code', ['', '  ', None])
def test_student_registration_without_invite(db, code):
    user = db.register_student(code, 'new.student', 'password123', 'New Student', config.PROGRAMS[0], 2)
    assert user['role'] == 'student'
    assert db.authenticate('new.student', 'password123')['student_id'] == user['student_id']
    with pytest.raises(PermissionError):
        db.create_user(user, 'staff', 'password123', 'admin', 'Staff')


def test_bad_invite_does_not_create_user(db):
    before = db.user_count()
    with pytest.raises(ValueError, match='invalid'):
        db.register_student('invalid', 'bad.student', 'password123', 'Student', config.PROGRAMS[0], 2)
    assert db.user_count() == before


def test_unknown_programme_rejected(db):
    with pytest.raises(ValueError, match='programme'):
        db.register_student('', 'new.student', 'password123', 'Student', 'Unknown', 2)


def test_signup_without_invite_opens_profile(tmp_path, monkeypatch):
    at = open_app(tmp_path, monkeypatch)
    click(at, 'Enter StudentGuard')
    for label, value in {'Display name': 'Student Example', 'Choose a username': 'open.student',
                         'Choose a password (at least 8 characters)': 'password123'}.items():
        next(w for w in at.text_input if w.label == label).set_value(value)
    next(w for w in at.selectbox if w.label == 'Programme / course').select(config.PROGRAMS[1])
    click(at, 'Create student account')
    assert not at.exception
    assert any(t.value == 'My profile' for t in at.title)


def test_academic_model_page_and_prediction(tmp_path):
    at = run('academic_model', 'render', 'counsellor', 'counsel123', tmp_path / 'lab.db')
    assert not at.exception
    assert any('Confusion matrix' in x.value for x in at.markdown)
    click(at, 'Run academic example')
    assert not at.exception and len(at.metric) == 1


def test_academic_model_denies_student(tmp_path):
    at = run('academic_model', 'render', 'student1', 'student123', tmp_path / 'student.db')
    assert not at.exception and len(at.error) == 1
    assert not at.number_input
