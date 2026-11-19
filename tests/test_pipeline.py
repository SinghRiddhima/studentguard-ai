import pandas as pd
import pytest
import config
from src import data_preprocessing as dp
from src.train_model import train


def test_missing_dataset_helpful_error(tmp_path):
    with pytest.raises(dp.DatasetError, match="not found"):
        dp.load_dataset(tmp_path / "nope.csv")


def test_incompatible_dataset_columns(tmp_path):
    with pytest.raises(dp.DatasetError, match="missing required feature columns"):
        dp.check_columns(pd.DataFrame({"a": [1]}))


def test_no_valid_target_is_reported(tmp_path):
    df = pd.read_csv(config.SYNTHETIC_TRAINING_CSV).drop(columns=["synthetic_concern_label"])
    p = tmp_path / "d.csv"
    df.to_csv(p, index=False)
    with pytest.raises(dp.DatasetError, match="No valid supervised target"):
        train(p, "synthetic_concern_label", save=False)


def test_training_reports_real_metrics_and_flags_synthetic():
    m = train(config.SYNTHETIC_TRAINING_CSV, save=False)
    assert m["is_synthetic"] and not m["validated_labels"] and not m["calibrated"]
    h = m["results"]["Random Forest"]["holdout"]
    cm = h["confusion_matrix"]
    assert sum(map(sum, cm)) == m["split"]["test"]
    assert m["results"]["Majority-class baseline"]["holdout"]["recall"] == 0.0


def test_text_labels_are_encoded():
    df = pd.DataFrame({"study_stress": ["Often", "never"], "academic_performance": ["Below average", "Excellent"]})
    out = dp.encode_survey_labels(df)
    assert out["study_stress"].tolist() == [4, 1] and out["academic_performance"].tolist() == [1, 4]
