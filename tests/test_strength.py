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