import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB_PATH = Path(os.getenv("FITPILOT_DB_PATH", "fitpilot.db"))


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_database(db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                name TEXT NOT NULL,
                primary_goal TEXT NOT NULL,
                experience_level TEXT NOT NULL,
                training_days INTEGER NOT NULL,
                strength_days INTEGER NOT NULL,
                running_days INTEGER NOT NULL,
                session_minutes INTEGER NOT NULL,
                equipment TEXT NOT NULL DEFAULT '',
                fitness_goals TEXT NOT NULL DEFAULT '',
                existing_schedule TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS strength_workouts (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id) ON DELETE CASCADE,
                workout_date TEXT NOT NULL,
                session_name TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS strength_sets (
                id INTEGER PRIMARY KEY,
                workout_id INTEGER NOT NULL REFERENCES strength_workouts(id) ON DELETE CASCADE,
                exercise_name TEXT NOT NULL,
                set_number INTEGER NOT NULL,
                reps INTEGER NOT NULL CHECK (reps > 0),
                weight_kg REAL NOT NULL CHECK (weight_kg >= 0),
                rpe REAL,
                notes TEXT NOT NULL DEFAULT '',
                pain INTEGER NOT NULL DEFAULT 0 CHECK (pain IN (0, 1))
            );
            CREATE TABLE IF NOT EXISTS running_workouts (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id) ON DELETE CASCADE,
                workout_date TEXT NOT NULL,
                run_type TEXT NOT NULL,
                distance_km REAL NOT NULL CHECK (distance_km > 0),
                duration_minutes REAL NOT NULL CHECK (duration_minutes > 0),
                rpe INTEGER,
                notes TEXT NOT NULL DEFAULT '',
                pain INTEGER NOT NULL DEFAULT 0 CHECK (pain IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_strength_date ON strength_workouts(workout_date);
            CREATE INDEX IF NOT EXISTS idx_strength_exercise ON strength_sets(exercise_name);
            CREATE INDEX IF NOT EXISTS idx_running_date ON running_workouts(workout_date);
            """
        )


def get_profile(db_path: str | Path | None = None) -> dict | None:
    with get_connection(db_path) as connection:
        row = connection.execute("SELECT * FROM users WHERE id = 1").fetchone()
        return dict(row) if row else None


def save_profile(profile: dict, db_path: str | Path | None = None) -> None:
    fields = (
        "name", "primary_goal", "experience_level", "training_days", "strength_days",
        "running_days", "session_minutes", "equipment", "fitness_goals", "existing_schedule",
    )
    values = [profile[field] for field in fields]
    assignments = ", ".join(f"{field} = excluded.{field}" for field in fields)
    with get_connection(db_path) as connection:
        connection.execute(
            f"INSERT INTO users (id, {', '.join(fields)}) VALUES (1, {', '.join('?' for _ in fields)}) "
            f"ON CONFLICT(id) DO UPDATE SET {assignments}, updated_at = CURRENT_TIMESTAMP",
            values,
        )