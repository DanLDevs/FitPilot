from uuid import uuid4

import streamlit as st

from models.schemas import RoutineExerciseInput, WorkoutRoutineInput
from services import database, routine_service


st.set_page_config(page_title="Workout Routines | FitPilot", page_icon="F", layout="wide")
database.init_database()
profile = database.get_profile()
st.title("Workout routines")
st.caption("Create reusable templates for your live sessions.")
if profile is None:
    st.warning("Set up your athlete profile on the Dashboard before creating routines.")
    st.stop()

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
    st.session_state[_key(row_id, "weight_enabled")] = exercise.get("starting_weight_kg") is not None
    st.session_state[_key(row_id, "weight")] = float(exercise.get("starting_weight_kg") or 20)
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
            cols[4].number_input("Weight (kg)", 0.0, 1000.0, step=2.5, key=_key(row_id, "weight"))
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
                starting_weight_kg=(st.session_state[_key(row_id, "weight")] if st.session_state[_key(row_id, "weight_enabled")] else None),
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