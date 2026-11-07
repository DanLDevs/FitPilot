from collections import defaultdict
from datetime import date, timedelta


def pounds_to_kg(weight_lb: float) -> float:
    return weight_lb / 2.2046226218


def kg_to_pounds(weight_kg: float) -> float:
    return weight_kg * 2.2046226218


def miles_to_km(distance_mi: float) -> float:
    return distance_mi * 1.609344


def km_to_miles(distance_km: float) -> float:
    return distance_km / 1.609344


def pace_minutes_per_km(distance_km: float, duration_minutes: float) -> float:
    if distance_km <= 0 or duration_minutes <= 0:
        raise ValueError("Distance and duration must be positive")
    return duration_minutes / distance_km


def weekly_totals(rows: list[dict], value_key: str, date_key: str, weeks: int = 8) -> list[dict]:
    today = date.today()
    this_monday = today - timedelta(days=today.weekday())
    totals: dict[date, float] = defaultdict(float)
    for row in rows:
        day = date.fromisoformat(str(row[date_key])[:10])
        week_start = day - timedelta(days=day.weekday())
        totals[week_start] += float(row.get(value_key, 0) or 0)
    starts = [this_monday - timedelta(weeks=offset) for offset in reversed(range(weeks))]
    return [{"week": start.isoformat(), "value": totals[start]} for start in starts]


def weekly_workout_counts(strength: list[dict], running: list[dict], weeks: int = 8) -> list[dict]:
    strength_totals = weekly_totals(strength, "id", "workout_date", weeks)
    running_totals = weekly_totals(running, "id", "workout_date", weeks)
    return [
        {"week": strength_week["week"],
         "strength": sum(1 for row in strength if _same_week(row["workout_date"], strength_week["week"])),
         "running": sum(1 for row in running if _same_week(row["workout_date"], running_week["week"]))}
        for strength_week, running_week in zip(strength_totals, running_totals)
    ]


def _same_week(value: str, week_start: str) -> bool:
    day = date.fromisoformat(str(value)[:10])
    return (day - timedelta(days=day.weekday())).isoformat() == week_start