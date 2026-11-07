from uuid import uuid4

import streamlit as st

from models.schemas import RoutineExerciseInput, WorkoutRoutineInput
from services import database, gemini_service, routine_service


st.set_page_config(page_title="Workout Routines | FitPilot", page_icon="F", layout="wide")
database.init_database()
profile = database.get_profile()
st.title("Workout routines")
st.caption("Build a reusable workout yourself, or review an optional AI-generated draft.")
if profile is None:
    st.warning("Set up your athlete profile on the Dashboard before creating routines.")
    st.stop()

EXERCISES = [
    "Bench Press", "Squat", "Deadlift", "Overhead Press", "Barbell Row", "Pull-Up",
    "Lat Pulldown", "Bicep Curl", "Tricep Pushdown", "Leg Press", "Romanian Deadlift",
    "Dumbbell Bench Press", "Custom",
]


def _row_key(row_id: str, field: str) -> str:
    return f"rt_{row_id}_{field}"


def _add_row(exercise: dict | None = None) -> None:
    row_id = uuid4().hex[:10]
    st.session_state["rt_rows"].append(row_id)
    exercise = exercise or {}
    name = exercise.get("exercise_name", "Bench Press")
    st.session_state[_row_key(row_id, "exercise")] = name if name in EXERCISES else "Custom"
    st.session_state[_row_key(row_id, "custom")]= "" if name in EXERCISES else name
    st.session_state[_row_key(row_id, "sets")] = int(exercise.get("sets", 3))
    st.session_state[_row_key(row_id, "minimum")] = int(exercise.get("target_reps_min", 8))
    st.session_state[_row_key(row_id, "maximum")] = int(exercise.get("target_reps_max", 12))
    st.session_state[_row_key(row_id, "weight_enabled")] = exercise.get("starting_weight_kg") is not None
    st.session_state[_row_key(row_id, "weight")] = float(exercise.get("starting_weight_kg") or 20)
    st.session_state[_row_key(row_id, "notes")] = exercise.get("notes", "")


def _clear_editor() -> None:
    for row_id in st.session_state.get("rt_rows", []):
        for key in list(st.session_state):
            if key.startswith(f"rt_{row_id}_"):
                del st.session_state[key]
    for key in ("rt_name", "rt_notes"):
        if key in st.session_state:
            del st.session_state[key]
    st.session_state["rt_rows"] = []
    st.session_state["rt_id"] = None
    st.session_state["rt_name"] = ""
    st.session_state["rt_notes"] = ""


def _load_routine() -> None:
    routine_id = st.session_state.get("rt_selected_id")
    if routine_id is None:
        _clear_editor()
        st.session_state["rt_draft_ready"] = False
        _add_row()
        return
    routine = routine_service.get_routine(routine_id)
    if routine is None:
        return
    _clear_editor()
    st.session_state["rt_id"] = routine_id
    st.session_state["rt_draft_ready"] = False
    st.session_state["rt_name"] = routine["name"]
    st.session_state["rt_notes"] = routine["notes"]
    for exercise in routine["exercises"]:
        _add_row(exercise)


def _edit_saved_routine(routine_id: int) -> None:
    routine = routine_service.get_routine(routine_id)
    if routine is None:
        return
    st.session_state["rt_selected_id"] = routine_id
    st.session_state["rt_selected_label"] = f"Edit: {routine['name']} · #{routine_id}"
    st.session_state["rt_mode"] = "Build manually"
    _load_routine()


def _populate_from_draft(draft: WorkoutRoutineInput) -> None:
    _clear_editor()
    st.session_state["rt_name"] = draft.name
    st.session_state["rt_notes"] = draft.notes
    for exercise in draft.exercises:
        _add_row(exercise.model_dump())
    st.session_state["rt_draft_ready"] = True


if "rt_rows" not in st.session_state:
    st.session_state["rt_rows"] = []
    st.session_state["rt_id"] = None
    st.session_state["rt_name"] = ""
    st.session_state["rt_notes"] = ""
    st.session_state["rt_selected_id"] = None
    st.session_state["rt_draft_ready"] = False
    _add_row()

