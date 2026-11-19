"""Explicit, configurable risk-mapping logic.

DEMONSTRATION rule score (0-100): weighted sum of per-indicator "concern levels" (0-1)
plus a small bonus for co-occurring patterns. Weights/thresholds are ILLUSTRATIVE
(see config.py) – they are transparent judgement calls, not validated statistics.
"""
import config


def concern_level(feature: dict, value) -> float:
    """Map a raw value to a 0-1 concern level (1 = most concerning)."""
    if value is None:
        return 0.0
    v = float(value)
    if "concern_map" in feature:
        return float(feature["concern_map"].get(int(round(v)), 0.0))
    if feature.get("kind") == "percent":
        return min(1.0, max(0.0, (90.0 - v) / 50.0))
    span = feature["max"] - feature["min"]
    frac = (v - feature["min"]) / span if span else 0.0
    frac = frac if feature["direction"] == "high_is_concern" else 1.0 - frac
    return min(1.0, max(0.0, frac)) ** config.CONCERN_EXPONENT


def concern_levels(features: dict) -> dict:
    return {f["key"]: concern_level(f, features.get(f["key"])) for f in config.FEATURES}


def detect_patterns(levels: dict) -> list:
    t = config.CONCERN_TRIGGER
    return [label for a, b, label in config.PATTERNS if levels.get(a, 0) >= t and levels.get(b, 0) >= t]


def score_features(features: dict) -> dict:
    """Return {'score', 'levels', 'points' (per-feature points), 'patterns', 'pattern_points'}."""
    levels = concern_levels(features)
    total_w = sum(f["weight"] for f in config.FEATURES)
    points = {f["key"]: 100.0 * f["weight"] / total_w * levels[f["key"]] for f in config.FEATURES}
    patterns = detect_patterns(levels)
    pattern_points = config.PATTERN_BONUS * len(patterns)
    score = min(100.0, sum(points.values()) + pattern_points)
    return dict(score=round(score, 2), levels=levels, points=points,
                patterns=patterns, pattern_points=pattern_points)


def validate_thresholds(t: dict, upper: float = 100.0):
    if not (0 < t["yellow"] < t["red"] <= upper):
        raise ValueError(f"Thresholds must satisfy 0 < yellow < red <= {upper:g}.")


def map_zone(value: float, thresholds: dict = None) -> str:
    """Map a score (or probability) to GREEN / YELLOW / RED using explicit thresholds."""
    t = thresholds or config.DEFAULT_SCORE_THRESHOLDS
    if value >= t["red"]:
        return "RED"
    if value >= t["yellow"]:
        return "YELLOW"
    return "GREEN"
