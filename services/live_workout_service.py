from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from models.schemas import LiveExerciseInput, LiveSetInput, LiveWorkoutInput
from services import strength_service
from services.database import get_connection
from services.progression_service import session_cue
from services.timer_service import (
    adjust_deadline,
    make_deadline,
    pause_remaining,
    remaining_seconds,
    resume_deadline,
)


def get_active_workout(db_path: str | Path | None = None) -> dict | None:
    with get_connection(db_path) as connection:
        workout = connection.execute(
            "SELECT * FROM strength_workouts WHERE status = 'active' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if workout is None:
            return None
        result = dict(workout)
        rows = connection.execute(
            """SELECT * FROM strength_sets WHERE workout_id = ?
            ORDER BY exercise_key, set_number, id""",
            (result["id"],),
        ).fetchall()
        exercises = {}
        for row in rows:
            item = dict(row)
            key = item["exercise_key"] or f"legacy:{item['exercise_name']}"
            if key not in exercises:
                exercises[key] = {
                    "exercise_key": key,
                    "exercise_name": item["exercise_name"],
                    "target_reps_min": item["target_reps_min"] or 8,
                    "target_reps_max": item["target_reps_max"] or 12,
                    "rest_seconds": item["rest_seconds"],
                    "notes": item["notes"],
                    "sets": [],
                }
            exercises[key]["sets"].append(item)
        result["exercises"] = list(exercises.values())
        return result


def start_workout(workout: LiveWorkoutInput, db_path: str | Path | None = None) -> int:
    with get_connection(db_path) as connection:
        existing = connection.execute(
            "SELECT id FROM strength_workouts WHERE status = 'active' LIMIT 1"
        ).fetchone()
        if existing:
            raise ValueError("An active workout already exists. Resume or discard it first.")
        active_run = connection.execute("SELECT id FROM active_runs LIMIT 1").fetchone()
        if active_run:
            raise ValueError("An active workout already exists. Resume or discard it first.")
        cursor = connection.execute(
            """INSERT INTO strength_workouts
            (workout_date, session_name, notes, status, default_rest_seconds, auto_start_rest)
            VALUES (?, ?, ?, 'active', ?, ?)""",
            (workout.workout_date.isoformat(), workout.session_name.strip(), workout.notes,
             workout.default_rest_seconds, int(workout.auto_start_rest)),
        )
        workout_id = int(cursor.lastrowid)
        for exercise in workout.exercises:
            _insert_exercise(connection, workout_id, exercise, workout.default_rest_seconds)
        return workout_id


def start_from_routine(
    routine_id: int,
    workout_date: date | None = None,
    db_path: str | Path | None = None,
) -> int:
    history = strength_service.list_sets(db_path)
    with get_connection(db_path) as connection:
        routine = connection.execute(
            "SELECT * FROM workout_routines WHERE id = ?", (routine_id,)
        ).fetchone()
        if routine is None:
            raise ValueError("Routine not found")
        rows = connection.execute(
            """SELECT * FROM routine_exercises WHERE routine_id = ? ORDER BY position""",
            (routine_id,),
        ).fetchall()
        exercises = []
        for row in rows:
            cue = session_cue(
                history,
                row["exercise_name"],
                row["target_reps_min"],
                row["target_reps_max"],
                starting_weight_kg=row["starting_weight_kg"],
            )
            exercises.append(LiveExerciseInput(
                exercise_name=row["exercise_name"],
                target_reps_min=row["target_reps_min"],
                target_reps_max=row["target_reps_max"],
                rest_seconds=row["rest_seconds"],
                notes=row["notes"],
                sets=[LiveSetInput(
                    reps=row["target_reps_min"],
                    weight_kg=cue["suggested_weight_kg"],
                ) for _ in range(row["sets"])],
            ))
        active = LiveWorkoutInput(
            workout_date=workout_date or date.today(),
            session_name=routine["name"],
            notes=routine["notes"],
            default_rest_seconds=routine["default_rest_seconds"],
            auto_start_rest=bool(routine["auto_start_rest"]),
            exercises=exercises,
        )
    return start_workout(active, db_path)


def add_exercise(
    workout_id: int,
    exercise: LiveExerciseInput,
    default_rest_seconds: int,
    db_path: str | Path | None = None,
) -> None:
    with get_connection(db_path) as connection:
        _require_active(connection, workout_id)
        _insert_exercise(connection, workout_id, exercise, default_rest_seconds)


def _insert_exercise(connection, workout_id: int, exercise: LiveExerciseInput, default_rest_seconds: int) -> None:
    exercise_key = exercise.exercise_key or uuid4().hex
    rest_seconds = exercise.rest_seconds if exercise.rest_seconds is not None else default_rest_seconds
    for set_number, performed_set in enumerate(exercise.sets, start=1):
        connection.execute(
            """INSERT INTO strength_sets
            (workout_id, exercise_name, exercise_key, set_number, reps, weight_kg, rpe,
            notes, pain, technique_concern, is_completed, target_reps_min, target_reps_max, rest_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (workout_id, exercise.exercise_name.strip(), exercise_key, set_number,
             performed_set.reps, performed_set.weight_kg, performed_set.rpe,
             performed_set.notes or exercise.notes, int(performed_set.pain),
             int(performed_set.technique_concern), int(performed_set.is_completed),
             exercise.target_reps_min, exercise.target_reps_max, rest_seconds),
        )


def _require_active(connection, workout_id: int) -> None:
    row = connection.execute(
        "SELECT status FROM strength_workouts WHERE id = ?", (workout_id,)
    ).fetchone()
    if row is None or row["status"] != "active":
        raise ValueError("Active workout not found")


def update_workout_details(
    workout_id: int,
    workout_date: date,
    session_name: str,
    notes: str,
    default_rest_seconds: int,
    auto_start_rest: bool,
    db_path: str | Path | None = None,
) -> None:
    with get_connection(db_path) as connection:
        _require_active(connection, workout_id)
        connection.execute(
            """UPDATE strength_workouts SET workout_date = ?, session_name = ?, notes = ?,
            default_rest_seconds = ?, auto_start_rest = ? WHERE id = ?""",
            (workout_date.isoformat(), session_name.strip(), notes,
             default_rest_seconds, int(auto_start_rest), workout_id),
        )


def update_set(
    workout_id: int,
    set_id: int,
    values: LiveSetInput,
    db_path: str | Path | None = None,
) -> None:
    with get_connection(db_path) as connection:
        _require_active(connection, workout_id)
        cursor = connection.execute(
            """UPDATE strength_sets SET reps = ?, weight_kg = ?, rpe = ?, notes = ?,
            pain = ?, technique_concern = ?
            WHERE id = ? AND workout_id = ? AND is_completed = 0""",
            (values.reps, values.weight_kg, values.rpe, values.notes,
             int(values.pain), int(values.technique_concern), set_id, workout_id),
        )
        if cursor.rowcount == 0:
            raise ValueError("Set not found or already completed")


def add_set(workout_id: int, exercise_key: str, db_path: str | Path | None = None) -> int:
    with get_connection(db_path) as connection:
        _require_active(connection, workout_id)
        last = connection.execute(
            """SELECT * FROM strength_sets WHERE workout_id = ? AND exercise_key = ?
            ORDER BY set_number DESC LIMIT 1""",
            (workout_id, exercise_key),
        ).fetchone()
        if last is None:
            raise ValueError("Exercise not found")
        cursor = connection.execute(
            """INSERT INTO strength_sets
            (workout_id, exercise_name, exercise_key, set_number, reps, weight_kg, rpe,
            notes, pain, technique_concern, is_completed, target_reps_min, target_reps_max, rest_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?, '', 0, 0, 0, ?, ?, ?)""",
            (workout_id, last["exercise_name"], exercise_key, last["set_number"] + 1,
             last["reps"], last["weight_kg"], last["rpe"], last["target_reps_min"],
             last["target_reps_max"], last["rest_seconds"]),
        )
        return int(cursor.lastrowid)


def remove_last_set(workout_id: int, exercise_key: str, db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        _require_active(connection, workout_id)
        last = connection.execute(
            """SELECT id, is_completed FROM strength_sets WHERE workout_id = ? AND exercise_key = ?
            ORDER BY set_number DESC LIMIT 1""",
            (workout_id, exercise_key),
        ).fetchone()
        if last is None or last["is_completed"]:
            raise ValueError("Cannot remove a completed set")
        connection.execute("DELETE FROM strength_sets WHERE id = ?", (last["id"],))


def remove_exercise(workout_id: int, exercise_key: str, db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        _require_active(connection, workout_id)
        count = connection.execute(
            "SELECT COUNT(*) FROM strength_sets WHERE workout_id = ? AND exercise_key = ? AND is_completed = 1",
            (workout_id, exercise_key),
        ).fetchone()[0]
        if count:
            raise ValueError("Cannot remove an exercise that already has completed sets")
        connection.execute(
            "DELETE FROM strength_sets WHERE workout_id = ? AND exercise_key = ?",
            (workout_id, exercise_key),
        )


def complete_set(
    workout_id: int,
    set_id: int,
    now: datetime | None = None,
    db_path: str | Path | None = None,
) -> None:
    with get_connection(db_path) as connection:
        _require_active(connection, workout_id)
        set_row = connection.execute(
            "SELECT * FROM strength_sets WHERE id = ? AND workout_id = ?",
            (set_id, workout_id),
        ).fetchone()
        if set_row is None:
            raise ValueError("Set not found")
        if set_row["is_completed"]:
            return
        connection.execute("UPDATE strength_sets SET is_completed = 1 WHERE id = ?", (set_id,))
        workout = connection.execute(
            "SELECT auto_start_rest, default_rest_seconds FROM strength_workouts WHERE id = ?",
            (workout_id,),
        ).fetchone()
        if workout["auto_start_rest"]:
            seconds = (
                set_row["rest_seconds"]
                if set_row["rest_seconds"] is not None
                else workout["default_rest_seconds"]
            )
            connection.execute(
                """UPDATE strength_workouts SET rest_ends_at = ?,
                rest_paused_remaining_seconds = NULL, rest_notification_sent = 0 WHERE id = ?""",
                (make_deadline(seconds, now), workout_id),
            )


def start_rest(workout_id: int, seconds: int, now: datetime | None = None, db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        _require_active(connection, workout_id)
        connection.execute(
            """UPDATE strength_workouts SET rest_ends_at = ?, rest_paused_remaining_seconds = NULL,
            rest_notification_sent = 0 WHERE id = ?""",
            (make_deadline(seconds, now), workout_id),
        )


def pause_rest(workout_id: int, now: datetime | None = None, db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        _require_active(connection, workout_id)
        row = connection.execute(
            "SELECT rest_ends_at FROM strength_workouts WHERE id = ?", (workout_id,)
        ).fetchone()
        if row["rest_ends_at"] is None:
            return
        seconds = pause_remaining(row["rest_ends_at"], now)
        connection.execute(
            "UPDATE strength_workouts SET rest_ends_at = NULL, rest_paused_remaining_seconds = ? WHERE id = ?",
            (seconds, workout_id),
        )


def resume_rest(workout_id: int, now: datetime | None = None, db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        _require_active(connection, workout_id)
        row = connection.execute(
            "SELECT rest_paused_remaining_seconds FROM strength_workouts WHERE id = ?", (workout_id,)
        ).fetchone()
        remaining = row["rest_paused_remaining_seconds"]
        if remaining is None:
            return
        connection.execute(
            "UPDATE strength_workouts SET rest_ends_at = ?, rest_paused_remaining_seconds = NULL WHERE id = ?",
            (resume_deadline(remaining, now), workout_id),
        )


def adjust_rest(workout_id: int, adjustment_seconds: int, now: datetime | None = None, db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        _require_active(connection, workout_id)
        row = connection.execute(
            "SELECT rest_ends_at, rest_paused_remaining_seconds FROM strength_workouts WHERE id = ?",
            (workout_id,),
        ).fetchone()
        if row["rest_paused_remaining_seconds"] is not None:
            new_remaining = max(0, row["rest_paused_remaining_seconds"] + adjustment_seconds)
            connection.execute(
                "UPDATE strength_workouts SET rest_paused_remaining_seconds = ? WHERE id = ?",
                (new_remaining, workout_id),
            )
        elif row["rest_ends_at"] is not None:
            connection.execute(
                "UPDATE strength_workouts SET rest_ends_at = ? WHERE id = ?",
                (adjust_deadline(row["rest_ends_at"], adjustment_seconds, now), workout_id),
            )


def claim_rest_notification(workout_id: int, now: datetime | None = None, db_path: str | Path | None = None) -> bool:
    instant = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """UPDATE strength_workouts SET rest_notification_sent = 1
            WHERE id = ? AND status = 'active' AND rest_ends_at IS NOT NULL
            AND rest_paused_remaining_seconds IS NULL AND rest_ends_at <= ?
            AND rest_notification_sent = 0""",
            (workout_id, instant),
        )
        return cursor.rowcount == 1


def finish_workout(workout_id: int, db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        _require_active(connection, workout_id)
        connection.execute(
            "DELETE FROM strength_sets WHERE workout_id = ? AND is_completed = 0",
            (workout_id,),
        )
        completed = connection.execute(
            "SELECT COUNT(*) FROM strength_sets WHERE workout_id = ? AND is_completed = 1",
            (workout_id,),
        ).fetchone()[0]
        if completed == 0:
            connection.execute(
                """UPDATE strength_workouts SET status = 'discarded', rest_ends_at = NULL,
                rest_paused_remaining_seconds = NULL WHERE id = ?""",
                (workout_id,),
            )
            return
        connection.execute(
            """UPDATE strength_workouts SET status = 'completed', completed_at = CURRENT_TIMESTAMP,
            rest_ends_at = NULL, rest_paused_remaining_seconds = NULL WHERE id = ?""",
            (workout_id,),
        )


def discard_workout(workout_id: int, db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        _require_active(connection, workout_id)
        connection.execute(
            """UPDATE strength_workouts SET status = 'discarded', rest_ends_at = NULL,
            rest_paused_remaining_seconds = NULL WHERE id = ?""",
            (workout_id,),
        )


def update_exercise_rest(
    workout_id: int,
    exercise_key: str,
    rest_seconds: int,
    db_path: str | Path | None = None,
) -> None:
    with get_connection(db_path) as connection:
        _require_active(connection, workout_id)
        connection.execute(
            "UPDATE strength_sets SET rest_seconds = ? WHERE workout_id = ? AND exercise_key = ?",
            (rest_seconds, workout_id, exercise_key),
        )


def update_exercise_details(
    workout_id: int,
    exercise_key: str,
    exercise_name: str,
    target_reps_min: int,
    target_reps_max: int,
    rest_seconds: int,
    db_path: str | Path | None = None,
) -> None:
    if target_reps_min > target_reps_max:
        raise ValueError("Minimum target reps cannot exceed maximum target reps")
    with get_connection(db_path) as connection:
        _require_active(connection, workout_id)
        cursor = connection.execute(
            """UPDATE strength_sets SET exercise_name = ?, target_reps_min = ?,
            target_reps_max = ?, rest_seconds = ? WHERE workout_id = ? AND exercise_key = ?""",
            (exercise_name.strip(), target_reps_min, target_reps_max, rest_seconds,
             workout_id, exercise_key),
        )
        if cursor.rowcount == 0:
            raise ValueError("Exercise not found")