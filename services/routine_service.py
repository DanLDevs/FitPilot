from pathlib import Path

from models.schemas import WorkoutRoutineInput
from services.database import get_connection


def list_routines(db_path: str | Path | None = None) -> list[dict]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            "SELECT id, name, notes, created_at, updated_at FROM workout_routines ORDER BY name COLLATE NOCASE"
        ).fetchall()
        routines = []
        for row in rows:
            routine = dict(row)
            routine["exercises"] = [dict(exercise) for exercise in connection.execute(
                """SELECT exercise_name, sets, target_reps_min, target_reps_max,
                starting_weight_kg, notes FROM routine_exercises
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
                "INSERT INTO workout_routines (name, notes) VALUES (?, ?)",
                (routine.name.strip(), routine.notes),
            )
            routine_id = int(cursor.lastrowid)
        else:
            connection.execute(
                "UPDATE workout_routines SET name = ?, notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (routine.name.strip(), routine.notes, routine_id),
            )
            if connection.execute("SELECT changes()").fetchone()[0] == 0:
                raise ValueError("Routine not found")
            connection.execute("DELETE FROM routine_exercises WHERE routine_id = ?", (routine_id,))

        connection.executemany(
            """INSERT INTO routine_exercises
            (routine_id, position, exercise_name, sets, target_reps_min, target_reps_max, starting_weight_kg, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (routine_id, position, exercise.exercise_name.strip(), exercise.sets,
                 exercise.target_reps_min, exercise.target_reps_max,
                 exercise.starting_weight_kg, exercise.notes)
                for position, exercise in enumerate(routine.exercises)
            ],
        )
        return routine_id


def duplicate_routine(routine_id: int, db_path: str | Path | None = None) -> int:
    routine = get_routine(routine_id, db_path)
    if routine is None:
        raise ValueError("Routine not found")
    duplicate = WorkoutRoutineInput(
        name=f"Copy of {routine['name']}", notes=routine["notes"],
        exercises=routine["exercises"],
    )
    return save_routine(duplicate, db_path=db_path)


def delete_routine(routine_id: int, db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        connection.execute("DELETE FROM workout_routines WHERE id = ?", (routine_id,))