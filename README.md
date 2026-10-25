# 🛡️ StudentGuard AI — AI-Powered Early Warning and Student Support System

A working Streamlit prototype for the project *“AI-Based Student Dropout Prediction System”*: multi-factor risk
**zones**, an **SOS counselling** workflow, **explainable** assessments and a **human-in-the-loop** review process.

> **Honest status: the app runs in DEMONSTRATION MODE.** The only input we had was the project brief PDF, which contains aggregate
> survey percentages — no student-level records and **no verified dropout outcomes**. A supervised dropout model cannot be validly
> trained from that. So the prototype uses a transparent rule score and a clearly labelled **synthetic** dataset to show the full
> workflow. Nothing in this app is a validated prediction of real dropout.

## Four USPs
1. **Three-level risk zones** (Green / Yellow / Red) from an explicit, admin-configurable mapping function.
2. **SOS counselling** — always available to every student, independent of risk zone; persisted, trackable, role-protected.
3. **Explainable AI** — per-indicator contributions (exact rule weights; SHAP when a trained model is the source) + co-occurring patterns.
4. **Human-in-the-loop** — counsellors accept / modify / reject suggestions with a mandatory reason; all actions audited.

## Architecture
```
Student data → validation → missing-value handling → encoding → preprocessing → model training/evaluation
        → risk assessment (mode-aware) → explanation → rule-based intervention suggestions → human decision → audit log
```
Stack: Python, Streamlit, pandas/NumPy, scikit-learn, Joblib, SHAP, Plotly, SQLite. (XGBoost not used: dataset is small and tabular,
the three scikit-learn models are enough and add no dependency.)

## Project structure
```
app.py                  entry point, login, role-based navigation
config.py               features/scales, weights, thresholds, notices (all judgement calls live here)
src/  survey (monthly check-in) · data_preprocessing · generate_synthetic_data · train_model · predict · risk_zones · explainability
      intervention_engine · database · authentication · validation · seed
views/ (the "pages" – named views/ because Streamlit auto-creates an unfiltered menu from a folder called pages/,
        which would bypass role-based navigation)
tests/ test_risk_zones · test_interventions · test_database · test_pipeline · test_survey · test_app (UI, per role/page)
data/  synthetic CSVs + README      models/  model.joblib, metrics.json (created by training)
```

## Install & run
```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m src.generate_synthetic_data   # optional: CSVs are already included
python -m src.train_model               # creates models/model.joblib + metrics.json (synthetic demo model)
streamlit run app.py
python -m pytest -q                     # run the tests
```
The database (`studentguard.db`) is created and seeded with synthetic data automatically on first launch.
The app also works if no model exists (rule-based demo mode). Delete `studentguard.db` to reset.

**Demo logins:** `student1/student123` (also student2, student3) · `counsellor/counsel123` · `admin/admin123`

## Demo walkthrough (presentation)
1. Student1 → press **SOS**, submit → note the request ID. 2. Sign out; counsellor → *SOS Requests* → acknowledge → schedule → resolve.
3. Student1 → status updated. 4. Counsellor → *Student Risk Assessment* → submit a profile → see zone, explanation, suggestions →
accept/modify/reject with reason. 5. *Intervention Centre* → audit trail. 6. Admin → aggregates only (no messages), thresholds, accounts.

## New: monthly check-in, progress tracking and service feedback
- **Monthly check-in (in-app version of the Google Form).** Students answer Q3–Q19 of the project survey inside their account. Answers are mapped to the
  model's 14 indicators (`src/survey.py`, mapping documented there), an assessment and zone are produced automatically, and everything is stored.
  **One check-in per student account per rolling 30 days**, enforced in the database layer; the student sees when the next one opens.
  "Not sure / prefer not to say" answers use a neutral default and are listed as *assumed* for the counsellor. Academic trend is derived from the previous snapshot.
- **Why not embed the Google Form itself?** Its submissions go to Google, not to this app, so the monthly limit and automatic zoning cannot work.
  The original form link is kept in Admin → Settings as anonymous research; it is not connected to accounts.
