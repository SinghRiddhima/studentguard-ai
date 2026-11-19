"""Generate SYNTHETIC data for demonstration. NOT real students, NOT real dropout outcomes.

Marginal distributions are loosely inspired by the survey brief (e.g. most students have high
attendance, many report some stress) but are NOT a replica of the 182 survey responses.
`synthetic_concern_label` is derived from the transparent rule score + noise; a model trained
on it can only re-learn that rule. It says nothing about real-world predictive validity.
"""
import argparse
import numpy as np
import pandas as pd
import config
from src import risk_zones


def _clip_round(x, lo, hi):
    return np.clip(np.rint(x), lo, hi).astype(int)


def generate_features(n: int, seed: int = 42, shift: float = 0.0, spread: float = 1.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    z = rng.normal(shift, spread, n)          # latent "difficulty" so indicators correlate realistically
    e = lambda s=0.9: rng.normal(0, s, n)  # noqa: E731
    df = pd.DataFrame({
        "academic_performance": _clip_round(2.4 - 0.5 * z + e(0.7), 1, 4),
        "academic_trend": _clip_round(2.1 - 0.45 * z + e(0.6), 1, 3),
        "attendance_pct": np.clip(np.rint(91 - 6 * z + rng.normal(0, 5, n)), 40, 100).astype(int),
        "study_stress": _clip_round(3.2 + 0.7 * z + e(), 1, 5),
        "motivation": _clip_round(3.6 - 0.6 * z + e(), 1, 5),
        "career_clarity": _clip_round(3.8 - 0.5 * z + e(1.0), 1, 5),
        "course_satisfaction": _clip_round(3.6 - 0.55 * z + e(1.0), 1, 5),
        "course_career_alignment": _clip_round(3.7 - 0.55 * z + e(1.0), 1, 5),
        "financial_difficulty": _clip_round(2.0 + 0.6 * z + e(0.9), 1, 5),
        "family_pressure": _clip_round(2.9 + 0.4 * z + e(1.0), 1, 5),
        "confidence_continuing": _clip_round(4.0 - 0.6 * z + e(0.8), 1, 5),
        "faculty_comfort": _clip_round(3.2 - 0.4 * z + e(1.1), 1, 5),
        "career_guidance": _clip_round(2.8 - 0.3 * z + e(0.9), 1, 4),
    })
    p_change = 1 / (1 + np.exp(-(-1.0 + 0.9 * z)))
    df["considered_change"] = (rng.random(n) < p_change).astype(int)
    return df[config.FEATURE_KEYS]


def build_training_data(n=1500, seed=42, missing_rate=0.02) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 1)
    df = generate_features(n, seed)
    scores = np.array([risk_zones.score_features(r)["score"] for r in df.to_dict("records")])
    noisy = scores + rng.normal(0, 7, n)
    cut = np.quantile(noisy, 0.80)   # ~20% flagged: imbalanced on purpose to demonstrate metrics
    out = df.copy()
    out.insert(0, "student_id", [f"SYN{i:05d}" for i in range(1, n + 1)])
    out["synthetic_concern_label"] = (noisy >= cut).astype(int)
    out["data_source"] = "SYNTHETIC"
    for col in ["study_stress", "career_clarity", "financial_difficulty", "faculty_comfort", "attendance_pct"]:
        out.loc[rng.random(n) < missing_rate, col] = np.nan   # demonstrate missing-value handling
    return out


def build_sample_students(n=40, seed=7) -> pd.DataFrame:
    """Small roster used to seed the demo database (all synthetic pseudonyms)."""
    rng = np.random.default_rng(seed)
    df = generate_features(n, seed, shift=0.7, spread=1.5)
    df.insert(0, "student_id", [f"S{i:03d}" for i in range(1, n + 1)])
    df.insert(1, "alias", [f"Demo Student {i:03d}" for i in range(1, n + 1)])
    df.insert(2, "program", rng.choice(config.PROGRAMS, n))
    df.insert(3, "year", rng.integers(1, 5, n))
    df["data_source"] = "SYNTHETIC"
    return df


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=1500)
    args = ap.parse_args()
    config.DATA_DIR.mkdir(exist_ok=True)
    t = build_training_data(args.n)
    t.to_csv(config.SYNTHETIC_TRAINING_CSV, index=False)
    s = build_sample_students()
    s.to_csv(config.SAMPLE_STUDENTS_CSV, index=False)
    print(f"Wrote {config.SYNTHETIC_TRAINING_CSV} ({len(t)} rows, SYNTHETIC)")
    print(f"Wrote {config.SAMPLE_STUDENTS_CSV} ({len(s)} rows, SYNTHETIC)")


if __name__ == "__main__":
    main()
