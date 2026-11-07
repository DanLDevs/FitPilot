from services.progression_service import recommend_progression


def history_for_two_sessions(latest_reps: list[int], **latest_flags) -> list[dict]:
    history = []
    for workout_id, workout_date, reps in ((1, "2026-10-25", [12, 12, 12]), (2, "2026-11-01", latest_reps)):
        for set_number, rep_count in enumerate(reps, start=1):
            history.append({
                "workout_id": workout_id, "workout_date": workout_date,
                "exercise_name": "Bench Press", "set_number": set_number,
                "reps": rep_count, "weight_kg": 50.0, "rpe": 7.0,
                "pain": 0, "technique_concern": 0,
                "target_reps_min": 8, "target_reps_max": 12,
                **(latest_flags if workout_id == 2 else {}),
            })
    return history


def test_progression_requires_all_sets_in_multiple_sessions() -> None:
    result = recommend_progression(history_for_two_sessions([12, 12, 12]), "Bench Press")
    assert result["status"] == "increase"
    assert result["supporting_metrics"]["suggested_weight_kg"] == 52.5

    one_set_short = recommend_progression(history_for_two_sessions([12, 11, 12]), "Bench Press")
    assert one_set_short["status"] == "maintain"


def test_progression_requires_multiple_qualifying_sessions() -> None:
    history = history_for_two_sessions([12, 12, 12])
    for row in history:
        if row["workout_id"] == 1:
            row["reps"] = 10
    result = recommend_progression(history, "Bench Press")
    assert result["status"] == "maintain"


def test_pain_and_technique_flags_block_increase() -> None:
    pain_result = recommend_progression(
        history_for_two_sessions([12, 12, 12], pain=1), "Bench Press"
    )
    assert pain_result["status"] == "caution"

    technique_result = recommend_progression(
        history_for_two_sessions([12, 12, 12], technique_concern=1), "Bench Press"
    )
    assert technique_result["status"] == "maintain"


def test_high_effort_and_performance_decline_do_not_progress() -> None:
    high_effort = recommend_progression(
        history_for_two_sessions([12, 12, 12], rpe=9.0), "Bench Press"
    )
    assert high_effort["status"] == "maintain"

    declining = recommend_progression(history_for_two_sessions([9, 9, 9]), "Bench Press")
    assert declining["status"] == "caution"

    unknown_effort = history_for_two_sessions([12, 12, 12])
    for row in unknown_effort:
        row["rpe"] = None
    assert recommend_progression(unknown_effort, "Bench Press")["status"] == "maintain"


def test_missing_or_unqualified_history_is_reported() -> None:
    assert recommend_progression([], "Bench Press")["status"] == "insufficient"
    history = history_for_two_sessions([12, 12, 12])
    for row in history:
        row["target_reps_max"] = None
    assert recommend_progression(history, "Bench Press")["status"] == "insufficient"