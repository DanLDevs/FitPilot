from models.schemas import RunningWorkoutInput
from services import database, running_service
from utils.calculations import km_to_miles, miles_to_km
from utils.sample_data import load_demo_data
from datetime import date


def test_running_crud_and_unit_conversion(tmp_path) -> None:
    db_path = tmp_path / "running.db"
    database.init_database(db_path)
    database.save_profile({
        "name": "Runner", "primary_goal": "Running Endurance", "experience_level": "Beginner",
        "training_days": 3, "strength_days": 1, "running_days": 2,
        "session_minutes": 45, "equipment": "", "fitness_goals": "", "existing_schedule": "",
    }, db_path)
    run = RunningWorkoutInput(
        workout_date="2026-11-06", run_type="Easy", distance_km=miles_to_km(3.1),
        duration_minutes=30, rpe=4,
    )
    run_id = running_service.add_workout(run, db_path)
    assert km_to_miles(running_service.list_workouts(db_path)[0]["distance_km"]) == 3.1

    edited = run.model_copy(update={"distance_km": 5.0, "duration_minutes": 28})
    running_service.update_workout(run_id, edited, db_path)
    assert running_service.list_workouts(db_path)[0]["duration_minutes"] == 28
    running_service.delete_workout(run_id, db_path)
    assert running_service.list_workouts(db_path) == []


def test_demo_loader_is_repeatable(tmp_path) -> None:
    db_path = tmp_path / "demo.db"
    database.init_database(db_path)
    assert load_demo_data(db_path) is True
    first_run_count = len(running_service.list_workouts(db_path))
    expected_current_week_runs = sum(offset <= date.today().weekday() for offset in (1, 3, 6))
    assert first_run_count == 15 + expected_current_week_runs
    assert all(row["workout_date"] <= date.today().isoformat() for row in running_service.list_workouts(db_path))
    assert load_demo_data(db_path) is False
    assert len(running_service.list_workouts(db_path)) == first_run_count