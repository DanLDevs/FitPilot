from uuid import uuid4

import streamlit as st

from models.schemas import GeneratedWeek, RoutineExerciseInput, WorkoutRoutineInput
from services import database, plan_service, routine_service
from services.gemini_plan_service import (
    GEMINI_MODELS,
    PlanCountError,
    gemini_configured,
    generate_week,
    resolve_day_counts,
)
from utils.calculations import kg_to_pounds, pounds_to_kg


st.set_page_config(page_title="Workout Routines | FitPilot", page_icon="F", layout="wide")
database.init_database()
profile = database.get_profile()
st.title("Workout routines")
st.caption("Create reusable templates for your live sessions.")
if profile is None:
    st.warning("Set up your athlete profile on the Dashboard before creating routines.")
    st.stop()
unit = profile.get("weight_unit") if profile.get("weight_unit") in ("kg", "lb") else "kg"


def _display_weight(weight_kg: float, display_unit: str) -> float:
    if display_unit == "lb":
        value = round(kg_to_pounds(weight_kg), 1)
    else:
        value = float(weight_kg)
    return min(1000.0, max(0.0, value))


def _stored_weight(weight: float, display_unit: str) -> float:
    return pounds_to_kg(weight) if display_unit == "lb" else float(weight)

EXERCISES = [
    "Bench Press", "Squat", "Deadlift", "Overhead Press", "Barbell Row", "Pull-Up",
    "Lat Pulldown", "Bicep Curl", "Tricep Pushdown", "Leg Press", "Romanian Deadlift",
    "Dumbbell Bench Press", "Custom",
]


def _key(row_id: str, name: str) -> str:
    return f"routine_{row_id}_{name}"


def _add_row(exercise: dict | None = None) -> None:
    row_id = uuid4().hex[:10]
    st.session_state["routine_rows"].append(row_id)
    exercise = exercise or {}
    name = exercise.get("exercise_name", "Bench Press")
    st.session_state[_key(row_id, "name")] = name if name in EXERCISES else "Custom"
    st.session_state[_key(row_id, "custom")]= "" if name in EXERCISES else name
    st.session_state[_key(row_id, "sets")] = int(exercise.get("sets", 3))
    st.session_state[_key(row_id, "minimum")] = int(exercise.get("target_reps_min", 8))
    st.session_state[_key(row_id, "maximum")] = int(exercise.get("target_reps_max", 12))
    stored_weight = exercise.get("starting_weight_kg")
    source_kg = None if stored_weight is None else float(stored_weight)
    st.session_state[_key(row_id, "weight_enabled")] = source_kg is not None
    st.session_state[_key(row_id, "weight_kg")] = source_kg
    st.session_state[_key(row_id, "weight")] = _display_weight(20.0 if source_kg is None else source_kg, unit)
    st.session_state[_key(row_id, "weight_unit")] = unit
    st.session_state[_key(row_id, "rest_enabled")] = exercise.get("rest_seconds") is not None
    st.session_state[_key(row_id, "rest")] = int(exercise.get("rest_seconds") or 90)
    st.session_state[_key(row_id, "notes")] = exercise.get("notes", "")


def _clear_editor() -> None:
    for row_id in st.session_state.get("routine_rows", []):
        for key in list(st.session_state):
            if key.startswith(f"routine_{row_id}_"):
                del st.session_state[key]
    st.session_state["routine_rows"] = []
    st.session_state["routine_id"] = None
    st.session_state["routine_name"] = ""
    st.session_state["routine_notes"] = ""


def _align_routine_weights(display_unit: str) -> None:
    for row_id in list(st.session_state.get("routine_rows", [])):
        weight_key = _key(row_id, "weight")
        unit_key = _key(row_id, "weight_unit")
        source_key = _key(row_id, "weight_kg")
        if weight_key not in st.session_state:
            continue
        previous = st.session_state.get(unit_key)
        current = float(st.session_state[weight_key])
        if previous is None:
            if st.session_state.get(source_key) is None:
                st.session_state[source_key] = current
            if display_unit != "kg":
                st.session_state[weight_key] = _display_weight(float(st.session_state[source_key]), display_unit)
            st.session_state[unit_key] = display_unit
            continue
        if previous == display_unit:
            continue
        source = st.session_state.get(source_key)
        if source is None:
            source = 20.0
        previous_display = _display_weight(float(source), previous)
        if abs(current - previous_display) < 0.05:
            st.session_state[weight_key] = _display_weight(float(source), display_unit)
        st.session_state[unit_key] = display_unit


