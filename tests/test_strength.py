import pytest

from models.schemas import StrengthSetInput, StrengthWorkoutInput
from services import database, strength_service
from utils.calculations import kg_to_pounds, pounds_to_kg


def test_volume_and_weight_conversion() -> None:
    exercise = StrengthSetInput(exercise_name="Bench Press", sets=3, reps=8, weight_kg=50)
    assert exercise.sets * exercise.reps * exercise.weight_kg == 1200
    assert pounds_to_kg(220.46226218) == pytest.approx(100)
    assert kg_to_pounds(100) == pytest.approx(220.46226218)


def test_empty_database_and_cascade_delete(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    database.init_database(db_path)
    database.save_profile({
        "name": "Test", "primary_goal": "Hybrid Fitness", "experience_level": "Beginner",
        "training_days": 3, "strength_days": 2, "running_days": 1,
        "session_minutes": 45, "equipment": "Dumbbells", "fitness_goals": "",
        "existing_schedule": "",
    }, db_path)
    assert strength_service.list_workouts(db_path) == []
    workout_id = strength_service.add_workout(
        StrengthWorkoutInput(
            workout_date="2026-11-06", session_name="Full Body",
            exercises=[StrengthSetInput(exercise_name="Squat", sets=2, reps=5, weight_kg=60)],
        ), db_path,
    )
    assert strength_service.list_workouts(db_path)[0]["volume_kg"] == 600
    strength_service.delete_workout(workout_id, db_path)
    assert strength_service.list_workouts(db_path) == []
    assert strength_service.list_sets(db_path) == []


def test_active_workout_migration_preserves_legacy_completed_data(tmp_path) -> None:
    import sqlite3

    db_path = tmp_path / "legacy_active.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE strength_workouts (
                id INTEGER PRIMARY KEY, user_id INTEGER, workout_date TEXT,
                session_name TEXT, notes TEXT, created_at TEXT
            );
            CREATE TABLE strength_sets (
                id INTEGER PRIMARY KEY, workout_id INTEGER, exercise_name TEXT,
                set_number INTEGER, reps INTEGER, weight_kg REAL, rpe REAL,
                notes TEXT, pain INTEGER
            );
            CREATE TABLE running_workouts (
                id INTEGER PRIMARY KEY, user_id INTEGER, workout_date TEXT,
                run_type TEXT, distance_km REAL, duration_minutes REAL, rpe INTEGER,
                notes TEXT, pain INTEGER, created_at TEXT
            );
            INSERT INTO users VALUES (1, 'Legacy');
            INSERT INTO strength_workouts VALUES (7, 1, '2026-10-01', 'Upper', 'kept', '2026-10-01');
            INSERT INTO strength_sets VALUES (11, 7, 'Bench Press', 1, 8, 50.0, 7.0, 'old set', 0);
            """
        )

    database.init_database(db_path)
    database.init_database(db_path)
    with sqlite3.connect(db_path) as connection:
        workout = connection.execute(
            "SELECT status, default_rest_seconds FROM strength_workouts WHERE id = 7"
        ).fetchone()
        set_row = connection.execute(
            "SELECT is_completed, exercise_key, technique_concern FROM strength_sets WHERE id = 11"
        ).fetchone()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        routine_tables = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name IN ('workout_routines', 'routine_exercises')"
        ).fetchone()[0]

    assert workout == ("completed", 90)
    assert set_row == (1, "legacy:Bench Press", 0)
    assert version == 1
    assert routine_tables == 2


def test_invalid_strength_input_is_rejected() -> None:
    with pytest.raises(ValueError):
        StrengthSetInput(exercise_name="Squat", sets=0, reps=5, weight_kg=60)