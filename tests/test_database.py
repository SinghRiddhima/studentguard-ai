import pytest
from src import predict
from src.database import Database
from tests.conftest import BAD


def test_init_and_seed(db, counsellor):
    assert db.user_count() == 6
    students = db.list_students(counsellor)
    assert len(students) == 40 and all(s["is_synthetic"] == 1 for s in students)
    assert sum(db.zone_distribution(counsellor).values()) == 40


def test_passwords_not_plaintext(db):
    rows = db._q("SELECT password_hash FROM users")
    plain = {"student123", "counsel123", "admin123"}
    assert all(r["password_hash"] not in plain and len(r["password_hash"]) == 64 for r in rows)
    assert db.authenticate("student1", "wrong") is None


def test_student_cannot_access_other_students(db, student, counsellor):
    with pytest.raises(PermissionError):
        db.get_assessments(student, "S002")
    with pytest.raises(PermissionError):
        db.get_student(student, "S002")
    with pytest.raises(PermissionError):
        db.list_students(student)
    with pytest.raises(PermissionError):
        db.list_sos_requests(student)
    assert db.get_assessments(student, "S001")


def test_admin_cannot_read_messages_or_students(db, admin):
    with pytest.raises(PermissionError):
        db.list_sos_requests(admin)
    with pytest.raises(PermissionError):
        db.list_students(admin)
    stats = db.sos_stats(admin)
    assert "message" not in str(stats).lower()


def test_sos_submit_persist_and_track(db, student, counsellor):
    rid = db.create_sos_request(student, "Academic pressure", "private text", "Email")
    assert rid.startswith("SOS-")
    db2 = Database(db.tmp_path)    # simulates app restart
    mine = db2.my_sos_requests(student)
    assert any(r["request_id"] == rid and r["status"] == "Submitted" for r in mine)
    assert any(r["request_id"] == rid and r["message"] == "private text" for r in db2.list_sos_requests(counsellor))
    with pytest.raises(ValueError):
        db.create_sos_request(student, "Not a category", "x", "Email")


def test_green_zone_student_can_still_submit_sos(db):
    # every student account may submit regardless of zone
    s = db.authenticate("student2", "student123")
    assert db.create_sos_request(s, "Other", "", "No preference")


def test_counsellor_updates_status_and_student_sees_it(db, student, counsellor):
    rid = db.create_sos_request(student, "Career confusion", "m", "Phone call")
    db.update_sos_status(counsellor, rid, "Acknowledged", "seen")
    with pytest.raises(ValueError):
        db.update_sos_status(counsellor, rid, "Session scheduled")  # needs a date
    db.update_sos_status(counsellor, rid, "Session scheduled", "booked", "2026-10-20 11:00")
    mine = [r for r in db.my_sos_requests(student) if r["request_id"] == rid][0]
    assert mine["status"] == "Session scheduled" and len(mine["history"]) == 3
    assert "seen" not in str(mine["history"])          # private counsellor notes hidden from student
    with pytest.raises(PermissionError):
        db.update_sos_status(student, rid, "Resolved")


def test_save_assessment_and_human_decisions_audited(db, counsellor):
    r = predict.assess("S001", BAD, None, db.get_thresholds())
    aid = db.save_assessment(counsellor, r, synthetic=True)
    for decision in ("accepted", "modified", "rejected"):
        db.record_decision(counsellor, "S001", aid, r["recommendations"], decision, "Career counselling", f"why {decision}")
    with pytest.raises(ValueError):
        db.record_decision(counsellor, "S001", aid, r["recommendations"], "accepted", "x", "  ")
    with pytest.raises(ValueError):
        db.record_decision(counsellor, "S001", aid, r["recommendations"], "auto-suspend", "x", "r")
    actions = [a["action"] for a in db.list_audit(counsellor, 50)]
    assert {"intervention_accepted", "intervention_modified", "intervention_rejected", "save_assessment"} <= set(actions)
    ints = [i for i in db.list_interventions(counsellor, "S001") if i["assessment_id"] == aid]
    assert len(ints) == 3 and {i["decision"] for i in ints} == {"accepted", "modified", "rejected"}
    iid = ints[0]["intervention_id"]
    db.update_intervention(counsellor, iid, "In progress", "called")
    assert "update_intervention" in [a["action"] for a in db.list_audit(counsellor, 5)]


