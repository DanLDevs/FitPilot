from datetime import date, datetime, timedelta, timezone

import pytest

from models.schemas import LiveExerciseInput, LiveSetInput, LiveWorkoutInput, RoutineExerciseInput, WorkoutRoutineInput
from services import analytics_service, database, live_workout_service, routine_service, strength_service
from services.timer_service import remaining_seconds


def _profile() -> dict:
    return {
        "name": "Live User", "primary_goal": "Strength", "experience_level": "Intermediate",
        "training_days": 4, "strength_days": 3, "running_days": 1,
        "session_minutes": 60, "equipment": "Full gym", "fitness_goals": "",
        "existing_schedule": "",
    }


def _live_input() -> LiveWorkoutInput:
    return LiveWorkoutInput(
        workout_date=date(2026, 11, 7), session_name="Upper A", default_rest_seconds=75,
        exercises=[LiveExerciseInput(
            exercise_key="bench", exercise_name="Bench Press", target_reps_min=8,
            target_reps_max=12, rest_seconds=90,
            sets=[LiveSetInput(reps=8, weight_kg=50), LiveSetInput(reps=8, weight_kg=50)],
        )],
    )


def test_live_workout_autosave_resume_and_completed_analytics(tmp_path) -> None:
    db_path = tmp_path / "live.db"
    database.init_database(db_path)
    database.save_profile(_profile(), db_path)
    workout_id = live_workout_service.start_workout(_live_input(), db_path)

    active = live_workout_service.get_active_workout(db_path)
    assert active["id"] == workout_id
    assert active["status"] == "active"
    assert strength_service.list_workouts(db_path) == []
    assert analytics_service.dashboard_data(db_path)["strength"] == []

    set_id = active["exercises"][0]["sets"][0]["id"]
    live_workout_service.update_set(
        workout_id, set_id,
        LiveSetInput(reps=11, weight_kg=52.5, rpe=7, notes="Smooth set"),
        db_path,
    )
    resumed = live_workout_service.get_active_workout(db_path)
    assert resumed["exercises"][0]["sets"][0]["reps"] == 11
    assert resumed["exercises"][0]["sets"][0]["weight_kg"] == 52.5

    live_workout_service.finish_workout(workout_id, db_path)
    assert live_workout_service.get_active_workout(db_path) is None
    assert strength_service.list_workouts(db_path) == []
    assert strength_service.list_sets(db_path) == []


def test_finish_keeps_only_completed_sets(tmp_path) -> None:
    db_path = tmp_path / "partial-finish.db"
    database.init_database(db_path)
    database.save_profile(_profile(), db_path)
    workout_id = live_workout_service.start_workout(_live_input(), db_path)
    active = live_workout_service.get_active_workout(db_path)
    live_workout_service.complete_set(workout_id, active["exercises"][0]["sets"][0]["id"], db_path=db_path)
    live_workout_service.finish_workout(workout_id, db_path)
    saved = strength_service.list_workouts(db_path)
    assert saved[0]["id"] == workout_id
    assert saved[0]["set_count"] == 1
    assert len(strength_service.get_workout(workout_id, db_path)["exercises"]) == 1


def test_finished_live_sets_stay_distinct_when_edited(tmp_path) -> None:
    db_path = tmp_path / "edit-live.db"
    database.init_database(db_path)
    database.save_profile(_profile(), db_path)
    workout_id = live_workout_service.start_workout(LiveWorkoutInput(
        workout_date=date(2026, 11, 7), session_name="Upper A",
        exercises=[LiveExerciseInput(
            exercise_key="bench", exercise_name="Bench Press", target_reps_min=8,
            target_reps_max=12, rest_seconds=90,
            sets=[
                LiveSetInput(reps=5, weight_kg=40, technique_concern=True),
                LiveSetInput(reps=8, weight_kg=20),
            ],
        )],
    ), db_path)
    active = live_workout_service.get_active_workout(db_path)
    completed = active["exercises"][0]["sets"][0]
    live_workout_service.complete_set(workout_id, completed["id"], db_path=db_path)
    live_workout_service.finish_workout(workout_id, db_path)

    loaded = strength_service.get_workout(workout_id, db_path)
    assert [(row["reps"], row["weight_kg"]) for row in loaded["exercises"]] == [(5, 40.0)]
    assert loaded["exercises"][0]["target_reps_min"] == 8
    assert loaded["exercises"][0]["technique_concern"] == 1

    strength_service.update_workout(
        workout_id, date(2026, 11, 8), "Upper A", "",
        [{
            "id": loaded["exercises"][0]["id"], "exercise_name": "Bench Press",
            "reps": 6, "weight_kg": 42.5, "rpe": None,
        }],
        db_path,
    )
    saved = strength_service.get_workout(workout_id, db_path)
    assert saved["workout_date"] == "2026-11-08"
    assert [(row["reps"], row["weight_kg"], row["technique_concern"], row["target_reps_max"]) for row in saved["exercises"]] == [
        (6, 42.5, 1, 12),
    ]
    assert len(strength_service.list_sets(db_path)) == 1


