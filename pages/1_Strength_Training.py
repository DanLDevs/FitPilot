from datetime import date
from uuid import uuid4

import pandas as pd
import streamlit as st

from models.schemas import (
    StrengthExerciseLogInput,
    StrengthSetLogInput,
    StrengthWorkoutLogInput,
)
from services import database, progression_service, routine_service, strength_service
from utils.calculations import kg_to_pounds, pounds_to_kg


st.set_page_config(page_title="Strength | FitPilot", page_icon="F", layout="wide")
database.init_database()
profile = database.get_profile()
st.title("Strength training")
st.caption("Record sessions, monitor working volume, and revisit your lifting history.")
if profile is None:
    st.warning("Set up your athlete profile on the Dashboard before logging workouts.")
    st.stop()


def _set_key(set_id: str, field: str) -> str:
    return f"sl_set_{set_id}_{field}"


def _exercise_key(exercise_id: str, field: str) -> str:
    return f"sl_ex_{exercise_id}_{field}"


def _add_set(exercise_id: str, starting_weight_kg: float = 20.0, reps: int | None = None) -> None:
    unit = st.session_state.get("sl_weight_unit", "kg")
    starting_weight = starting_weight_kg if unit == "kg" else kg_to_pounds(starting_weight_kg)
    set_id = uuid4().hex[:10]
    exercise = next(item for item in st.session_state["sl_exercises"] if item["id"] == exercise_id)
    exercise["set_ids"].append(set_id)
    exercise["set_defaults"][set_id] = {
        "reps": reps or st.session_state.get(_exercise_key(exercise_id, "target_min"), 8),
        "weight": starting_weight,
        "rpe": 7.0,
    }
    st.session_state[_set_key(set_id, "pain")] = False
    st.session_state[_set_key(set_id, "technique")] = False
    st.session_state[_set_key(set_id, "notes")] = ""


def _add_exercise(name: str = "Bench Press", target_min: int = 8, target_max: int = 12, sets: int = 3, weight_kg: float = 20.0) -> None:
    exercise_id = uuid4().hex[:10]
    st.session_state["sl_exercises"].append({"id": exercise_id, "set_ids": [], "set_defaults": {}})
    st.session_state[_exercise_key(exercise_id, "name")] = name if name in common_exercises else "Custom"
    st.session_state[_exercise_key(exercise_id, "custom_name")] = name if name not in common_exercises else ""
    st.session_state[_exercise_key(exercise_id, "target_min")] = target_min
    st.session_state[_exercise_key(exercise_id, "target_max")] = target_max
    for _ in range(sets):
        _add_set(exercise_id, weight_kg, target_min)


def _clear_log_entries() -> None:
    for key in list(st.session_state):
        if key.startswith(("sl_ex_", "sl_set_")):
            del st.session_state[key]
    st.session_state["sl_exercises"] = []


def _load_selected_routine() -> None:
    _clear_log_entries()
    routine_id = st.session_state.get("sl_template_id")
    if routine_id is None:
        st.session_state["sl_session_name"] = "Full Body"
        _add_exercise()
        return
    routine = routine_service.get_routine(routine_id)
    if routine is None:
        _add_exercise()
        return
    st.session_state["sl_session_name"] = routine["name"]
    for exercise in routine["exercises"]:
        _add_exercise(
            name=exercise["exercise_name"],
            target_min=exercise["target_reps_min"],
            target_max=exercise["target_reps_max"],
            sets=exercise["sets"],
            weight_kg=exercise["starting_weight_kg"] or 20.0,
        )


def _convert_logged_weights() -> None:
    old_unit = st.session_state.get("sl_previous_weight_unit", "kg")
    new_unit = st.session_state.get("sl_weight_unit", "kg")
    if old_unit == new_unit:
        return
    for exercise in st.session_state.get("sl_exercises", []):
        for set_id in exercise["set_ids"]:
            key = _set_key(set_id, "weight")
            value = st.session_state.get(key, exercise["set_defaults"][set_id]["weight"])
            converted = kg_to_pounds(value) if new_unit == "lb" else pounds_to_kg(value)
            exercise["set_defaults"][set_id]["weight"] = converted
            if key in st.session_state:
                del st.session_state[key]
    st.session_state["sl_previous_weight_unit"] = new_unit


