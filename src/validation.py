"""Input validation for assessments and SOS requests."""
import math
import config


def validate_assessment(raw: dict):
    """Validate a feature dict. Returns (clean_dict, errors). Values must be numeric and in range."""
    clean, errors = {}, []
    for f in config.FEATURES:
        k = f["key"]
        if k not in raw or raw[k] is None or (isinstance(raw[k], float) and math.isnan(raw[k])):
            errors.append(f"'{f['label']}' is required.")
            continue
        try:
            v = float(raw[k])
        except (TypeError, ValueError):
            errors.append(f"'{f['label']}' must be a number.")
            continue
        if not (f["min"] <= v <= f["max"]):
            errors.append(f"'{f['label']}' must be between {f['min']} and {f['max']} (got {v:g}).")
            continue
        if f.get("options") and int(v) != v:
            errors.append(f"'{f['label']}' must be a whole-number code.")
            continue
        clean[k] = int(v) if f.get("options") else v
    return clean, errors


def validate_sos(category: str, message: str, contact_method: str):
    errors = []
    if category not in config.SOS_CATEGORIES:
        errors.append("Please choose a support category.")
    if contact_method not in config.SOS_CONTACT_METHODS:
        errors.append("Please choose a valid contact method.")
    if message is not None and len(message) > 2000:
        errors.append("The message must be 2000 characters or fewer.")
    return errors
