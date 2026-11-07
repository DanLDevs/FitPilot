from collections import defaultdict


def recommend_progression(
    history: list[dict],
    exercise_name: str,
    weight_increment_kg: float = 2.5,
    max_acceptable_rpe: float = 8.0,
) -> dict:
    sessions: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for row in history:
        if row["exercise_name"] == exercise_name:
            key = row.get("exercise_key") or exercise_name
            sessions[(int(row["workout_id"]), key)].append(row)
    recent = sorted(
        sessions.values(),
        key=lambda items: (items[0]["workout_date"], items[0]["workout_id"]),
        reverse=True,
    )
    recent = [
        sorted(items, key=lambda row: row["set_number"])
        for items in recent
        if all(row.get("is_completed", 1) for row in items)
    ]
    recent = [items for items in recent if items and items[0].get("target_reps_max") is not None]
    if len(recent) < 2:
        return _result("insufficient", exercise_name, "Log two completed sessions with target reps and effort to assess progression.")

    latest, previous = recent[:2]
    metrics = _metrics(latest)
    for session in (latest, previous):
        if any(row["pain"] for row in session):
            return _result("caution", exercise_name, "Pain was reported in a recent session. Do not increase load based on this history.", metrics)
        if any(row["technique_concern"] for row in session):
            return _result("maintain", exercise_name, "A technique concern was recorded recently. Maintain the load while addressing technique.", metrics)
        if any(row["rpe"] is None for row in session):
            return _result("maintain", exercise_name, "Effort is missing for a recent set. Record RPE before considering an increase.", metrics)
        if any(row["rpe"] > max_acceptable_rpe for row in session):
            return _result("maintain", exercise_name, "A recent session exceeded the effort threshold. Repeat the load and monitor recovery.", metrics)

    previous_metrics = _metrics(previous)
    if metrics["average_reps"] <= previous_metrics["average_reps"] - 2 and metrics["average_weight_kg"] <= previous_metrics["average_weight_kg"] + 0.01:
        return _result("caution", exercise_name, "Reps declined by at least two per set at a similar load. Consider recovery before progressing.", metrics)

    if all(
        all(row["reps"] >= session[0]["target_reps_max"] for row in session)
        for session in (latest, previous)
    ):
        suggested_weight = max(row["weight_kg"] for row in latest) + weight_increment_kg
        return _result(
            "increase", exercise_name,
            f"Every set reached {latest[0]['target_reps_max']} reps in both recent sessions at RPE {max_acceptable_rpe} or lower. Consider {suggested_weight:g} kg next time if recovered.",
            metrics | {"suggested_weight_kg": suggested_weight},
        )
    return _result("maintain", exercise_name, "Not every set reached the top of the target range in both recent sessions. Maintain load and build reps.", metrics)


def _metrics(session: list[dict]) -> dict:
    efforts = [row["rpe"] for row in session if row["rpe"] is not None]
    return {
        "date": session[0]["workout_date"],
        "sets": len(session),
        "average_reps": sum(row["reps"] for row in session) / len(session),
        "average_weight_kg": sum(float(row["weight_kg"]) for row in session) / len(session),
        "max_rpe": max(efforts) if efforts else None,
        "target_reps_max": session[0]["target_reps_max"],
        "pain_reported": any(row["pain"] for row in session),
        "technique_concern": any(row["technique_concern"] for row in session),
    }


def _result(status: str, exercise_name: str, explanation: str, metrics: dict | None = None) -> dict:
    return {"status": status, "exercise_name": exercise_name, "explanation": explanation, "supporting_metrics": metrics or {}}