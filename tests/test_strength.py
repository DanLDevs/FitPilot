import pytest
import sqlite3

from models.schemas import (
    RoutineExerciseInput,
    StrengthExerciseLogInput,
    StrengthSetInput,
    StrengthWorkoutInput,
    WorkoutRoutineInput,
        StrengthSetLogInput,
        StrengthWorkoutLogInput,
)
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
    assert version == 6
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
    assert version == 6


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
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
        assert connection.execute("SELECT plan_id FROM workout_routines WHERE id = 4").fetchone()[0] is None


def test_profile_weight_unit_defaults_to_kilograms(tmp_path) -> None:
    db_path = tmp_path / "units.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE users (
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
            PRAGMA user_version = 5;
            """
        )
    database.init_database(db_path)
    profile = {
        "name": "Test", "primary_goal": "Hybrid Fitness", "experience_level": "Beginner",
        "training_days": 3, "strength_days": 2, "running_days": 1,
        "session_minutes": 45, "equipment": "", "fitness_goals": "",
        "existing_schedule": "",
    }
    database.save_profile(profile, db_path)
    assert database.get_profile(db_path)["weight_unit"] == "kg"
    database.save_profile(profile | {"weight_unit": "lb"}, db_path)
    assert database.get_profile(db_path)["weight_unit"] == "lb"
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6


def test_invalid_strength_input_is_rejected() -> None:
    with pytest.raises(ValueError):
        StrengthSetInput(exercise_name="Squat", sets=0, reps=5, weight_kg=60)


def test_per_set_and_routine_models_validate_rep_ranges() -> None:
    with pytest.raises(ValueError):
        StrengthExerciseLogInput(
            exercise_name="Squat", target_reps_min=12, target_reps_max=8,
            sets=[{"reps": 10, "weight_kg": 50}],
        )
    routine = WorkoutRoutineInput(
        name="Leg day",
        exercises=[RoutineExerciseInput(
            exercise_name="Squat", sets=3, target_reps_min=8,
            target_reps_max=12, starting_weight_kg=50,
        )],
    )
    assert routine.exercises[0].target_reps_max == 12


def test_strength_schema_migration_preserves_existing_sets(tmp_path) -> None:
    db_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE strength_workouts (id INTEGER PRIMARY KEY, user_id INTEGER, workout_date TEXT, session_name TEXT, notes TEXT);
        CREATE TABLE strength_sets (
            id INTEGER PRIMARY KEY, workout_id INTEGER, exercise_name TEXT,
            set_number INTEGER, reps INTEGER, weight_kg REAL, rpe REAL,
            notes TEXT, pain INTEGER
        );
        INSERT INTO users VALUES (1, 'Legacy User');
        INSERT INTO strength_workouts VALUES (7, 1, '2026-10-01', 'Upper', 'kept');
        INSERT INTO strength_sets VALUES (11, 7, 'Bench Press', 1, 8, 50.0, 7.0, 'old set', 0);
        """
    )
    connection.commit()
    connection.close()

    database.init_database(db_path)
    database.init_database(db_path)
    with sqlite3.connect(db_path) as migrated:
        migrated.row_factory = sqlite3.Row
        row = migrated.execute("SELECT * FROM strength_sets WHERE id = 11").fetchone()
        tables = {item[0] for item in migrated.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert row["reps"] == 8
    assert row["weight_kg"] == 50.0
    assert row["target_reps_min"] is None
    assert row["technique_concern"] == 0
    assert {"workout_routines", "routine_exercises"} <= tables

def test_per_set_values_persist_independently(tmp_path) -> None:
    db_path = tmp_path / "per_set.db"
    database.init_database(db_path)
    database.save_profile({
        "name": "Test", "primary_goal": "Strength", "experience_level": "Beginner",
        "training_days": 3, "strength_days": 2, "running_days": 1,
        "session_minutes": 45, "equipment": "Barbell", "fitness_goals": "",
        "existing_schedule": "",
    }, db_path)
    workout = StrengthWorkoutLogInput(
        workout_date="2026-11-06", session_name="Upper",
        exercises=[StrengthExerciseLogInput(
            exercise_name="Bench Press", target_reps_min=8, target_reps_max=12,
            sets=[
                StrengthSetLogInput(reps=12, weight_kg=50, rpe=7),
                StrengthSetLogInput(reps=10, weight_kg=50, rpe=8, technique_concern=True),
                StrengthSetLogInput(reps=9, weight_kg=47.5, rpe=9, pain=True),
            ],
        )],
    )
    workout_id = strength_service.add_workout(workout, db_path)
    records = strength_service.list_sets(db_path)
    assert [row["reps"] for row in records] == [12, 10, 9]
    assert records[1]["technique_concern"] == 1
    assert records[2]["pain"] == 1
    assert all(row["target_reps_max"] == 12 for row in records)
    assert strength_service.get_workout(workout_id, db_path)["exercises"][0]["sets"] == 3