- **Self-reported intention (Q17–Q19)** is shown to counsellors as context and can raise a ⚑ review flag. It is not a score input and not a dropout label.
- **Progress & Trends:** timeline of each student's zone with counselling/intervention events marked; "before support → latest" outcome
  (Improved / Same zone / Higher concern); cohort transitions (e.g. RED→YELLOW). A change after support is **not proof of causation**.
- **Service feedback:** after a request is *Resolved* the student rates the service (4 ratings + optional comment), once per request.
  Counsellors see ratings and comments; admins see averages only.
- Demo data now has 3 months of history for each synthetic student, including some cases that did *not* improve.
  If you upgraded from the first version, **delete `studentguard.db`** once so the new demo history is created.

## Methodology
**Dataset requirements:** see `data/README.md`. `inspect_dataset` reports records, features, missing values, duplicates, dtypes,
target, class distribution and whether there is one record per student; `validate_target` rejects missing/non-binary/too-small classes.

**Model evaluation:** Logistic Regression, Decision Tree, Random Forest (deployed baseline) plus a majority-class baseline. Preprocessing
(median imputation + scaling) sits inside a scikit-learn `Pipeline`, so it is fitted only on training folds (no leakage). Stratified 80/20 split
(group-aware if `student_id` repeats) + 5-fold CV. Reported: accuracy, precision, recall, F1, ROC-AUC, Brier, confusion matrix. Accuracy alone is
misleading on imbalanced data — the baseline row demonstrates this. All numbers are computed, never hard-coded. Probabilities are **not** claimed calibrated.

**Risk zones:** *Demonstration mode* — score 0–100 = weighted per-indicator concern levels + 4 points per co-occurring pattern.
Weights, the 1.5 exponent and thresholds (Yellow ≥ 30, Red ≥ 55) are **illustrative expert judgement**, not validated. Admins can change thresholds (stored per assessment).
*Trained-model mode* is enabled **only** if the model was trained with `--validated-labels` on non-synthetic data; zones then come from model probability with
placeholder thresholds in `config.py` that you must validate and document before relying on them.

**Explainability:** `RULE_WEIGHTS` = exact points per indicator in the demo score. `SHAP` (TreeExplainer) is used only when the trained model drives the result.
The synthetic-trained model's output is shown as “illustrative” and does not set the zone. Factors are associations, not causes; no diagnoses.

**Interventions:** transparent rule-based mapping (not ML) in `intervention_engine.py`; each suggestion shows concern, support, reason and
“Pending human review”.

**SOS workflow:** Submitted → Acknowledged → Contact in progress → Session scheduled → Resolved; timestamps and request ID (`SOS-YYYYMMDD-XXXXXX`).
Students see status history but not counsellors' private notes. Admins see counts only.

**Privacy / safeguards:** permissions are enforced in `database.py` (not just the UI); parameterised SQL; salted PBKDF2 password hashes; SOS messages never
in aggregates; no automatic penalties; synthetic rows flagged `is_synthetic`.

## What works in demo mode vs needs more
| Works now | Needs real data / integrations |
|---|---|
| Full UI workflow, SQLite persistence, roles, audit, SOS, rule-based zones, SHAP code path, tests | Validated dropout model (needs verified outcomes), calibrated thresholds, email/SMS alerts, SSO, encryption, emergency services |

## Limitations
- No real labelled data → no validated predictive claims; synthetic-label metrics only show the pipeline works.
- The survey's “considered discontinuing” (38.5%) is not a dropout probability or label.
- Demo auth only (no lockout/MFA/session expiry/HTTPS); local unencrypted SQLite; passwords published for the demo.
- **No notifications** are sent; counsellors must check the queue. Not an emergency service.
- Small, single-institution data would not generalise to other colleges.

## Future improvements
Collect verified outcome labels (e.g. enrolment status after 6–12 months) with consent; validate/calibrate thresholds;
fairness checks; SSO + encryption; email/SMS notifications; consent management; longitudinal tracking.
