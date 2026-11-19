import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database import Database  # noqa: E402
from src.seed import seed_demo_data  # noqa: E402


@pytest.fixture()
def db(tmp_path):
    d = Database(tmp_path / "t.db")
    seed_demo_data(d, None)
    d.tmp_path = tmp_path / "t.db"
    return d


@pytest.fixture()
def counsellor(db):
    return db.authenticate("counsellor", "counsel123")


@pytest.fixture()
def student(db):
    return db.authenticate("student1", "student123")


@pytest.fixture()
def admin(db):
    return db.authenticate("admin", "admin123")


GOOD = dict(academic_performance=4, academic_trend=3, attendance_pct=98, study_stress=1, motivation=5, career_clarity=5,
            course_satisfaction=5, course_career_alignment=5, financial_difficulty=1, family_pressure=1,
            confidence_continuing=5, faculty_comfort=5, career_guidance=4, considered_change=0)
BAD = dict(academic_performance=1, academic_trend=1, attendance_pct=45, study_stress=5, motivation=1, career_clarity=1,
           course_satisfaction=1, course_career_alignment=1, financial_difficulty=5, family_pressure=5,
           confidence_continuing=1, faculty_comfort=1, career_guidance=1, considered_change=1)
