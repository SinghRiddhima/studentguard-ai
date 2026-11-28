# StudentGuard AI

StudentGuard is a B.Tech team project that helps a college counsellor decide whom to follow up with and what support to offer. A student completes a monthly check-in or asks for help directly. The counsellor can see which answers contributed to a concern, review suggested interventions and record a decision. Students can track their requests.

The project also includes an **Academic Model Lab**. It compares three classifiers on a public dataset with recorded student outcomes. The selected Random Forest achieved **0.825 dropout F1** on a held-out set of **726 UCI records**.

**Stack** · Python, Streamlit, scikit-learn, pandas, SQLite and Plotly.

## Try the support workflow

| Sign in as | Demo username | Demo password | What to try |
|---|---|---|---|
| Student | student1 | student123 | Open My Profile, submit an SOS counselling request with a fictional message and note its ID. Students in any risk zone can ask for help. |
| Counsellor | counsellor | counsel123 | Open SOS Counselling Requests, find the ID and acknowledge the request. Sign back in as the student to see the updated status. |
| Administrator | admin | admin123 | Open Overview to see cohort-level information. Open Settings to inspect the risk thresholds. |

For a second walkthrough, sign in as the counsellor and open **Student Risk Assessment**. Inspect the contributing indicators, then use **Intervention Centre** to accept, modify or reject a suggestion and record the reason. SQLite stores assessments, requests and review history between sessions.

The monthly check-in maps survey answers to 14 indicators. Weighted rules assign green, yellow or red support zones in the demo. These zones help organise follow-up. Their thresholds still need validation against local student outcomes. Use fictional student details with the published demo accounts.

## Academic benchmark

The experiment asks whether eight academic measurements available by the end of semester one can distinguish eventual dropout from graduation. Of 4,424 UCI records, 794 had an unresolved outcome (“Enrolled”). The remaining 3,630 were split into 2,904 training records and 726 held-out test records. Five-fold stratified cross-validation on the training data selected the model by dropout F1. Each fold fitted its own preprocessing pipeline.

| Model | Test accuracy | Dropout precision | Dropout recall | Dropout F1 |
|---|---:|---:|---:|---:|
| Majority-class baseline | 60.9% | 0.000 | 0.000 | 0.000 |
| Logistic Regression | 84.7% | 0.787 | 0.835 | 0.810 |
| Decision Tree | 85.3% | 0.811 | 0.813 | 0.812 |
| **Random Forest** | **86.4%** | **0.829** | **0.820** | **0.825** |

The forest identified 233 of 284 dropout cases, missed 51 and flagged 48 graduates. These figures describe a single institution and students with resolved outcomes. The probabilities are uncalibrated. The **Academic Model Lab** lets counsellors explore example academic inputs separately from student check-in records.

[UCI dataset and attribution](https://doi.org/10.24432/C5MC89) · [Training script](StudentGuard_UCI/train_uci.py) · [Full evaluation and confusion matrices](StudentGuard_UCI_results/uci_metrics.json)

## Run locally

From the repository root in Windows PowerShell, use Python 3.11 or 3.12. The first launch seeds a local SQLite database with synthetic student histories. Choose **Enter StudentGuard** to sign in.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

On Linux or macOS, run the following from the same directory.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

Open the local URL printed by Streamlit. With the project environment active, run the test suite or reproduce the UCI benchmark in a separate output directory.

```sh
python -m pytest -q
python StudentGuard_UCI/train_uci.py --out benchmark-run
```

## Explore the implementation

| Area | Entry point |
|---|---|
| Monthly check-in and answer mapping | [Survey logic](src/survey.py) |
| Support zones and intervention suggestions | [Risk zones](src/risk_zones.py) · [Intervention rules](src/intervention_engine.py) |
| Role permissions, request history and persistence | [Database layer](src/database.py) |
| Academic experiment in the dashboard | [Academic Model Lab](views/academic_model.py) |
| Demo data and optional survey-model training | [Dataset guide](data/README.md) · [Training pipeline](src/train_model.py) |
| Contact verification | [Verification service](src/contact_verification.py) |

Local sign-up accepts fictional contact details and stores them as unverified. Optional email and phone verification uses Twilio Verify with a configured email sender, SMS delivery and the server variables `TWILIO_VERIFY_SERVICE_SID`, `TWILIO_VERIFY_API_KEY` and `TWILIO_VERIFY_API_SECRET`. Counsellors check the SOS queue in the app. Institutional authentication, secure handling of real student records and validation on future cohorts remain future work.
