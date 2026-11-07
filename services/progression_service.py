from collections import defaultdict


def recommend_progression(
    history: list[dict],
    exercise_name: str,
    weight_increment_kg: float = 2.5,
    required_qualifying_sessions: int = 2,
    max_acceptable_rpe: float = 8.0,
) -> dict:
    """Evaluate recent set history; never alters workout or routine weights."""
    exercise_rows = [row for row in history if row["exercise_name"] == exercise_name]
    sessions: dict[int, list[dict]] = defaultdict(list)
    for row in exercise_rows:
        sessions[int(row["workout_id"])].append(row)
    recent = sorted(
        sessions.values(),
        key=lambda rows: (rows[0]["workout_date"], rows[0]["workout_id"]),
        reverse=True,
    )
    recent = [
        sorted(rows, key=lambda row: row["set_number"])
        for rows in recent
        if rows and rows[0].get("target_reps_max") is not None
    ]
    if len(recent) < required_qualifying_sessions:
        return _result(
            "insufficient", exercise_name,
            "Log at least two sessions with a target rep range to assess progression.",
        )

    latest = recent[0]
    previous = recent[1]
    latest_metrics = _session_metrics(latest)
    previous_metrics = _session_metrics(previous)

    if any(row["pain"] for row in latest):
        return _result("caution", exercise_name, "Pain was reported in the latest session. Do not increase weight based on this history.", latest_metrics)
    if any(row["technique_concern"] for row in latest):
        return _result("maintain", exercise_name, "A technique concern was recorded. Maintain the load while addressing technique.", latest_metrics)
    if latest_metrics["max_rpe"] is not None and latest_metrics["max_rpe"] > max_acceptable_rpe:
        return _result("maintain", exercise_name, "Effort exceeded the configured progression threshold. Repeat the load and monitor recovery.", latest_metrics)
    if any(row["pain"] for row in previous):
        return _result("caution", exercise_name, "Pain was reported in a recent session. Do not increase weight based on this history.", latest_metrics)
    if any(row["technique_concern"] for row in previous):
        return _result("maintain", exercise_name, "A technique concern was recorded in a recent session. Maintain the load while addressing technique.", latest_metrics)
    if any(row["rpe"] is None for session in recent[:required_qualifying_sessions] for row in session):
        return _result("maintain", exercise_name, "Effort was not recorded for every set in the recent sessions. Record RPE before considering a weight increase.", latest_metrics)
    if any(row["rpe"] > max_acceptable_rpe for row in previous):
        return _result("maintain", exercise_name, "A recent session exceeded the configured effort threshold. Repeat the load and monitor recovery.", latest_metrics)

    comparable_load = latest_metrics["average_weight_kg"] <= previous_metrics["average_weight_kg"] + 0.01
    performance_drop = latest_metrics["average_reps"] <= previous_metrics["average_reps"] - 2
    if comparable_load and performance_drop:
        return _result("caution", exercise_name, "Repetitions declined by at least two per set at a similar or lower load. Consider recovery before progressing.", latest_metrics)

    qualifies = all(_session_qualifies(session, max_acceptable_rpe) for session in recent[:required_qualifying_sessions])
    if qualifies:
        current_weight = max(row["weight_kg"] for row in latest)
        next_weight = current_weight + weight_increment_kg
        return _result(
            "increase", exercise_name,
            f"All sets reached the top of the target range in the last {required_qualifying_sessions} sessions with appropriate effort and no pain or technique flags. Consider {next_weight:g} kg next time if you feel recovered.",
            latest_metrics | {"suggested_weight_kg": next_weight},
        )

    return _result(
        "maintain", exercise_name,
        "Not all sets reached the top of the target range in both recent sessions. Maintain the load and build reps with controlled technique.",
        latest_metrics,
    )


def _session_qualifies(session: list[dict], max_acceptable_rpe: float) -> bool:
    if not session:
        return False
    for row in session:
        if row.get("target_reps_max") is None:
            return False
        if row["reps"] < row["target_reps_max"]:
            return False
        if row["pain"] or row["technique_concern"]:
            return False
        if row["rpe"] is None or row["rpe"] > max_acceptable_rpe:
            return False
    return True


def _session_metrics(session: list[dict]) -> dict:
    weights = [float(row["weight_kg"]) for row in session]
    effort = [float(row["rpe"]) for row in session if row["rpe"] is not None]
    return {
        "date": session[0]["workout_date"],
        "sets": len(session),
        "average_reps": sum(row["reps"] for row in session) / len(session),
        "average_weight_kg": sum(weights) / len(weights),
        "max_rpe": max(effort) if effort else None,
        "target_reps_max": session[0]["target_reps_max"],
        "pain_reported": any(row["pain"] for row in session),
        "technique_concern": any(row["technique_concern"] for row in session),
    }


def _result(status: str, exercise_name: str, explanation: str, metrics: dict | None = None) -> dict:
    return {
        "status": status,
        "exercise_name": exercise_name,
        "explanation": explanation,
        "supporting_metrics": metrics or {},
    }