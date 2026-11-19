"""Monthly check-in: in-app version of the project's Google Form (original Q3–Q19).

Left out on purpose:
  Q1–Q2 (year/field) – already in the student profile (data minimisation)
  Q20–Q24 (case studies) – research opinions about fictional students, not about the respondent
  Q25–Q26 (open essays) – research only
  Name – the logged-in account identifies the student.

Q17–Q19 (self-reported intention to discontinue) are shown to counsellors as CONTEXT and can raise a
review flag, but they are NOT inputs to the risk score and are NOT treated as dropout labels.
"""
import config
from src import predict, validation

SECTIONS = {"A": "About your studies", "B": "Academic & career factors", "C": "Financial, family & personal factors",
            "D": "Institutional support", "E": "Continuing your education"}


def _single(qid, sec, text, options):
    return dict(id=qid, section=sec, text=text, kind="single", options=options)


def _scale(qid, sec, text, low, high):
    return dict(id=qid, section=sec, text=text, kind="scale", options=[f"1 – {low}", "2", "3", "4", "5 – " + high])


def _multi(qid, sec, text, options, max_choices):
    return dict(id=qid, section=sec, text=text, kind="multi", options=options, max_choices=max_choices)


QUESTIONS = [
    _single("q3", "A", "3. How would you describe your current academic performance?",
            ["Excellent", "Above Average", "Average", "Below Average", "Poor", "Prefer not to say"]),
    _single("q4", "A", "4. What is your approximate attendance?",
            ["90–100%", "80–89%", "70–79%", "60–69%", "Below 60%", "Not sure"]),
    _single("q5", "B", "5. How often do you feel stressed by your studies?", ["Never", "Rarely", "Sometimes", "Often", "Very often"]),
    _single("q6", "B", "6. How has your motivation to study changed this year?",
            ["Increased significantly", "Increased slightly", "Stayed about the same", "Decreased slightly", "Decreased significantly", "Not sure"]),
    _scale("q7", "B", "7. How clear are you about the career you want to pursue?", "Not clear at all", "Very clear"),
    _scale("q8", "B", "8. How satisfied are you with your current course/degree?", "Very dissatisfied", "Very satisfied"),
    _scale("q9", "B", "9. How well does your course/degree align with the career you want?", "Not aligned at all", "Highly aligned"),
    _single("q10", "B", "10. Have you seriously considered changing your course, field, or career path?",
            ["Never", "Thought about it, but not seriously", "Occasionally considered it seriously", "Seriously considering it", "Currently planning to change"]),
    _scale("q11", "C", "11. To what extent could financial difficulties affect your ability to continue your education?", "Not at all", "Very significantly"),
    _scale("q12", "C", "12. How much do family expectations or circumstances influence your educational decisions?", "Not at all", "Very strongly"),
    _scale("q13", "C", "13. How confident are you that you can continue your education even during a difficult period?", "Not confident at all", "Very confident"),
    _scale("q14", "D", "14. How comfortable are you asking faculty for help with academic problems?", "Very uncomfortable", "Very comfortable"),
    _single("q15", "D", "15. How helpful is your college's career guidance?",
            ["Very adequate", "Adequate", "Somewhat adequate", "Inadequate", "Not available", "I don't know"]),
    _multi("q16", "D", "16. Which TWO forms of support would be most useful to a student facing difficulties?",
           ["Career counselling", "Academic tutoring / remedial support", "Financial assistance", "Mental / emotional support",
            "Flexible attendance", "Temporary academic break", "Course / stream change guidance", "Skill-development opportunities",
            "Parent / family counselling", "Entrepreneurship guidance", "Other"], 2),
    _single("q17", "E", "17. Have you ever seriously considered discontinuing your education?",
            ["Never", "Once, but not seriously", "Occasionally", "Seriously", "I am currently considering it"]),
    _scale("q18", "E", "18. How likely are you to stop your education in the next 12 months?", "Very unlikely", "Very likely"),
    _single("q19", "E", "19. Which factor would be MOST likely to make you consider discontinuing your education?",
            ["Low marks / academic difficulties", "Attendance problems", "Financial difficulties", "Career switching / uncertainty",
             "Lack of interest in the course", "Family circumstances or pressure", "Emotional / personal difficulties",
             "Better career or business opportunity elsewhere", "Strict institutional policies", "Lack of institutional support", "Other"]),
]
Q_BY_ID = {q["id"]: q for q in QUESTIONS}

