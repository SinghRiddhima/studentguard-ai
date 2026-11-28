# StudentGuard AI | B.Tech team project

**Python · Streamlit · scikit-learn · pandas · SQLite**

## Résumé entry

- Co-developed a student-support app that turns monthly check-ins into explainable risk zones and lets counsellors review interventions and track student-initiated SOS requests.
- Compared Logistic Regression, Decision Tree and Random Forest on 3,630 UCI records with known outcomes. Random Forest achieved 0.825 dropout F1 and 82.0% recall on 726 held-out records.

## Interview walkthrough

Start as a student, send a fictional SOS request and show the request ID. Switch to the counsellor account, acknowledge the request, then return to the student view to show the status change. This demonstrates a complete workflow across roles.

For the ML portion, open Academic Model Lab. Explain why the team used only inputs available by the end of semester one and excluded 794 still-enrolled students. Compare the forest with the majority baseline. The baseline reached 60.9% accuracy while missing every dropout. The forest caught 233 of 284 dropout cases at the default threshold.

If asked about impact, describe what the team measured on the UCI holdout. Evaluating whether counselling reduces dropout would require follow-up outcomes. When discussing your individual role, name the component you personally worked on and one implementation decision you can explain.

[Project repository](https://github.com/SinghRiddhima/studentguard-ai)
