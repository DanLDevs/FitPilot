def strength_log_defaults(routine: dict) -> dict:
    exercises = []
    for exercise in routine["exercises"]:
        starting_weight = exercise.get("starting_weight_kg")
        exercises.append({
            "exercise_name": exercise["exercise_name"],
            "sets": int(exercise["sets"]),
            "reps": int(exercise["target_reps_min"]),
            "target_reps_min": int(exercise["target_reps_min"]),
            "target_reps_max": int(exercise["target_reps_max"]),
            "weight_kg": 0.0 if starting_weight is None else float(starting_weight),
            "notes": exercise.get("notes") or "",
        })
    return {
        "session_name": routine["name"],
        "notes": routine.get("notes") or "",
        "exercises": exercises,
    }


def running_log_defaults(day: dict) -> dict:
    distance = day.get("distance_km")
    duration = day.get("duration_minutes")
    return {
        "run_type": day.get("run_type"),
        "distance_km": 0.0 if distance is None else float(distance),
        "duration_minutes": 0.0 if duration is None else float(duration),
        "notes": day.get("notes") or "",
    }
