"""UCI academic benchmark page. Does not write predictions to student records."""
from pathlib import Path

import joblib
import pandas as pd
import streamlit as st

import config

FIELDS = [
    ('Admission grade', 'Admission grade (0–200)', 0.0, 200.0, 120.0),
    ('Previous qualification (grade)', 'Previous qualification grade (0–200)', 0.0, 200.0, 120.0),
    ('Curricular units 1st sem (credited)', 'Credited units', 0, 100, 0),
    ('Curricular units 1st sem (enrolled)', 'Enrolled units', 0, 100, 6),
    ('Curricular units 1st sem (evaluations)', 'Number of evaluations', 0, 300, 6),
    ('Curricular units 1st sem (approved)', 'Passed units', 0, 100, 6),
    ('Curricular units 1st sem (grade)', 'Semester-one grade (0–20)', 0.0, 20.0, 12.0),
    ('Curricular units 1st sem (without evaluations)', 'Units without evaluations', 0, 100, 0),
]


def validate_inputs(values):
    enrolled = values['Curricular units 1st sem (enrolled)']
    if values['Curricular units 1st sem (approved)'] > enrolled:
        return 'Passed units cannot exceed enrolled units.'
    if values['Curricular units 1st sem (without evaluations)'] > enrolled:
        return 'Units without evaluations cannot exceed enrolled units.'
    return None


@st.cache_resource
def load_model(path, modified_ns):
    # Only the fixed, locally trained project artifact is loaded; no upload path.
    bundle = joblib.load(path)
    metadata = bundle.get('metadata', {})
    expected = [field[0] for field in FIELDS]
    if metadata.get('features') != expected or 'pipeline' not in bundle:
        raise ValueError('The saved model does not match the eight UCI academic inputs.')
    if metadata.get('label_mapping') != {'Graduate': 0, 'Dropout': 1}:
        raise ValueError('Unexpected model outcome labels. Retrain with train_uci.py.')
    return bundle


def render(ctx):
    if ctx.user.get('role') not in ('counsellor', 'administrator', 'admin'):
        st.error('This research page is available to counsellors and administrators only.')
        return
    st.title('Academic Model Lab')
    st.caption('UCI academic benchmark · predictions after semester one')
    st.info('This model was evaluated on UCI records from another institution. '
            'It is not validated for your college, and its probabilities are not calibrated. '
            'Results here do not change student risk zones or records.')
    path = Path(config.BASE_DIR) / 'StudentGuard_UCI_results' / 'uci_academic_benchmark.joblib'
    if not path.is_file():
        st.warning('Train the UCI model first and save it in StudentGuard_UCI_results '
                   'inside your project folder.')
        st.code(str(path))
        return
    try:
        bundle = load_model(str(path), path.stat().st_mtime_ns)
    except Exception as exc:
        st.error(f'Could not load the academic model: {exc}')
        st.caption('Run train_uci.py again using the same Python environment as this app.')
        return
    metadata = bundle['metadata']
    st.subheader('Evaluation on held-out UCI records')
    selected = metadata.get('selected_model', 'Unknown')
    st.caption(f'Selected using training cross-validation: {selected}. '
               f"Training records: {metadata.get('train_rows', '?')}; "
               f"test records: {metadata.get('test_rows', '?')}.")
    rows = []
    for name, result in metadata.get('results', {}).items():
        test = result.get('test', {})
        rows.append({'Model': name, **{metric.title(): round(test[metric], 3)
                                     for metric in ('accuracy', 'precision', 'recall', 'f1') if metric in test}})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption('Positive class = Dropout. Enrolled records were excluded because their final '
               'outcomes were unresolved; the comparison is Dropout versus Graduate only.')
    st.subheader('Try an academic example')
    st.write('Use the source grading scales below. Defaults are an illustrative example. '
             'Do not enter CGPA or percentages directly into grade fields with a different scale.')
    st.caption('A curricular unit means a course/module, not a mark or attendance percentage. '
               'Credited units are recognised prior credits; evaluations are assessment attempts. '
               'Unit counts refer to semester one. Input limits are form safeguards, not validated ranges.')
    with st.form('uci_academic_example'):
        columns = st.columns(2)
        values = {}
        for index, (key, label, low, high, default) in enumerate(FIELDS):
            with columns[index % 2]:
                values[key] = st.number_input(label, min_value=low, max_value=high,
                                             value=default, step=0.1 if isinstance(default, float) else 1,
                                             key='uci_' + key)
        submitted = st.form_submit_button('Run academic example')
    if submitted:
        error = validate_inputs(values)
        if error:
            st.error(error)
            return
        try:
            pipeline = bundle['pipeline']
            inputs = pd.DataFrame([values], columns=metadata['features'])
            probability = float(pipeline.predict_proba(inputs)[0, list(pipeline.classes_).index(1)])
            st.metric('Model score for the Dropout class', f'{probability:.1%}')
            st.caption('Uncalibrated model output—not a verified personal chance of dropping out. '
                       'No green/yellow/red zone is assigned. This example is not saved.')
        except Exception as exc:
            st.error(f'Could not calculate this example: {exc}')
    with st.expander('Dataset and limitations'):
        st.markdown('[UCI dataset and citation](https://doi.org/10.24432/C5MC89) · CC BY 4.0')
        for limitation in metadata.get('limitations', []):
            st.write('• ' + limitation)
