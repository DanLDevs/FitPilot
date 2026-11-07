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


def test_invalid_strength_input_is_rejected() -> None:
    with pytest.raises(ValueError):
        StrengthSetInput(exercise_name="Squat", sets=0, reps=5, weight_kg=60)