common_exercises = [
    "Bench Press", "Squat", "Deadlift", "Overhead Press", "Barbell Row", "Pull-Up",
    "Lat Pulldown", "Bicep Curl", "Tricep Pushdown", "Leg Press", "Romanian Deadlift",
    "Dumbbell Bench Press", "Custom",
]
if "sl_exercises" not in st.session_state:
    st.session_state["sl_exercises"] = []
    st.session_state["sl_session_name"] = "Full Body"
    st.session_state["sl_weight_unit"] = "kg"
    st.session_state["sl_previous_weight_unit"] = "kg"
    st.session_state["sl_template_id"] = None
    _add_exercise()
if st.session_state.pop("sl_reset_name_after_save", False):
    st.session_state["sl_session_name"] = "Full Body"
if st.session_state.pop("sl_reset_template_after_save", False):
    st.session_state["sl_template_id"] = None
    st.session_state["sl_template_label"] = "Blank workout"

tab_log, tab_history, tab_progress = st.tabs(["Log session", "History and edits", "Progress"])
with tab_log:
    routines = routine_service.list_routines()
    routine_labels = {f"#{routine['id']} · {routine['name']}": routine["id"] for routine in routines}
    template_options = ["Blank workout", *routine_labels]
    template_to_id = {label: routine_id for label, routine_id in routine_labels.items()}
    current_template = next((label for label, routine_id in routine_labels.items() if routine_id == st.session_state["sl_template_id"]), "Blank workout")
    selected_template = st.selectbox(
        "Start from a saved routine", template_options,
        index=template_options.index(current_template), key="sl_template_label",
    )
    selected_template_id = template_to_id.get(selected_template)
    if selected_template_id != st.session_state["sl_template_id"]:
        st.session_state["sl_template_id"] = selected_template_id
        _load_selected_routine()
        st.rerun()

    header1, header2, header3 = st.columns([1.5, 1, 1])
    workout_date = header1.date_input("Workout date", value=date.today(), key="sl_workout_date")
    session_name = header2.text_input("Session name", key="sl_session_name")
    unit = header3.radio("Weight unit", ["kg", "lb"], horizontal=True, key="sl_weight_unit", on_change=_convert_logged_weights)
    st.caption("Weights are stored in kilograms. Set reps, load, and effort are recorded individually.")

    remove_exercise_id = None
    for index, exercise in enumerate(list(st.session_state["sl_exercises"])):
        exercise_id = exercise["id"]
        with st.expander(f"Exercise {index + 1}", expanded=True):
            exercise_cols = st.columns([2, 1, 1, 1])
            choice = exercise_cols[0].selectbox("Exercise", common_exercises, key=_exercise_key(exercise_id, "name"))
            if choice == "Custom":
                exercise_name = exercise_cols[0].text_input("Custom exercise name", key=_exercise_key(exercise_id, "custom_name"))
            else:
                exercise_name = choice
            target_min = exercise_cols[1].number_input("Target reps, min", 1, 100, key=_exercise_key(exercise_id, "target_min"))
            target_max = exercise_cols[2].number_input("Target reps, max", 1, 100, key=_exercise_key(exercise_id, "target_max"))
            if len(st.session_state["sl_exercises"]) > 1 and exercise_cols[3].button("Remove exercise", key=f"sl_remove_ex_{exercise_id}"):
                remove_exercise_id = exercise_id

            for set_index, set_id in enumerate(list(exercise["set_ids"])):
                st.markdown(f"**Set {set_index + 1}**")
                set_cols = st.columns([1, 1.2, 1, 0.8, 1, 1.6])
                defaults = exercise["set_defaults"][set_id]
                set_cols[0].number_input("Reps", 1, 100, value=defaults["reps"], key=_set_key(set_id, "reps"))
                set_cols[1].number_input(f"Weight ({unit})", 0.0, 1000.0, value=defaults["weight"], step=2.5, key=_set_key(set_id, "weight"))
                set_cols[2].number_input("RPE", 1.0, 10.0, value=defaults["rpe"], step=0.5, key=_set_key(set_id, "rpe"))
                set_cols[3].checkbox("Pain", key=_set_key(set_id, "pain"))
                set_cols[4].checkbox("Technique concern", key=_set_key(set_id, "technique"))
                set_cols[5].text_input("Set notes", key=_set_key(set_id, "notes"))
            add_set_col, remove_set_col, _ = st.columns([1, 1, 4])
            if add_set_col.button("Add set", key=f"sl_add_set_{exercise_id}"):
                _add_set(exercise_id)
                st.rerun()
            if len(exercise["set_ids"]) > 1 and remove_set_col.button("Remove last set", key=f"sl_remove_set_{exercise_id}"):
                removed_set_id = exercise["set_ids"].pop()
                exercise["set_defaults"].pop(removed_set_id, None)
                for key in list(st.session_state):
                    if key.startswith(f"sl_set_{removed_set_id}_"):
                        del st.session_state[key]
                st.rerun()

    if remove_exercise_id is not None:
        st.session_state["sl_exercises"] = [item for item in st.session_state["sl_exercises"] if item["id"] != remove_exercise_id]
        for key in list(st.session_state):
            if key.startswith(f"sl_ex_{remove_exercise_id}_"):
                del st.session_state[key]
        st.rerun()

    if st.button("Add Exercise", type="secondary", key="sl_add_exercise"):
        _add_exercise()
        st.rerun()
    workout_notes = st.text_area("Session notes", key="sl_workout_notes")
    if st.button("Save strength session", type="primary", key="sl_save_workout"):
        try:
            validated = StrengthWorkoutLogInput(
                workout_date=workout_date,
                session_name=session_name.strip(),
                notes=workout_notes,
                exercises=[
                    StrengthExerciseLogInput(
                        exercise_name=(st.session_state[_exercise_key(exercise["id"], "custom_name")]
                                       if st.session_state[_exercise_key(exercise["id"], "name")] == "Custom"
                                       else st.session_state[_exercise_key(exercise["id"], "name")]).strip(),
                        target_reps_min=st.session_state[_exercise_key(exercise["id"], "target_min")],
                        target_reps_max=st.session_state[_exercise_key(exercise["id"], "target_max")],
                        sets=[StrengthSetLogInput(
                            reps=st.session_state[_set_key(set_id, "reps")],
                            weight_kg=(pounds_to_kg(st.session_state[_set_key(set_id, "weight")]) if unit == "lb" else st.session_state[_set_key(set_id, "weight")]),
                            rpe=st.session_state[_set_key(set_id, "rpe")],
                            pain=st.session_state[_set_key(set_id, "pain")],
                            technique_concern=st.session_state[_set_key(set_id, "technique")],
                            notes=st.session_state[_set_key(set_id, "notes")],
                        ) for set_id in exercise["set_ids"]],
                    ) for exercise in st.session_state["sl_exercises"]
                ],
            )
            strength_service.add_workout(validated)
            st.success("Strength session saved.")
            _clear_log_entries()
            st.session_state["sl_template_id"] = None
            st.session_state["sl_reset_name_after_save"] = True
            st.session_state["sl_reset_template_after_save"] = True
            _add_exercise()
            st.rerun()
        except Exception as error:
            st.error(f"Session not saved: {error}")

