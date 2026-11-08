from pathlib import Path

from models.schemas import (
    StrengthExerciseLogInput,
    StrengthSetInput,
    StrengthWorkoutInput,
    StrengthWorkoutLogInput,
)
from services.database import get_connection


def _insert_workout(connection, workout: StrengthWorkoutInput | StrengthWorkoutLogInput) -> int:
    cursor = connection.execute(
        "INSERT INTO strength_workouts (workout_date, session_name, notes) VALUES (?, ?, ?)",
        (workout.workout_date.isoformat(), workout.session_name, workout.notes),
    )
    workout_id = int(cursor.lastrowid)
    for exercise in workout.exercises:
        if isinstance(exercise, StrengthExerciseLogInput):
            for set_number, performed_set in enumerate(exercise.sets, start=1):
                connection.execute(
                    """INSERT INTO strength_sets
                    (workout_id, exercise_name, set_number, reps, weight_kg, rpe, notes,
                    pain, technique_concern, target_reps_min, target_reps_max)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (workout_id, exercise.exercise_name.strip(), set_number, performed_set.reps,
                     performed_set.weight_kg, performed_set.rpe, performed_set.notes,
                     int(performed_set.pain), int(performed_set.technique_concern),
                     exercise.target_reps_min, exercise.target_reps_max),
                )
        else:
            _insert_legacy_exercise(connection, workout_id, exercise)
    return workout_id


def _insert_legacy_exercise(connection, workout_id: int, exercise: StrengthSetInput) -> None:
    for set_number in range(1, exercise.sets + 1):
        connection.execute(
            """INSERT INTO strength_sets
            (workout_id, exercise_name, set_number, reps, weight_kg, rpe, notes,
            pain, technique_concern, target_reps_min, target_reps_max)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (workout_id, exercise.exercise_name.strip(), set_number, exercise.reps,
             exercise.weight_kg, exercise.rpe, exercise.notes, int(exercise.pain),
             int(exercise.technique_concern), exercise.target_reps_min,
             exercise.target_reps_max),
        )


def add_workout(workout: StrengthWorkoutInput | StrengthWorkoutLogInput, db_path: str | Path | None = None) -> int:
    with get_connection(db_path) as connection:
        return _insert_workout(connection, workout)


def list_workouts(db_path: str | Path | None = None, limit: int = 100) -> list[dict]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """SELECT w.id, w.workout_date, w.session_name, w.notes,
            COUNT(s.id) AS set_count, COALESCE(SUM(s.reps * s.weight_kg), 0) AS volume_kg
            FROM strength_workouts w LEFT JOIN strength_sets s
            ON s.workout_id = w.id AND s.is_completed = 1
            WHERE w.status = 'completed'
            GROUP BY w.id ORDER BY w.workout_date DESC, w.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def list_sets(db_path: str | Path | None = None) -> list[dict]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """SELECT w.id AS workout_id, w.workout_date, w.session_name,
            s.exercise_name, s.exercise_key, s.set_number, s.reps, s.weight_kg,
            s.rpe, s.notes, s.pain, s.technique_concern, s.is_completed,
            s.target_reps_min, s.target_reps_max
            FROM strength_sets s JOIN strength_workouts w ON w.id = s.workout_id
            WHERE w.status = 'completed' AND s.is_completed = 1
            ORDER BY w.workout_date, s.exercise_name, s.set_number"""
        ).fetchall()
        return [dict(row) for row in rows]


def get_workout(workout_id: int, db_path: str | Path | None = None) -> dict | None:
    with get_connection(db_path) as connection:
        workout = connection.execute(
            "SELECT * FROM strength_workouts WHERE id = ? AND status = 'completed'", (workout_id,)
        ).fetchone()
        if workout is None:
            return None
        result = dict(workout)
        result["exercises"] = [dict(row) for row in connection.execute(
            """SELECT id, exercise_name, exercise_key, set_number, reps, weight_kg, rpe,
            pain, notes, technique_concern, target_reps_min, target_reps_max, rest_seconds
            FROM strength_sets
            WHERE workout_id = ? AND is_completed = 1
            ORDER BY id""",
            (workout_id,),
        ).fetchall()]
        return result


def update_workout(
    workout_id: int,
    workout_date,
    session_name: str,
    notes: str,
    sets: list[dict],
    db_path: str | Path | None = None,
) -> None:
    with get_connection(db_path) as connection:
        updated = connection.execute(
            "UPDATE strength_workouts SET workout_date = ?, session_name = ?, notes = ? WHERE id = ? AND status = 'completed'",
            (workout_date.isoformat(), session_name, notes, workout_id),
        )
        if updated.rowcount == 0:
            raise ValueError("Completed workout not found")
        for item in sets:
            changed = connection.execute(
                """UPDATE strength_sets SET exercise_name = ?, reps = ?, weight_kg = ?, rpe = ?
                WHERE id = ? AND workout_id = ? AND is_completed = 1""",
                (item["exercise_name"].strip(), int(item["reps"]), float(item["weight_kg"]),
                 item["rpe"], item["id"], workout_id),
            )
            if changed.rowcount != 1:
                raise ValueError("Completed set not found")


def delete_workout(workout_id: int, db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        connection.execute("DELETE FROM strength_workouts WHERE id = ? AND status = 'completed'", (workout_id,))