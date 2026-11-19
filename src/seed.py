"""Load SYNTHETIC demo data into an empty database (everything flagged is_synthetic=1).

Each demo student gets 3 monthly snapshots (≈65, 33 and 2 days ago). A few students also have a
counselling case in between, with different outcomes on purpose (improved / same zone / higher concern),
so the Progress & Trends screens are honest rather than only showing successes."""
import json
import random
from datetime import datetime, timedelta
import pandas as pd
import config
from src import intervention_engine, predict
from src.data_preprocessing import DatasetError

DEMO_ACCOUNTS = [  # DEMO ONLY – published credentials
    ("admin", "admin123", "admin", "Demo Administrator", None),
    ("counsellor", "counsel123", "counsellor", "Dr. Demo Counsellor", None),
    ("counsellor2", "counsel123", "counsellor", "Prof. Demo Mentor", None),
    ("student1", "student123", "student", "Demo Student 001", "S001"),
    ("student2", "student123", "student", "Demo Student 002", "S002"),
    ("student3", "student123", "student", "Demo Student 003", "S003"),
]
FB_COMMENTS = ["[SYNTHETIC] The counsellor listened carefully.", "[SYNTHETIC] Got a slot quickly and a clear plan.",
               "[SYNTHETIC] Helpful, but I would have liked a faster reply.", "[SYNTHETIC] Felt comfortable sharing my situation.", ""]


def _ts(days):
    return (datetime.now() - timedelta(days=days)).replace(microsecond=0).isoformat(sep=" ")


def _clamp(g, k, d, lo, hi):
    g[k] = min(hi, max(lo, int(g[k]) + d))


def worsen(f, d):
    g = dict(f)
    _clamp(g, "study_stress", d, 1, 5); _clamp(g, "motivation", -d, 1, 5); _clamp(g, "confidence_continuing", -d, 1, 5)
    if d >= 2:
        _clamp(g, "career_clarity", -1, 1, 5); _clamp(g, "course_satisfaction", -1, 1, 5)
        _clamp(g, "financial_difficulty", 1, 1, 5); _clamp(g, "faculty_comfort", -1, 1, 5)
    g["attendance_pct"] = float(max(40, g["attendance_pct"] - 4 * d))
    return g


