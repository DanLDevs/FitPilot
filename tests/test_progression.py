from services.progression_service import recommend_progression


def _history(latest_reps: list[int], rpe: float | None = 7.0, pain: int = 0, technique: int = 0) -> list[dict]:
    rows = []
    for workout_id, workout_date, reps in ((1, "2026-10-24", [12, 12, 12]), (2, "2026-10-31", latest_reps)):
        for set_number, value in enumerate(reps, start=1):
            rows.append({
                "workout_id": workout_id, "workout_date": workout_date,
                "exercise_name": "Bench Press", "exercise_key": "bench",
                "set_number": set_number, "reps": value, "weight_kg": 50,
                "rpe": rpe if workout_id == 2 else 7, "pain": pain if workout_id == 2 else 0,
                "technique_concern": technique if workout_id == 2 else 0,
                "target_reps_min": 8, "target_reps_max": 12, "is_completed": 1,
            })
    return rows


def test_progression_requires_all_sets_in_two_sessions() -> None:
    result = recommend_progression(_history([12, 12, 12]), "Bench Press")
    assert result["status"] == "increase"
    assert result["supporting_metrics"]["suggested_weight_kg"] == 52.5
    assert recommend_progression(_history([12, 11, 12]), "Bench Press")["status"] == "maintain"


def test_safety_and_history_gaps_block_increase() -> None:
    assert recommend_progression(_history([12, 12, 12], pain=1), "Bench Press")["status"] == "caution"
    assert recommend_progression(_history([12, 12, 12], technique=1), "Bench Press")["status"] == "maintain"
    assert recommend_progression(_history([12, 12, 12], rpe=9), "Bench Press")["status"] == "maintain"
    missing = _history([12, 12, 12], rpe=None)
    for row in missing:
        row["rpe"] = None
    assert recommend_progression(missing, "Bench Press")["status"] == "maintain"
    assert recommend_progression([], "Bench Press")["status"] == "insufficient"


def test_performance_decline_and_incomplete_sets_do_not_progress() -> None:
    assert recommend_progression(_history([9, 9, 9]), "Bench Press")["status"] == "caution"
    incomplete = _history([12, 12, 12])
    incomplete[0]["is_completed"] = 0
    assert recommend_progression(incomplete, "Bench Press")["status"] == "insufficient"