def _load_routine(routine_id: int | None) -> None:
    _clear_editor()
    if routine_id is None:
        _add_row()
        return
    routine = routine_service.get_routine(routine_id)
    if routine is None:
        _add_row()
        return
    st.session_state["routine_id"] = routine_id
    st.session_state["routine_name"] = routine["name"]
    st.session_state["routine_notes"] = routine["notes"]
    st.session_state["routine_default_rest"] = routine["default_rest_seconds"]
    st.session_state["routine_auto_rest"] = bool(routine["auto_start_rest"])
    for exercise in routine["exercises"]:
        _add_row(exercise)


def _render_plan_days(days: list[dict], saved: bool) -> None:
    for index, day in enumerate(days):
        with st.container(border=True):
            label = day.get("weekday") or f"Day {index + 1}"
            kind = "Strength" if day.get("session_kind") == "strength" else "Running"
            st.markdown(f"**{label} · {day['title']}**")
            st.caption(kind)
            if day.get("session_kind") == "strength":
                for exercise in day.get("exercises") or []:
                    rest = exercise.get("rest_seconds")
                    rest_text = f" · rest {rest}s" if rest is not None else ""
                    st.write(
                        f"{exercise['exercise_name']} — {exercise['sets']} sets · "
                        f"{exercise['target_reps_min']}–{exercise['target_reps_max']} reps{rest_text}"
                    )
                if saved and day.get("routine_id"):
                    if st.button("Edit routine", key=f"edit_plan_routine_{day['routine_id']}"):
                        routine = routine_service.get_routine(day["routine_id"])
                        if routine is not None:
                            st.session_state["routine_pending_selection"] = f"{routine['name']} · #{routine['id']}"
                            st.rerun()
                elif saved:
                    st.caption("This strength routine was removed. You can recreate it in the editor below.")
            else:
                distance = day.get("distance_km")
                duration = day.get("duration_minutes")
                if distance is not None and duration is not None:
                    st.write(f"{day.get('run_type')} · {distance:g} km · {duration:g} min")
                st.caption("Log this run on the Running page when you complete it.")
            if day.get("notes"):
                st.caption(day["notes"])


st.subheader("Weekly plan")
st.caption("Gemini builds one session for each available training day from your athlete profile.")
summary_left, summary_right = st.columns(2)
summary_left.markdown(
    f"**Primary goal:** {profile['primary_goal']}  \n"
    f"**Experience:** {profile['experience_level']}  \n"
    f"**Training days:** {profile['training_days']}  \n"
    f"**Strength days:** {profile['strength_days']}  \n"
    f"**Running days:** {profile['running_days']}"
)
summary_right.markdown(
    f"**Minutes per session:** {profile['session_minutes']}  \n"
    f"**Equipment:** {profile['equipment'] or 'Not set'}  \n"
    f"**Fitness goals:** {profile['fitness_goals'] or 'Not set'}  \n"
    f"**Schedule:** {profile['existing_schedule'] or 'Not set'}"
)
st.text_input(
    "Anything else Gemini should know",
    key="plan_extra_note",
    placeholder="Optional: injury, preference, or focus",
)

plan_counts = None
try:
    plan_counts = resolve_day_counts(profile)
    st.caption(
        f"Gemini will build {plan_counts['strength_days']} strength sessions and "
        f"{plan_counts['running_days']} running sessions."
    )
except PlanCountError as error:
    st.warning(str(error))

if not gemini_configured():
    st.info("Add GEMINI_API_KEY to your .env file to generate a weekly plan. You can still create routines manually.")
