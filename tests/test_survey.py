from datetime import datetime, timedelta
import pytest
from src import survey
from src.database import CheckInTooSoon

CALM = {"q3": "Above Average", "q4": "90–100%", "q5": "Rarely", "q6": "Increased slightly", "q7": "5 – Very clear",
        "q8": "5 – Very satisfied", "q9": "5 – Highly aligned", "q10": "Never", "q11": "1 – Not at all", "q12": "2",
        "q13": "5 – Very confident", "q14": "5 – Very comfortable", "q15": "Adequate", "q16": ["Career counselling"],
        "q17": "Never", "q18": "1 – Very unlikely", "q19": "Other"}
STRESSED = dict(CALM, q3="Below Average", q4="Below 60%", q5="Very often", q6="Decreased significantly", q7="1 – Not clear at all",
                q8="1 – Very dissatisfied", q9="1 – Not aligned at all", q10="Currently planning to change", q11="5 – Very significantly",
                q13="1 – Not confident at all", q14="1 – Very uncomfortable", q15="Not available", q17="I am currently considering it",
                q18="5 – Very likely")


def test_mapping_values():
    f, assumed = survey.map_answers(CALM)
    assert f["academic_performance"] == 3 and f["attendance_pct"] == 95 and f["study_stress"] == 2
    assert f["motivation"] == 4 and f["career_clarity"] == 5 and f["considered_change"] == 0 and f["career_guidance"] == 4
    assert assumed == ["academic_trend"]            # no previous snapshot -> trend assumed
    assert set(f) == set(__import__("config").FEATURE_KEYS)


def test_unknown_answers_are_flagged_not_silently_used():
    f, assumed = survey.map_answers(dict(CALM, q3="Prefer not to say", q4="Not sure", q15="I don't know"))
    assert {"academic_performance", "attendance_pct", "career_guidance"} <= set(assumed)


def test_trend_derived_from_previous_snapshot():
    prev = dict(survey.map_answers(CALM)[0])
    f, assumed = survey.map_answers(dict(CALM, q3="Average"), prev)
    assert f["academic_trend"] == 1 and "academic_trend" not in assumed
    f, _ = survey.map_answers(dict(CALM, q3="Excellent"), prev)
    assert f["academic_trend"] == 3
    f, _ = survey.map_answers(dict(CALM, q4="80–89%"), prev)
    assert f["academic_trend"] == 1          # attendance fell 10 points


def test_intent_flag_and_validation():
    assert survey.intent_flag(CALM) == 0 and survey.intent_flag(STRESSED) == 1
    assert survey.intent_flag(dict(CALM, q18="4")) == 1
    bad = {k: v for k, v in CALM.items() if k != "q5"}
    assert survey.validate_answers(bad)
    assert survey.validate_answers(dict(CALM, q16=["Career counselling", "Financial assistance", "Other"]))
    assert survey.validate_answers(dict(CALM, q5="Sometimes-ish"))
    assert not survey.validate_answers(CALM)


def test_checkin_creates_assessment_and_zone(db):
    s = db.authenticate("student1", "student123")
    res = survey.submit_checkin(db, s, STRESSED, None, True)
    assert res["zone"] == "RED" and res["mode"] == "DEMONSTRATION"
    assert db.get_assessments(s, "S001")[0]["assessment_id"] == res["assessment_id"]
    c = db.authenticate("counsellor", "counsel123")
    chk = db.get_checkins(c, "S001")[0]
    assert chk["intent_flag"] == 1 and chk["extras"]["main_factor"] == "Other"


def test_consent_required(db):
    s = db.authenticate("student1", "student123")
    with pytest.raises(ValueError, match="agree"):
        survey.submit_checkin(db, s, CALM, None, False)
    assert db.checkin_status(s)["available"]          # nothing saved


def test_once_per_30_days_per_student(db):
    s1 = db.authenticate("student1", "student123")
    s2 = db.authenticate("student2", "student123")
    t0 = datetime(2026, 11, 1, 10, 0)
    survey.submit_checkin(db, s1, CALM, None, True, at=t0)
    with pytest.raises(CheckInTooSoon) as e:
        survey.submit_checkin(db, s1, CALM, None, True, at=t0 + timedelta(days=10))
    assert e.value.available_on == t0 + timedelta(days=30)
    survey.submit_checkin(db, s2, CALM, None, True, at=t0 + timedelta(days=10))      # other student unaffected
    survey.submit_checkin(db, s1, CALM, None, True, at=t0 + timedelta(days=31))      # window reopened
    assert len(db.get_checkins(s1, "S001")) == 2
    assert [a["action"] for a in db.list_audit(db.authenticate("counsellor", "counsel123"), 20)].count("submit_checkin") == 3


def test_only_students_can_checkin(db, counsellor):
    with pytest.raises(PermissionError):
        survey.submit_checkin(db, counsellor, CALM, None, True)
