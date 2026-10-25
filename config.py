"""Central configuration for StudentGuard AI.

Everything that is a *judgement call* (weights, thresholds, scales) lives here so it
can be inspected, documented and changed without touching application logic.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MODEL_DIR = BASE_DIR / "models"
DB_PATH = Path(os.environ.get("STUDENTGUARD_DB", BASE_DIR / "studentguard.db"))
MODEL_PATH = MODEL_DIR / "model.joblib"
METRICS_PATH = MODEL_DIR / "metrics.json"
SAMPLE_STUDENTS_CSV = DATA_DIR / "sample_students.csv"
SYNTHETIC_TRAINING_CSV = DATA_DIR / "synthetic_training_data.csv"

APP_TITLE = "StudentGuard AI"
APP_SUBTITLE = "AI-Powered Early Warning and Student Support System"

ADVISORY_NOTICE = ("AI-generated risk assessments are advisory only. Final intervention decisions "
                   "remain with authorised human counsellors or faculty members.")
DEMO_BANNER = ("DEMONSTRATION MODE — Outputs are illustrative and are not validated predictions "
               "of actual student dropout.")
EMERGENCY_NOTE = ("This prototype is NOT an emergency-response service and is not monitored "
                  "continuously. No email/SMS alerts are sent. If you or someone else is in "
                  "immediate danger, contact your local emergency services or a trusted person right now.")

# ---------------------------------------------------------------------------
# Feature definitions. Scales follow the Google-Forms survey (1-5 Likert /
# frequency answers). Where the survey used categories they are mapped to
# ordinal codes below (documented mapping, not a silent change).
# direction: "low_is_concern" -> low values raise concern; "high_is_concern" -> opposite.
# weight: ILLUSTRATIVE expert-judgement weight for the demonstration rule score.
# ---------------------------------------------------------------------------
LIKERT_5 = {1: "1 – Very low", 2: "2 – Low", 3: "3 – Moderate", 4: "4 – High", 5: "5 – Very high"}
FREQ_5 = {1: "Never", 2: "Rarely", 3: "Sometimes", 4: "Often", 5: "Very often"}
SEVERITY_5 = {1: "None", 2: "Slight", 3: "Moderate", 4: "Significant", 5: "Severe"}

FEATURES = [
    dict(key="academic_performance", label="Academic performance", min=1, max=4, default=2,
         options={1: "Below average", 2: "Average", 3: "Above average", 4: "Excellent"},
         direction="low_is_concern", weight=0.05, category="academic",
         help="Self-reported/recorded overall academic performance."),
    dict(key="academic_trend", label="Academic trend", min=1, max=3, default=2,
         options={1: "Declining", 2: "Stable", 3: "Improving"}, direction="low_is_concern",
         weight=0.05, category="academic", concern_map={1: 1.0, 2: 0.15, 3: 0.0},
         help="Recent direction of marks."),
    dict(key="attendance_pct", label="Attendance (%)", min=0, max=100, default=90, kind="percent",
         direction="low_is_concern", weight=0.06, category="attendance",
         help="Attendance percentage. Concern rises below 90% (0 at ≥90%, 1 at ≤40%)."),
    dict(key="study_stress", label="Study stress (how often)", min=1, max=5, default=3, options=FREQ_5,
         direction="high_is_concern", weight=0.12, category="emotional",
         help="How often the student feels stressed about studies. Self-reported; not a diagnosis."),
    dict(key="motivation", label="Motivation level", min=1, max=5, default=3, options=LIKERT_5,
         direction="low_is_concern", weight=0.10, category="emotional", help="Current motivation to study."),
    dict(key="career_clarity", label="Career clarity", min=1, max=5, default=3, options=LIKERT_5,
         direction="low_is_concern", weight=0.09, category="career", help="Clarity about career direction."),
    dict(key="course_satisfaction", label="Course satisfaction", min=1, max=5, default=3, options=LIKERT_5,
         direction="low_is_concern", weight=0.09, category="career", help="Satisfaction with the course."),
    dict(key="course_career_alignment", label="Course–career alignment", min=1, max=5, default=3,
         options=LIKERT_5, direction="low_is_concern", weight=0.09, category="career",
         help="How well the course matches the intended career."),
    dict(key="financial_difficulty", label="Financial difficulty", min=1, max=5, default=2, options=SEVERITY_5,
         direction="high_is_concern", weight=0.10, category="financial",
         help="Extent to which finances affect continuing education."),
    dict(key="family_pressure", label="Family pressure / responsibility", min=1, max=5, default=2,
         options=LIKERT_5, direction="high_is_concern", weight=0.06, category="family",
         help="Extent of family pressure or responsibilities affecting studies."),
    dict(key="confidence_continuing", label="Confidence in continuing education", min=1, max=5, default=4,
         options=LIKERT_5, direction="low_is_concern", weight=0.12, category="emotional",
         help="Confidence that the student will continue their education."),
    dict(key="faculty_comfort", label="Comfort approaching faculty", min=1, max=5, default=3,
         options=LIKERT_5, direction="low_is_concern", weight=0.06, category="institutional",
         help="Comfort asking faculty for help."),
    dict(key="career_guidance", label="Career guidance availability", min=1, max=4, default=3,
         options={1: "Not available", 2: "Inadequate", 3: "Somewhat adequate", 4: "Adequate"},
         direction="low_is_concern", weight=0.04, category="institutional",
         help="Perceived adequacy of career guidance."),
    dict(key="considered_change", label="Has considered changing course/career", min=0, max=1, default=0,
         options={0: "No", 1: "Yes"}, direction="high_is_concern", weight=0.06, category="career",
         help="Whether the student has considered changing course or career."),
]
FEATURE_KEYS = [f["key"] for f in FEATURES]
FEATURE_BY_KEY = {f["key"]: f for f in FEATURES}

# ---------------------------------------------------------------------------
# Risk zones (ILLUSTRATIVE thresholds on the 0-100 demonstration concern score).
# They are stored in the DB `settings` table once an administrator changes them.
# ---------------------------------------------------------------------------
DEFAULT_SCORE_THRESHOLDS = {"yellow": 30.0, "red": 55.0}
# Used only in TRAINED_MODEL mode (validated labels). Placeholders until validated on real data.
DEFAULT_PROB_THRESHOLDS = {"yellow": 0.30, "red": 0.60}
CONCERN_TRIGGER = 0.5          # indicator concern level (0-1) that triggers a recommendation / pattern
PATTERN_BONUS = 4.0            # score points added per co-occurring pattern (illustrative)
CONCERN_EXPONENT = 1.5         # makes mid-scale answers count less than extreme answers

ZONES = {
    "GREEN": dict(label="Green Zone — Low current concern", short="Low current concern",
                  color="#16a34a", bg="#dcfce7"),
    "YELLOW": dict(label="Yellow Zone — Moderate concern", short="Moderate concern",
                   color="#b45309", bg="#fef3c7"),
    "RED": dict(label="Red Zone — High concern", short="High concern (review suggested)",
                color="#b91c1c", bg="#fee2e2"),
}

# Illustrative co-occurring patterns (association, NOT proven causation)
PATTERNS = [
    ("study_stress", "motivation", "High study stress combined with low motivation"),
    ("career_clarity", "course_satisfaction", "Low career clarity combined with course dissatisfaction"),
    ("financial_difficulty", "confidence_continuing", "Financial difficulty combined with low confidence in continuing"),
    ("academic_trend", "attendance_pct", "Declining academic performance combined with attendance difficulty"),
    ("faculty_comfort", "career_clarity", "Low comfort with faculty combined with career uncertainty"),
]

SOS_CATEGORIES = ["Emotional or personal difficulties", "Academic pressure", "Career confusion",
                  "Financial difficulties", "Family-related difficulties", "Other"]
SOS_CONTACT_METHODS = ["No preference", "In-person meeting", "Phone call", "Email", "Chat message"]
SOS_STATUSES = ["Submitted", "Acknowledged", "Contact in progress", "Session scheduled", "Resolved"]
DECISIONS = ["accepted", "modified", "rejected"]
INTERVENTION_STATUSES = ["Planned", "In progress", "Completed", "Closed – not needed"]

INTERVENTION_CATALOGUE = [
    "Academic mentoring", "Remedial classes / tutoring", "Progress monitoring",
    "Career counselling", "Career exploration session", "Course / stream guidance",
    "Scholarship information", "Fee assistance information", "Referral to financial support services",
    "Confidential counselling", "Emotional-support resources",
    "Family counselling (with consent)", "Structured family communication (with consent)",
    "Faculty mentoring", "Student support contact",
    "Flexible attendance / temporary academic-break options", "Combined intervention plan",
    "No intervention needed at this time",
]

PROGRAMS = ["Computer Engineering", "Mechanical Engineering", "Electronics Engineering",
            "Civil Engineering", "Information Technology"]

MIN_SAMPLES_PER_CLASS = 10

# ---------------------------------------------------------------------------
# Monthly check-in survey (in-app version of the project's Google Form)
# ---------------------------------------------------------------------------
CHECKIN_INTERVAL_DAYS = 30            # one check-in per student account per rolling 30 days
RESEARCH_FORM_URL = "https://forms.gle/AV4QTg2ueKTXx8Uc6"
FEEDBACK_ASPECTS = {"overall": "Overall experience", "timeliness": "How quickly you were responded to",
                    "helpfulness": "How helpful the support was", "respected": "Felt listened to and respected"}
