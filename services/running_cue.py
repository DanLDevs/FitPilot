from utils.calculations import km_to_miles


_GOALS = {
    "Easy": "Cover the distance and keep this easy. The time is a pace ceiling.",
    "Recovery": "Cover the distance and keep this easy. The time is a pace ceiling.",
    "Long Run": "The distance is the goal.",
    "Tempo": "Hold the effort for the planned time. The distance is the expected result of that pace.",
    "Interval": "Hold the effort for the planned time. The distance is the expected result of that pace.",
}


def format_run_clock(minutes: float) -> str:
    total_seconds = int(round(float(minutes) * 60))
    whole_minutes, seconds = divmod(max(0, total_seconds), 60)
    return f"{whole_minutes}:{seconds:02d}"


def format_run_distance(distance_km: float, unit: str = "km") -> str:
    value = km_to_miles(distance_km) if unit == "mi" else float(distance_km)
    label = "mi" if unit == "mi" else "km"
    return f"{value:.1f} {label}"


def format_run_pace(distance_km: float, duration_minutes: float, unit: str = "km") -> str:
    distance = km_to_miles(distance_km) if unit == "mi" else float(distance_km)
    if distance <= 0:
        raise ValueError("Distance must be positive")
    return f"{format_run_clock(float(duration_minutes) / distance)}/{'mi' if unit == 'mi' else 'km'}"


def run_session_cue(
    run_type: str,
    distance_km: float,
    duration_minutes: float,
    last_run: dict | None = None,
    unit: str = "km",
) -> str:
    """Target for one planned run. Reports history without asking for more distance or speed."""
    parts = [
        f"Aim for {format_run_distance(distance_km, unit)} in about {format_run_clock(duration_minutes)} "
        f"(about {format_run_pace(distance_km, duration_minutes, unit)})."
    ]
    goal = _GOALS.get(run_type)
    if goal:
        parts.append(goal)
    if last_run is not None:
        parts.append(
            f"Last {run_type.lower()} run was {format_run_distance(last_run['distance_km'], unit)} "
            f"in {format_run_clock(last_run['duration_minutes'])}."
        )
    return " ".join(parts)
