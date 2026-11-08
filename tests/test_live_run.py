from datetime import date, datetime, timedelta, timezone

import pytest

from models.schemas import GeneratedWeek, LiveWorkoutInput
from services import analytics_service, database, live_run_service, live_workout_service, plan_service, running_service
from services.running_cue import run_session_cue
from services.timer_service import remaining_seconds


_BANNED = ("faster", "farther", "further", "increase", "speed up", "longer than", "more than")


def _profile() -> dict:
    return {
        "name": "Runner", "primary_goal": "Hybrid Fitness", "experience_level": "Intermediate",
        "training_days": 4, "strength_days": 2, "running_days": 2,
        "session_minutes": 45, "equipment": "treadmill", "fitness_goals": "",
        "existing_schedule": "",
    }


def _running_day(title: str, run_type: str, distance: float, duration: float, weekday: str) -> dict:
    return {
        "weekday": weekday,
        "session_kind": "running",
        "title": title,
        "notes": "Keep it conversational",
        "run_type": run_type,
        "distance_km": distance,
        "duration_minutes": duration,
        "exercises": [],
    }


def _prepare(db_path, days: list[dict] | None = None) -> None:
    database.init_database(db_path)
    database.save_profile(_profile(), db_path)
    plan_service.save_plan(GeneratedWeek.model_validate({
        "name": "Run week",
        "summary": "",
        "days": days or [
            _running_day("Easy run", "Easy", 5, 30, "Tuesday"),
            _running_day("Long day", "Long Run", 16, 80, "Saturday"),
        ],
    }), db_path)


def test_run_cues_name_the_goal_without_asking_for_more() -> None:
    last_easy = {"distance_km": 5.1, "duration_minutes": 31 + 20 / 60}
    easy = run_session_cue("Easy", 5, 30, last_easy)
    assert easy == (
        "Aim for 5.0 km in about 30:00 (about 6:00/km). "
        "Cover the distance and keep this easy. The time is a pace ceiling. "
        "Last easy run was 5.1 km in 31:20."
    )
    assert run_session_cue("Recovery", 5, 30) == (
        "Aim for 5.0 km in about 30:00 (about 6:00/km). "
        "Cover the distance and keep this easy. The time is a pace ceiling."
    )
    assert run_session_cue("Long Run", 16, 80) == (
        "Aim for 16.0 km in about 80:00 (about 5:00/km). The distance is the goal."
    )
    tempo = (
        "Aim for 5.0 km in about 25:00 (about 5:00/km). "
        "Hold the effort for the planned time. The distance is the expected result of that pace."
    )
    assert run_session_cue("Tempo", 5, 25) == tempo
    assert run_session_cue("Interval", 5, 25) == tempo
    assert run_session_cue("Other", 5, 30) == "Aim for 5.0 km in about 30:00 (about 6:00/km)."
    assert "Last" not in run_session_cue("Easy", 5, 30)
    miles = run_session_cue("Easy", 5, 30, unit="mi")
    assert miles.startswith("Aim for 3.1 mi in about 30:00 (about 9:39/mi).")

    farther = run_session_cue("Easy", 5, 30, {"distance_km": 10, "duration_minutes": 50})
    messages = [
        easy, miles, farther,
        run_session_cue("Recovery", 4, 28, {"distance_km": 3, "duration_minutes": 20}),
        run_session_cue("Long Run", 16, 80, {"distance_km": 14, "duration_minutes": 75}),
        run_session_cue("Tempo", 5, 25, {"distance_km": 5.4, "duration_minutes": 24}),
        run_session_cue("Interval", 5, 25, {"distance_km": 4, "duration_minutes": 22}),
        run_session_cue("Other", 5, 30, {"distance_km": 6, "duration_minutes": 32}),
    ]
    for message in messages:
        lowered = message.lower()
        for banned in _BANNED:
            assert banned not in lowered


def test_start_from_plan_day_prefills_the_selected_run(tmp_path) -> None:
    db_path = tmp_path / "start-run.db"
    _prepare(db_path)
    run_id = live_run_service.start_from_plan_day(1, date(2026, 11, 8), db_path)
    run = live_run_service.get_active_run(db_path)
    assert run["id"] == run_id
    assert run["title"] == "Long day"
    assert run["run_type"] == "Long Run"
    assert run["target_distance_km"] == 16
    assert run["target_duration_minutes"] == 80
    assert run["distance_km"] == 16
    assert run["duration_minutes"] == 80
    assert run["notes"] == "Keep it conversational"
    assert "The distance is the goal." in live_run_service.session_message(run, db_path)
    assert "Last" not in live_run_service.session_message(run, db_path)


