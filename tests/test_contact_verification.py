"""Exercise account creation and contact changes with the delivery provider mocked."""
from src.contact_verification import VerifyService
from src.database import Database
from tests.test_app import click, open_app


def test_signup_and_contact_changes_require_approved_codes(tmp_path, monkeypatch):
    monkeypatch.setenv("TWILIO_VERIFY_SERVICE_SID", "VA" + "a" * 32)
    monkeypatch.setenv("TWILIO_VERIFY_API_KEY", "test-key")
    monkeypatch.setenv("TWILIO_VERIFY_API_SECRET", "test-secret")
    challenges = {}

    def verify_response(service, resource, **fields):
        if resource == "Verifications":
            sid = f"VE{len(challenges):032x}"
            challenges[sid] = (fields["Channel"], fields["To"])
            return {"status": "pending", "sid": sid}
        assert resource == "VerificationCheck"
        sid = fields["VerificationSid"]
        channel, destination = challenges[sid]
        return {"status": "approved" if fields["Code"] == "123456" else "pending",
                "sid": sid, "channel": channel, "to": destination}

    monkeypatch.setattr(VerifyService, "_post", verify_response)
    at = open_app(tmp_path, monkeypatch)
    db = Database(tmp_path / "app.db")

    def enter(label, value):
        next(widget for widget in at.text_input if widget.label == label).set_value(value)

    click(at, "Enter StudentGuard")
    for label, value in {
        "Display name": "Example Student", "Choose a username": "college.student",
        "Choose a password (at least 8 characters)": "demoPass123", "College student ID": "CE/2026/10",
        "Email address": "old@example.com", "Phone number": "+12025550123",
    }.items():
        enter(label, value)
    click(at, "Continue to verification")
    click(at, "Send email code")
    enter("email verification code", "123456")
    click(at, "Verify email code")
    assert db.authenticate("college.student", "demoPass123") is None
    click(at, "Send SMS code")
    enter("SMS verification code", "123456")
    click(at, "Verify SMS code")
    click(at, "Create student account")
    user = db.authenticate("college.student", "demoPass123")
    assert user and all(contact["verified_at"] for contact in db.own_contacts(user).values())

    request = db.create_sos_request(user, "Other", "", "No preference")
    enter("College student ID", "CE/2026/11")
    enter("Username", "updated.student")
    click(at, "Save profile")
    updated = db.authenticate("updated.student", "demoPass123")
    assert updated["student_id"] == user["student_id"]
    assert db.get_student(updated, updated["student_id"])["college_id"] == "CE/2026/11"
    assert db.my_sos_requests(updated)[0]["request_id"] == request

    enter("Email address", "new@example.com")
    click(at, "Verify email address")
    click(at, "Send email code")
    enter("email verification code", "999999")
    click(at, "Verify email code")
    assert db.own_contacts(updated)["email"]["destination"] == "old@example.com"
    enter("email verification code", "123456")
    click(at, "Verify email code")
    email = db.own_contacts(updated)["email"]
    assert email["destination"] == "new@example.com" and email["verified_at"]
