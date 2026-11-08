from datetime import date
from uuid import uuid4

import pandas as pd
import streamlit as st

from models.schemas import StrengthSetInput, StrengthWorkoutInput
from services import database, routine_service, strength_service
from services.log_defaults import strength_log_defaults
from utils.calculations import kg_to_pounds, pounds_to_kg
from services import progression_service


st.set_page_config(page_title="Strength | FitPilot", page_icon="F", layout="wide")
database.init_database()
profile = database.get_profile()
st.title("Strength training")
st.caption("Record sessions, monitor working volume, and revisit your lifting history.")
if profile is None:
    st.warning("Set up your athlete profile on the Dashboard before logging workouts.")
    st.stop()
unit = profile.get("weight_unit") if profile.get("weight_unit") in ("kg", "lb") else "kg"

def _seed(key: str, value) -> None:
    if key not in st.session_state:
        st.session_state[key] = value


def _display_weight(weight_kg: float, unit: str) -> float:
    if unit == "lb":
        return round(kg_to_pounds(weight_kg), 1)
    return float(weight_kg)


def _stored_weight(weight: float, unit: str) -> float:
    return pounds_to_kg(weight) if unit == "lb" else float(weight)


def _seed_logged_weight(weight_key: str, suggested_kg: float, unit: str) -> None:
    suggested = min(1000.0, max(0.0, _display_weight(suggested_kg, unit)))
    unit_key = f"{weight_key}_unit"
    if weight_key not in st.session_state:
        st.session_state[weight_key] = suggested
        st.session_state[unit_key] = unit
        return
    previous_unit = st.session_state.get(unit_key)
    if previous_unit == unit:
        return
    previous_suggested = min(1000.0, max(0.0, _display_weight(suggested_kg, previous_unit or "kg")))
    if abs(float(st.session_state[weight_key]) - previous_suggested) < 0.05:
        st.session_state[weight_key] = suggested
    st.session_state[unit_key] = unit


def _show_session_cue(cue: dict, unit: str) -> None:
    message = progression_service.format_session_cue(cue, unit)
    if cue["status"] == "increase":
        st.success(message)
    elif cue["status"] == "caution":
        st.warning(message)
    else:
        st.info(message)


def _save_strength_session(workout_date, session_name, workout_notes, unit, exercises) -> None:
    try:
        validated = StrengthWorkoutInput(
            workout_date=workout_date, session_name=session_name.strip(), notes=workout_notes,
            exercises=[StrengthSetInput(
                exercise_name=name.strip(), sets=sets, reps=reps,
                weight_kg=_stored_weight(weight, unit),
                rpe=rpe, pain=pain, notes=note,
            ) for name, sets, reps, weight, rpe, pain, note in exercises],
        )
        strength_service.add_workout(validated)
        st.success("Strength session saved.")
    except Exception as error:
        st.error(f"Session not saved: {error}")