def test_same_type_history_is_reported_and_edits_do_not_change_the_target(tmp_path) -> None:
    db_path = tmp_path / "history-run.db"
    _prepare(db_path)
    running_service.add_workout(
        _completed("Easy", 5.1, 31 + 20 / 60, date(2026, 11, 1)), db_path,
    )
    running_service.add_workout(
        _completed("Tempo", 6, 28, date(2026, 11, 2)), db_path,
    )
    live_run_service.start_from_plan_day(0, date(2026, 11, 8), db_path)
    run = live_run_service.get_active_run(db_path)
    message = live_run_service.session_message(run, db_path)
    assert "Last easy run was 5.1 km in 31:20." in message
    assert "Tempo" not in message
    assert "faster" not in message.lower()

    live_run_service.update_run(
        run["id"], date(2026, 11, 8), 6, 33, "km", 4, "felt smooth", False, db_path,
    )
    edited = live_run_service.get_active_run(db_path)
    assert "5.0 km" in live_run_service.session_message(edited, db_path)
    assert "6.0 km" not in live_run_service.session_message(edited, db_path)
    assert edited["target_distance_km"] == 5


def test_finish_saves_one_run_and_discard_saves_none(tmp_path) -> None:
    db_path = tmp_path / "finish-run.db"
    _prepare(db_path)
    run_id = live_run_service.start_from_plan_day(0, date.today(), db_path)
    live_run_service.update_run(
        run_id, date.today(), 5.4, 32, "km", 4, "easy", False, db_path,
    )
    saved_id = live_run_service.finish_run(run_id, db_path)
    assert live_run_service.get_active_run(db_path) is None
    saved = running_service.list_workouts(db_path)
    assert len(saved) == 1
    assert saved[0]["id"] == saved_id
    assert saved[0]["run_type"] == "Easy"
    assert saved[0]["distance_km"] == 5.4
    assert saved[0]["duration_minutes"] == 32
    dashboard = analytics_service.dashboard_data(db_path)
    assert [row["id"] for row in dashboard["running"]] == [saved_id]
    assert sum(week["value"] for week in dashboard["running_distance_weeks"]) == pytest.approx(5.4)

    discarded = live_run_service.start_from_plan_day(0, date.today(), db_path)
    live_run_service.discard_run(discarded, db_path)
    assert live_run_service.get_active_run(db_path) is None
    assert [row["id"] for row in running_service.list_workouts(db_path)] == [saved_id]


def test_run_clock_pauses_and_resets(tmp_path) -> None:
    db_path = tmp_path / "clock.db"
    _prepare(db_path)
    run_id = live_run_service.start_from_plan_day(0, date(2026, 11, 8), db_path)
    live_run_service.update_run(
        run_id, date(2026, 11, 8), 5, 20, "km", None, "", False, db_path,
    )
    now = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    live_run_service.start_timer(run_id, now, db_path)
    started = live_run_service.get_active_run(db_path)
    assert remaining_seconds(started["timer_ends_at"], now) == 20 * 60
    live_run_service.pause_timer(run_id, now + timedelta(seconds=15), db_path)
    paused = live_run_service.get_active_run(db_path)
    assert paused["timer_ends_at"] is None
    assert paused["timer_paused_remaining_seconds"] == 20 * 60 - 15
    live_run_service.resume_timer(run_id, now + timedelta(minutes=1), db_path)
    resumed = live_run_service.get_active_run(db_path)
    assert remaining_seconds(resumed["timer_ends_at"], now + timedelta(minutes=1)) == 20 * 60 - 15
    live_run_service.reset_timer(run_id, db_path)
    reset = live_run_service.get_active_run(db_path)
    assert reset["timer_ends_at"] is None
    assert reset["timer_paused_remaining_seconds"] is None


def test_strength_and_run_sessions_block_each_other(tmp_path) -> None:
    db_path = tmp_path / "busy.db"
    _prepare(db_path)
    live_workout_service.start_workout(LiveWorkoutInput(
        workout_date=date(2026, 11, 8), session_name="Lift",
    ), db_path)
    with pytest.raises(ValueError, match="already exists"):
        live_run_service.start_from_plan_day(0, date(2026, 11, 8), db_path)
    active = live_workout_service.get_active_workout(db_path)
    live_workout_service.discard_workout(active["id"], db_path)

    live_run_service.start_from_plan_day(0, date(2026, 11, 8), db_path)
    with pytest.raises(ValueError, match="already exists"):
        live_workout_service.start_workout(LiveWorkoutInput(
            workout_date=date(2026, 11, 8), session_name="Lift",
        ), db_path)
    with pytest.raises(ValueError, match="already exists"):
        live_run_service.start_from_plan_day(1, date(2026, 11, 8), db_path)
    assert live_workout_service.get_active_workout(db_path) is None
    assert live_run_service.get_active_run(db_path)["run_type"] == "Easy"


def test_version_four_database_gains_active_runs(tmp_path) -> None:
    db_path = tmp_path / "upgrade.db"
    database.init_database(db_path)
    with database.get_connection(db_path) as connection:
        connection.execute("DROP TABLE active_runs")
        connection.execute("PRAGMA user_version = 4")
    database.init_database(db_path)
    with database.get_connection(db_path) as connection:
        connection.execute("SELECT id FROM active_runs")
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6


def _completed(run_type: str, distance_km: float, duration_minutes: float, workout_date: date):
    from models.schemas import RunningWorkoutInput
    return RunningWorkoutInput(
        workout_date=workout_date, run_type=run_type,
        distance_km=distance_km, duration_minutes=duration_minutes,
    )
