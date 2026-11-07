from pathlib import Path

from models.schemas import StrengthWorkoutInput
from services.database import get_connection


def add_workout(workout: StrengthWorkoutInput, db_path: str | Path | None = None) -> int:
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO strength_workouts (workout_date, session_name, notes) VALUES (?, ?, ?)",
            (workout.workout_date.isoformat(), workout.session_name, workout.notes),
        )
        workout_id = cursor.lastrowid
        for exercise in workout.exercises:
            for set_number in range(1, exercise.sets + 1):
                connection.execute(
                    """INSERT INTO strength_sets
                    (workout_id, exercise_name, set_number, reps, weight_kg, rpe, notes, pain)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (workout_id, exercise.exercise_name.strip(), set_number, exercise.reps,
                     exercise.weight_kg, exercise.rpe, exercise.notes, int(exercise.pain)),
                )
        return int(workout_id)


def list_workouts(db_path: str | Path | None = None, limit: int = 100) -> list[dict]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """SELECT w.id, w.workout_date, w.session_name, w.notes,
            COUNT(s.id) AS set_count, COALESCE(SUM(s.reps * s.weight_kg), 0) AS volume_kg
            FROM strength_workouts w LEFT JOIN strength_sets s ON s.workout_id = w.id
            GROUP BY w.id ORDER BY w.workout_date DESC, w.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def list_sets(db_path: str | Path | None = None) -> list[dict]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """SELECT w.workout_date, w.session_name, s.exercise_name, s.set_number,
            s.reps, s.weight_kg, s.rpe, s.notes, s.pain
            FROM strength_sets s JOIN strength_workouts w ON w.id = s.workout_id
            ORDER BY w.workout_date, s.exercise_name, s.set_number"""
        ).fetchall()
        return [dict(row) for row in rows]


def get_workout(workout_id: int, db_path: str | Path | None = None) -> dict | None:
    with get_connection(db_path) as connection:
        workout = connection.execute(
            "SELECT * FROM strength_workouts WHERE id = ?", (workout_id,)
        ).fetchone()
        if workout is None:
            return None
        result = dict(workout)
        result["exercises"] = [dict(row) for row in connection.execute(
            """SELECT exercise_name, COUNT(*) AS sets, AVG(reps) AS reps,
            AVG(weight_kg) AS weight_kg, AVG(rpe) AS rpe,
            MAX(pain) AS pain, GROUP_CONCAT(DISTINCT notes) AS notes
            FROM strength_sets WHERE workout_id = ? GROUP BY exercise_name ORDER BY MIN(id)""",
            (workout_id,),
        ).fetchall()]
        return result


def update_workout(workout_id: int, workout: StrengthWorkoutInput, db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        connection.execute(
            "UPDATE strength_workouts SET workout_date = ?, session_name = ?, notes = ? WHERE id = ?",
            (workout.workout_date.isoformat(), workout.session_name, workout.notes, workout_id),
        )
        connection.execute("DELETE FROM strength_sets WHERE workout_id = ?", (workout_id,))
        for exercise in workout.exercises:
            for set_number in range(1, exercise.sets + 1):
                connection.execute(
                    """INSERT INTO strength_sets
                    (workout_id, exercise_name, set_number, reps, weight_kg, rpe, notes, pain)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (workout_id, exercise.exercise_name.strip(), set_number, exercise.reps,
                     exercise.weight_kg, exercise.rpe, exercise.notes, int(exercise.pain)),
                )


def delete_workout(workout_id: int, db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        connection.execute("DELETE FROM strength_workouts WHERE id = ?", (workout_id,))