from datetime import date
from pathlib import Path

from services import running_service, strength_service
from utils.calculations import weekly_totals, weekly_workout_counts


def dashboard_data(db_path: str | Path | None = None) -> dict:
    strength = strength_service.list_workouts(db_path, limit=500)
    running = running_service.list_workouts(db_path, limit=500)
    today = date.today()
    monday = today.fromordinal(today.toordinal() - today.weekday())
    strength_this_week = [row for row in strength if date.fromisoformat(row["workout_date"]) >= monday]
    running_this_week = [row for row in running if date.fromisoformat(row["workout_date"]) >= monday]
    return {
        "strength": strength,
        "running": running,
        "strength_this_week": strength_this_week,
        "running_this_week": running_this_week,
        "strength_volume_weeks": weekly_totals(strength, "volume_kg", "workout_date"),
        "running_distance_weeks": weekly_totals(running, "distance_km", "workout_date"),
        "frequency_weeks": weekly_workout_counts(strength, running),
    }