def test_sos_not_affected_by_red_zone(db, counsellor):
    # a RED assessment must not change SOS handling
    s = db.authenticate("student3", "student123")
    rid = db.create_sos_request(s, "Other", "", "No preference")
    assert db.my_sos_requests(s)[0]["request_id"] == rid


def test_threshold_settings_admin_only(db, admin, counsellor):
    db.set_thresholds(admin, 20, 40)
    assert db.get_thresholds() == {"yellow": 20.0, "red": 40.0}
    with pytest.raises(PermissionError):
        db.set_thresholds(counsellor, 10, 20)
    with pytest.raises(ValueError):
        db.set_thresholds(admin, 50, 40)


# ---------------- progression & feedback ----------------
def test_progression_before_after_support(db, counsellor):
    p = db.progression(counsellor, "S001")
    assert p["first_support_at"] and p["zone_before"] == "RED" and p["zone_after"] in ("YELLOW", "GREEN")
    assert p["outcome"] == "Improved" and len(p["timeline"]) == 3
    assert db.progression(counsellor, "S002")["outcome"] == "No support recorded yet"


def test_progression_summary_mixed_outcomes_and_admin_aggregate_only(db, counsellor, admin):
    s = db.progression_summary(counsellor)
    assert s["n_with_support"] == sum(s["outcomes"].values()) > 5
    assert {"Improved", "Same zone", "Higher concern"} <= set(s["outcomes"])       # not only good news
    assert db.progression_summary(admin) == s
    with pytest.raises(PermissionError):
        db.progression_rows(admin)
    with pytest.raises(PermissionError):
        db.progression(admin, "S001")


def test_student_sees_only_own_progression(db, student):
    assert db.progression(student, "S001")["student_id"] == "S001"
    with pytest.raises(PermissionError):
        db.progression(student, "S005")


def test_new_support_changes_progression(db, student, counsellor):
    rid = db.create_sos_request(db.authenticate("student2", "student123"), "Other", "", "No preference")
    s2 = db.authenticate("student2", "student123")
    assert db.progression(s2, "S002")["first_support_at"] is None
    db.update_sos_status(counsellor, rid, "Contact in progress")
    assert db.progression(s2, "S002")["first_support_at"] is not None


def test_feedback_only_on_own_resolved_request_once(db, student, counsellor):
    resolved = [r for r in db.my_sos_requests(student) if r["status"] == "Resolved"][0]
    assert resolved["feedback"] is None                      # S001 demo request awaits feedback
    db.submit_feedback(student, resolved["request_id"], 5, 4, 5, 5, "Very helpful")
    with pytest.raises(ValueError, match="already"):
        db.submit_feedback(student, resolved["request_id"], 1, 1, 1, 1)
    open_id = db.create_sos_request(student, "Other", "", "No preference")
    with pytest.raises(ValueError, match="Resolved"):
        db.submit_feedback(student, open_id, 5, 5, 5, 5)
    other = db.authenticate("student2", "student123")
    with pytest.raises(PermissionError):
        db.submit_feedback(other, resolved["request_id"], 5, 5, 5, 5)
    with pytest.raises(ValueError):
        db.submit_feedback(student, "x", 9, 1, 1, 1)
    with pytest.raises(PermissionError):
        db.submit_feedback(counsellor, open_id, 5, 5, 5, 5)


def test_feedback_visibility_admin_gets_no_comments(db, student, admin, counsellor):
    st_ = db.feedback_stats(admin)
    assert st_["n"] > 0 and "comment" not in str(st_)
    with pytest.raises(PermissionError):
        db.list_feedback(admin)
    assert db.list_feedback(counsellor)


def test_zone_does_not_block_feedback_or_sos(db):
    red_student = db.authenticate("student1", "student123")        # S001 history includes RED
    assert db.create_sos_request(red_student, "Other", "", "No preference").startswith("SOS-")