def seed_demo_data(db, bundle=None, csv_path=None):
    """Idempotent: does nothing if users already exist. Returns number of students loaded."""
    if db.user_count() > 0:
        return 0
    csv_path = csv_path or config.SAMPLE_STUDENTS_CSV
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        raise DatasetError(f"Sample data '{csv_path}' not found. Run `python -m src.generate_synthetic_data`.")
    missing = [c for c in config.FEATURE_KEYS + ["student_id", "alias"] if c not in df.columns]
    if missing:
        raise DatasetError(f"Sample data is missing columns: {', '.join(missing)}")
    rng = random.Random(11)
    thr = db.get_thresholds()
    with db.conn() as c:
        uids = {}
        for username, pw, role, name, sid in DEMO_ACCOUNTS:
            uids[sid or username] = db._insert_user(c, username, pw, role, name)
        counsellor_id = uids["counsellor"]
        for idx, row in enumerate(df.to_dict("records")):
            sid = row["student_id"]
            db.add_student(c, sid, row["alias"], row.get("program"), row.get("year", 1), user_id=uids.get(sid), synthetic=True)
            feats = {k: (int(row[k]) if k != "attendance_pct" else float(row[k])) for k in config.FEATURE_KEYS}
            case = {0: "improved", 4: "stuck", 6: "worse"}.get(idx % 8)
            if case == "improved":
                snaps = [(worsen(feats, 2), 65), (worsen(feats, 3), 33), (feats, 2)]
            elif case == "stuck":
                w = worsen(feats, 2)
                snaps = [(w, 65), (w, 33), (w, 2)]
            elif case == "worse":
                snaps = [(feats, 65), (feats, 33), (worsen(feats, 2), 2)]
            else:
                older = dict(feats)
                older["study_stress"] = min(5, max(1, older["study_stress"] + rng.choice([-1, 0, 1])))
                older["attendance_pct"] = float(min(100, max(40, older["attendance_pct"] + rng.choice([-3, 0, 4]))))
                snaps = [(older, 65), (older, 33), (feats, 2)]
            aids, results = [], []
            for f, days in snaps:
                r = predict.assess(sid, f, bundle, thr)
                results.append(r)
                aids.append(db._insert_assessment(c, None, r, True, assessed_at=_ts(days)))
            if case:   # counselling case between the 2nd and 3rd snapshot
                rid = f"SOS-DEMO-C{idx + 1:03d}"
                cat = "Academic pressure" if idx % 2 else "Emotional or personal difficulties"
                c.execute("INSERT INTO counselling_requests(request_id,student_id,category,message,contact_method,status,created_at,"
                          "updated_at,assigned_to,is_synthetic) VALUES (?,?,?,?,?,?,?,?,?,1)",
                          (rid, sid, cat, "[SYNTHETIC] Demo request.", "In-person meeting", "Resolved", _ts(27), _ts(20), counsellor_id))
                for d, st, sched in ((27, "Submitted", None), (26.5, "Acknowledged", None),
                                     (26, "Session scheduled", _ts(24)), (20, "Resolved", None)):
                    c.execute("INSERT INTO follow_up_records(student_id,request_id,author_id,kind,status_after,scheduled_for,created_at) "
                              "VALUES (?,?,?,?,?,?,?)", (sid, rid, None if st == "Submitted" else counsellor_id, "status_change", st, sched, _ts(d)))
                recs = results[1]["recommendations"]
                final = "; ".join(intervention_engine.flat_support(recs)[:3])
                c.execute("INSERT INTO interventions(student_id,assessment_id,ai_suggestion_json,decision,final_intervention,reason,"
                          "counsellor_notes,follow_up_date,status,counsellor_id,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                          (sid, aids[1], json.dumps(recs), "accepted", final, "[SYNTHETIC] Seeded demo decision.", None, None,
                           "Completed", counsellor_id, _ts(26), _ts(20)))
                if idx != 0:   # S001 is left without feedback so the student demo can submit it live
                    lo = 2 if case != "improved" else 3
                    vals = [rng.randint(lo, 5) for _ in range(4)]
                    c.execute("INSERT INTO service_feedback(request_id,student_id,submitted_at,overall,timeliness,helpfulness,respected,comment,"
                              "is_synthetic) VALUES (?,?,?,?,?,?,?,?,1)", (rid, sid, _ts(18), *vals, rng.choice(FB_COMMENTS)))
            if idx in (3, 5, 7, 9, 11, 13, 15, 17):   # students who already used this month's check-in
                z = results[-1]["zone"]
                flag = int(z != "GREEN" and rng.random() < 0.6)
                extras = dict(preferred_support=rng.sample(["Career counselling", "Mental / emotional support", "Financial assistance",
                                                            "Academic tutoring / remedial support"], 2),
                              discontinuation_consideration="Seriously" if flag else "Never",
                              likelihood_12m=4 if flag else 1,
                              main_factor=rng.choice(["Career switching / uncertainty", "Financial difficulties", "Low marks / academic difficulties"]),
                              motivation_change="Decreased slightly")
                c.execute("INSERT INTO survey_responses(student_id,submitted_at,answers_json,assumed_json,extras_json,intent_flag,assessment_id,"
                          "is_synthetic) VALUES (?,?,?,?,?,?,?,1)", (sid, _ts(2), json.dumps({"_synthetic": True}), json.dumps(["academic_trend"]),
                                                                     json.dumps(extras), flag, aids[-1]))
        # extra SYNTHETIC open requests so the counsellor queue is not empty
        for i, (sid, cat, msg, cm, st) in enumerate([
                ("S003", "Academic pressure", "[SYNTHETIC] Feeling overloaded before internals.", "Email", "Submitted"),
                ("S002", "Career confusion", "[SYNTHETIC] Unsure whether this branch fits my goals.", "In-person meeting", "Acknowledged")], 1):
            rid = f"SOS-DEMO-{i:04d}"
            c.execute("INSERT INTO counselling_requests(request_id,student_id,category,message,contact_method,status,created_at,updated_at,is_synthetic)"
                      " VALUES (?,?,?,?,?,?,?,?,1)", (rid, sid, cat, msg, cm, st, _ts(i), _ts(i)))
            for s_ in ["Submitted"] + ([st] if st != "Submitted" else []):
                c.execute("INSERT INTO follow_up_records(student_id,request_id,kind,status_after,created_at) VALUES (?,?,?,?,?)",
                          (sid, rid, "status_change", s_, _ts(i)))
    return len(df)
