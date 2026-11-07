from datetime import date, timedelta
from pathlib import Path

from models.schemas import RunningWorkoutInput, StrengthSetInput, StrengthWorkoutInput
from services import database, running_service, strength_service


DEMO_MARKER = "FITPILOT_DEMO"


def load_demo_data(db_path: str | Path | None = None) -> bool:
    profile = database.get_profile(db_path)
    if profile is None:
        database.save_profile({
            "name": "Jordan Lee", "primary_goal": "Hybrid Fitness", "experience_level": "Intermediate",
            "training_days": 6, "strength_days": 3, "running_days": 3,
            "session_minutes": 60, "equipment": "Full gym", "fitness_goals": "Build strength and improve 10K endurance",
            "existing_schedule": "",
        }, db_path)
    if any(DEMO_MARKER in (row.get("notes") or "") for row in strength_service.list_workouts(db_path, 1000)):
        return False
    if any(DEMO_MARKER in (row.get("notes") or "") for row in running_service.list_workouts(db_path, 1000)):
        return False

    today = date.today()
    strength_templates = [
        ("Upper Body", [("Bench Press", 3, 8, 50), ("Barbell Row", 3, 10, 45), ("Overhead Press", 3, 8, 30)]),
        ("Lower Body", [("Squat", 3, 8, 70), ("Romanian Deadlift", 3, 10, 55), ("Leg Press", 3, 10, 100)]),
        ("Full Body", [("Deadlift", 3, 5, 90), ("Dumbbell Bench Press", 3, 10, 22.5), ("Lat Pulldown", 3, 10, 45)]),
    ]
    run_templates = [("Easy", 5.0), ("Tempo", 5.5), ("Long Run", 8.0)]

    for week in range(6):
        week_start = today - timedelta(days=today.weekday(), weeks=5 - week)
        for day_offset, (name, exercises) in zip((0, 2, 4), strength_templates):
            date_offset = week_start + timedelta(days=day_offset)
            if date_offset > today:
                continue
            adjusted_exercises = []
            for exercise_name, sets, reps, base_weight in exercises:
                increment = min(week // 2, 2) * (2.5 if exercise_name not in ("Leg Press", "Deadlift") else 5)
                rpe = 8.5 if week == 4 and exercise_name == "Squat" else 7
                adjusted_exercises.append(StrengthSetInput(
                    exercise_name=exercise_name, sets=sets, reps=reps, weight_kg=base_weight + increment,
                    rpe=rpe, notes="Heavy session" if rpe > 8 else "", pain=False,
                ))
            strength_service.add_workout(StrengthWorkoutInput(
                workout_date=date_offset, session_name=name,
                notes=f"{DEMO_MARKER}: sample training session", exercises=adjusted_exercises,
            ), db_path)

        for day_offset, (run_type, base_distance) in zip((1, 3, 6), run_templates):
            run_date = week_start + timedelta(days=day_offset)
            if run_date > today:
                continue
            distance = base_distance + week * (0.25 if run_type == "Easy" else 0.4)
            pace = {"Easy": 6.4 - week * 0.04, "Tempo": 5.3 - week * 0.025, "Long Run": 6.7}[run_type]
            duration = distance * pace
            effort = 8 if week == 4 and run_type == "Tempo" else (4 if run_type == "Easy" else 7)
            note = "Felt unusually difficult" if effort >= 8 else "Steady effort"
            running_service.add_workout(RunningWorkoutInput(
                workout_date=run_date, run_type=run_type,
                distance_km=distance, duration_minutes=duration, rpe=effort,
                notes=f"{DEMO_MARKER}: {note}", pain=False,
            ), db_path)
    return True