# --- documented mappings from survey answers to model features (None = unknown -> default assumed + flagged) ---
PERF = {"Excellent": 4, "Above Average": 3, "Average": 2, "Below Average": 1, "Poor": 1, "Prefer not to say": None}  # Poor merged with Below Average
ATT = {"90–100%": 95, "80–89%": 85, "70–79%": 75, "60–69%": 65, "Below 60%": 50, "Not sure": None}               # band mid-points
STRESS = {"Never": 1, "Rarely": 2, "Sometimes": 3, "Often": 4, "Very often": 5}
MOTIV = {"Increased significantly": 5, "Increased slightly": 4, "Stayed about the same": 3, "Decreased slightly": 2,
         "Decreased significantly": 1, "Not sure": None}   # motivation CHANGE used as a proxy for motivation level
CHANGE = {"Never": 0, "Thought about it, but not seriously": 0, "Occasionally considered it seriously": 1,
          "Seriously considering it": 1, "Currently planning to change": 1}
GUIDE = {"Very adequate": 4, "Adequate": 4, "Somewhat adequate": 3, "Inadequate": 2, "Not available": 1, "I don't know": None}
INTENT_HIGH = ("Seriously", "I am currently considering it")


def scale_value(label) -> int:
    return int(str(label)[0])


def validate_answers(a: dict):
    errs = []
    for q in QUESTIONS:
        v = a.get(q["id"])
        if q["kind"] == "multi":
            if not v or len(v) > q["max_choices"]:
                errs.append(f"Q{q['id'][1:]}: choose 1 to {q['max_choices']} options.")
        elif v is None or v not in q["options"]:
            errs.append(f"Q{q['id'][1:]}: please select an answer.")
    return errs


def map_answers(a: dict, prev_features: dict = None):
    """Return (features, assumed_fields). Unknown answers get the neutral config default and are listed in `assumed`."""
    f, assumed = {}, []

    def put(key, val):
        if val is None:
            assumed.append(key)
            f[key] = config.FEATURE_BY_KEY[key]["default"]
        else:
            f[key] = val

    perf, att = PERF[a["q3"]], ATT[a["q4"]]
    put("academic_performance", perf)
    put("attendance_pct", att)
    put("study_stress", STRESS[a["q5"]])
    put("motivation", MOTIV[a["q6"]])
    put("career_clarity", scale_value(a["q7"]))
    put("course_satisfaction", scale_value(a["q8"]))
    put("course_career_alignment", scale_value(a["q9"]))
    put("considered_change", CHANGE[a["q10"]])
    put("financial_difficulty", scale_value(a["q11"]))
    put("family_pressure", scale_value(a["q12"]))
    put("confidence_continuing", scale_value(a["q13"]))
    put("faculty_comfort", scale_value(a["q14"]))
    put("career_guidance", GUIDE[a["q15"]])
    # Academic trend is not asked in the form: derived from the previous snapshot (lower perf / attendance drop >= 10 pts = declining)
    if prev_features is None or perf is None:
        f["academic_trend"] = 2
        assumed.append("academic_trend")
    else:
        pp = prev_features.get("academic_performance", perf)
        trend = 3 if perf > pp else (1 if perf < pp else 2)
        if att is not None and prev_features.get("attendance_pct") is not None and att <= prev_features["attendance_pct"] - 10:
            trend = 1
        f["academic_trend"] = trend
    return f, assumed


def intent_flag(a: dict) -> int:
    return int(a["q17"] in INTENT_HIGH or scale_value(a["q18"]) >= 4)


def extras_of(a: dict) -> dict:
    return dict(preferred_support=a["q16"], discontinuation_consideration=a["q17"], likelihood_12m=scale_value(a["q18"]),
                main_factor=a["q19"], motivation_change=a["q6"])


def submit_checkin(db, user, answers: dict, bundle, consent: bool, at=None) -> dict:
    """Validate -> map -> assess -> store. Raises ValueError / CheckInTooSoon / PermissionError."""
    if not consent:
        raise ValueError("Please confirm that you agree to share your answers with authorised counsellors.")
    st = db.checkin_status(user, at)
    if not st["available"]:
        from src.database import CheckInTooSoon
        raise CheckInTooSoon(st["available_on"])
    errs = validate_answers(answers)
    if errs:
        raise ValueError(" ".join(errs))
    feats, assumed = map_answers(answers, db.latest_assessment_features(user))
    clean, verrs = validation.validate_assessment(feats)
    if verrs:
        raise ValueError(" ".join(verrs))
    result = predict.assess(user["student_id"], clean, bundle, db.get_thresholds())
    ids = db.save_checkin(user, answers, clean, assumed, extras_of(answers), intent_flag(answers), result, at=at)
    return dict(result, **ids, assumed=assumed)
