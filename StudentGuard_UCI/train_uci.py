"""Standalone UCI academic benchmark; not compatible with the survey app model.
Run: python train_uci.py --data data/uci_dropout.csv
"""
import argparse
import hashlib
import json
from pathlib import Path

import joblib
import pandas as pd
import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                             f1_score, roc_auc_score, confusion_matrix)
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_validate
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

# Numeric academic measurements only. No semester-two information, demographic
# category codes, or invented survey responses. Predictions occur AFTER semester one.
FEATURES = [
    'Admission grade', 'Previous qualification (grade)',
    'Curricular units 1st sem (credited)',
    'Curricular units 1st sem (enrolled)',
    'Curricular units 1st sem (evaluations)',
    'Curricular units 1st sem (approved)',
    'Curricular units 1st sem (grade)',
    'Curricular units 1st sem (without evaluations)',
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path('data/uci_dropout.csv'))
    parser.add_argument('--out', type=Path, default=Path('uci_results'))
    args = parser.parse_args()
    df = pd.read_csv(args.data, sep=';')
    df.columns = df.columns.str.strip()
    required = FEATURES + ['Target']
    missing = sorted(set(required) - set(df.columns))
    if missing:
        raise SystemExit('Missing UCI columns: ' + ', '.join(missing))
    labels = df['Target'].astype(str).str.strip()
    if not set(labels).issubset({'Dropout', 'Graduate', 'Enrolled'}):
        raise SystemExit('Unexpected target values; expected Dropout/Graduate/Enrolled.')
    original_counts = labels.value_counts().to_dict()
    df['Target'] = labels
    # Remove exact duplicate source rows before splitting to avoid exact-copy leakage.
    duplicates = int(df.duplicated().sum())
    df = df.drop_duplicates()
    df = df.loc[df['Target'].isin(['Dropout', 'Graduate'])].copy()
    X = df[FEATURES].apply(pd.to_numeric, errors='raise')
    y = df['Target'].map({'Dropout': 1, 'Graduate': 0})
    if y.value_counts().min() < 20 or y.nunique() != 2:
        raise SystemExit('Insufficient examples of both outcomes for this experiment.')
    Xtrain, Xtest, ytrain, ytest = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y)
    candidates = {
        'Logistic Regression': LogisticRegression(max_iter=2000, class_weight='balanced'),
        'Decision Tree': DecisionTreeClassifier(max_depth=5, class_weight='balanced', random_state=42),
        'Random Forest': RandomForestClassifier(n_estimators=200, min_samples_leaf=3,
                                                class_weight='balanced_subsample', random_state=42, n_jobs=1),
    }
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    fitted, results = {}, {}
    for name, estimator in candidates.items():
        pipeline = make_pipeline(SimpleImputer(strategy='median'), StandardScaler(), estimator)
        scores = cross_validate(pipeline, Xtrain, ytrain, cv=cv,
                                scoring=['precision', 'recall', 'f1', 'roc_auc'], n_jobs=1)
        results[name] = {'cv': {metric: {'mean': float(scores['test_' + metric].mean()),
                                       'std': float(scores['test_' + metric].std())}
                               for metric in ['precision', 'recall', 'f1', 'roc_auc']}}
        fitted[name] = pipeline.fit(Xtrain, ytrain)
    # Choose using training CV only, before evaluating the untouched test partition.
    winner = max(results, key=lambda name: results[name]['cv']['f1']['mean'])
    baseline = DummyClassifier(strategy='most_frequent').fit(Xtrain, ytrain)
    results['Majority baseline'] = {'cv': None}
    for name, model in {**fitted, 'Majority baseline': baseline}.items():
        prediction = model.predict(Xtest)
        probability = model.predict_proba(Xtest)[:, list(model.classes_).index(1)]
        results[name]['test'] = {
            'accuracy': float(accuracy_score(ytest, prediction)),
            'precision': float(precision_score(ytest, prediction, zero_division=0)),
            'recall': float(recall_score(ytest, prediction, zero_division=0)),
            'f1': float(f1_score(ytest, prediction, zero_division=0)),
            'roc_auc': float(roc_auc_score(ytest, probability)),
            'confusion_matrix': confusion_matrix(ytest, prediction, labels=[0, 1]).tolist(),
        }
    metadata = {
        'purpose': 'UCI academic research benchmark; not a StudentGuard survey model',
        'prediction_time': 'End of first semester',
        'source': 'https://doi.org/10.24432/C5MC89', 'license': 'CC BY 4.0',
        'source_sha256': hashlib.sha256(args.data.read_bytes()).hexdigest(),
        'sklearn_version': sklearn.__version__,
        'source_class_counts': original_counts, 'exact_duplicates_removed': duplicates,
        'label_mapping': {'Graduate': 0, 'Dropout': 1},
        'excluded_label': 'Enrolled (unresolved final outcome)',
        'features': FEATURES, 'selected_model': winner, 'selection_metric': 'Training CV F1',
        'train_rows': len(ytrain), 'test_rows': len(ytest),
        'test_dropout_count': int(ytest.sum()), 'seed': 42,
        'confusion_matrix_order': 'Rows=actual, columns=predicted; [Graduate, Dropout]',
        'threshold': 0.5, 'calibrated': False,
        'limitations': [
            'Evaluation is conditional on resolved Dropout/Graduate outcomes; Enrolled is excluded.',
            'One institution and a random holdout; no validation on your college or future cohorts.',
            'No attendance percentage or survey stress/motivation inputs are available.',
            'Probabilities and green/yellow/red thresholds are not validated for deployment.',
            'Source has no student identifiers to independently verify student-disjoint partitions.',
        ],
        'results': results,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'uci_metrics.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    joblib.dump({'pipeline': fitted[winner], 'metadata': metadata}, args.out / 'uci_academic_benchmark.joblib')
    print(f'Train: {len(ytrain)} | Test: {len(ytest)} | Selected by CV: {winner}')
    for name, result in results.items():
        m = result['test']
        print(f"{name:22} accuracy={m['accuracy']:.3f} precision={m['precision']:.3f} "
              f"recall={m['recall']:.3f} F1={m['f1']:.3f}")
    print('Saved to', args.out.resolve())
    print('Research benchmark only. Do not replace models/model.joblib with this model.')


if __name__ == '__main__':
    main()
