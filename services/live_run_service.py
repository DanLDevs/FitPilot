from datetime import date, datetime
from pathlib import Path

from models.schemas import RunningWorkoutInput
from services import plan_service, running_service
from services.database import get_connection
from services.running_cue import run_session_cue
from services.timer_service import make_deadline, pause_remaining, resume_deadline


_ACTIVE_MESSAGE = "An active workout already exists. Resume or discard it first."


def get_active_run(db_path: str | Path | None = None) -> dict | None:
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM active_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def start_from_plan_day(
    position: int,
    workout_date: date | None = None,
    db_path: str | Path | None = None,
) -> int:
    plan = plan_service.get_current_plan(db_path)
    with get_connection(db_path) as connection:
        _raise_if_busy(connection)
        if plan is None:
            raise ValueError("Save a weekly plan with a running day first")
        day = next(
            (
                item for item in plan["days"]
                if item["position"] == position and item["session_kind"] == "running"
            ),
            None,
        )
        if day is None:
            raise ValueError("Planned run not found")
        if day["distance_km"] is None or day["duration_minutes"] is None:
            raise ValueError("That run is missing a distance or duration")
        chosen_date = workout_date or date.today()
        cursor = connection.execute(
            """INSERT INTO active_runs
            (workout_date, title, run_type, target_distance_km, target_duration_minutes,
            distance_km, duration_minutes, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                chosen_date.isoformat(), day["title"], day["run_type"],
                float(day["distance_km"]), float(day["duration_minutes"]),
                float(day["distance_km"]), float(day["duration_minutes"]),
                day.get("notes") or "",
            ),
        )
        return int(cursor.lastrowid)


def update_run(
    run_id: int,
    workout_date: date,
    distance_km: float,
    duration_minutes: float,
    distance_unit: str,
    rpe: int | None,
    notes: str,
    pain: bool,
    db_path: str | Path | None = None,
) -> None:
    if distance_unit not in {"km", "mi"}:
        raise ValueError("Distance unit must be km or mi")
    if not 0 < float(distance_km) <= 500:
        raise ValueError("Running distance must be greater than 0 and at most 500 km")
    if not 0 < float(duration_minutes) <= 3000:
        raise ValueError("Running duration must be greater than 0 and at most 3000 minutes")
    stored_rpe = None if rpe is None else int(rpe)
    if stored_rpe is not None and not 1 <= stored_rpe <= 10:
        raise ValueError("RPE must be between 1 and 10")
    with get_connection(db_path) as connection:
        _require_run(connection, run_id)
        connection.execute(
            """UPDATE active_runs SET workout_date = ?, distance_km = ?, duration_minutes = ?,
            distance_unit = ?, rpe = ?, notes = ?, pain = ? WHERE id = ?""",
            (
                workout_date.isoformat(), float(distance_km), float(duration_minutes),
                distance_unit, stored_rpe, notes, int(pain), run_id,
            ),
        )


def session_message(run: dict, db_path: str | Path | None = None) -> str:
    with get_connection(db_path) as connection:
        last_run = _latest_same_type(connection, run["run_type"])
    return run_session_cue(
        run["run_type"],
        float(run["target_distance_km"]),
        float(run["target_duration_minutes"]),
        last_run,
        run.get("distance_unit") or "km",
    )


def start_timer(run_id: int, now: datetime | None = None, db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        row = _require_run(connection, run_id)
        if row["duration_minutes"] is None:
            raise ValueError("Enter a duration before starting the clock")
        seconds = int(round(float(row["duration_minutes"]) * 60))
        connection.execute(
            """UPDATE active_runs SET timer_ends_at = ?, timer_paused_remaining_seconds = NULL
            WHERE id = ?""",
            (make_deadline(seconds, now), run_id),
        )


def pause_timer(run_id: int, now: datetime | None = None, db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        row = _require_run(connection, run_id)
        if row["timer_ends_at"] is None:
            return
        remaining = pause_remaining(row["timer_ends_at"], now)
        connection.execute(
            """UPDATE active_runs SET timer_ends_at = NULL, timer_paused_remaining_seconds = ?
            WHERE id = ?""",
            (remaining, run_id),
        )


def resume_timer(run_id: int, now: datetime | None = None, db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        row = _require_run(connection, run_id)
        remaining = row["timer_paused_remaining_seconds"]
        if remaining is None:
            return
        connection.execute(
            """UPDATE active_runs SET timer_ends_at = ?, timer_paused_remaining_seconds = NULL
            WHERE id = ?""",
            (resume_deadline(remaining, now), run_id),
        )


def reset_timer(run_id: int, db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        _require_run(connection, run_id)
        connection.execute(
            """UPDATE active_runs SET timer_ends_at = NULL, timer_paused_remaining_seconds = NULL
            WHERE id = ?""",
            (run_id,),
        )


def finish_run(run_id: int, db_path: str | Path | None = None) -> int:
    with get_connection(db_path) as connection:
        run = dict(_require_run(connection, run_id))
    if run["distance_km"] is None or run["duration_minutes"] is None:
        raise ValueError("Enter a distance and duration before finishing")
    workout = RunningWorkoutInput(
        workout_date=date.fromisoformat(run["workout_date"]),
        run_type=run["run_type"],
        distance_km=run["distance_km"],
        duration_minutes=run["duration_minutes"],
        rpe=run["rpe"],
        notes=run["notes"] or "",
        pain=bool(run["pain"]),
    )
    workout_id = running_service.add_workout(workout, db_path)
    with get_connection(db_path) as connection:
        connection.execute("DELETE FROM active_runs WHERE id = ?", (run_id,))
    return workout_id


def discard_run(run_id: int, db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        _require_run(connection, run_id)
        connection.execute("DELETE FROM active_runs WHERE id = ?", (run_id,))


def _raise_if_busy(connection) -> None:
    strength = connection.execute(
        "SELECT id FROM strength_workouts WHERE status = 'active' LIMIT 1"
    ).fetchone()
    if strength is not None:
        raise ValueError(_ACTIVE_MESSAGE)
    active = connection.execute("SELECT id FROM active_runs LIMIT 1").fetchone()
    if active is not None:
        raise ValueError(_ACTIVE_MESSAGE)


def _require_run(connection, run_id: int):
    row = connection.execute(
        "SELECT * FROM active_runs WHERE id = ?", (run_id,)
    ).fetchone()
    if row is None:
        raise ValueError("Active run not found")
    return row


def _latest_same_type(connection, run_type: str) -> dict | None:
    row = connection.execute(
        """SELECT distance_km, duration_minutes, run_type FROM running_workouts
        WHERE run_type = ? ORDER BY workout_date DESC, id DESC LIMIT 1""",
        (run_type,),
    ).fetchone()
    return dict(row) if row else None
