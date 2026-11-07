from pathlib import Path

from models.schemas import WorkoutRoutineInput
from services.database import get_connection


def list_routines(db_path: str | Path | None = None) -> list[dict]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            "SELECT id, name, notes, default_rest_seconds, auto_start_rest FROM workout_routines ORDER BY name COLLATE NOCASE"
        ).fetchall()
        routines = []
        for row in rows:
            routine = dict(row)
            routine["exercises"] = [dict(exercise) for exercise in connection.execute(
                """SELECT exercise_name, sets, target_reps_min, target_reps_max,
                starting_weight_kg, rest_seconds, notes FROM routine_exercises
                WHERE routine_id = ? ORDER BY position""",
                (routine["id"],),
            ).fetchall()]
            routines.append(routine)
        return routines


def get_routine(routine_id: int, db_path: str | Path | None = None) -> dict | None:
    return next((routine for routine in list_routines(db_path) if routine["id"] == routine_id), None)


def save_routine(
    routine: WorkoutRoutineInput,
    routine_id: int | None = None,
    db_path: str | Path | None = None,
) -> int:
    with get_connection(db_path) as connection:
        if routine_id is None:
            cursor = connection.execute(
                """INSERT INTO workout_routines
                (name, notes, default_rest_seconds, auto_start_rest)
                VALUES (?, ?, ?, ?)""",
                (routine.name.strip(), routine.notes, routine.default_rest_seconds,
                 int(routine.auto_start_rest)),
            )
            routine_id = int(cursor.lastrowid)
        else:
            connection.execute(
                """UPDATE workout_routines SET name = ?, notes = ?, default_rest_seconds = ?,
                auto_start_rest = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (routine.name.strip(), routine.notes, routine.default_rest_seconds,
                 int(routine.auto_start_rest), routine_id),
            )
            if connection.execute("SELECT changes()").fetchone()[0] == 0:
                raise ValueError("Routine not found")
            connection.execute("DELETE FROM routine_exercises WHERE routine_id = ?", (routine_id,))

        connection.executemany(
            """INSERT INTO routine_exercises
            (routine_id, position, exercise_name, sets, target_reps_min, target_reps_max,
            starting_weight_kg, rest_seconds, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (routine_id, position, exercise.exercise_name.strip(), exercise.sets,
                 exercise.target_reps_min, exercise.target_reps_max,
                 exercise.starting_weight_kg, exercise.rest_seconds, exercise.notes)
                for position, exercise in enumerate(routine.exercises)
            ],
        )
        return routine_id


def delete_routine(routine_id: int, db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        connection.execute("DELETE FROM workout_routines WHERE id = ?", (routine_id,))