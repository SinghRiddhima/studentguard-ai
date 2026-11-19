from src import intervention_engine as ie
from tests.conftest import BAD, GOOD


def cats(f):
    return [r["category"] for r in ie.recommend(f)]


def test_no_concern_gives_general_resources_only():
    assert cats(GOOD) == ["general"]


def test_financial_concern_maps_to_financial_support():
    r = [x for x in ie.recommend(dict(GOOD, financial_difficulty=5)) if x["category"] == "financial"][0]
    assert "Scholarship information" in r["support"] and "Financial difficulty" in r["reason"]


def test_career_and_emotional_mapping():
    assert "career" in cats(dict(GOOD, career_clarity=1, course_satisfaction=1))
    assert "emotional" in cats(dict(GOOD, study_stress=5))


def test_multiple_concerns_produce_combined_plan():
    recs = ie.recommend(BAD)
    assert recs[0]["category"] == "multiple" and "Combined intervention plan" in recs[0]["support"]


def test_all_recommendations_pending_human_review():
    assert all(r["decision_status"] == "Pending human review" for r in ie.recommend(BAD))
