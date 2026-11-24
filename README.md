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

## Install and run in Windows PowerShell

Extract the ZIP and open PowerShell in the inner `studentguard-ai` folder that contains `app.py`. Use Python 3.12.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open `http://localhost:8501`. These commands use the virtual environment directly, so PowerShell activation is optional.
On macOS or Linux, use `python3.12 -m venv .venv` and replace `.\.venv\Scripts\python.exe` with `.venv/bin/python`.
Run `python -m pytest -q` with the same virtual environment's Python. The included model uses scikit-learn 1.8.0.
To retrain it on the included synthetic CSV, run `python -m src.train_model` with the same Python.

The app creates and seeds `studentguard.db` on first launch. To carry your v2 demo history forward, stop the
old app and copy its SQLite database next to the new `app.py` before launching. Back it up first.
Fresh starts can use a new database and the bundled synthetic data.

## Redesigned demo

Open **Enter StudentGuard**, then sign in as `student1` / `student123`, `counsellor` / `counsel123`,
or `admin` / `admin123`. Each role opens **My Profile**. Students can edit their display name,
username, college-issued student ID, programme, year and photo. Contact details and password have
their own forms. Existing students can add their college ID while keeping their previous check-ins and counselling records.
Dark is the default. The theme selector stores its setting in the current URL so a reload can restore it.
Signing in is scoped to the Streamlit session.

New students enter their own college ID, email and international-format phone number in **Student sign-up**.
Invites are optional. Administrators can generate a one-time invite valid for 24 hours under **Settings → Student invitations**.

### Email and phone verification

With a configured [Twilio Verify service](https://www.twilio.com/docs/verify), sign-up requires both an email code and an SMS code.
For [email delivery](https://www.twilio.com/docs/verify/email), connect a verified SendGrid sender and template to the Verify service.
Enable SMS delivery to the destination countries you plan to test. Set these environment variables in the server environment before restarting Streamlit.

- `TWILIO_VERIFY_SERVICE_SID` for the Verify service SID
- `TWILIO_VERIFY_API_KEY` for the Twilio API key SID
- `TWILIO_VERIFY_API_SECRET` for the Twilio API key secret

For a local demo without those settings, use fictional contact details. They are saved as unverified.
When changing an already verified contact, the app keeps the current address or number until the replacement is verified.
Codes confirm access to the email address and phone number. The college ID is self-reported.
The demo still uses local accounts and published sample credentials. Use institutional authentication before handling real student records.

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

## Release audit

| # | Check | Verification |
|---|---|---|
| 1 | Welcome copy and landing route | AppTest |
| 2 | Orbital artwork | Implemented in CSS |
| 3 | Dark default and light control | AppTest checks toggle and URL state |
| 4 | Theme on browser reload, including initial paint | Browser check pending |
| 5 | Mobile layout and menu | Browser check pending |
| 6 | Keyboard focus, contrast and screen reader navigation | Accessibility audit pending |
| 7 | Reduced motion | CSS media query in place; browser check pending |
| 8 | Sign-in for all three roles | AppTest |
| 9 | Student invitation and one-time use | AppTest and SQLite |
| 10 | Personal profile as the first page after sign-in | AppTest for each role |
| 11 | Display-name persistence | AppTest |
| 12 | Avatar upload and removal | Image processing and SQLite tested; browser upload check pending |
| 13 | Sign-out | AppTest |
| 14 | Direct SOS submission from a profile | AppTest |
| 15 | Check-in lock, progress and service feedback | AppTest and SQLite |
| 16 | Human decisions and audit trail | SQLite tests |
| 17 | Demonstration risk scoring and explanation | Pipeline and unit tests |

The browser checks cover the remaining visual work, including native widget styling in light mode.
Authentication uses Streamlit sessions. This build has no persistent sign-in cookie or password reset.
