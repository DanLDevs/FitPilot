from datetime import date

import pandas as pd
import streamlit as st

from models.schemas import StrengthSetInput, StrengthWorkoutInput
from services import database, routine_service, strength_service
from services.log_defaults import strength_log_defaults
from utils.calculations import kg_to_pounds, pounds_to_kg


st.set_page_config(page_title="Strength | FitPilot", page_icon="F", layout="wide")
database.init_database()
profile = database.get_profile()
st.title("Strength training")
st.caption("Record sessions, monitor working volume, and revisit your lifting history.")
if profile is None:
    st.warning("Set up your athlete profile on the Dashboard before logging workouts.")
    st.stop()

def _seed(key: str, value) -> None:
    if key not in st.session_state:
        st.session_state[key] = value


def _save_strength_session(workout_date, session_name, workout_notes, unit, exercises) -> None:
    try:
        validated = StrengthWorkoutInput(
            workout_date=workout_date, session_name=session_name.strip(), notes=workout_notes,
            exercises=[StrengthSetInput(
                exercise_name=name.strip(), sets=sets, reps=reps,
                weight_kg=pounds_to_kg(weight) if unit == "lb" else weight,
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
        with st.form("strength_log"):
            top1, top2, top3 = st.columns(3)
            with top1:
                workout_date = st.date_input("Workout date", value=date.today())
                session_name = st.selectbox("Session", ["Upper Body", "Lower Body", "Push", "Pull", "Full Body", "Custom"])
                if session_name == "Custom":
                    session_name = st.text_input("Session name")
            with top2:
                unit = st.radio("Weight unit", ["kg", "lb"], horizontal=True)
                exercise_count = st.number_input("Exercises", min_value=1, max_value=8, value=3)
            with top3:
                workout_notes = st.text_input("Session notes", placeholder="Optional")
                st.caption("Weights are stored in kilograms; pounds are converted on save.")

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
                weight = columns[3].number_input(f"Weight ({unit})", 0.0, 1000.0, 20.0, step=2.5, key=f"weight_{index}")
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
        with st.form(f"strength_log_{routine_id}"):
            top1, top2, top3 = st.columns(3)
            with top1:
                workout_date = st.date_input("Workout date", value=date.today(), key=f"log_strength_date_{routine_id}")
                _seed(f"log_strength_session_{routine_id}", defaults["session_name"])
                session_name = st.text_input("Session name", key=f"log_strength_session_{routine_id}")
            with top2:
                _seed(f"log_strength_unit_{routine_id}", "kg")
                unit = st.radio("Weight unit", ["kg", "lb"], horizontal=True, key=f"log_strength_unit_{routine_id}")
            with top3:
                _seed(f"log_strength_notes_{routine_id}", defaults["notes"])
                workout_notes = st.text_input("Session notes", key=f"log_strength_notes_{routine_id}")
                st.caption("Weights are stored in kilograms; pounds are converted on save.")

            exercises = []
            for index, exercise in enumerate(defaults["exercises"]):
                st.markdown(f"**{exercise['exercise_name']}**")
                st.caption(f"Planned {exercise['target_reps_min']}–{exercise['target_reps_max']} reps")
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
                _seed(weight_key, min(1000.0, max(0.0, exercise["weight_kg"])))
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
            edit_exercises = []
            for index, exercise in enumerate(selected["exercises"]):
                cols = st.columns(5)
                name = cols[0].text_input("Exercise", exercise["exercise_name"], key=f"edit_exercise_{selected_id}_{index}")
                sets = cols[1].number_input("Sets", 1, 20, int(exercise["sets"]), key=f"edit_sets_{selected_id}_{index}")
                reps = cols[2].number_input("Reps per set", 1, 100, int(exercise["reps"]), key=f"edit_reps_{selected_id}_{index}")
                weight = cols[3].number_input("Weight (kg)", 0.0, 1000.0, float(exercise["weight_kg"]), key=f"edit_weight_{selected_id}_{index}")
                rpe = cols[4].number_input("RPE", 1.0, 10.0, float(exercise["rpe"] or 7), key=f"edit_rpe_{selected_id}_{index}")
                edit_exercises.append((name, int(sets), int(reps), weight, rpe, bool(exercise["pain"]), exercise["notes"] or ""))
            update, delete = st.columns(2)
            with update:
                update_clicked = st.form_submit_button("Save edits", type="primary")
            with delete:
                delete_clicked = st.form_submit_button("Delete session")
        if update_clicked:
            try:
                updated = StrengthWorkoutInput(
                    workout_date=edit_date, session_name=edit_name.strip(), notes=edit_notes,
                    exercises=[StrengthSetInput(
                        exercise_name=name, sets=sets, reps=reps, weight_kg=weight,
                        rpe=rpe, pain=pain, notes=notes,
                    ) for name, sets, reps, weight, rpe, pain, notes in edit_exercises],
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
        progression = frame[frame["exercise_name"] == selected_exercise].groupby("workout_date", as_index=False).agg(weight_kg=("weight_kg", "max"), reps=("reps", "max"))
        progression["Weight"] = progression["weight_kg"].map(kg_to_pounds)
        st.line_chart(progression.set_index("workout_date")[["Weight"]], y_label="Maximum weight (lb)")
        st.dataframe(progression[["workout_date", "Weight", "reps"]].rename(columns={"workout_date": "Date", "reps": "Best reps"}), hide_index=True)
    else:
        st.info("Log a few strength sessions to see exercise progression.")