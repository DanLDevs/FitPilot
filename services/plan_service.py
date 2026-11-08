from pathlib import Path

from models.schemas import GeneratedDay, GeneratedWeek, RoutineExerciseInput, WorkoutRoutineInput
from services import routine_service
from services.database import get_connection


def save_plan(week: GeneratedWeek, db_path: str | Path | None = None) -> int:
    with get_connection(db_path) as connection:
        _delete_current_plans(connection)
        cursor = connection.execute(
            "INSERT INTO training_plans (name, summary) VALUES (?, ?)",
            (week.name.strip(), week.summary),
        )
        plan_id = int(cursor.lastrowid)
        for position, day in enumerate(week.days):
            routine_id = None
            if day.session_kind == "strength":
                routine_id = routine_service.write_routine(
                    connection, _routine_input(day), plan_id=plan_id,
                )
            connection.execute(
                """INSERT INTO plan_days
                (plan_id, position, weekday, session_kind, title, notes, routine_id,
                run_type, distance_km, duration_minutes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (plan_id, position, day.weekday, day.session_kind, day.title.strip(), day.notes,
                 routine_id, day.run_type, day.distance_km, day.duration_minutes),
            )
        return plan_id


def get_current_plan(db_path: str | Path | None = None) -> dict | None:
    with get_connection(db_path) as connection:
        plan = connection.execute(
            "SELECT id, name, summary, created_at FROM training_plans ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if plan is None:
            return None
        result = dict(plan)
        days = []
        rows = connection.execute(
            """SELECT position, weekday, session_kind, title, notes, routine_id,
            run_type, distance_km, duration_minutes
            FROM plan_days WHERE plan_id = ? ORDER BY position""",
            (result["id"],),
        ).fetchall()
        for row in rows:
            day = dict(row)
            routine_id = day["routine_id"]
            if routine_id is None:
                day["exercises"] = []
            else:
                day["exercises"] = [dict(exercise) for exercise in connection.execute(
                    """SELECT exercise_name, sets, target_reps_min, target_reps_max,
                    starting_weight_kg, rest_seconds, notes
                    FROM routine_exercises WHERE routine_id = ? ORDER BY position""",
                    (routine_id,),
                ).fetchall()]
            days.append(day)
        result["days"] = days
        return result


def _delete_current_plans(connection) -> None:
    connection.execute("DELETE FROM plan_days")
    connection.execute("DELETE FROM workout_routines WHERE plan_id IS NOT NULL")
    connection.execute("DELETE FROM training_plans")


def _routine_input(day: GeneratedDay) -> WorkoutRoutineInput:
    return WorkoutRoutineInput(
        name=day.title,
        notes=day.notes,
        default_rest_seconds=day.default_rest_seconds,
        auto_start_rest=day.auto_start_rest,
        exercises=[
            RoutineExerciseInput(
                exercise_name=exercise.exercise_name,
                sets=exercise.sets,
                target_reps_min=exercise.target_reps_min,
                target_reps_max=exercise.target_reps_max,
                starting_weight_kg=None,
                rest_seconds=exercise.rest_seconds,
                notes=exercise.notes,
            )
            for exercise in day.exercises
        ],
    )
