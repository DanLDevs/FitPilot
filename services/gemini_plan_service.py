import json
import os

from pydantic import ValidationError

from models.schemas import GeneratedWeek


class PlanCountError(ValueError):
    pass


GEMINI_MODELS = ("gemini-3.5-flash-lite", "gemini-3.5-flash")
DEFAULT_GEMINI_MODEL = GEMINI_MODELS[0]


def gemini_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY", "").strip())


def resolve_gemini_model(model: str | None = None) -> str:
    if model is not None:
        choice = model.strip()
        if choice not in GEMINI_MODELS:
            raise ValueError(
                "Choose Gemini 3.5 Flash-Lite or Gemini 3.5 Flash."
            )
        return choice
    env_model = os.getenv("GEMINI_MODEL", "").strip()
    if env_model in GEMINI_MODELS:
        return env_model
    return DEFAULT_GEMINI_MODEL


def resolve_day_counts(profile: dict) -> dict:
    training = int(profile["training_days"])
    strength = int(profile["strength_days"])
    running = int(profile["running_days"])
    if strength > 0 and running > 0:
        strength_count, running_count = strength, running
    elif strength == 0 and running == 0:
        strength_count, running_count = _counts_from_goal(profile["primary_goal"], training)
    elif running == 0:
        strength_count = strength
        running_count = max(0, training - strength)
    else:
        running_count = running
        strength_count = max(0, training - running)

    total = strength_count + running_count
    if total < 1 or total > 7:
        raise PlanCountError(
            f"This profile requests {total} sessions "
            f"({strength_count} strength and {running_count} running). "
            "Update the athlete profile so the week stays between 1 and 7 sessions."
        )
    return {"strength_days": strength_count, "running_days": running_count}


def build_prompt(profile: dict, counts: dict, extra_note: str) -> str:
    equipment = profile.get("equipment") or "bodyweight only"
    fitness_goals = profile.get("fitness_goals") or "none"
    schedule = profile.get("existing_schedule") or "none"
    note = extra_note.strip() or "none"
    return "\n".join([
        "You are a fitness coach creating one weekly training plan.",
        "This is general training guidance, not medical advice.",
        "Return only JSON that matches the schema.",
        f"Athlete name: {profile['name']}",
        f"Primary goal: {profile['primary_goal']}",
        f"Experience level: {profile['experience_level']}",
        f"Training days per week: {profile['training_days']}",
        f"Preferred strength days: {profile['strength_days']}",
        f"Preferred running days: {profile['running_days']}",
        f"Available minutes per session: {profile['session_minutes']}",
        f"Available equipment: {equipment}",
        f"Fitness goals: {fitness_goals}",
        f"Existing weekly schedule: {schedule}",
        f"Additional note: {note}",
        f"Required strength sessions: {counts['strength_days']}",
        f"Required running sessions: {counts['running_days']}",
        "Rules:",
        f"- Include exactly {counts['strength_days']} strength days and {counts['running_days']} running days.",
        "- Order the days across the week. Use weekday names when the schedule supports them.",
        f"- Every session must fit in {profile['session_minutes']} minutes.",
        "- Use only the available equipment.",
        "- Match the experience level.",
        "- Do not set starting weights.",
        "- Choose sets, reps, and rest from the primary goal.",
        "- Running day run_type must be one of: Easy, Tempo, Interval, Long Run, Recovery, Other.",
        "- Store running distance in kilometers and duration in minutes.",
        "- Strength days need exercises. Running days need run_type, distance_km, and duration_minutes, and no exercises.",
    ])


def generate_week(profile: dict, extra_note: str = "", generate=None, model: str | None = None) -> GeneratedWeek:
    counts = resolve_day_counts(profile)
    prompt = build_prompt(profile, counts, extra_note)
    raw = generate(prompt) if generate is not None else _call_gemini(prompt, model)
    week = _parse_week(raw)
    _assert_counts(week, counts)
    return week


def _counts_from_goal(goal: str, training: int) -> tuple[int, int]:
    if goal == "Running Endurance":
        return 0, training
    if goal == "Hybrid Fitness":
        running_count = training // 2
        return training - running_count, running_count
    return training, 0


def _assert_counts(week: GeneratedWeek, counts: dict) -> None:
    strength = sum(day.session_kind == "strength" for day in week.days)
    running = sum(day.session_kind == "running" for day in week.days)
    if strength != counts["strength_days"] or running != counts["running_days"]:
        raise ValueError(
            f"Gemini returned {strength} strength and {running} running sessions. "
            f"Expected {counts['strength_days']} strength and {counts['running_days']} running."
        )


def _parse_week(raw) -> GeneratedWeek:
    if isinstance(raw, GeneratedWeek):
        return raw
    if isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError("Gemini returned a plan that could not be read.") from error
    elif isinstance(raw, dict):
        payload = raw
    else:
        raise ValueError("Gemini returned a plan that could not be read.")
    try:
        return GeneratedWeek.model_validate(payload)
    except ValidationError as error:
        messages = "; ".join(item["msg"] for item in error.errors())
        raise ValueError(messages or "The generated plan was not usable.") from error


def gemini_response_schema() -> dict:
    # Gemini 3.5 rejects maxItems on an array nested inside another array.
    # GeneratedWeek still checks the exercise count after the response arrives.
    schema = GeneratedWeek.model_json_schema()
    schema["$defs"]["GeneratedDay"]["properties"]["exercises"].pop("maxItems", None)
    return schema


def _call_gemini(prompt: str, model: str | None = None) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Add GEMINI_API_KEY to your .env file to generate a weekly plan.")
    try:
        from google import genai
        from google.genai import errors, types
    except ImportError as error:
        raise ValueError("Install google-genai to generate a weekly plan.") from error
    client = genai.Client(api_key=api_key)
    model = resolve_gemini_model(model)
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=gemini_response_schema(),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
            ),
        )
    except errors.APIError as error:
        raise ValueError(error.message or "Gemini could not generate a plan.") from error
    text = getattr(response, "text", None)
    if not text:
        raise ValueError("Gemini returned an empty plan.")
    return text