elif plan_counts is not None:
    st.selectbox(
        "Gemini model",
        GEMINI_MODELS,
        format_func=lambda model_id: (
            "Gemini 3.5 Flash-Lite" if model_id == "gemini-3.5-flash-lite" else "Gemini 3.5 Flash"
        ),
        key="plan_gemini_model",
        help="Flash-Lite is the default. Choose Flash when Flash-Lite is busy.",
    )
    if st.button("Generate weekly plan", key="generate_weekly_plan"):
        try:
            with st.spinner("Building your week..."):
                generated = generate_week(
                    profile,
                    st.session_state.get("plan_extra_note", ""),
                    model=st.session_state["plan_gemini_model"],
                )
            st.session_state["plan_draft"] = generated.model_dump()
            st.rerun()
        except Exception as error:
            st.error(f"Plan not generated: {error}")

current_plan = plan_service.get_current_plan()
plan_draft = st.session_state.get("plan_draft")
if plan_draft:
    st.markdown(f"**{plan_draft['name']}**")
    if plan_draft.get("summary"):
        st.write(plan_draft["summary"])
    if current_plan is not None:
        st.caption("Saving replaces the current generated plan and its strength routines. Routines you created yourself stay.")
    _render_plan_days(plan_draft["days"], saved=False)
    save_col, discard_col = st.columns(2)
    if save_col.button("Save plan", type="primary", key="save_weekly_plan"):
        try:
            plan_service.save_plan(GeneratedWeek.model_validate(plan_draft))
            st.session_state.pop("plan_draft", None)
            st.success("Weekly plan saved. Strength days are available in Live Workout and in the editor below.")
            st.rerun()
        except Exception as error:
            st.error(f"Plan not saved: {error}")
    if discard_col.button("Discard", key="discard_weekly_plan"):
        st.session_state.pop("plan_draft", None)
        st.rerun()
elif current_plan is not None:
    st.markdown(f"**{current_plan['name']}**")
    if current_plan.get("summary"):
        st.write(current_plan["summary"])
    _render_plan_days(current_plan["days"], saved=True)
else:
    st.caption("No weekly plan yet.")

st.divider()
st.subheader("Routine editor")

if "routine_rows" not in st.session_state:
    st.session_state["routine_rows"] = []
    st.session_state["routine_id"] = None
    st.session_state["routine_name"] = ""
    st.session_state["routine_notes"] = ""
    st.session_state["routine_default_rest"] = 90
    st.session_state["routine_auto_rest"] = True
    _add_row()

routines = routine_service.list_routines()
routine_labels = {"New routine": None}
routine_labels.update({f"{routine['name']} · #{routine['id']}": routine["id"] for routine in routines})
pending_selection = st.session_state.pop("routine_pending_selection", None)
if pending_selection in routine_labels:
    st.session_state["routine_selected_label"] = pending_selection
if st.session_state.pop("routine_reset_editor", False):
    _load_routine(None)
selected_label = st.selectbox("Create or edit routine", list(routine_labels), key="routine_selected_label")
selected_id = routine_labels[selected_label]
if selected_id != st.session_state["routine_id"]:
    _load_routine(selected_id)
_align_routine_weights(unit)

st.text_input("Routine name", key="routine_name")
st.text_area("Routine notes", key="routine_notes")
settings = st.columns(2)
settings[0].number_input("Default rest (seconds)", 0, 3600, step=15, key="routine_default_rest")
settings[1].checkbox("Start rest automatically after each set", key="routine_auto_rest")

