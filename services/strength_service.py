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
            FROM strength_workouts w LEFT JOIN strength_sets s ON s.workout_id = w.id
            GROUP BY w.id ORDER BY w.workout_date DESC, w.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def list_sets(db_path: str | Path | None = None) -> list[dict]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """SELECT w.id AS workout_id, w.workout_date, w.session_name,
            s.exercise_name, s.set_number, s.reps, s.weight_kg, s.rpe, s.notes,
            s.pain, s.technique_concern, s.target_reps_min, s.target_reps_max
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
        exercises = [dict(row) for row in connection.execute(
            """SELECT exercise_name, COUNT(*) AS sets, AVG(reps) AS reps,
            AVG(weight_kg) AS weight_kg, AVG(rpe) AS rpe, MAX(pain) AS pain,
            MAX(technique_concern) AS technique_concern,
            MAX(target_reps_min) AS target_reps_min, MAX(target_reps_max) AS target_reps_max,
            GROUP_CONCAT(DISTINCT notes) AS notes
            FROM strength_sets WHERE workout_id = ? GROUP BY exercise_name ORDER BY MIN(id)""",
            (workout_id,),
        ).fetchall()]
        for exercise in exercises:
            exercise["working_sets"] = [dict(row) for row in connection.execute(
                """SELECT id, set_number, reps, weight_kg, rpe, pain, technique_concern,
                notes, target_reps_min, target_reps_max FROM strength_sets
                WHERE workout_id = ? AND exercise_name = ? ORDER BY set_number""",
                (workout_id, exercise["exercise_name"]),
            ).fetchall()]
        result["exercises"] = exercises
        return result


def update_workout(workout_id: int, workout: StrengthWorkoutInput | StrengthWorkoutLogInput, db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        connection.execute(
            "UPDATE strength_workouts SET workout_date = ?, session_name = ?, notes = ? WHERE id = ?",
            (workout.workout_date.isoformat(), workout.session_name, workout.notes, workout_id),
        )
        connection.execute("DELETE FROM strength_sets WHERE workout_id = ?", (workout_id,))
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


def delete_workout(workout_id: int, db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        connection.execute("DELETE FROM strength_workouts WHERE id = ?", (workout_id,))