with tab_history:
    workouts = strength_service.list_workouts()
    if not workouts:
        st.info("No strength sessions recorded yet.")
    else:
        st.dataframe([
            {"ID": row["id"], "Date": row["workout_date"], "Session": row["session_name"],
             "Sets": row["set_count"], "Volume (lb)": round(kg_to_pounds(row["volume_kg"]))}
            for row in workouts
        ], hide_index=True, use_container_width=True)
        selected_id = st.selectbox("Select a session to edit or delete", [row["id"] for row in workouts], format_func=lambda value: next(f"{row['workout_date']} · {row['session_name']} · #{row['id']}" for row in workouts if row["id"] == value))
        selected = strength_service.get_workout(selected_id)
        st.markdown("**Edit selected session**")
        edit_date = st.date_input("Date", date.fromisoformat(selected["workout_date"]), key=f"edit_date_{selected_id}")
        edit_name = st.text_input("Session name", selected["session_name"], key=f"edit_name_{selected_id}")
        edit_notes = st.text_input("Session notes", selected["notes"], key=f"edit_notes_{selected_id}")
        edit_exercises = []
        for index, exercise in enumerate(selected["exercises"]):
            exercise_id = f"{selected_id}_{index}"
            st.markdown(f"**{exercise['exercise_name']} target range**")
            target_enabled = st.checkbox(
                "Track a target range", value=exercise["target_reps_min"] is not None,
                key=f"edit_target_enabled_{exercise_id}",
            )
            target_min = target_max = None
            if target_enabled:
                target_cols = st.columns(2)
                target_min = target_cols[0].number_input("Target reps, min", 1, 100, int(exercise["target_reps_min"] or 8), key=f"edit_target_min_{exercise_id}")
                target_max = target_cols[1].number_input("Target reps, max", 1, 100, int(exercise["target_reps_max"] or 12), key=f"edit_target_max_{exercise_id}")
            edit_sets = []
            for set_row in exercise["working_sets"]:
                set_id = set_row["id"]
                cols = st.columns([1, 1, 1, 1, 1, 1.5])
                reps = cols[0].number_input("Reps", 1, 100, int(set_row["reps"]), key=f"edit_reps_{set_id}")
                weight = cols[1].number_input("Weight (kg)", 0.0, 1000.0, float(set_row["weight_kg"]), key=f"edit_weight_{set_id}")
                rpe = cols[2].number_input("RPE", 1.0, 10.0, float(set_row["rpe"] or 7), key=f"edit_rpe_{set_id}")
                pain = cols[3].checkbox("Pain", bool(set_row["pain"]), key=f"edit_pain_{set_id}")
                technique = cols[4].checkbox("Technique", bool(set_row["technique_concern"]), key=f"edit_technique_{set_id}")
                notes = cols[5].text_input("Set notes", set_row["notes"], key=f"edit_notes_{set_id}")
                edit_sets.append(StrengthSetLogInput(
                    reps=reps, weight_kg=weight, rpe=rpe, pain=pain,
                    technique_concern=technique, notes=notes,
                ))
            edit_exercises.append(StrengthExerciseLogInput(
                exercise_name=exercise["exercise_name"],
                target_reps_min=target_min, target_reps_max=target_max,
                sets=edit_sets,
            ))
        update, delete = st.columns(2)
        with update:
            update_clicked = st.button("Save edits", type="primary", key=f"save_edit_{selected_id}")
        with delete:
            delete_clicked = st.button("Delete session", key=f"delete_edit_{selected_id}")
        if update_clicked:
            try:
                updated = StrengthWorkoutLogInput(
                    workout_date=edit_date, session_name=edit_name.strip(), notes=edit_notes,
                    exercises=edit_exercises,
                )
                strength_service.update_workout(selected_id, updated)
                st.success("Session updated.")
                st.rerun()
            except Exception as error:
                st.error(f"Session not updated: {error}")
        if delete_clicked:
            strength_service.delete_workout(selected_id)
            st.success("Session deleted.")
            st.rerun()