def test_live_workout_discard_does_not_enter_history(tmp_path) -> None:
    db_path = tmp_path / "discard.db"
    database.init_database(db_path)
    database.save_profile(_profile(), db_path)
    workout_id = live_workout_service.start_workout(_live_input(), db_path)
    live_workout_service.discard_workout(workout_id, db_path)
    assert live_workout_service.get_active_workout(db_path) is None
    assert strength_service.list_workouts(db_path) == []


def test_routine_crud_and_prefill_active_workout(tmp_path) -> None:
    db_path = tmp_path / "routine-live.db"
    database.init_database(db_path)
    database.save_profile(_profile(), db_path)
    routine_id = routine_service.save_routine(WorkoutRoutineInput(
        name="Push Day", default_rest_seconds=120,
        exercises=[RoutineExerciseInput(
            exercise_name="Bench Press", sets=3, target_reps_min=8,
            target_reps_max=12, starting_weight_kg=45, rest_seconds=150,
        )],
    ), db_path=db_path)
    workout_id = live_workout_service.start_from_routine(routine_id, date(2026, 11, 7), db_path)
    workout = live_workout_service.get_active_workout(db_path)
    assert workout["id"] == workout_id
    assert workout["session_name"] == "Push Day"
    assert workout["default_rest_seconds"] == 120
    assert len(workout["exercises"][0]["sets"]) == 3
    assert workout["exercises"][0]["sets"][0]["rest_seconds"] == 150

    routine_service.delete_routine(routine_id, db_path)
    assert routine_service.get_routine(routine_id, db_path) is None


def test_completed_set_starts_rest_and_notification_is_one_shot(tmp_path) -> None:
    db_path = tmp_path / "timer-live.db"
    database.init_database(db_path)
    database.save_profile(_profile(), db_path)
    workout_id = live_workout_service.start_workout(_live_input(), db_path)
    workout = live_workout_service.get_active_workout(db_path)
    set_id = workout["exercises"][0]["sets"][0]["id"]
    now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
    live_workout_service.complete_set(workout_id, set_id, now, db_path)
    active = live_workout_service.get_active_workout(db_path)
    assert active["rest_ends_at"] is not None
    assert live_workout_service.claim_rest_notification(
        workout_id, now + timedelta(minutes=2), db_path
    ) is True
    assert live_workout_service.claim_rest_notification(
        workout_id, now + timedelta(minutes=2), db_path
    ) is False


def test_auto_rest_can_be_disabled(tmp_path) -> None:
    db_path = tmp_path / "manual-rest.db"
    database.init_database(db_path)
    database.save_profile(_profile(), db_path)
    workout = _live_input().model_copy(update={"auto_start_rest": False})
    workout_id = live_workout_service.start_workout(workout, db_path)
    active = live_workout_service.get_active_workout(db_path)
    live_workout_service.complete_set(workout_id, active["exercises"][0]["sets"][0]["id"], db_path=db_path)
    assert live_workout_service.get_active_workout(db_path)["rest_ends_at"] is None


def test_rest_timer_persists_pause_resume_and_adjustments(tmp_path) -> None:
    db_path = tmp_path / "timer-controls.db"
    database.init_database(db_path)
    database.save_profile(_profile(), db_path)
    workout_id = live_workout_service.start_workout(_live_input(), db_path)
    now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
    live_workout_service.start_rest(workout_id, 60, now, db_path)
    live_workout_service.pause_rest(workout_id, now + timedelta(seconds=15), db_path)
    paused = live_workout_service.get_active_workout(db_path)
    assert paused["rest_paused_remaining_seconds"] == 45
    assert paused["rest_ends_at"] is None

    resume_at = now + timedelta(seconds=30)
    live_workout_service.resume_rest(workout_id, resume_at, db_path)
    resumed = live_workout_service.get_active_workout(db_path)
    assert remaining_seconds(resumed["rest_ends_at"], resume_at) == 45
    live_workout_service.adjust_rest(workout_id, 15, resume_at, db_path)
    adjusted = live_workout_service.get_active_workout(db_path)
    assert remaining_seconds(adjusted["rest_ends_at"], resume_at) == 60


def test_active_exercise_targets_and_rest_can_be_edited(tmp_path) -> None:
    db_path = tmp_path / "edit-exercise.db"
    database.init_database(db_path)
    database.save_profile(_profile(), db_path)
    workout_id = live_workout_service.start_workout(_live_input(), db_path)
    active = live_workout_service.get_active_workout(db_path)
    exercise_key = active["exercises"][0]["exercise_key"]
    live_workout_service.update_exercise_details(
        workout_id, exercise_key, "Incline Bench Press", 6, 10, 120, db_path,
    )
    updated = live_workout_service.get_active_workout(db_path)["exercises"][0]
    assert updated["exercise_name"] == "Incline Bench Press"
    assert updated["target_reps_min"] == 6
    assert updated["target_reps_max"] == 10
    assert updated["rest_seconds"] == 120


def test_active_workout_is_singleton(tmp_path) -> None:
    db_path = tmp_path / "singleton.db"
    database.init_database(db_path)
    database.save_profile(_profile(), db_path)
    live_workout_service.start_workout(_live_input(), db_path)
    with pytest.raises(ValueError, match="already exists"):
        live_workout_service.start_workout(_live_input(), db_path)