from services.coach_service import build_coach_prompt


def test_coach_prompt_includes_athlete_context() -> None:
    profile = {
        "name": "Avery",
        "primary_goal": "Hybrid Fitness",
        "experience_level": "Intermediate",
        "training_days": 4,
        "strength_days": 2,
        "running_days": 2,
        "session_minutes": 45,
        "equipment": "dumbbells and a treadmill",
        "fitness_goals": "Build a 5K",
        "existing_schedule": "Monday and Thursday evenings are free",
    }
    plan = {
        "name": "Hybrid week",
        "days": [
            {
                "weekday": "Monday",
                "session_kind": "strength",
                "title": "Lower strength",
                "exercises": [{
                    "exercise_name": "Goblet Squat",
                    "sets": 3,
                    "target_reps_min": 8,
                    "target_reps_max": 12,
                }],
            },
            {
                "weekday": "Tuesday",
                "session_kind": "running",
                "title": "Easy run",
                "run_type": "Easy",
                "distance_km": 5,
                "duration_minutes": 32,
            },
        ],
    }
    strength_workouts = [{
        "workout_date": "2026-11-02",
        "session_name": "Evening squat session",
        "volume_kg": 1200,
    }]
    running_workouts = [{
        "workout_date": "2026-11-03",
        "run_type": "Tempo",
        "distance_km": 6,
        "duration_minutes": 33,
    }]
    prompt = build_coach_prompt(
        profile,
        plan,
        strength_workouts,
        running_workouts,
        [{"role": "user", "content": "How was Monday?"}],
        "What should I do tomorrow?",
    )

    assert "Hybrid Fitness" in prompt
    assert "Lower strength" in prompt
    assert "Easy run" in prompt
    assert "5 km" in prompt
    assert "32 min" in prompt
    assert "Evening squat session" in prompt
    assert "Tempo" in prompt
    assert "not medical advice" in prompt
    assert "Goblet Squat" in prompt
    assert "What should I do tomorrow?" in prompt
    assert "Do not invent weights, injuries, or sessions" in prompt
