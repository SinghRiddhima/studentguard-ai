"""SQLite persistence + role-based access enforcement.

Every public method that touches student data takes the acting `user` dict and enforces permissions
HERE (not only in the UI). All SQL is parameterised. Counselling messages are only returned to
counsellors (all) or to the student who wrote them – never to admins or in aggregates."""
import hashlib
import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

import config
from src.authentication import (hash_password, require_own_student, require_role, verify_password)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  user_id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL, salt TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('student','counsellor','admin')),
  display_name TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS student_invites (
  digest TEXT PRIMARY KEY, expires_at TEXT NOT NULL, used_by INTEGER REFERENCES users(user_id));
CREATE TABLE IF NOT EXISTS user_avatars (
  user_id INTEGER PRIMARY KEY REFERENCES users(user_id), image BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS student_profiles (
  student_id TEXT PRIMARY KEY, user_id INTEGER UNIQUE REFERENCES users(user_id),
  alias TEXT NOT NULL, program TEXT, year INTEGER, is_synthetic INTEGER NOT NULL DEFAULT 0,
  consent_to_assessment INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assessments (
  assessment_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL REFERENCES student_profiles(student_id),
  assessed_at TEXT NOT NULL, assessed_by INTEGER REFERENCES users(user_id), mode TEXT NOT NULL,
  zone TEXT NOT NULL CHECK (zone IN ('GREEN','YELLOW','RED')), risk_value REAL, model_output REAL,
  features_json TEXT NOT NULL, contributions_json TEXT NOT NULL, patterns_json TEXT NOT NULL,
  recommendations_json TEXT NOT NULL, thresholds_json TEXT NOT NULL, explanation_method TEXT,
  is_synthetic INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS counselling_requests (
  request_id TEXT PRIMARY KEY, student_id TEXT NOT NULL REFERENCES student_profiles(student_id),
  category TEXT NOT NULL, message TEXT, contact_method TEXT, status TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, assigned_to INTEGER REFERENCES users(user_id),
  is_synthetic INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS interventions (
  intervention_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL REFERENCES student_profiles(student_id),
  assessment_id INTEGER REFERENCES assessments(assessment_id), ai_suggestion_json TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('accepted','modified','rejected')),
  final_intervention TEXT NOT NULL, reason TEXT NOT NULL, counsellor_notes TEXT, follow_up_date TEXT,
  status TEXT NOT NULL, counsellor_id INTEGER NOT NULL REFERENCES users(user_id),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS follow_up_records (
  record_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL REFERENCES student_profiles(student_id),
  request_id TEXT REFERENCES counselling_requests(request_id),
  intervention_id INTEGER REFERENCES interventions(intervention_id),
  author_id INTEGER REFERENCES users(user_id), kind TEXT NOT NULL, status_after TEXT, note TEXT,
  scheduled_for TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_logs (
  log_id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, actor_user_id INTEGER, actor_role TEXT,
  action TEXT NOT NULL, entity_type TEXT, entity_id TEXT, details_json TEXT);
CREATE TABLE IF NOT EXISTS model_metadata (
  model_id INTEGER PRIMARY KEY AUTOINCREMENT, trained_at TEXT, model_name TEXT, target TEXT,
  is_synthetic INTEGER NOT NULL, metrics_json TEXT, recorded_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS survey_responses (
  response_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL REFERENCES student_profiles(student_id),
  submitted_at TEXT NOT NULL, answers_json TEXT NOT NULL, assumed_json TEXT NOT NULL, extras_json TEXT NOT NULL,
  intent_flag INTEGER NOT NULL DEFAULT 0, assessment_id INTEGER REFERENCES assessments(assessment_id),
  is_synthetic INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS service_feedback (
  feedback_id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT UNIQUE NOT NULL REFERENCES counselling_requests(request_id),
  student_id TEXT NOT NULL REFERENCES student_profiles(student_id), submitted_at TEXT NOT NULL,
  overall INTEGER NOT NULL CHECK (overall BETWEEN 1 AND 5), timeliness INTEGER NOT NULL CHECK (timeliness BETWEEN 1 AND 5),
  helpfulness INTEGER NOT NULL CHECK (helpfulness BETWEEN 1 AND 5), respected INTEGER NOT NULL CHECK (respected BETWEEN 1 AND 5),
  comment TEXT, is_synthetic INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_by INTEGER, updated_at TEXT NOT NULL);
"""


RANK = {"GREEN": 0, "YELLOW": 1, "RED": 2}


class CheckInTooSoon(ValueError):
    """Raised when a student tries to submit a second check-in inside the monthly window."""
    def __init__(self, available_on):
        self.available_on = available_on
        super().__init__(f"You have already completed a check-in recently. The next one opens on {available_on:%d %b %Y}.")


def now() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


class Database:
    def __init__(self, path=None):
        self.path = str(path or config.DB_PATH)
        self.init_db()

    @contextmanager
    def conn(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def init_db(self):
        with self.conn() as c:
            c.executescript(SCHEMA)

    def _q(self, sql, params=()):
        with self.conn() as c:
            return [dict(r) for r in c.execute(sql, params).fetchall()]

    def _audit(self, c, actor, action, entity_type=None, entity_id=None, details=None):
        c.execute("INSERT INTO audit_logs(timestamp,actor_user_id,actor_role,action,entity_type,entity_id,details_json)"
                  " VALUES (?,?,?,?,?,?,?)",
                  (now(), actor.get("user_id") if actor else None, actor.get("role") if actor else None, action,
                   entity_type, str(entity_id) if entity_id is not None else None, json.dumps(details or {})))

    # ---------------- users / auth ----------------
    def _insert_user(self, c, username, password, role, display_name):
        h, s = hash_password(password)
        cur = c.execute("INSERT INTO users(username,password_hash,salt,role,display_name,created_at) VALUES (?,?,?,?,?,?)",
                        (username.strip().lower(), h, s, role, display_name, now()))
        return cur.lastrowid

    def user_count(self):
        return self._q("SELECT COUNT(*) n FROM users")[0]["n"]

    def authenticate(self, username, password):
        rows = self._q("SELECT u.*, p.student_id FROM users u LEFT JOIN student_profiles p ON p.user_id=u.user_id "
                       "WHERE u.username=?", ((username or "").strip().lower(),))
        with self.conn() as c:
            if rows and rows[0]["is_active"] and verify_password(password or "", rows[0]["password_hash"], rows[0]["salt"]):
                u = rows[0]
                user = dict(user_id=u["user_id"], username=u["username"], role=u["role"],
                            display_name=u["display_name"], student_id=u["student_id"])
                self._audit(c, user, "login")
                return user
            self._audit(c, None, "login_failed", "user", (username or "")[:50])
        return None

    def active_user(self, user_id):
        rows = self._q(
            "SELECT u.user_id,u.username,u.role,u.display_name,p.student_id FROM users u "
            "LEFT JOIN student_profiles p ON p.user_id=u.user_id WHERE u.user_id=? AND u.is_active=1",
            (user_id,),
        )
        return rows[0] if rows else None

    def create_student_invite(self, actor):
        require_role(actor, "admin")
        code = secrets.token_urlsafe(24)
        digest = hashlib.sha256(code.encode()).hexdigest()
        expires = (datetime.now() + timedelta(hours=24)).isoformat(sep=" ", timespec="seconds")
        with self.conn() as c:
            c.execute("INSERT INTO student_invites(digest,expires_at) VALUES (?,?)", (digest, expires))
            self._audit(c, actor, "create_student_invite")
        return code

    def register_student(self, code, username, password, display_name, program, year):
        username = username.strip().lower()
        display_name = display_name.strip()
        program = program.strip()
        if not 3 <= len(username) <= 40 or not all(ch.isascii() and (ch.isalnum() or ch in "_-.") for ch in username):
            raise ValueError("Use 3–40 letters, numbers, dots, underscores or hyphens for the username.")
        if not 8 <= len(password) <= 128:
            raise ValueError("Use a password between 8 and 128 characters.")
        if not 1 <= len(display_name) <= 80 or not 1 <= len(program) <= 80 or year not in range(1, 9):
            raise ValueError("Enter a display name, programme and year of study.")
        if program not in config.PROGRAMS:
            raise ValueError("Select a programme from the available options.")
        code = (code or "").strip()
        digest = hashlib.sha256(code.encode()).hexdigest() if code else None
        try:
            with self.conn() as c:
                c.execute("BEGIN IMMEDIATE")
                if digest is not None:
                    invite = c.execute(
                        "SELECT digest FROM student_invites WHERE digest=? AND expires_at>? AND used_by IS NULL",
                        (digest, now()),
                    ).fetchone()
                    if invite is None:
                        raise ValueError("This invite is invalid, expired or already used.")
                user_id = self._insert_user(c, username, password, "student", display_name)
                student_id = f"SG-{user_id}"
                self.add_student(c, student_id, display_name, program, year, user_id, synthetic=True)
                if digest is not None:
                    c.execute("UPDATE student_invites SET used_by=? WHERE digest=?", (user_id, digest))
                user = dict(user_id=user_id, username=username, role="student",
                            display_name=display_name, student_id=student_id)
                self._audit(c, user, "register_student", "student", student_id)
        except sqlite3.IntegrityError as exc:
            raise ValueError("That username already exists.") from exc
        return user

    def own_avatar(self, actor):
        require_role(actor, "student", "counsellor", "admin")
        rows = self._q("SELECT image FROM user_avatars WHERE user_id=?", (actor["user_id"],))
        return rows[0]["image"] if rows else None

    def update_own_profile(self, actor, display_name, avatar=None, remove_avatar=False):
        require_role(actor, "student", "counsellor", "admin")
        display_name = display_name.strip()
        if not 1 <= len(display_name) <= 80:
            raise ValueError("Enter a display name between 1 and 80 characters.")
        with self.conn() as c:
            c.execute("UPDATE users SET display_name=? WHERE user_id=?", (display_name, actor["user_id"]))
            if avatar is not None:
                c.execute("INSERT INTO user_avatars(user_id,image) VALUES (?,?) "
                          "ON CONFLICT(user_id) DO UPDATE SET image=excluded.image", (actor["user_id"], avatar))
            elif remove_avatar:
                c.execute("DELETE FROM user_avatars WHERE user_id=?", (actor["user_id"],))
            self._audit(c, actor, "update_profile", "user", actor["user_id"])

    def create_user(self, actor, username, password, role, display_name):
        require_role(actor, "admin")
        if role not in ("counsellor", "admin"):
            raise ValueError("Admins can create counsellor/admin accounts here.")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters.")
        if not username.strip() or not display_name.strip():
            raise ValueError("Username and display name are required.")
        try:
            with self.conn() as c:
                uid = self._insert_user(c, username, password, role, display_name.strip())
                self._audit(c, actor, "create_user", "user", uid, {"role": role})
        except sqlite3.IntegrityError:
            raise ValueError("That username already exists.")
        return uid

    def list_users(self, actor):
        require_role(actor, "admin")
        return self._q("SELECT user_id,username,role,display_name,is_active,created_at FROM users ORDER BY role,username")

    def set_user_active(self, actor, user_id, active: bool):
        require_role(actor, "admin")
        if actor["user_id"] == user_id:
            raise ValueError("You cannot deactivate your own account.")
        with self.conn() as c:
            c.execute("UPDATE users SET is_active=? WHERE user_id=?", (1 if active else 0, user_id))
            self._audit(c, actor, "set_user_active", "user", user_id, {"active": active})

    # ---------------- students ----------------
    def add_student(self, c, student_id, alias, program, year, user_id=None, synthetic=True):
        c.execute("INSERT INTO student_profiles(student_id,user_id,alias,program,year,is_synthetic,created_at) "
                  "VALUES (?,?,?,?,?,?,?)", (student_id, user_id, alias, program, int(year), 1 if synthetic else 0, now()))

    def list_students(self, actor):
        require_role(actor, "counsellor")
        return self._q("""SELECT p.student_id,p.alias,p.program,p.year,p.is_synthetic,(SELECT intent_flag FROM survey_responses s WHERE s.student_id=p.student_id ORDER BY s.response_id DESC LIMIT 1) AS intent_flag,a.zone,a.risk_value,a.assessed_at,a.mode
            FROM student_profiles p LEFT JOIN assessments a ON a.assessment_id =
              (SELECT MAX(assessment_id) FROM assessments WHERE student_id=p.student_id)
            ORDER BY p.student_id""")

    def get_student(self, actor, student_id):
        if actor and actor.get("role") == "student":
            require_own_student(actor, student_id)
        else:
            require_role(actor, "counsellor")
        r = self._q("SELECT student_id,alias,program,year,is_synthetic,consent_to_assessment FROM student_profiles "
                    "WHERE student_id=?", (student_id,))
        return r[0] if r else None

    # ---------------- assessments ----------------
    def save_assessment(self, actor, result, synthetic=False, c_ext=None):
        require_role(actor, "counsellor")
        with self.conn() as c:
            aid = self._insert_assessment(c, actor, result, synthetic)
            self._audit(c, actor, "save_assessment", "assessment", aid, {"zone": result["zone"], "mode": result["mode"]})
        return aid

    def _insert_assessment(self, c, actor, r, synthetic, assessed_at=None):
        cur = c.execute("""INSERT INTO assessments(student_id,assessed_at,assessed_by,mode,zone,risk_value,model_output,
            features_json,contributions_json,patterns_json,recommendations_json,thresholds_json,explanation_method,is_synthetic)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (r["student_id"], assessed_at or r["assessed_at"], actor.get("user_id") if actor else None,
                         r["mode"], r["zone"], r["risk_value"], r.get("model_output"), json.dumps(r["features"]),
                         json.dumps(r["contributions"]), json.dumps(r["patterns"]), json.dumps(r["recommendations"]),
                         json.dumps(r["thresholds"]), r.get("explanation_method"), 1 if synthetic else 0))
        return cur.lastrowid

    @staticmethod
    def _decode_assessment(row):
        for k in ("features", "contributions", "patterns", "recommendations", "thresholds"):
            row[k] = json.loads(row.pop(f"{k}_json"))
        return row

    def get_assessments(self, actor, student_id):
        if actor and actor.get("role") == "student":
            require_own_student(actor, student_id)
        else:
            require_role(actor, "counsellor")
        rows = self._q("SELECT * FROM assessments WHERE student_id=? ORDER BY assessment_id DESC", (student_id,))
        return [self._decode_assessment(r) for r in rows]

    def zone_distribution(self, actor):
        require_role(actor, "counsellor", "admin")
        rows = self._q("""SELECT a.zone, COUNT(*) n FROM student_profiles p JOIN assessments a ON a.assessment_id =
            (SELECT MAX(assessment_id) FROM assessments WHERE student_id=p.student_id) GROUP BY a.zone""")
        d = {"GREEN": 0, "YELLOW": 0, "RED": 0}
        d.update({r["zone"]: r["n"] for r in rows})
        return d

    def admin_counts(self, actor):
        require_role(actor, "admin")
        q = lambda s: self._q(s)[0]["n"]  # noqa: E731
        return dict(students=q("SELECT COUNT(*) n FROM student_profiles"),
                    synthetic_students=q("SELECT COUNT(*) n FROM student_profiles WHERE is_synthetic=1"),
                    assessments=q("SELECT COUNT(*) n FROM assessments"),
                    counsellors=q("SELECT COUNT(*) n FROM users WHERE role='counsellor' AND is_active=1"),
                    sos_total=q("SELECT COUNT(*) n FROM counselling_requests"))

    # ---------------- SOS counselling ----------------
    def create_sos_request(self, actor, category, message, contact_method):
        from src.validation import validate_sos
        require_role(actor, "student")
        errs = validate_sos(category, message, contact_method)
        if errs:
            raise ValueError(" ".join(errs))
        rid = f"SOS-{datetime.now():%Y%m%d}-{secrets.token_hex(3).upper()}"
        t = now()
        with self.conn() as c:
            prof = c.execute("SELECT is_synthetic FROM student_profiles WHERE student_id=?", (actor["student_id"],)).fetchone()
            c.execute("INSERT INTO counselling_requests(request_id,student_id,category,message,contact_method,status,"
                      "created_at,updated_at,is_synthetic) VALUES (?,?,?,?,?,?,?,?,?)",
                      (rid, actor["student_id"], category, (message or "").strip(), contact_method, "Submitted", t, t,
                       prof["is_synthetic"] if prof else 0))
            c.execute("INSERT INTO follow_up_records(student_id,request_id,author_id,kind,status_after,note,created_at) "
                      "VALUES (?,?,?,?,?,?,?)", (actor["student_id"], rid, actor["user_id"], "status_change", "Submitted", None, t))
            self._audit(c, actor, "create_sos_request", "counselling_request", rid, {"category": category})
        return rid

    def my_sos_requests(self, actor):
        require_role(actor, "student")
        rows = self._q("SELECT * FROM counselling_requests WHERE student_id=? ORDER BY created_at DESC, request_id", (actor["student_id"],))
        for r in rows:   # students see status timeline only – not private counsellor notes
            r["history"] = self._q("SELECT status_after,created_at,scheduled_for FROM follow_up_records WHERE request_id=? "
                                   "AND kind='status_change' ORDER BY record_id", (r["request_id"],))
            fb = self._q("SELECT overall,timeliness,helpfulness,respected,comment,submitted_at FROM service_feedback WHERE request_id=?", (r["request_id"],))
            r["feedback"] = fb[0] if fb else None
        return rows

    def list_sos_requests(self, actor, statuses=None):
        require_role(actor, "counsellor")
        sql = ("SELECT r.*, p.alias, p.program FROM counselling_requests r JOIN student_profiles p ON p.student_id=r.student_id")
        params = ()
        if statuses:
            sql += f" WHERE r.status IN ({','.join('?' * len(statuses))})"
            params = tuple(statuses)
        rows = self._q(sql + " ORDER BY r.created_at DESC, r.request_id", params)
        for r in rows:
            r["history"] = self._q("SELECT f.*, u.display_name author FROM follow_up_records f LEFT JOIN users u ON u.user_id=f.author_id "
                                   "WHERE request_id=? ORDER BY record_id", (r["request_id"],))
            fb = self._q("SELECT overall,timeliness,helpfulness,respected,comment,submitted_at FROM service_feedback WHERE request_id=?", (r["request_id"],))
            r["feedback"] = fb[0] if fb else None
        return rows

    def update_sos_status(self, actor, request_id, new_status, note="", scheduled_for=None):
        require_role(actor, "counsellor")
        if new_status not in config.SOS_STATUSES:
            raise ValueError("Invalid status.")
        if new_status == "Session scheduled" and not scheduled_for:
            raise ValueError("Please choose a session date/time when scheduling a session.")
        t = now()
        with self.conn() as c:
            row = c.execute("SELECT student_id,status FROM counselling_requests WHERE request_id=?", (request_id,)).fetchone()
            if not row:
                raise ValueError("Request not found.")
            c.execute("UPDATE counselling_requests SET status=?, updated_at=?, assigned_to=? WHERE request_id=?",
                      (new_status, t, actor["user_id"], request_id))
            c.execute("INSERT INTO follow_up_records(student_id,request_id,author_id,kind,status_after,note,scheduled_for,created_at) "
                      "VALUES (?,?,?,?,?,?,?,?)", (row["student_id"], request_id, actor["user_id"], "status_change",
                                                    new_status, note or None, str(scheduled_for) if scheduled_for else None, t))
            self._audit(c, actor, "update_sos_status", "counselling_request", request_id,
                        {"from": row["status"], "to": new_status})

    def sos_stats(self, actor):
        """Counts only – never message text."""
        require_role(actor, "counsellor", "admin")
        by_status = {s: 0 for s in config.SOS_STATUSES}
        by_status.update({r["status"]: r["n"] for r in self._q("SELECT status, COUNT(*) n FROM counselling_requests GROUP BY status")})
        by_cat = {r["category"]: r["n"] for r in self._q("SELECT category, COUNT(*) n FROM counselling_requests GROUP BY category")}
        return dict(by_status=by_status, by_category=by_cat)

    # ---------------- interventions (human-in-the-loop) ----------------
    def record_decision(self, actor, student_id, assessment_id, ai_suggestion, decision, final_intervention,
                        reason, notes="", follow_up_date=None):
        require_role(actor, "counsellor")
        if decision not in config.DECISIONS:
            raise ValueError("Decision must be accepted, modified or rejected.")
        if not (reason or "").strip():
            raise ValueError("A reason for the decision is required.")
        if not final_intervention:
            raise ValueError("Select the final intervention (or 'No intervention needed at this time').")
        t = now()
        with self.conn() as c:
            cur = c.execute("""INSERT INTO interventions(student_id,assessment_id,ai_suggestion_json,decision,final_intervention,
                reason,counsellor_notes,follow_up_date,status,counsellor_id,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (student_id, assessment_id, json.dumps(ai_suggestion), decision,
                             final_intervention if isinstance(final_intervention, str) else "; ".join(final_intervention),
                             reason.strip(), notes, str(follow_up_date) if follow_up_date else None,
                             "Planned", actor["user_id"], t, t))
            iid = cur.lastrowid
            if follow_up_date or notes:
                c.execute("INSERT INTO follow_up_records(student_id,intervention_id,author_id,kind,note,scheduled_for,created_at) "
                          "VALUES (?,?,?,?,?,?,?)", (student_id, iid, actor["user_id"], "intervention_note", notes or None,
                                                      str(follow_up_date) if follow_up_date else None, t))
            self._audit(c, actor, f"intervention_{decision}", "intervention", iid,
                        {"student_id": student_id, "reason": reason.strip(),
                         "final": final_intervention if isinstance(final_intervention, str) else list(final_intervention)})
        return iid

    def list_interventions(self, actor, student_id=None):
        require_role(actor, "counsellor")
        sql = ("SELECT i.*, p.alias, u.display_name counsellor FROM interventions i JOIN student_profiles p ON p.student_id=i.student_id "
               "JOIN users u ON u.user_id=i.counsellor_id")
        rows = self._q(sql + (" WHERE i.student_id=?" if student_id else "") + " ORDER BY i.intervention_id DESC",
                       (student_id,) if student_id else ())
        for r in rows:
            r["ai_suggestion"] = json.loads(r.pop("ai_suggestion_json"))
        return rows

    def update_intervention(self, actor, intervention_id, status, note="", follow_up_date=None):
        require_role(actor, "counsellor")
        if status not in config.INTERVENTION_STATUSES:
            raise ValueError("Invalid intervention status.")
        t = now()
        with self.conn() as c:
            row = c.execute("SELECT student_id,status FROM interventions WHERE intervention_id=?", (intervention_id,)).fetchone()
            if not row:
                raise ValueError("Intervention not found.")
            c.execute("UPDATE interventions SET status=?, follow_up_date=COALESCE(?,follow_up_date), updated_at=? WHERE intervention_id=?",
                      (status, str(follow_up_date) if follow_up_date else None, t, intervention_id))
            c.execute("INSERT INTO follow_up_records(student_id,intervention_id,author_id,kind,status_after,note,scheduled_for,created_at) "
                      "VALUES (?,?,?,?,?,?,?,?)", (row["student_id"], intervention_id, actor["user_id"], "intervention_update",
                                                    status, note or None, str(follow_up_date) if follow_up_date else None, t))
            self._audit(c, actor, "update_intervention", "intervention", intervention_id, {"from": row["status"], "to": status})

    def intervention_stats(self, actor):
        require_role(actor, "counsellor", "admin")
        d = {x: 0 for x in config.DECISIONS}
        d.update({r["decision"]: r["n"] for r in self._q("SELECT decision, COUNT(*) n FROM interventions GROUP BY decision")})
        s = {x: 0 for x in config.INTERVENTION_STATUSES}
        s.update({r["status"]: r["n"] for r in self._q("SELECT status, COUNT(*) n FROM interventions GROUP BY status")})
        return dict(by_decision=d, by_status=s)

    def list_follow_ups(self, actor, student_id):
        require_role(actor, "counsellor")
        return self._q("SELECT f.*, u.display_name author FROM follow_up_records f LEFT JOIN users u ON u.user_id=f.author_id "
                       "WHERE student_id=? ORDER BY record_id DESC", (student_id,))

    def list_audit(self, actor, limit=200):
        require_role(actor, "counsellor", "admin")
        return self._q("SELECT * FROM audit_logs ORDER BY log_id DESC LIMIT ?", (int(limit),))


    # ---------------- monthly check-in (survey) ----------------
    def checkin_status(self, actor, at=None):
        """Is the student's monthly check-in open? (rolling window, one per account)."""
        require_role(actor, "student")
        return self._checkin_status_for(actor["student_id"], at)

    def _checkin_status_for(self, student_id, at=None, conn=None):
        rows = (conn.execute("SELECT MAX(submitted_at) last FROM survey_responses WHERE student_id=?", (student_id,)).fetchall()
                if conn else self._q("SELECT MAX(submitted_at) last FROM survey_responses WHERE student_id=?", (student_id,)))
        last = rows[0]["last"]
        if not last:
            return dict(available=True, last=None, available_on=None)
        avail = datetime.fromisoformat(last) + timedelta(days=config.CHECKIN_INTERVAL_DAYS)
        return dict(available=(at or datetime.now()) >= avail, last=last, available_on=avail)

    def latest_assessment_features(self, actor):
        require_role(actor, "student")
        r = self._q("SELECT features_json FROM assessments WHERE student_id=? ORDER BY assessed_at DESC, assessment_id DESC LIMIT 1",
                    (actor["student_id"],))
        return json.loads(r[0]["features_json"]) if r else None

    def save_checkin(self, actor, answers, features, assumed, extras, intent_flag, result, at=None):
        """Store a student's check-in + the assessment derived from it. One per rolling 30 days."""
        require_role(actor, "student")
        ts = (at or datetime.now()).replace(microsecond=0).isoformat(sep=" ")
        with self.conn() as c:
            st = self._checkin_status_for(actor["student_id"], at, c)
            if not st["available"]:
                raise CheckInTooSoon(st["available_on"])
            prof = c.execute("SELECT is_synthetic FROM student_profiles WHERE student_id=?", (actor["student_id"],)).fetchone()
            syn = prof["is_synthetic"] if prof else 0
            aid = self._insert_assessment(c, None, dict(result, student_id=actor["student_id"]), bool(syn), assessed_at=ts)
            cur = c.execute("INSERT INTO survey_responses(student_id,submitted_at,answers_json,assumed_json,extras_json,intent_flag,"
                            "assessment_id,is_synthetic) VALUES (?,?,?,?,?,?,?,?)",
                            (actor["student_id"], ts, json.dumps(answers), json.dumps(assumed), json.dumps(extras),
                             int(intent_flag), aid, syn))
            self._audit(c, actor, "submit_checkin", "survey_response", cur.lastrowid, {"zone": result["zone"]})
        return dict(response_id=cur.lastrowid, assessment_id=aid)

    def get_checkins(self, actor, student_id):
        if actor and actor.get("role") == "student":
            require_own_student(actor, student_id)
        else:
            require_role(actor, "counsellor")
        rows = self._q("SELECT * FROM survey_responses WHERE student_id=? ORDER BY response_id DESC", (student_id,))
        for r in rows:
            for k in ("answers", "assumed", "extras"):
                r[k] = json.loads(r.pop(f"{k}_json"))
        return rows

    def checkin_stats(self, actor):
        """Counts only."""
        require_role(actor, "counsellor", "admin")
        q = lambda sql, p=(): self._q(sql, p)[0]["n"]  # noqa: E731
        since = (datetime.now() - timedelta(days=config.CHECKIN_INTERVAL_DAYS)).isoformat(sep=" ", timespec="seconds")
        return dict(students=q("SELECT COUNT(*) n FROM student_profiles"),
                    total_checkins=q("SELECT COUNT(*) n FROM survey_responses"),
                    students_recent=q("SELECT COUNT(DISTINCT student_id) n FROM survey_responses WHERE submitted_at>=?", (since,)),
                    flagged_latest=q("""SELECT COUNT(*) n FROM student_profiles p WHERE (SELECT intent_flag FROM survey_responses s
                        WHERE s.student_id=p.student_id ORDER BY s.response_id DESC LIMIT 1)=1"""))

    # ---------------- student feedback on services ----------------
    def submit_feedback(self, actor, request_id, overall, timeliness, helpfulness, respected, comment=""):
        require_role(actor, "student")
        vals = [overall, timeliness, helpfulness, respected]
        if any(not isinstance(v, int) or not 1 <= v <= 5 for v in vals):
            raise ValueError("Ratings must be whole numbers from 1 to 5.")
        if len(comment or "") > 1500:
            raise ValueError("Comment must be 1500 characters or fewer.")
        with self.conn() as c:
            row = c.execute("SELECT student_id,status,is_synthetic FROM counselling_requests WHERE request_id=?", (request_id,)).fetchone()
            if not row or row["student_id"] != actor["student_id"]:
                raise PermissionError("You can only give feedback on your own requests.")
            if row["status"] != "Resolved":
                raise ValueError("Feedback opens once a request is marked Resolved.")
            if c.execute("SELECT 1 FROM service_feedback WHERE request_id=?", (request_id,)).fetchone():
                raise ValueError("Feedback was already submitted for this request.")
            c.execute("INSERT INTO service_feedback(request_id,student_id,submitted_at,overall,timeliness,helpfulness,respected,comment,is_synthetic)"
                      " VALUES (?,?,?,?,?,?,?,?,?)", (request_id, actor["student_id"], now(), *vals, (comment or "").strip(), row["is_synthetic"]))
            self._audit(c, actor, "submit_feedback", "counselling_request", request_id, {"overall": overall})

    def list_feedback(self, actor):
        """Counsellors only (includes comments)."""
        require_role(actor, "counsellor")
        return self._q("""SELECT f.*, r.category, p.alias FROM service_feedback f JOIN counselling_requests r ON r.request_id=f.request_id
                          JOIN student_profiles p ON p.student_id=f.student_id ORDER BY f.submitted_at DESC""")

    def feedback_stats(self, actor):
        """Aggregates only – no comments, no student identity."""
        require_role(actor, "counsellor", "admin")
        n = self._q("SELECT COUNT(*) n FROM service_feedback")[0]["n"]
        avg = self._q("SELECT AVG(overall) overall, AVG(timeliness) timeliness, AVG(helpfulness) helpfulness, AVG(respected) respected "
                      "FROM service_feedback")[0] if n else {}
        by_cat = self._q("SELECT r.category category, COUNT(*) n, AVG(f.overall) overall FROM service_feedback f "
                         "JOIN counselling_requests r ON r.request_id=f.request_id GROUP BY r.category")
        resolved = self._q("SELECT COUNT(*) n FROM counselling_requests WHERE status='Resolved'")[0]["n"]
        return dict(n=n, resolved_requests=resolved, averages={k: (round(v, 2) if v is not None else None) for k, v in avg.items()},
                    by_category=by_cat)

    # ---------------- progression (before / after support) ----------------
    def _support_events(self, sid):
        ev = []
        for r in self._q("SELECT created_at, status_after, request_id FROM follow_up_records WHERE student_id=? AND kind='status_change' "
                         "AND status_after IN ('Contact in progress','Session scheduled','Resolved') ORDER BY created_at, record_id", (sid,)):
            ev.append(dict(at=r["created_at"], type="counselling", label=f"Counselling: {r['status_after']} ({r['request_id']})"))
        for r in self._q("SELECT created_at, final_intervention, intervention_id FROM interventions WHERE student_id=? AND decision!='rejected' "
                         "AND final_intervention NOT LIKE 'No intervention%' AND final_intervention NOT LIKE 'Continue regular%'", (sid,)):
            ev.append(dict(at=r["created_at"], type="intervention", label=f"Intervention #{r['intervention_id']}: {r['final_intervention'][:70]}"))
        return sorted(ev, key=lambda e: e["at"])

    def _progression(self, sid):
        asses = self._q("SELECT assessment_id,assessed_at,zone,risk_value,mode FROM assessments WHERE student_id=? "
                        "ORDER BY assessed_at, assessment_id", (sid,))
        ev = self._support_events(sid)
        out = dict(student_id=sid, timeline=asses, support_events=ev, first_support_at=None, zone_before=None, zone_after=None,
                   score_before=None, score_after=None, outcome="No support recorded yet")
        if ev:
            first = ev[0]["at"]
            out["first_support_at"] = first
            before = [a for a in asses if a["assessed_at"] <= first]
            after = [a for a in asses if a["assessed_at"] > first]
            if not before:
                out["outcome"] = "No baseline assessment before support"
            elif not after:
                out["outcome"] = "No assessment yet after support"
            else:
                b, a = before[-1], after[-1]
                out.update(zone_before=b["zone"], zone_after=a["zone"], score_before=b["risk_value"], score_after=a["risk_value"])
                d = RANK[a["zone"]] - RANK[b["zone"]]
                out["outcome"] = "Improved" if d < 0 else ("Higher concern" if d > 0 else "Same zone")
        return out

    def progression(self, actor, student_id):
        if actor and actor.get("role") == "student":
            require_own_student(actor, student_id)
        else:
            require_role(actor, "counsellor")
        return self._progression(student_id)

    def _progression_rows(self):
        ids = [r["student_id"] for r in self._q(
            "SELECT DISTINCT student_id FROM follow_up_records WHERE kind='status_change' AND status_after IN "
            "('Contact in progress','Session scheduled','Resolved') UNION SELECT DISTINCT student_id FROM interventions")]
        rows = []
        for sid in sorted(ids):
            p = self._progression(sid)
            if p["first_support_at"]:
                al = self._q("SELECT alias FROM student_profiles WHERE student_id=?", (sid,))
                rows.append(dict(student_id=sid, alias=al[0]["alias"] if al else sid, first_support_at=p["first_support_at"],
                                 zone_before=p["zone_before"], zone_after=p["zone_after"], score_before=p["score_before"],
                                 score_after=p["score_after"], outcome=p["outcome"]))
        return rows

    def progression_rows(self, actor):
        require_role(actor, "counsellor")
        return self._progression_rows()

    def progression_summary(self, actor):
        """Aggregate counts only (safe for admins)."""
        require_role(actor, "counsellor", "admin")
        rows = self._progression_rows()
        outcomes, trans = {}, {}
        for r in rows:
            outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
            if r["zone_before"] and r["zone_after"]:
                k = f"{r['zone_before']} → {r['zone_after']}"
                trans[k] = trans.get(k, 0) + 1
        return dict(n_with_support=len(rows), outcomes=outcomes, transitions=trans)

    # ---------------- settings & model metadata ----------------
    def get_thresholds(self):
        r = self._q("SELECT value FROM settings WHERE key='score_thresholds'")
        return json.loads(r[0]["value"]) if r else dict(config.DEFAULT_SCORE_THRESHOLDS)

    def set_thresholds(self, actor, yellow, red):
        from src.risk_zones import validate_thresholds
        require_role(actor, "admin")
        t = {"yellow": float(yellow), "red": float(red)}
        validate_thresholds(t)
        with self.conn() as c:
            c.execute("INSERT INTO settings(key,value,updated_by,updated_at) VALUES ('score_thresholds',?,?,?) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_by=excluded.updated_by, updated_at=excluded.updated_at",
                      (json.dumps(t), actor["user_id"], now()))
            self._audit(c, actor, "set_thresholds", "settings", "score_thresholds", t)

    def record_model_metadata(self, metrics: dict):
        with self.conn() as c:
            if c.execute("SELECT 1 FROM model_metadata WHERE trained_at=?", (metrics["trained_at"],)).fetchone():
                return
            c.execute("INSERT INTO model_metadata(trained_at,model_name,target,is_synthetic,metrics_json,recorded_at) VALUES (?,?,?,?,?,?)",
                      (metrics["trained_at"], metrics["deployed_model"], metrics["target"], 1 if metrics["is_synthetic"] else 0,
                       json.dumps({"split": metrics["split"], "holdout": metrics["results"][metrics["deployed_model"]]["holdout"]}), now()))
