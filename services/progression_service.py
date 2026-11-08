from collections import defaultdict

from utils.calculations import kg_to_pounds


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


def session_cue(
    history: list[dict],
    exercise_name: str,
    target_reps_min: int,
    target_reps_max: int,
    weight_increment_kg: float = 2.5,
    starting_weight_kg: float | None = None,
) -> dict:
    session = _latest_completed_session(history, exercise_name)
    minimum = int(target_reps_min)
    maximum = int(target_reps_max)
    if not session:
        suggested = 0.0 if starting_weight_kg is None else float(starting_weight_kg)
        cue = _session_cue_result(
            "first", suggested, None, [], [], False, "first", minimum, maximum, starting_weight_kg,
        )
        cue["message"] = _compose_session_message(cue, "kg")
        return cue

    last_sets = [
        {"set_number": int(row["set_number"]), "reps": int(row["reps"]), "weight_kg": float(row["weight_kg"])}
        for row in session
    ]
    weights = [item["weight_kg"] for item in last_sets]
    working_weight = min(weights)
    loads_differ = max(weights) - working_weight > 0.01
    aim_reps = [min(item["reps"] + 1, maximum) for item in last_sets]
    if any(row.get("pain") for row in session):
        detail = "both" if any(row.get("technique_concern") for row in session) else "pain"
        status = "caution"
        suggested = working_weight
    elif any(row.get("technique_concern") for row in session):
        detail = "technique"
        status = "caution"
        suggested = working_weight
    elif all(item["reps"] >= maximum for item in last_sets):
        effort_blocks_increase = any(row.get("rpe") is None or float(row["rpe"]) > 8.0 for row in session)
        if effort_blocks_increase:
            detail = "effort"
            status = "build"
            suggested = working_weight
        else:
            detail = "increase"
            status = "increase"
            suggested = working_weight + weight_increment_kg
            aim_reps = [minimum for _ in last_sets]
    else:
        detail = "build"
        status = "build"
        suggested = working_weight
    cue = _session_cue_result(
        status, suggested, working_weight, last_sets, aim_reps, loads_differ, detail, minimum, maximum, starting_weight_kg,
    )
    cue["message"] = _compose_session_message(cue, "kg")
    return cue


def format_session_cue(cue: dict, unit: str) -> str:
    if unit != "lb":
        return cue["message"]
    return _compose_session_message(cue, "lb")


def _latest_completed_session(history: list[dict], exercise_name: str) -> list[dict]:
    sessions: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for row in history:
        if row["exercise_name"] != exercise_name or not row.get("is_completed", 1):
            continue
        key = row.get("exercise_key") or exercise_name
        sessions[(int(row["workout_id"]), key)].append(row)
    if not sessions:
        return []
    latest = max(sessions.values(), key=lambda items: (items[0]["workout_date"], items[0]["workout_id"]))
    return sorted(latest, key=lambda row: row["set_number"])


def _session_cue_result(
    status: str,
    suggested_weight_kg: float,
    working_weight_kg: float | None,
    last_sets: list[dict],
    aim_reps: list[int],
    loads_differ: bool,
    detail: str,
    target_reps_min: int,
    target_reps_max: int,
    starting_weight_kg: float | None,
) -> dict:
    return {
        "status": status,
        "message": "",
        "suggested_weight_kg": float(suggested_weight_kg),
        "working_weight_kg": None if working_weight_kg is None else float(working_weight_kg),
        "last_sets": last_sets,
        "aim_reps": aim_reps,
        "loads_differ": loads_differ,
        "detail": detail,
        "target_reps_min": target_reps_min,
        "target_reps_max": target_reps_max,
        "starting_weight_kg": starting_weight_kg,
    }


def _compose_session_message(cue: dict, unit: str) -> str:
    minimum = cue["target_reps_min"]
    maximum = cue["target_reps_max"]
    detail = cue["detail"]
    if detail == "first":
        planned = f"Planned range is {minimum}–{maximum}."
        if cue["starting_weight_kg"] is None:
            return f"No completed history. Aim for {minimum} reps. {planned}"
        start = _weight_label(cue["starting_weight_kg"], unit)
        return f"No completed history. Start at {start} and aim for {minimum} reps. {planned}"

    working = _weight_label(cue["working_weight_kg"], unit)
    reps = _rep_list([item["reps"] for item in cue["last_sets"]])
    performed = _set_list(cue["last_sets"], unit)
    if detail in {"pain", "technique", "both"}:
        if detail == "pain":
            reason = "Pain was reported"
        elif detail == "technique":
            reason = "A technique concern was recorded"
        else:
            reason = "Pain and a technique concern were recorded"
        if cue["loads_differ"]:
            return f"{reason} last time. Sets were {performed}. Loads differed, so repeat {working} and do not add weight."
        return f"{reason} last time at {working} for {reps}. Repeat {working} and do not add weight."
    if detail == "effort":
        if cue["loads_differ"]:
            return (
                f"Last time every set reached {maximum} reps, but loads differed ({performed}) and effort was above 8 or missing. "
                f"Repeat {working} until every set is recorded at RPE 8 or lower."
            )
        return (
            f"Last time every set reached {maximum} reps at {working}, but effort was above 8 or missing. "
            f"Repeat {working} until every set is recorded at RPE 8 or lower."
        )
    if detail == "increase":
        suggested = _weight_label(cue["suggested_weight_kg"], unit)
        if cue["loads_differ"]:
            return (
                f"Last time every set reached {maximum} reps, but loads differed ({performed}). "
                f"Use {suggested} and aim for {minimum} reps."
            )
        return f"Last time every set reached {maximum} reps at {working}. Use {suggested} and aim for {minimum} reps."
    aim = _rep_list(cue["aim_reps"])
    if cue["loads_differ"]:
        return f"Last time sets were {performed}. Loads differed, so stay at {working} and aim for {aim}."
    return f"Last time {working} for {reps}. Stay at {working} and aim for {aim}."


def _weight_label(weight_kg: float, unit: str) -> str:
    if unit == "lb":
        return f"{kg_to_pounds(float(weight_kg)):.1f} lb"
    return f"{float(weight_kg):g} kg"


def _rep_list(reps: list[int]) -> str:
    return ", ".join(str(rep) for rep in reps)


def _set_list(last_sets: list[dict], unit: str) -> str:
    return ", ".join(f"{_weight_label(item['weight_kg'], unit)} × {item['reps']}" for item in last_sets)
