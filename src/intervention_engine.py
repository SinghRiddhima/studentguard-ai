"""Transparent RULE-BASED support recommendations. Not machine learning, and independent of the
prediction model. All suggestions are advisory – a counsellor accepts, modifies or rejects them."""
import config
from src import risk_zones

CATEGORIES = {
    "academic": dict(concern="Academic difficulty / declining performance",
                     support=["Academic mentoring", "Remedial classes / tutoring", "Progress monitoring"]),
    "attendance": dict(concern="Attendance difficulty",
                       support=["Student support contact", "Flexible attendance / temporary academic-break options"]),
    "career": dict(concern="Career uncertainty / course mismatch",
                   support=["Career counselling", "Career exploration session", "Course / stream guidance"]),
    "financial": dict(concern="Financial difficulty",
                      support=["Scholarship information", "Fee assistance information",
                               "Referral to financial support services"]),
    "emotional": dict(concern="Reported stress / low motivation / low confidence",
                      support=["Confidential counselling", "Emotional-support resources"]),
    "family": dict(concern="Family pressure / circumstances",
                   support=["Family counselling (with consent)", "Structured family communication (with consent)"]),
    "institutional": dict(concern="Low perceived faculty / guidance support",
                          support=["Faculty mentoring", "Student support contact"]),
}


def recommend(features: dict) -> list:
    """Return a list of dicts: category, concern, support[], reason, triggers[], level, decision_status."""
    levels = risk_zones.concern_levels(features)
    recs = []
    for cat, meta in CATEGORIES.items():
        trig = [f for f in config.FEATURES if f["category"] == cat and levels[f["key"]] >= config.CONCERN_TRIGGER]
        if not trig:
            continue
        shown = "; ".join(f"{f['label']} = {f['options'][int(features[f['key']])] if f.get('options') else str(features[f['key']]) + '%'}"
                          for f in trig)
        recs.append(dict(category=cat, concern=meta["concern"], support=list(meta["support"]),
                         reason=f"Triggered by: {shown}.", triggers=[f["key"] for f in trig],
                         level=round(max(levels[f["key"]] for f in trig), 2),
                         decision_status="Pending human review"))
    recs.sort(key=lambda r: -r["level"])
    if len(recs) >= 3:
        recs.insert(0, dict(category="multiple", concern="Multiple concerns identified",
                            support=["Combined intervention plan", "Counsellor review", "Coordinated follow-up"],
                            reason=f"{len(recs)} separate concern areas were triggered "
                                   f"({', '.join(r['category'] for r in recs)}).",
                            triggers=[], level=1.0, decision_status="Pending human review"))
    if not recs:
        recs.append(dict(category="general", concern="No specific concern identified",
                         support=["Continue regular academic monitoring", "General academic and career resources"],
                         reason="No indicator reached the concern trigger. This is not a guarantee of future outcomes.",
                         triggers=[], level=0.0, decision_status="Pending human review"))
    return recs


def flat_support(recs: list) -> list:
    seen, out = set(), []
    for r in recs:
        for s in r["support"]:
            if s not in seen:
                seen.add(s)
                out.append(s)
    return out
