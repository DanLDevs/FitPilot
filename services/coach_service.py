def build_coach_prompt(
    profile: dict,
    plan: dict | None,
    strength_workouts: list[dict],
    running_workouts: list[dict],
    messages: list[dict],
    question: str,
) -> str:
    equipment = profile.get("equipment") or "bodyweight only"
    fitness_goals = profile.get("fitness_goals") or "none"
    schedule = profile.get("existing_schedule") or "none"
    lines = [
        "You are this athlete's fitness coach.",
        "This is general training guidance, not medical advice.",
        "Answer from the athlete's goal, experience, equipment, weekly plan, and recent logs.",
        "Do not invent weights, injuries, or sessions that are not in the snapshot.",
        "Do not replace the weekly plan generator or write workouts into the database.",
        "Reply in plain text.",
        "",
        "Athlete snapshot:",
        f"Name: {profile.get('name') or 'Athlete'}",
        f"Primary goal: {profile.get('primary_goal') or 'not set'}",
        f"Experience level: {profile.get('experience_level') or 'not set'}",
        f"Training days per week: {profile.get('training_days')}",
        f"Preferred strength days: {profile.get('strength_days')}",
        f"Preferred running days: {profile.get('running_days')}",
        f"Available minutes per session: {profile.get('session_minutes')}",
        f"Available equipment: {equipment}",
        f"Fitness goals: {fitness_goals}",
        f"Existing weekly schedule: {schedule}",
        "",
        "Weekly plan:",
        *_plan_lines(plan),
        "",
        "Recent strength logs:",
        *_workout_lines(strength_workouts[:3], _strength_line, "No recent strength sessions."),
        "",
        "Recent running logs:",
        *_workout_lines(running_workouts[:3], _running_line, "No recent runs."),
        "",
        "Conversation so far:",
        *_conversation_lines(messages),
        "",
        f"Question: {question.strip()}",
    ]
    return "\n".join(lines)


def _plan_lines(plan: dict | None) -> list[str]:
    if not plan or not plan.get("days"):
        return ["No weekly plan yet."]
    lines = []
    name = plan.get("name")
    if name:
        lines.append(name)
    for day in plan["days"]:
        lines.append(_day_line(day))
    return lines


def _day_line(day: dict) -> str:
    label = day.get("weekday") or "Unscheduled"
    kind = day.get("session_kind") or "session"
    title = day.get("title") or "Untitled"
    if kind == "running":
        return f"- {label} · running · {title} · {_run_detail(day)}"
    exercises = day.get("exercises") or []
    if not exercises:
        detail = "no exercises listed"
    else:
        detail = "; ".join(
            f"{exercise.get('exercise_name') or 'Exercise'} "
            f"{exercise.get('sets')}x{exercise.get('target_reps_min')}-{exercise.get('target_reps_max')}"
            for exercise in exercises
        )
    return f"- {label} · strength · {title} · {detail}"


def _run_detail(day: dict) -> str:
    parts = [str(day.get("run_type") or "Run")]
    distance = day.get("distance_km")
    duration = day.get("duration_minutes")
    if isinstance(distance, (int, float)):
        parts.append(f"{distance:g} km")
    if isinstance(duration, (int, float)):
        parts.append(f"{duration:g} min")
    return " · ".join(parts)


def _workout_lines(rows: list[dict], formatter, empty: str) -> list[str]:
    if not rows:
        return [empty]
    return [formatter(row) for row in rows]


def _strength_line(row: dict) -> str:
    volume = row.get("volume_kg")
    volume_text = f"{volume:g} kg" if isinstance(volume, (int, float)) else "volume not recorded"
    return f"- {row.get('workout_date')} · {row.get('session_name')} · {volume_text}"


def _running_line(row: dict) -> str:
    distance = row.get("distance_km")
    duration = row.get("duration_minutes")
    distance_text = f"{distance:g} km" if isinstance(distance, (int, float)) else "distance not recorded"
    duration_text = f"{duration:g} min" if isinstance(duration, (int, float)) else "duration not recorded"
    return f"- {row.get('workout_date')} · {row.get('run_type')} · {distance_text} · {duration_text}"


def _conversation_lines(messages: list[dict]) -> list[str]:
    if not messages:
        return ["none"]
    lines = []
    for message in messages:
        speaker = "You" if message.get("role") == "user" else "Coach"
        lines.append(f"{speaker}: {message.get('content', '')}")
    return lines
