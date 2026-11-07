# FitPilot

FitPilot is a local-first fitness tracking MVP for hybrid athletes. It records strength sessions and runs in SQLite, summarizes training on a Streamlit dashboard, and runs without an AI API key.

## Features

- Local profile setup for goals, experience, schedule, and equipment.
- Flexible strength logging with add/remove exercise and set controls, per-set reps, weight, RPE, pain, and technique flags.
- Saved manual workout routines that can be edited, duplicated, and loaded into the strength logger.
- Optional Gemini-generated routine drafts that are validated, editable, and saved only after user review.
- Deterministic progressive-overload checks based on repeated set-level performance; recommendations never change loads automatically.
- Running logs with automatic pace calculation and pain/effort tracking.
- Weekly strength-volume and running-distance analytics with interactive charts.
- Repeatable six-week demo data for exploring the dashboard.

## Stack and architecture

Python 3.11+, Streamlit, SQLite, Pydantic, Pandas, NumPy, Plotly, and python-dotenv. `app.py` and `pages/` contain the UI; `services/` owns persistence and queries; `models/` validates inputs; `utils/` contains unit conversions and demo data. All stored strength weights are kilograms and run distances are kilometers.

## Install and run

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

The SQLite database is created automatically at `FITPILOT_DB_PATH` if set, or `fitpilot.db` otherwise. The app applies additive SQLite migrations automatically and preserves existing workout records.

Complete the profile form on the dashboard and use **Load demo data** to add six weeks of example sessions. The demo loader avoids duplicates. In **Workout routines**, build a routine manually without an API key, or choose **Ask Gemini for a draft**. Set `GEMINI_API_KEY` in `.env` or Streamlit secrets to enable generation. The Gemini routine is a draft and is not saved until reviewed and approved.

## Tests

```powershell
python -m pytest
```

## Limitations and next steps

Progression suggestions are based on recorded set history and are not medical advice. Gemini generation is optional; manual tracking and routines remain available without credentials. The app currently supports one local profile. It does not yet include running AI coaching, schedule analysis, or full weekly plan generation. Deterministic tests do not require a Gemini API key; Gemini integration tests mock the client.
