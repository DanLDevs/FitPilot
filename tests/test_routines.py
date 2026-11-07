from models.schemas import RoutineExerciseInput, WorkoutRoutineInput
from services import database, routine_service


def _profile() -> dict:
    return {
        "name": "Test", "primary_goal": "Strength", "experience_level": "Intermediate",
        "training_days": 4, "strength_days": 3, "running_days": 1,
        "session_minutes": 60, "equipment": "Full gym", "fitness_goals": "",
        "existing_schedule": "",
    }


def _routine(name: str = "Upper A") -> WorkoutRoutineInput:
    return WorkoutRoutineInput(
        name=name, notes="Controlled progression",
        exercises=[RoutineExerciseInput(
            exercise_name="Bench Press", sets=3, target_reps_min=8,
            target_reps_max=12, starting_weight_kg=50,
        )],
    )


def test_routine_crud_duplicate_and_cascade(tmp_path) -> None:
    db_path = tmp_path / "routines.db"
    database.init_database(db_path)
    database.save_profile(_profile(), db_path)

    routine_id = routine_service.save_routine(_routine(), db_path=db_path)
    routine = routine_service.get_routine(routine_id, db_path)
    assert routine["exercises"][0]["target_reps_max"] == 12

    updated_id = routine_service.save_routine(_routine("Upper B"), routine_id, db_path)
    assert updated_id == routine_id
    assert routine_service.get_routine(routine_id, db_path)["name"] == "Upper B"

    duplicate_id = routine_service.duplicate_routine(routine_id, db_path)
    assert routine_service.get_routine(duplicate_id, db_path)["name"] == "Copy of Upper B"
    routine_service.delete_routine(routine_id, db_path)
    assert routine_service.get_routine(routine_id, db_path) is None
    assert len(routine_service.list_routines(db_path)) == 1