# FitPilot

FitPilot is a local-first fitness tracking MVP for hybrid athletes. It records strength sessions and runs in SQLite, summarizes training on a Streamlit dashboard, and runs without an AI API key.

## Features

- Local profile setup for goals, experience, schedule, and equipment.
- Strength workout logging with multiple exercises and sets, effort, notes, and pain flags.
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

The SQLite database is created automatically at `FITPILOT_DB_PATH` if set, or `fitpilot.db` otherwise. `.env` is optional; copy `.env.example` to `.env` only when configuring future Gemini integration. No Gemini calls are made in this Phase 1 build.

Complete the profile form on the dashboard and use **Load demo data** to add six weeks of example sessions. The demo loader avoids duplicates.

## Tests

```powershell
python -m pytest
```

## Limitations and next steps

This phase provides tracking and basic descriptive analytics only. It does not yet include deterministic progression recommendations, AI coaching, schedule analysis, or plan generation. The app currently supports one local profile and is not a medical tool. Planned follow-up work includes progression and hybrid-training insights, Gemini integration with validated responses, editable training plans, and broader test coverage.