tab_log, tab_history, tab_progress = st.tabs(["Log session", "History and edits", "Progress"])
with tab_log:
    routines = routine_service.list_routines()
    routine_labels = {"Log from scratch": None}
    routine_labels.update({f"{routine['name']} · #{routine['id']}": routine["id"] for routine in routines})
    selected_routine = None
    if routines:
        selected_label = st.selectbox("Start from a routine", list(routine_labels), key="strength_log_routine")
        selected_id = routine_labels[selected_label]
        selected_routine = next((routine for routine in routines if routine["id"] == selected_id), None)

    if selected_routine is None:
        for index in range(8):
            _seed_logged_weight(f"weight_{index}", 20.0, unit)
        with st.form("strength_log"):
            top1, top2, top3 = st.columns(3)
            with top1:
                workout_date = st.date_input("Workout date", value=date.today())
                session_name = st.selectbox("Session", ["Upper Body", "Lower Body", "Push", "Pull", "Full Body", "Custom"])
                if session_name == "Custom":
                    session_name = st.text_input("Session name")
            with top2:
                exercise_count = st.number_input("Exercises", min_value=1, max_value=8, value=3)
            with top3:
                workout_notes = st.text_input("Session notes", placeholder="Optional")

            exercises = []
            common_exercises = ["Bench Press", "Squat", "Deadlift", "Overhead Press", "Barbell Row", "Pull-Up", "Lat Pulldown", "Bicep Curl", "Tricep Pushdown", "Leg Press", "Romanian Deadlift", "Dumbbell Bench Press", "Custom"]
            for index in range(int(exercise_count)):
                st.markdown(f"**Exercise {index + 1}**")
                columns = st.columns([2, 1, 1, 1, 1, 1])
                exercise_name = columns[0].selectbox("Exercise", common_exercises, key=f"exercise_{index}")
                if exercise_name == "Custom":
                    exercise_name = columns[0].text_input("Custom name", key=f"custom_exercise_{index}")
                sets = columns[1].number_input("Sets", 1, 20, 3, key=f"sets_{index}")
                reps = columns[2].number_input("Reps / set", 1, 100, 8, key=f"reps_{index}")
                weight = columns[3].number_input(f"Weight ({unit})", 0.0, 1000.0, step=2.5, key=f"weight_{index}")
                rpe = columns[4].number_input("RPE", 1.0, 10.0, 7.0, step=0.5, key=f"rpe_{index}")
                pain = columns[5].checkbox("Pain", key=f"pain_{index}")
                note = st.text_input("Exercise notes", key=f"exercise_note_{index}")
                exercises.append((exercise_name, int(sets), int(reps), float(weight), float(rpe), pain, note))

            submitted = st.form_submit_button("Save strength session", type="primary")
        if submitted:
            _save_strength_session(workout_date, session_name, workout_notes, unit, exercises)
    else:
        defaults = strength_log_defaults(selected_routine)
        routine_id = selected_routine["id"]
        historical_sets = strength_service.list_sets()
        with st.form(f"strength_log_{routine_id}"):
            top1, top2 = st.columns(2)
            with top1:
                workout_date = st.date_input("Workout date", value=date.today(), key=f"log_strength_date_{routine_id}")
                _seed(f"log_strength_session_{routine_id}", defaults["session_name"])
                session_name = st.text_input("Session name", key=f"log_strength_session_{routine_id}")
            with top2:
                _seed(f"log_strength_notes_{routine_id}", defaults["notes"])
                workout_notes = st.text_input("Session notes", key=f"log_strength_notes_{routine_id}")

            exercises = []
            for index, exercise in enumerate(defaults["exercises"]):
                routine_exercise = selected_routine["exercises"][index]
                cue = progression_service.session_cue(
                    historical_sets,
                    routine_exercise["exercise_name"],
                    routine_exercise["target_reps_min"],
                    routine_exercise["target_reps_max"],
                    starting_weight_kg=routine_exercise.get("starting_weight_kg"),
                )
                st.markdown(f"**{routine_exercise['exercise_name']}**")
                _show_session_cue(cue, unit)
                columns = st.columns([2, 1, 1, 1, 1, 1])
                name_key = f"log_strength_name_{routine_id}_{index}"
                sets_key = f"log_strength_sets_{routine_id}_{index}"
                reps_key = f"log_strength_reps_{routine_id}_{index}"
                weight_key = f"log_strength_weight_{routine_id}_{index}"
                rpe_key = f"log_strength_rpe_{routine_id}_{index}"
                pain_key = f"log_strength_pain_{routine_id}_{index}"
                note_key = f"log_strength_exercise_note_{routine_id}_{index}"
                _seed(name_key, exercise["exercise_name"])
                _seed(sets_key, min(20, max(1, exercise["sets"])))
                _seed(reps_key, min(100, max(1, exercise["reps"])))
                _seed_logged_weight(weight_key, cue["suggested_weight_kg"], unit)
                _seed(rpe_key, 7.0)
                _seed(pain_key, False)
                _seed(note_key, exercise["notes"])
                exercise_name = columns[0].text_input("Exercise", key=name_key)
                sets = columns[1].number_input("Sets", 1, 20, key=sets_key)
                reps = columns[2].number_input("Reps / set", 1, 100, key=reps_key)
                weight = columns[3].number_input(f"Weight ({unit})", 0.0, 1000.0, step=2.5, key=weight_key)
                rpe = columns[4].number_input("RPE", 1.0, 10.0, step=0.5, key=rpe_key)
                pain = columns[5].checkbox("Pain", key=pain_key)
                note = st.text_input("Exercise notes", key=note_key)
                exercises.append((exercise_name, int(sets), int(reps), float(weight), float(rpe), pain, note))

            submitted = st.form_submit_button("Save strength session", type="primary")
        if submitted:
            _save_strength_session(workout_date, session_name, workout_notes, unit, exercises)

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
        with st.form(f"edit_strength_{selected_id}"):
            edit_date = st.date_input("Date", date.fromisoformat(selected["workout_date"]), key=f"edit_date_{selected_id}")
            edit_name = st.text_input("Session name", selected["session_name"], key=f"edit_name_{selected_id}")
            edit_notes = st.text_input("Session notes", selected["notes"], key=f"edit_notes_{selected_id}")
            edit_sets = []
            if not selected["exercises"]:
                st.caption("This session has no completed sets.")
            for exercise in selected["exercises"]:
                st.caption(f"{exercise['exercise_name']} · set {exercise['set_number']}")
                cols = st.columns(4)
                set_id = exercise["id"]
                name = cols[0].text_input("Exercise", exercise["exercise_name"], key=f"edit_exercise_{selected_id}_{set_id}")
                reps = cols[1].number_input("Reps", 1, 100, int(exercise["reps"]), key=f"edit_reps_{selected_id}_{set_id}")
                weight_key = f"edit_weight_{selected_id}_{set_id}"
                _seed_logged_weight(weight_key, float(exercise["weight_kg"]), unit)
                weight = cols[2].number_input(f"Weight ({unit})", 0.0, 1000.0, step=2.5, key=weight_key)
                rpe = cols[3].number_input(
                    "RPE", min_value=1.0, max_value=10.0, step=0.5,
                    value=None if exercise["rpe"] is None else float(exercise["rpe"]),
                    key=f"edit_rpe_{selected_id}_{set_id}",
                )
                edit_sets.append({
                    "id": set_id, "exercise_name": name, "reps": int(reps),
                    "weight_kg": _stored_weight(float(weight), unit), "rpe": rpe,
                })
            update, delete = st.columns(2)
            with update:
                update_clicked = st.form_submit_button("Save edits", type="primary")
            with delete:
                delete_clicked = st.form_submit_button("Delete session")
        if update_clicked:
            try:
                strength_service.update_workout(selected_id, edit_date, edit_name.strip(), edit_notes, edit_sets)
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