with tab_progress:
    rows = strength_service.list_sets()
    if rows:
        frame = pd.DataFrame(rows)
        options = sorted(frame["exercise_name"].unique())
        selected_exercise = st.selectbox("Exercise", options)
        recommendation = progression_service.recommend_progression(rows, selected_exercise)
        st.markdown("**Progression check**")
        if recommendation["status"] == "increase":
            st.success(recommendation["explanation"])
        elif recommendation["status"] == "caution":
            st.warning(recommendation["explanation"])
        elif recommendation["status"] == "insufficient":
            st.info(recommendation["explanation"])
        else:
            st.info(recommendation["explanation"])
        metrics = recommendation["supporting_metrics"]
        if metrics:
            st.caption(
                f"Latest session: {metrics['date']} · {metrics['sets']} sets · "
                f"{metrics['average_reps']:.1f} avg reps · {metrics['average_weight_kg']:.1f} kg avg load"
            )
        progression = frame[frame["exercise_name"] == selected_exercise].groupby("workout_date", as_index=False).agg(weight_kg=("weight_kg", "max"), reps=("reps", "max"))
        progression["Weight"] = progression["weight_kg"].map(kg_to_pounds)
        st.line_chart(progression.set_index("workout_date")[["Weight"]], y_label="Maximum weight (lb)")
        st.dataframe(progression[["workout_date", "Weight", "reps"]].rename(columns={"workout_date": "Date", "reps": "Best reps"}), hide_index=True)
    else:
        st.info("Log a few strength sessions to see exercise progression.")