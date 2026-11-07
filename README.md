# FitPilot

FitPilot is a local-first fitness tracking MVP for hybrid athletes. It records strength sessions and runs in SQLite, summarizes training on a Streamlit dashboard, and runs without an AI API key.

## Features

- Local profile setup for goals, experience, schedule, and equipment.
- Strength workout logging with multiple exercises and sets, effort, notes, and pain flags.
- Live Workout mode with autosaved, resumable sessions, set completion, rest timers, and routine prefill.
- Editable manual workout routines and deterministic, history-based progression cues.
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

The SQLite database is created automatically at `FITPILOT_DB_PATH` if set, or `fitpilot.db` otherwise. Additive database migrations preserve existing workout history. The app supports one local athlete profile.

Complete the profile form on the dashboard and use **Load demo data** to add six weeks of example sessions. The demo loader avoids duplicates. Use **Live Workout** to start a blank session or load a saved routine. Set edits are persisted as you work, and an active session can be resumed after a refresh. Rest timers use saved timestamps and keep an in-app completion alert; optional browser notifications require permission and may be restricted by the browser or embedded frame.

## Tests

```powershell
python -m pytest
```

## Limitations and next steps

Progression cues are deterministic suggestions based on completed set history and never change weights automatically. Live Workout supports manual routines; AI-generated routines, AI coaching, schedule analysis, and full training-plan generation are not included in this checkout. FitPilot is not a medical tool. Browser notifications may be unavailable in some mobile browsers; the in-app timer remains the fallback.
