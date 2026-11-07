from pathlib import Path

from models.schemas import RunningWorkoutInput
from services.database import get_connection


def add_workout(workout: RunningWorkoutInput, db_path: str | Path | None = None) -> int:
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """INSERT INTO running_workouts
            (workout_date, run_type, distance_km, duration_minutes, rpe, notes, pain)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (workout.workout_date.isoformat(), workout.run_type, workout.distance_km,
             workout.duration_minutes, workout.rpe, workout.notes, int(workout.pain)),
        )
        return int(cursor.lastrowid)


def list_workouts(db_path: str | Path | None = None, limit: int = 100) -> list[dict]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM running_workouts ORDER BY workout_date DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def update_workout(workout_id: int, workout: RunningWorkoutInput, db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        connection.execute(
            """UPDATE running_workouts SET workout_date = ?, run_type = ?, distance_km = ?,
            duration_minutes = ?, rpe = ?, notes = ?, pain = ? WHERE id = ?""",
            (workout.workout_date.isoformat(), workout.run_type, workout.distance_km,
             workout.duration_minutes, workout.rpe, workout.notes, int(workout.pain), workout_id),
        )


def delete_workout(workout_id: int, db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        connection.execute("DELETE FROM running_workouts WHERE id = ?", (workout_id,))