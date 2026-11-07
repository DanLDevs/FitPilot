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
    assert version == 3
    assert routine_tables == 2


def test_partial_schema_version_still_receives_live_workout_columns(tmp_path) -> None:
    import sqlite3

    db_path = tmp_path / "partial.db"
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
                notes TEXT, pain INTEGER, target_reps_min INTEGER,
                target_reps_max INTEGER, technique_concern INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE running_workouts (
                id INTEGER PRIMARY KEY, user_id INTEGER, workout_date TEXT,
                run_type TEXT, distance_km REAL, duration_minutes REAL, rpe INTEGER,
                notes TEXT, pain INTEGER, created_at TEXT
            );
            INSERT INTO users VALUES (1, 'Partial');
            INSERT INTO strength_workouts VALUES (3, 1, '2026-10-02', 'Lower', '', '2026-10-02');
            INSERT INTO strength_sets VALUES (4, 3, 'Squat', 1, 5, 80, 8, '', 0, 5, 8, 0);
            PRAGMA user_version = 1;
            """
        )

    database.init_database(db_path)
    with sqlite3.connect(db_path) as connection:
        status = connection.execute("SELECT status FROM strength_workouts WHERE id = 3").fetchone()[0]
        completed = connection.execute("SELECT is_completed FROM strength_sets WHERE id = 4").fetchone()[0]
        version = connection.execute("PRAGMA user_version").fetchone()[0]

    assert status == "completed"
    assert completed == 1
    assert version == 3


def test_existing_routines_gain_rest_columns_without_losing_rows(tmp_path) -> None:
    import sqlite3

    from services import routine_service

    db_path = tmp_path / "routines_v2.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE workout_routines (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL DEFAULT 1,
                name TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE routine_exercises (
                id INTEGER PRIMARY KEY,
                routine_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                exercise_name TEXT NOT NULL,
                sets INTEGER NOT NULL,
                target_reps_min INTEGER NOT NULL,
                target_reps_max INTEGER NOT NULL,
                starting_weight_kg REAL,
                notes TEXT NOT NULL DEFAULT ''
            );
            INSERT INTO users VALUES (1, 'Existing');
            INSERT INTO workout_routines (id, name, notes) VALUES (4, 'Push Day', 'kept');
            INSERT INTO routine_exercises
                (routine_id, position, exercise_name, sets, target_reps_min, target_reps_max, starting_weight_kg, notes)
                VALUES (4, 0, 'Bench Press', 3, 6, 10, 60, '');
            PRAGMA user_version = 2;
            """
        )

    database.init_database(db_path)
    routines = routine_service.list_routines(db_path)

    assert len(routines) == 1
    assert routines[0]["name"] == "Push Day"
    assert routines[0]["notes"] == "kept"
    assert routines[0]["default_rest_seconds"] == 90
    assert routines[0]["auto_start_rest"] == 1
    assert routines[0]["exercises"][0]["exercise_name"] == "Bench Press"
    assert routines[0]["exercises"][0]["rest_seconds"] is None
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3


def test_invalid_strength_input_is_rejected() -> None:
    with pytest.raises(ValueError):
        StrengthSetInput(exercise_name="Squat", sets=0, reps=5, weight_kg=60)