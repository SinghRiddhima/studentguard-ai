# StudentGuard UCI academic benchmark

This is a separate real-data experiment. Your existing StudentGuard app expects
14 survey features; UCI does not measure those inputs. Do not rename UCI fields
into stress, motivation, attendance percentage, or other survey answers.
Do not replace your app's models/model.joblib with this benchmark model.

## Run on Windows
Extract this ZIP into your studentguard-ai project folder. It contains a
StudentGuard_UCI subfolder. Open PowerShell in studentguard-ai and run:

```powershell
.\.venv\Scripts\python.exe .\StudentGuard_UCI\train_uci.py --data .\StudentGuard_UCI\data\uci_dropout.csv --out .\StudentGuard_UCI\uci_results
```

If dependencies are missing, install them in your existing environment:

```powershell
.\.venv\Scripts\python.exe -m pip install pandas numpy scikit-learn joblib
```

The script trains locally and saves uci_academic_benchmark.joblib and
uci_metrics.json under StudentGuard_UCI/uci_results. The supplied results JSON
is a reference run; rerunning replaces it. No prebuilt model is included:
training locally avoids pickle compatibility issues between sklearn versions.

## Experiment design
- Original data: 4,424 records, 36 features; semicolon-separated CSV.
- Dropout = 1; Graduate = 0; exclude 794 Enrolled records (unresolved outcomes).
- 3,630 resolved records: 2,904 training / 726 untouched test records.
- Eight numeric academic inputs: admission and prior-qualification grades,
  plus six first-semester curricular-unit measures.
- Prediction time: after semester one. Semester-two measures are excluded.
- Five-fold stratified CV within training data selects the model by F1.
- Logistic Regression, Decision Tree and Random Forest are compared;
  a majority-class baseline is also reported.
- Preprocessing is fitted inside each training fold.
- Default binary threshold 0.5; probabilities are not calibrated.
- No red/yellow/green thresholds are validated by this experiment.

## Reference results
Model | Test accuracy | Dropout precision | Dropout recall | F1
--- | --- | --- | --- | ---
Logistic Regression | 0.847 | 0.787 | 0.835 | 0.810
Decision Tree | 0.853 | 0.811 | 0.813 | 0.812
Random Forest | 0.864 | 0.829 | 0.820 | 0.825
Majority baseline | 0.609 | 0.000 | 0.000 | 0.000

These are random-holdout results from the source institution, restricted to
resolved outcomes. They do not establish performance on your college, on future
cohorts, or on the 14-input survey. UCI has no student IDs to independently
confirm student-disjoint splits. Academic features may also fail to represent
students who leave before a semester-one assessment is possible.

## Connecting to StudentGuard later
A UCI model needs an academic-input form with the same definitions and scales.
Your current survey can remain a separate support-needs assessment. To train a
predictive model using survey answers, collect consented survey records linked
to subsequently observed outcomes and validate on held-out students/cohorts.
Artificially filling UCI's missing survey fields would not validate that model.

## Source and attribution
Realinho, V., Vieira Martins, M., Machado, J., & Baptista, L. (2021).
Predict Students' Dropout and Academic Success [Dataset].
UCI Machine Learning Repository. https://doi.org/10.24432/C5MC89
License: CC BY 4.0 https://creativecommons.org/licenses/by/4.0/
The bundled source CSV is unchanged. The script performs the documented
selection and binary target transformation in memory.