remove_row = None
for index, row_id in enumerate(list(st.session_state["routine_rows"])):
    with st.container(border=True):
        st.markdown(f"**Exercise {index + 1}**")
        cols = st.columns([2, 0.8, 0.8, 0.8, 1, 1, 1])
        name_choice = cols[0].selectbox("Exercise", EXERCISES, key=_key(row_id, "name"))
        if name_choice == "Custom":
            cols[0].text_input("Custom name", key=_key(row_id, "custom"))
        cols[1].number_input("Sets", 1, 30, key=_key(row_id, "sets"))
        cols[2].number_input("Min reps", 1, 100, key=_key(row_id, "minimum"))
        cols[3].number_input("Max reps", 1, 100, key=_key(row_id, "maximum"))
        cols[4].checkbox("Starting load", key=_key(row_id, "weight_enabled"))
        cols[5].checkbox("Custom rest", key=_key(row_id, "rest_enabled"))
        if st.session_state[_key(row_id, "weight_enabled")]:
            weight_key = _key(row_id, "weight")
            ready_key = _key(row_id, "weight_ready")
            if not st.session_state.get(ready_key):
                source = st.session_state.get(_key(row_id, "weight_kg"))
                display = _display_weight(20.0 if source is None else float(source), unit)
                current = st.session_state.get(weight_key)
                if current is None or abs(float(current) - display) < 0.05 or float(current) == 0.0:
                    if weight_key in st.session_state:
                        del st.session_state[weight_key]
                    st.session_state[weight_key] = display
                st.session_state[ready_key] = True
            cols[4].number_input(f"Weight ({unit})", 0.0, 1000.0, step=2.5, key=weight_key)
        if st.session_state[_key(row_id, "rest_enabled")]:
            cols[5].number_input("Rest (sec)", 0, 3600, step=15, key=_key(row_id, "rest"))
        cols[6].text_input("Exercise notes", key=_key(row_id, "notes"))
        if len(st.session_state["routine_rows"]) > 1 and cols[6].button("Remove", key=f"remove_{row_id}"):
            remove_row = row_id

if remove_row:
    st.session_state["routine_rows"].remove(remove_row)
    for key in list(st.session_state):
        if key.startswith(f"routine_{remove_row}_"):
            del st.session_state[key]
    st.rerun()

add_col, save_col, delete_col = st.columns([1, 1.2, 1])
if add_col.button("Add exercise"):
    _add_row()
    st.rerun()
if save_col.button("Save routine", type="primary"):
    try:
        exercises = []
        for row_id in st.session_state["routine_rows"]:
            choice = st.session_state[_key(row_id, "name")]
            exercise_name = st.session_state[_key(row_id, "custom")] if choice == "Custom" else choice
            exercises.append(RoutineExerciseInput(
                exercise_name=exercise_name.strip(),
                sets=st.session_state[_key(row_id, "sets")],
                target_reps_min=st.session_state[_key(row_id, "minimum")],
                target_reps_max=st.session_state[_key(row_id, "maximum")],
                starting_weight_kg=(
                    _stored_weight(st.session_state[_key(row_id, "weight")], unit)
                    if st.session_state[_key(row_id, "weight_enabled")] else None
                ),
                rest_seconds=(st.session_state[_key(row_id, "rest")] if st.session_state[_key(row_id, "rest_enabled")] else None),
                notes=st.session_state[_key(row_id, "notes")],
            ))
        validated = WorkoutRoutineInput(
            name=st.session_state["routine_name"].strip(),
            notes=st.session_state["routine_notes"],
            default_rest_seconds=st.session_state["routine_default_rest"],
            auto_start_rest=st.session_state["routine_auto_rest"],
            exercises=exercises,
        )
        routine_id = routine_service.save_routine(validated, routine_id=st.session_state["routine_id"])
        for row_id in st.session_state["routine_rows"]:
            if st.session_state[_key(row_id, "weight_enabled")]:
                st.session_state[_key(row_id, "weight_kg")] = _stored_weight(
                    st.session_state[_key(row_id, "weight")], unit,
                )
            else:
                st.session_state[_key(row_id, "weight_kg")] = None
        st.session_state["routine_id"] = routine_id
        st.session_state["routine_pending_selection"] = f"{validated.name} · #{routine_id}"
        st.success("Routine saved. It is available from Live Workout.")
        st.rerun()
    except Exception as error:
        st.error(f"Routine not saved: {error}")
if st.session_state["routine_id"] is not None and delete_col.button("Delete routine"):
    routine_service.delete_routine(st.session_state["routine_id"])
    st.session_state["routine_id"] = None
    st.session_state["routine_pending_selection"] = "New routine"
    st.session_state["routine_reset_editor"] = True
    st.rerun()