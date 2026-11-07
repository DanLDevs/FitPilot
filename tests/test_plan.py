import json

import pytest

from models.schemas import GeneratedWeek, RoutineExerciseInput, WorkoutRoutineInput
from services import database, plan_service, routine_service
from services.gemini_plan_service import (
    PlanCountError,
    build_prompt,
    gemini_response_schema,
    generate_week,
    resolve_day_counts,
    resolve_gemini_model,
)
from services.log_defaults import running_log_defaults, strength_log_defaults


def _profile(**overrides) -> dict:
    profile = {
        "name": "Avery",
        "primary_goal": "Hybrid Fitness",
        "experience_level": "Intermediate",
        "training_days": 4,
        "strength_days": 2,
        "running_days": 2,
        "session_minutes": 45,
        "equipment": "dumbbells and a treadmill",
        "fitness_goals": "Build a 5K",
        "existing_schedule": "Monday and Thursday evenings are free",
    }
    profile.update(overrides)
    return profile


def _strength_day(title: str, weekday: str) -> dict:
    return {
        "weekday": weekday,
        "session_kind": "strength",
        "title": title,
        "notes": "Keep the last set shy of failure",
        "default_rest_seconds": 90,
        "auto_start_rest": True,
        "exercises": [{
            "exercise_name": "Goblet Squat",
            "sets": 3,
            "target_reps_min": 8,
            "target_reps_max": 12,
            "rest_seconds": 75,
            "notes": "",
        }],
    }


def _running_day(title: str, weekday: str) -> dict:
    return {
        "weekday": weekday,
        "session_kind": "running",
        "title": title,
        "notes": "Easy conversational pace",
        "run_type": "Easy",
        "distance_km": 5,
        "duration_minutes": 32,
        "exercises": [],
    }


def _week_payload() -> dict:
    return {
        "name": "Hybrid week",
        "summary": "Two lifts and two easy runs.",
        "days": [
            _strength_day("Lower strength", "Monday"),
            _running_day("Easy run", "Tuesday"),
            _strength_day("Upper strength", "Thursday"),
            _running_day("Short shakeout", "Saturday"),
        ],
    }


def test_prompt_includes_profile_fields() -> None:
    profile = _profile()
    counts = resolve_day_counts(profile)
    prompt = build_prompt(profile, counts, "watch the left knee")
    for value in (
        "Avery", "Hybrid Fitness", "Intermediate", "4", "2", "45",
        "dumbbells and a treadmill", "Build a 5K",
        "Monday and Thursday evenings are free", "watch the left knee",
    ):
        assert value in prompt
    assert "Required strength sessions: 2" in prompt
    assert "Required running sessions: 2" in prompt


def test_day_counts_follow_profile_preferences() -> None:
    assert resolve_day_counts(_profile()) == {"strength_days": 2, "running_days": 2}
    assert resolve_day_counts(_profile(strength_days=3, running_days=0, training_days=5)) == {
        "strength_days": 3, "running_days": 2,
    }
    assert resolve_day_counts(_profile(strength_days=4, running_days=0, training_days=2)) == {
        "strength_days": 4, "running_days": 0,
    }
    assert resolve_day_counts(_profile(
        primary_goal="Running Endurance", strength_days=0, running_days=0, training_days=3,
    )) == {"strength_days": 0, "running_days": 3}
    assert resolve_day_counts(_profile(
        primary_goal="Hybrid Fitness", strength_days=0, running_days=0, training_days=5,
    )) == {"strength_days": 3, "running_days": 2}
    with pytest.raises(PlanCountError):
        resolve_day_counts(_profile(strength_days=4, running_days=4, training_days=4))
    with pytest.raises(PlanCountError, match="add up to 6 sessions"):
        resolve_day_counts(_profile(strength_days=3, running_days=3, training_days=4))