builder_tab, saved_tab = st.tabs(["Create routine", "Saved routines"])
with builder_tab:
    routines = routine_service.list_routines()
    routine_options = {"New routine": None}
    routine_options.update({f"Edit: {routine['name']} · #{routine['id']}": routine["id"] for routine in routines})
    current_label = next((label for label, item_id in routine_options.items() if item_id == st.session_state["rt_selected_id"]), "New routine")
    if st.session_state.get("rt_selected_label") not in routine_options:
        st.session_state["rt_selected_label"] = current_label
    elif st.session_state["rt_selected_id"] is not None:
        st.session_state["rt_selected_label"] = current_label

    def on_routine_selection_change() -> None:
        st.session_state["rt_selected_id"] = routine_options[st.session_state["rt_selected_label"]]
        _load_routine()

    st.selectbox(
        "Start new or edit a saved routine", list(routine_options),
        key="rt_selected_label", on_change=on_routine_selection_change,
    )
    mode = st.radio("Routine builder", ["Build manually", "Ask Gemini for a draft"], horizontal=True, key="rt_mode")

    if mode == "Ask Gemini for a draft":
        st.caption("Gemini uses your profile to propose an editable draft. Nothing is saved until you choose Save routine.")
        if st.button("Generate routine draft", type="primary", key="rt_generate"):
            try:
                generated = gemini_service.generate_routine_draft(profile)
                _populate_from_draft(generated)
                st.success("Draft generated. Review and edit every exercise before saving.")
                st.rerun()
            except gemini_service.GeminiRoutineError as error:
                st.error(str(error))
        if not st.session_state["rt_draft_ready"] and st.session_state["rt_id"] is None:
            st.info("Manual routine building remains available without Gemini credentials.")

    if mode == "Build manually" or st.session_state["rt_draft_ready"] or st.session_state["rt_id"] is not None:
        st.text_input("Routine name", key="rt_name")
        st.text_area("Routine notes", key="rt_notes")
        remove_row_id = None
        for index, row_id in enumerate(list(st.session_state["rt_rows"])):
            with st.container(border=True):
                st.markdown(f"**Exercise {index + 1}**")
                cols = st.columns([2, 1, 1, 1, 1, 0.8])
                selected_name = cols[0].selectbox("Exercise", EXERCISES, key=_row_key(row_id, "exercise"))
                if selected_name == "Custom":
                    cols[0].text_input("Custom name", key=_row_key(row_id, "custom"))
                cols[1].number_input("Sets", 1, 30, key=_row_key(row_id, "sets"))
                cols[2].number_input("Min reps", 1, 100, key=_row_key(row_id, "minimum"))
                cols[3].number_input("Max reps", 1, 100, key=_row_key(row_id, "maximum"))
                cols[4].checkbox("Starting load", key=_row_key(row_id, "weight_enabled"))
                if st.session_state[_row_key(row_id, "weight_enabled")]:
                    cols[4].number_input("Weight (kg)", 0.0, 1000.0, step=2.5, key=_row_key(row_id, "weight"))
                cols[5].text_input("Notes", key=_row_key(row_id, "notes"))
                if len(st.session_state["rt_rows"]) > 1 and cols[5].button("Remove", key=f"rt_remove_{row_id}"):
                    remove_row_id = row_id

        if remove_row_id is not None:
            st.session_state["rt_rows"].remove(remove_row_id)
            for key in list(st.session_state):
                if key.startswith(f"rt_{remove_row_id}_"):
                    del st.session_state[key]
            st.rerun()
        if st.button("Add exercise", key="rt_add_exercise"):
            _add_row()
            st.rerun()

        save_col, cancel_col, _ = st.columns([1.2, 1.2, 4])
        if save_col.button("Save routine", type="primary", key="rt_save"):
            try:
                exercises = []
                for row_id in st.session_state["rt_rows"]:
                    exercise_name = st.session_state[_row_key(row_id, "exercise")]
                    if exercise_name == "Custom":
                        exercise_name = st.session_state[_row_key(row_id, "custom")]
                    exercises.append(RoutineExerciseInput(
                        exercise_name=exercise_name.strip(),
                        sets=st.session_state[_row_key(row_id, "sets")],
                        target_reps_min=st.session_state[_row_key(row_id, "minimum")],
                        target_reps_max=st.session_state[_row_key(row_id, "maximum")],
                        starting_weight_kg=(st.session_state[_row_key(row_id, "weight")]
                                             if st.session_state[_row_key(row_id, "weight_enabled")] else None),
                        notes=st.session_state[_row_key(row_id, "notes")],
                    ))
                validated = WorkoutRoutineInput(
                    name=st.session_state["rt_name"].strip(),
                    notes=st.session_state["rt_notes"],
                    exercises=exercises,
                )
                saved_routine_id = routine_service.save_routine(validated, routine_id=st.session_state["rt_id"])
                st.session_state["rt_id"] = saved_routine_id
                st.session_state["rt_selected_id"] = saved_routine_id
                st.session_state["rt_draft_ready"] = False
                st.success("Routine saved. It is now available in the strength logger.")
                st.rerun()
            except Exception as error:
                st.error(f"Routine not saved: {error}")
        if cancel_col.button("Discard draft", key="rt_cancel"):
            _clear_editor()
            st.session_state["rt_draft_ready"] = False
            _add_row()
            st.rerun()

with saved_tab:
    routines = routine_service.list_routines()
    if not routines:
        st.info("You haven't saved any routines yet.")
    else:
        for routine in routines:
            with st.container(border=True):
                st.subheader(routine["name"])
                if routine["notes"]:
                    st.caption(routine["notes"])
                st.dataframe([
                    {"Exercise": exercise["exercise_name"], "Sets": exercise["sets"],
                     "Target reps": f"{exercise['target_reps_min']}-{exercise['target_reps_max']}",
                     "Starting weight (kg)": exercise["starting_weight_kg"]}
                    for exercise in routine["exercises"]
                ], hide_index=True, use_container_width=True)
                edit_col, duplicate_col, delete_col = st.columns(3)
                edit_col.button(
                    "Edit", key=f"rt_edit_{routine['id']}",
                    on_click=_edit_saved_routine, args=(routine["id"],),
                )
                if duplicate_col.button("Duplicate", key=f"rt_duplicate_{routine['id']}"):
                    routine_service.duplicate_routine(routine["id"])
                    st.success("Routine duplicated.")
                    st.rerun()
                if delete_col.button("Delete", key=f"rt_delete_{routine['id']}"):
                    routine_service.delete_routine(routine["id"])
                    st.success("Routine deleted.")
                    st.rerun()