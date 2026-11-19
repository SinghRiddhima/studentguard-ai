# Data folder

| File | What it is | Real? |
|---|---|---|
| `sample_students.csv` | 40 pseudonymised **synthetic** students used to seed the demo database | **SYNTHETIC** |
| `synthetic_training_data.csv` | 1,500 **synthetic** rows with `synthetic_concern_label` (generated from the demo rule score + noise) | **SYNTHETIC** |

Regenerate both: `python -m src.generate_synthetic_data`

**The 182-response Google-Forms survey is NOT in this project** — only its aggregate percentages appear in the project brief.
Nothing here is real student data and `synthetic_concern_label` is **not** a dropout outcome.

## Using your own real data
Required columns (names exactly as in `config.FEATURES`; text answers like "Often" are auto-mapped to codes):
`academic_performance (1-4), academic_trend (1-3), attendance_pct (0-100), study_stress (1-5), motivation (1-5), career_clarity (1-5),
course_satisfaction (1-5), course_career_alignment (1-5), financial_difficulty (1-5), family_pressure (1-5),
confidence_continuing (1-5), faculty_comfort (1-5), career_guidance (1-4), considered_change (0/1)`
plus optional `student_id`, and — for supervised training — a **binary 0/1 target of VERIFIED historical outcomes**
(e.g. student left the programme within N months of the survey).

Survey answers such as "I have considered discontinuing" are NOT verified outcomes; do not use them as the target.
Then: `python -m src.train_model --data your.csv --target your_target --validated-labels`