def test_gemini_model_defaults_to_flash_lite(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert resolve_gemini_model() == "gemini-3.5-flash-lite"
    assert resolve_gemini_model("gemini-3.5-flash") == "gemini-3.5-flash"
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash")
    assert resolve_gemini_model() == "gemini-3.5-flash"
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    assert resolve_gemini_model() == "gemini-3.5-flash-lite"
    with pytest.raises(ValueError, match="Choose Gemini 3.5 Flash-Lite or Gemini 3.5 Flash"):
        resolve_gemini_model("gemini-3.8-flash")


def test_gemini_response_schema_omits_nested_exercise_limit() -> None:
    schema = gemini_response_schema()
    exercises = schema["$defs"]["GeneratedDay"]["properties"]["exercises"]
    assert "maxItems" not in exercises
    assert schema["properties"]["days"]["maxItems"] == 7


def test_invalid_rep_range_is_rejected() -> None:
    payload = _week_payload()
    payload["days"][0]["exercises"][0]["target_reps_min"] = 12
    payload["days"][0]["exercises"][0]["target_reps_max"] = 8

    def fake(_prompt: str) -> str:
        return json.dumps(payload)

    with pytest.raises(ValueError, match="Minimum target reps cannot exceed maximum target reps"):
        generate_week(_profile(), generate=fake)


def test_wrong_day_counts_are_rejected() -> None:
    payload = _week_payload()
    payload["days"] = [_strength_day("Full body", "Monday"), _strength_day("Full body B", "Thursday")]

    def fake(_prompt: str) -> str:
        return json.dumps(payload)

    with pytest.raises(ValueError, match="Expected 2 strength and 2 running"):
        generate_week(_profile(), generate=fake)


def test_save_plan_creates_strength_routines_and_running_days(tmp_path) -> None:
    db_path = tmp_path / "plan.db"
    database.init_database(db_path)
    database.save_profile(_profile(), db_path)
    plan_id = plan_service.save_plan(GeneratedWeek.model_validate(_week_payload()), db_path)

    plan = plan_service.get_current_plan(db_path)
    routines = routine_service.list_routines(db_path)
    assert plan["id"] == plan_id
    assert plan["name"] == "Hybrid week"
    assert [day["session_kind"] for day in plan["days"]] == ["strength", "running", "strength", "running"]
    assert plan["days"][1]["run_type"] == "Easy"
    assert plan["days"][1]["distance_km"] == 5
    assert plan["days"][0]["exercises"][0]["exercise_name"] == "Goblet Squat"
    assert plan["days"][0]["exercises"][0]["starting_weight_kg"] is None
    assert {routine["name"] for routine in routines} == {"Lower strength", "Upper strength"}
    with database.get_connection(db_path) as connection:
        plan_ids = [row["plan_id"] for row in connection.execute("SELECT plan_id FROM workout_routines")]
    assert plan_ids == [plan_id, plan_id]


def test_replacing_a_plan_keeps_manual_routines(tmp_path) -> None:
    db_path = tmp_path / "replace-plan.db"
    database.init_database(db_path)
    database.save_profile(_profile(), db_path)
    manual_id = routine_service.save_routine(WorkoutRoutineInput(
        name="Manual push",
        exercises=[RoutineExerciseInput(
            exercise_name="Bench Press", sets=3, target_reps_min=5, target_reps_max=8,
        )],
    ), db_path=db_path)
    plan_service.save_plan(GeneratedWeek.model_validate(_week_payload()), db_path)

    replacement = _week_payload()
    replacement["name"] = "Replacement week"
    replacement["days"][0]["title"] = "Squat focus"
    replacement["days"][2]["title"] = "Press focus"
    plan_service.save_plan(GeneratedWeek.model_validate(replacement), db_path)

    names = {routine["name"] for routine in routine_service.list_routines(db_path)}
    current = plan_service.get_current_plan(db_path)
    assert routine_service.get_routine(manual_id, db_path)["name"] == "Manual push"
    assert "Squat focus" in names
    assert "Press focus" in names
    assert "Lower strength" not in names
    assert "Upper strength" not in names
    assert current["name"] == "Replacement week"
    with database.get_connection(db_path) as connection:
        manual_plan = connection.execute(
            "SELECT plan_id FROM workout_routines WHERE id = ?", (manual_id,)
        ).fetchone()["plan_id"]
    assert manual_plan is None


def test_strength_log_defaults_use_target_reps_and_zero_weight() -> None:
    routine = {
        "name": "Lower strength",
        "notes": "Keep the last set shy of failure",
        "exercises": [{
            "exercise_name": "Goblet Squat",
            "sets": 3,
            "target_reps_min": 8,
            "target_reps_max": 12,
            "starting_weight_kg": None,
            "notes": "Full depth",
        }],
    }
    defaults = strength_log_defaults(routine)
    exercise = defaults["exercises"][0]
    assert defaults["session_name"] == "Lower strength"
    assert exercise["reps"] == 8
    assert exercise["target_reps_max"] == 12
    assert exercise["weight_kg"] == 0.0

    routine["exercises"][0]["starting_weight_kg"] = 24
    weighted = strength_log_defaults(routine)["exercises"][0]
    assert weighted["weight_kg"] == 24.0


def test_running_log_defaults_use_planned_distance_and_duration() -> None:
    defaults = running_log_defaults({
        "run_type": "Easy",
        "distance_km": 5,
        "duration_minutes": 32,
        "notes": "Easy conversational pace",
    })
    assert defaults["run_type"] == "Easy"
    assert defaults["distance_km"] == 5
    assert defaults["duration_minutes"] == 32
    assert defaults["notes"] == "Easy conversational pace"
