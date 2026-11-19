"""Dataset inspection, validation, encoding and the sklearn preprocessing pipeline."""
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import config


class DatasetError(Exception):
    """Raised with a human-readable message when a dataset is missing or incompatible."""


def load_dataset(path) -> pd.DataFrame:
    try:
        df = pd.read_csv(path)
    except FileNotFoundError:
        raise DatasetError(f"Dataset not found at '{path}'. Run `python -m src.generate_synthetic_data` "
                           "to create the synthetic demo data, or provide your own CSV.")
    except Exception as e:  # noqa: BLE001
        raise DatasetError(f"Could not read '{path}' as CSV: {e}")
    if df.empty:
        raise DatasetError(f"'{path}' contains no rows.")
    return df


def encode_survey_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Map text answers (e.g. 'Often', 'Below average') to ordinal codes using config option labels.
    Numeric columns are left untouched. Unknown text becomes NaN (and is reported as missing)."""
    df = df.copy()
    for f in config.FEATURES:
        k = f["key"]
        if k in df.columns and not pd.api.types.is_numeric_dtype(df[k]) and f.get("options"):
            inv = {}
            for code, text in f["options"].items():
                inv[str(text).lower()] = code
                inv[str(text).split("–")[-1].strip().lower()] = code
                inv[str(code)] = code
            df[k] = df[k].astype(str).str.strip().str.lower().map(inv)
        elif k in df.columns:
            df[k] = pd.to_numeric(df[k], errors="coerce")
    return df


def check_columns(df: pd.DataFrame, required=None):
    required = required or config.FEATURE_KEYS
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise DatasetError("Dataset is missing required feature columns: " + ", ".join(missing) +
                           ". Rename/derive them (see data/README.md) or remove them from config.FEATURES.")


def clip_out_of_range(df: pd.DataFrame):
    """Set out-of-range values to NaN (they are then imputed inside the pipeline). Returns (df, n_changed)."""
    df, n = df.copy(), 0
    for f in config.FEATURES:
        k = f["key"]
        bad = df[k].notna() & ((df[k] < f["min"]) | (df[k] > f["max"]))
        n += int(bad.sum())
        df.loc[bad, k] = np.nan
    return df, n


def inspect_dataset(df: pd.DataFrame, target: str = None, id_col: str = "student_id") -> dict:
    feats = [c for c in config.FEATURE_KEYS if c in df.columns]
    rep = dict(n_records=int(len(df)), n_columns=int(df.shape[1]), n_features_available=len(feats),
               features_missing_from_dataset=[c for c in config.FEATURE_KEYS if c not in df.columns],
               missing_values={c: int(v) for c, v in df[feats].isna().sum().items() if v > 0},
               duplicate_rows=int(df.duplicated().sum()),
               dtypes={c: str(t) for c, t in df.dtypes.items()})
    if id_col in df.columns:
        rep["unique_students"] = int(df[id_col].nunique())
        rep["one_record_per_student"] = bool(df[id_col].nunique() == len(df))
    else:
        rep["unique_students"] = None
        rep["one_record_per_student"] = None
        rep["id_note"] = f"No '{id_col}' column: cannot confirm one record per student."
    if target and target in df.columns:
        vc = df[target].value_counts(dropna=False)
        rep["target"] = target
        rep["class_distribution"] = {str(k): int(v) for k, v in vc.items()}
    else:
        rep["target"] = None
        rep["class_distribution"] = None
    return rep


def validate_target(df: pd.DataFrame, target: str):
    """Return (ok, messages). Labels must be binary 0/1 with enough examples per class."""
    msgs = []
    if not target or target not in df.columns:
        return False, [f"Target column '{target}' not found – no supervised target available."]
    y = df[target]
    if y.isna().any():
        msgs.append(f"{int(y.isna().sum())} rows have missing labels.")
    vals = set(y.dropna().unique().tolist())
    if not vals.issubset({0, 1}):
        msgs.append(f"Target must be binary 0/1; found values {sorted(map(str, vals))}.")
    counts = y.value_counts()
    for cls in (0, 1):
        if counts.get(cls, 0) < config.MIN_SAMPLES_PER_CLASS:
            msgs.append(f"Class {cls} has {int(counts.get(cls, 0))} examples (< {config.MIN_SAMPLES_PER_CLASS}); "
                        "metrics would be unreliable.")
    return len(msgs) == 0, msgs


def build_preprocessor(feature_keys=None) -> ColumnTransformer:
    """Median imputation + standardisation. Fitted only inside a Pipeline on training folds (no leakage).
    All features are already ordinal numeric, so no one-hot encoding is required."""
    feature_keys = feature_keys or config.FEATURE_KEYS
    numeric = Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())])
    return ColumnTransformer([("num", numeric, feature_keys)], remainder="drop")
