import pytest
import config
from src import predict, risk_zones, explainability, validation
from tests.conftest import BAD, GOOD


def test_extreme_profiles_map_to_expected_zones():
    assert risk_zones.map_zone(risk_zones.score_features(GOOD)["score"]) == "GREEN"
    assert risk_zones.map_zone(risk_zones.score_features(BAD)["score"]) == "RED"


def test_zone_assignment_is_deterministic_and_boundaries_inclusive():
    a = risk_zones.score_features(GOOD)["score"]
    assert a == risk_zones.score_features(dict(GOOD))["score"]
    t = {"yellow": 30, "red": 55}
    assert risk_zones.map_zone(29.99, t) == "GREEN" and risk_zones.map_zone(30, t) == "YELLOW"
    assert risk_zones.map_zone(55, t) == "RED"


def test_thresholds_are_configurable_and_validated():
    assert risk_zones.map_zone(40, {"yellow": 50, "red": 80}) == "GREEN"
    with pytest.raises(ValueError):
        risk_zones.validate_thresholds({"yellow": 60, "red": 40})


def test_contributions_match_rule_score():
    exp = explainability.rule_explanation(BAD)
    sc = risk_zones.score_features(BAD)
    assert abs(sum(r["contribution"] for r in exp) + sc["pattern_points"] - sc["score"]) < 0.1 or sc["score"] == 100
    assert all(r["method"] == "RULE_WEIGHTS" for r in exp)


def test_patterns_detected():
    p = risk_zones.score_features(dict(GOOD, study_stress=5, motivation=1))["patterns"]
    assert "High study stress combined with low motivation" in p


def test_assess_without_model_is_demonstration_mode():
    r = predict.assess("X", GOOD, None)
    assert r["mode"] == "DEMONSTRATION" and r["model_output"] is None and "DEMONSTRATION MODE" in r["banner"]
    assert set(["student_id", "zone", "assessed_at", "mode", "contributions", "suggested_next_steps"]) <= set(r)


def test_synthetic_model_never_enables_trained_mode():
    from src.train_model import train
    train(config.SYNTHETIC_TRAINING_CSV, save=False)  # runs
    fake = dict(pipeline=None, is_synthetic=True, validated_labels=False)
    assert predict.mode_of(fake) == "DEMONSTRATION"
    assert predict.mode_of(dict(fake, is_synthetic=False, validated_labels=True)) == "TRAINED_MODEL"


def test_invalid_inputs_rejected():
    _, errs = validation.validate_assessment(dict(GOOD, study_stress=9))
    assert errs
    _, errs = validation.validate_assessment({k: v for k, v in GOOD.items() if k != "motivation"})
    assert errs
    _, errs = validation.validate_assessment(dict(GOOD, attendance_pct="abc"))
    assert errs
    clean, errs = validation.validate_assessment(GOOD)
    assert not errs and clean["study_stress"] == 1
