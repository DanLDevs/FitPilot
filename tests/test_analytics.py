from datetime import date

from utils.calculations import pace_minutes_per_km, weekly_totals, weekly_workout_counts


def test_pace_calculation() -> None:
    assert pace_minutes_per_km(5, 25) == 5


def test_weekly_aggregation_includes_empty_weeks() -> None:
    result = weekly_totals(
        [{"workout_date": date.today().isoformat(), "volume_kg": 1200}],
        "volume_kg", "workout_date", weeks=2,
    )
    assert len(result) == 2
    assert result[-1]["value"] == 1200
    assert result[0]["value"] == 0


def test_weekly_workout_frequency_separates_activities() -> None:
    today = date.today().isoformat()
    result = weekly_workout_counts(
        [{"id": 1, "workout_date": today}],
        [{"id": 2, "workout_date": today}],
        weeks=1,
    )
    assert result == [{"week": result[0]["week"], "strength": 1, "running": 1}]