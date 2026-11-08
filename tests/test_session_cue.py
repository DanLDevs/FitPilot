from services.progression_service import format_session_cue, session_cue


def _row(
    workout_id: int,
    workout_date: str,
    reps: int,
    set_number: int,
    weight_kg: float = 50,
    rpe: float | None = 7,
    pain: int = 0,
    technique: int = 0,
    is_completed: int = 1,
    exercise_name: str = "Bench Press",
) -> dict:
    return {
        "workout_id": workout_id,
        "workout_date": workout_date,
        "exercise_name": exercise_name,
        "exercise_key": "bench",
        "set_number": set_number,
        "reps": reps,
        "weight_kg": weight_kg,
        "rpe": rpe,
        "pain": pain,
        "technique_concern": technique,
        "is_completed": is_completed,
        "target_reps_min": 6,
        "target_reps_max": 10,
    }


def _session(reps: list[int], **overrides) -> list[dict]:
    return [_row(1, "2026-11-01", value, index, **overrides) for index, value in enumerate(reps, start=1)]


def _cue(history: list[dict], starting_weight_kg: float | None = None) -> dict:
    return session_cue(history, "Bench Press", 8, 12, starting_weight_kg=starting_weight_kg)


def test_first_session_uses_starting_weight_or_zero() -> None:
    with_weight = _cue([], starting_weight_kg=45)
    assert with_weight["status"] == "first"
    assert with_weight["suggested_weight_kg"] == 45
    assert with_weight["working_weight_kg"] is None
    assert with_weight["last_sets"] == []
    assert with_weight["message"] == "No completed history. Start at 45 kg and aim for 8 reps. Planned range is 8–12."

    without_weight = _cue([])
    assert without_weight["suggested_weight_kg"] == 0
    assert without_weight["message"] == "No completed history. Aim for 8 reps. Planned range is 8–12."


def test_mixed_reps_stay_at_the_same_weight() -> None:
    cue = _cue(_session([10, 10, 9]))
    assert cue["status"] == "build"
    assert cue["suggested_weight_kg"] == 50
    assert cue["aim_reps"] == [11, 11, 10]
    assert cue["loads_differ"] is False
    assert cue["message"] == "Last time 50 kg for 10, 10, 9. Stay at 50 kg and aim for 11, 11, 10."


def test_every_set_at_the_top_increases_weight() -> None:
    cue = _cue(_session([12, 12, 12], rpe=8))
    assert cue["status"] == "increase"
    assert cue["suggested_weight_kg"] == 52.5
    assert cue["aim_reps"] == [8, 8, 8]
    assert cue["message"] == "Last time every set reached 12 reps at 50 kg. Use 52.5 kg and aim for 8 reps."


def test_one_set_below_the_max_keeps_building() -> None:
    cue = _cue(_session([12, 12, 11]))
    assert cue["status"] == "build"
    assert cue["suggested_weight_kg"] == 50
    assert cue["aim_reps"] == [12, 12, 12]
    assert cue["message"] == "Last time 50 kg for 12, 12, 11. Stay at 50 kg and aim for 12, 12, 12."


def test_pain_or_technique_blocks_an_increase() -> None:
    pain = _cue(_session([12, 12, 12], pain=1))
    assert pain["status"] == "caution"
    assert pain["suggested_weight_kg"] == 50
    assert pain["message"] == "Pain was reported last time at 50 kg for 12, 12, 12. Repeat 50 kg and do not add weight."

    technique = _cue(_session([12, 12, 12], technique=1))
    assert technique["status"] == "caution"
    assert technique["suggested_weight_kg"] == 50
    assert technique["message"] == (
        "A technique concern was recorded last time at 50 kg for 12, 12, 12. Repeat 50 kg and do not add weight."
    )


def test_high_or_missing_effort_repeats_the_load() -> None:
    high = _cue(_session([12, 12, 12], rpe=9))
    missing = _cue(_session([12, 12, 12], rpe=None))
    expected = (
        "Last time every set reached 12 reps at 50 kg, but effort was above 8 or missing. "
        "Repeat 50 kg until every set is recorded at RPE 8 or lower."
    )
    assert high["status"] == "build"
    assert missing["status"] == "build"
    assert high["suggested_weight_kg"] == 50
    assert missing["suggested_weight_kg"] == 50
    assert high["message"] == expected
    assert missing["message"] == expected


def test_mixed_weights_use_the_lightest_load() -> None:
    history = [
        _row(1, "2026-11-01", 10, 1, weight_kg=50),
        _row(1, "2026-11-01", 10, 2, weight_kg=47.5),
        _row(1, "2026-11-01", 9, 3, weight_kg=47.5),
    ]
    cue = _cue(history)
    assert cue["status"] == "build"
    assert cue["loads_differ"] is True
    assert cue["suggested_weight_kg"] == 47.5
    assert cue["working_weight_kg"] == 47.5
    assert cue["message"] == (
        "Last time sets were 50 kg × 10, 47.5 kg × 10, 47.5 kg × 9. "
        "Loads differed, so stay at 47.5 kg and aim for 11, 11, 10."
    )


def test_latest_completed_session_wins() -> None:
    history = _session([12, 12, 12], weight_kg=40)
    history.extend(_session([10, 9]))
    for row in history[3:]:
        row["workout_id"] = 2
        row["workout_date"] = "2026-11-08"
    history.append(_row(3, "2026-11-09", 12, 1, weight_kg=60, is_completed=0))
    cue = _cue(history)
    assert cue["status"] == "build"
    assert cue["suggested_weight_kg"] == 50
    assert [item["reps"] for item in cue["last_sets"]] == [10, 9]
    assert cue["message"] == "Last time 50 kg for 10, 9. Stay at 50 kg and aim for 11, 10."


def test_pound_text_converts_without_changing_stored_weight() -> None:
    cue = _cue(_session([10, 10, 9]))
    assert format_session_cue(cue, "kg") == cue["message"]
    assert format_session_cue(cue, "lb") == "Last time 110.2 lb for 10, 10, 9. Stay at 110.2 lb and aim for 11, 11, 10."
    assert cue["suggested_weight_kg"] == 50
