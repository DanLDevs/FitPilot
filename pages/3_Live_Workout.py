from datetime import date
from uuid import uuid4

import streamlit as st

from models.schemas import LiveExerciseInput, LiveSetInput, LiveWorkoutInput
from services import database, live_workout_service, progression_service, routine_service, strength_service, timer_service
from utils.browser_notifications import rest_timer_html
from utils.calculations import kg_to_pounds, pounds_to_kg


st.set_page_config(page_title="Live Workout | FitPilot", page_icon="F", layout="wide")
database.init_database()
profile = database.get_profile()
st.title("Live workout")
st.caption("Run the session as you train. Set changes are saved automatically.")
if profile is None:
    st.warning("Set up your athlete profile on the Dashboard before starting a live workout.")
    st.stop()


def _set_key(set_id: int, field: str) -> str:
    return f"live_set_{set_id}_{field}"


def _exercise_open_key(exercise_key: str) -> str:
    return f"live_ex_open_{exercise_key}"


def _show_session_cue(cue: dict) -> None:
    message = progression_service.format_session_cue(cue, "kg")
    if cue["status"] == "increase":
        st.success(message)
    elif cue["status"] == "caution":
        st.warning(message)
    else:
        st.info(message)


def _complete_set(
    workout_id: int,
    set_id: int,
    exercise_key: str,
    is_last_set: bool,
) -> None:
    _autosave_set(workout_id, set_id)
    live_workout_service.complete_set(workout_id, set_id)
    st.session_state[_exercise_open_key(exercise_key)] = not is_last_set


def _initialize_set_state(set_row: dict) -> None:
    defaults = {
        "reps": set_row["reps"], "weight_kg": set_row["weight_kg"],
        "rpe": set_row["rpe"], "pain": bool(set_row["pain"]),
        "technique": bool(set_row["technique_concern"]), "notes": set_row["notes"] or "",
    }
    for field, value in defaults.items():
        key = _set_key(set_row["id"], field)
        if key not in st.session_state:
            st.session_state[key] = value


def _autosave_set(workout_id: int, set_id: int) -> None:
    live_workout_service.update_set(workout_id, set_id, LiveSetInput(
        reps=st.session_state[_set_key(set_id, "reps")],
        weight_kg=st.session_state[_set_key(set_id, "weight_kg")],
        rpe=st.session_state[_set_key(set_id, "rpe")],
        pain=st.session_state[_set_key(set_id, "pain")],
        technique_concern=st.session_state[_set_key(set_id, "technique")],
        notes=st.session_state[_set_key(set_id, "notes")],
    ))


def _save_header(workout_id: int) -> None:
    live_workout_service.update_workout_details(
        workout_id,
        st.session_state["live_workout_date"],
        st.session_state["live_session_name"],
        st.session_state["live_session_notes"],
        st.session_state["live_default_rest"],
        st.session_state["live_auto_rest"],
    )


def _save_exercise_rest(workout_id: int, exercise_key: str) -> None:
    _save_exercise_details(workout_id, exercise_key)


def _save_exercise_details(workout_id: int, exercise_key: str) -> None:
    choice = st.session_state[f"live_ex_name_{exercise_key}"]
    exercise_name = (
        st.session_state[f"live_ex_custom_{exercise_key}"]
        if choice == "Custom" else choice
    )
    live_workout_service.update_exercise_details(
        workout_id, exercise_key, exercise_name,
        st.session_state[f"live_target_min_{exercise_key}"],
        st.session_state[f"live_target_max_{exercise_key}"],
        st.session_state[f"live_rest_{exercise_key}"],
    )


def _render_timer(workout: dict) -> None:
    workout_id = workout["id"]
    deadline = workout["rest_ends_at"]
    paused = workout["rest_paused_remaining_seconds"]
    if deadline is None and paused is None:
        st.caption("Rest timer ready. Completing a set starts it automatically when enabled.")
        if st.button("Start rest", key=f"manual_rest_{workout_id}"):
            live_workout_service.start_rest(workout_id, workout["default_rest_seconds"])
            st.rerun()
        return

    st.html(rest_timer_html(workout_id, deadline, paused), unsafe_allow_javascript=True)
    if deadline and paused is None and timer_service.remaining_seconds(deadline) == 0:
        live_workout_service.claim_rest_notification(workout_id)
    primary = st.columns(2)
    secondary = st.columns(2)
    if paused is None:
        if primary[0].button("Pause", key=f"pause_rest_{workout_id}"):
            live_workout_service.pause_rest(workout_id)
            st.rerun()
    elif primary[0].button("Resume", key=f"resume_rest_{workout_id}"):
        live_workout_service.resume_rest(workout_id)
        st.rerun()
    if primary[1].button("Skip", key=f"skip_rest_{workout_id}"):
        live_workout_service.start_rest(workout_id, 0)
        st.rerun()
    if secondary[0].button("-15 sec", key=f"less_rest_{workout_id}"):
        live_workout_service.adjust_rest(workout_id, -15)
        st.rerun()
    if secondary[1].button("+15 sec", key=f"more_rest_{workout_id}"):
        live_workout_service.adjust_rest(workout_id, 15)
        st.rerun()


active = live_workout_service.get_active_workout()
if active is None:
    routines = routine_service.list_routines()
    labels = {"Blank workout": None}
    labels.update({f"{routine['name']} · #{routine['id']}": routine["id"] for routine in routines})
    selected_label = st.selectbox("Start from a routine", list(labels), key="start_routine")
    selected_routine = next((routine for routine in routines if routine["id"] == labels[selected_label]), None)
    col1, col2 = st.columns(2)
    with col1:
        session_name = st.text_input("Workout name", selected_routine["name"] if selected_routine else "Workout")
        workout_date = st.date_input("Date", date.today())
    with col2:
        default_rest = st.number_input(
            "Default rest (seconds)", 0, 3600,
            selected_routine["default_rest_seconds"] if selected_routine else 90,
            step=15,
        )
        auto_rest = st.checkbox(
            "Start rest automatically after completing a set",
            selected_routine["auto_start_rest"] if selected_routine else True,
        )
    st.caption("You can edit every exercise, rep target, and set after the workout starts.")
    if st.button("Start workout", type="primary"):
        try:
            if selected_routine:
                workout_id = live_workout_service.start_from_routine(
                    selected_routine["id"], workout_date,
                )
                live_workout_service.update_workout_details(
                    workout_id, workout_date, session_name, selected_routine["notes"],
                    default_rest, auto_rest,
                )
            else:
                workout_id = live_workout_service.start_workout(LiveWorkoutInput(
                    workout_date=workout_date, session_name=session_name,
                    default_rest_seconds=default_rest, auto_start_rest=auto_rest,
                ))
            st.session_state["last_live_workout_id"] = workout_id
            st.rerun()
        except Exception as error:
            st.error(f"Could not start workout: {error}")
    if not routines:
        st.info("Create a routine first, or start a blank workout.")
        st.page_link("pages/4_Workout_Routines.py", label="Create a routine")
else:
    workout_id = active["id"]
    if st.session_state.get("live_widget_workout_id") != workout_id:
        for key in list(st.session_state):
            if key.startswith(("live_set_", "live_rest_", "live_ex_open_")):
                del st.session_state[key]
        st.session_state["live_widget_workout_id"] = workout_id
    st.session_state.setdefault("live_workout_date", date.fromisoformat(active["workout_date"]))
    st.session_state.setdefault("live_session_name", active["session_name"])
    st.session_state.setdefault("live_session_notes", active["notes"])
    st.session_state.setdefault("live_default_rest", active["default_rest_seconds"])
    st.session_state.setdefault("live_auto_rest", bool(active["auto_start_rest"]))

    header = st.columns([1.2, 1, 1])
    header[0].date_input("Workout date", key="live_workout_date", on_change=_save_header, args=(workout_id,))
    header[1].text_input("Session", key="live_session_name", on_change=_save_header, args=(workout_id,))
    header[2].number_input("Default rest (sec)", 0, 3600, step=15, key="live_default_rest", on_change=_save_header, args=(workout_id,))
    st.text_input("Session notes", key="live_session_notes", on_change=_save_header, args=(workout_id,))
    st.checkbox("Auto-start rest after each set", key="live_auto_rest", on_change=_save_header, args=(workout_id,))

    completed_sets = sum(
        1 for exercise in active["exercises"] for row in exercise["sets"] if row["is_completed"]
    )
    set_count = sum(len(exercise["sets"]) for exercise in active["exercises"])
    volume_kg = sum(
        row["reps"] * row["weight_kg"]
        for exercise in active["exercises"] for row in exercise["sets"] if row["is_completed"]
    )
    st.progress(completed_sets / set_count if set_count else 0, text=f"{completed_sets} of {set_count} sets complete")
    _render_timer(active)

    historical_sets = strength_service.list_sets()
    for exercise_index, exercise in enumerate(active["exercises"]):
        done = sum(row["is_completed"] for row in exercise["sets"])
        exercise_key = exercise["exercise_key"]
        open_key = _exercise_open_key(exercise_key)
        if open_key not in st.session_state:
            st.session_state[open_key] = exercise_index == 0
        with st.expander(
            f"{exercise['exercise_name']} · {done}/{len(exercise['sets'])} sets",
            key=open_key,
            on_change="rerun",
        ):
            common_exercises = ["Bench Press", "Squat", "Deadlift", "Overhead Press", "Barbell Row", "Pull-Up", "Lat Pulldown", "Bicep Curl", "Tricep Pushdown", "Leg Press", "Romanian Deadlift", "Dumbbell Bench Press", "Custom"]
            name_key = f"live_ex_name_{exercise_key}"
            custom_key = f"live_ex_custom_{exercise_key}"
            minimum_key = f"live_target_min_{exercise_key}"
            maximum_key = f"live_target_max_{exercise_key}"
            st.session_state.setdefault(name_key, exercise["exercise_name"] if exercise["exercise_name"] in common_exercises else "Custom")
            st.session_state.setdefault(custom_key, "" if exercise["exercise_name"] in common_exercises else exercise["exercise_name"])
            st.session_state.setdefault(minimum_key, exercise["target_reps_min"])
            st.session_state.setdefault(maximum_key, exercise["target_reps_max"])
            edit_cols = st.columns([2, 1, 1])
            name_choice = edit_cols[0].selectbox(
                "Exercise", common_exercises, key=name_key,
                on_change=_save_exercise_details, args=(workout_id, exercise_key),
            )
            if name_choice == "Custom":
                edit_cols[0].text_input(
                    "Custom exercise name", key=custom_key,
                    on_change=_save_exercise_details, args=(workout_id, exercise_key),
                )
            edit_cols[1].number_input(
                "Target min", 1, 100, key=minimum_key,
                on_change=_save_exercise_details, args=(workout_id, exercise_key),
            )
            edit_cols[2].number_input(
                "Target max", 1, 100, key=maximum_key,
                on_change=_save_exercise_details, args=(workout_id, exercise_key),
            )
            first_weight = exercise["sets"][0]["weight_kg"] if exercise["sets"] else None
            cue = progression_service.session_cue(
                historical_sets,
                exercise["exercise_name"],
                exercise["target_reps_min"],
                exercise["target_reps_max"],
                starting_weight_kg=first_weight or None,
            )
            _show_session_cue(cue)
            rest_key = f"live_rest_{exercise_key}"
            if rest_key not in st.session_state:
                st.session_state[rest_key] = exercise["rest_seconds"]
            st.number_input(
                "Exercise rest (seconds)", 0, 3600, step=15, key=rest_key,
                on_change=_save_exercise_rest, args=(workout_id, exercise_key),
            )
            next_set_id = next(
                (row["id"] for row in exercise["sets"] if not row["is_completed"]), None
            )
            for set_index, set_row in enumerate(exercise["sets"]):
                set_id = set_row["id"]
                _initialize_set_state(set_row)
                if set_row["is_completed"]:
                    st.markdown(f"**Set {set_index + 1} · Complete**")
                elif set_id == next_set_id:
                    st.markdown(f"**Set {set_index + 1} · Next set**")
                else:
                    st.markdown(f"**Set {set_index + 1} · Up next**")
                columns = st.columns([1, 1.2, 0.9, 0.75, 1, 1.4])
                columns[0].number_input("Reps", 1, 100, key=_set_key(set_id, "reps"), disabled=bool(set_row["is_completed"]), on_change=_autosave_set, args=(workout_id, set_id))
                columns[1].number_input("Weight (kg)", 0.0, 1000.0, step=2.5, key=_set_key(set_id, "weight_kg"), disabled=bool(set_row["is_completed"]), on_change=_autosave_set, args=(workout_id, set_id))
                columns[2].number_input("RPE", 1.0, 10.0, step=0.5, key=_set_key(set_id, "rpe"), disabled=bool(set_row["is_completed"]), on_change=_autosave_set, args=(workout_id, set_id))
                columns[3].checkbox("Pain", key=_set_key(set_id, "pain"), disabled=bool(set_row["is_completed"]), on_change=_autosave_set, args=(workout_id, set_id))
                columns[4].checkbox("Technique", key=_set_key(set_id, "technique"), disabled=bool(set_row["is_completed"]), on_change=_autosave_set, args=(workout_id, set_id))
                columns[5].text_input("Notes", key=_set_key(set_id, "notes"), disabled=bool(set_row["is_completed"]), on_change=_autosave_set, args=(workout_id, set_id))
                if not set_row["is_completed"]:
                    incomplete_ids = [
                        row["id"] for row in exercise["sets"] if not row["is_completed"]
                    ]
                    st.button(
                        "Complete set",
                        key=f"complete_{set_id}",
                        type="primary",
                        on_click=_complete_set,
                        args=(
                            workout_id,
                            set_id,
                            exercise_key,
                            len(incomplete_ids) == 1,
                        ),
                    )
            set_actions = st.columns(2)
            if set_actions[0].button("Add set", key=f"add_set_{exercise['exercise_key']}"):
                live_workout_service.add_set(workout_id, exercise["exercise_key"])
                st.rerun()
            if set_actions[1].button("Remove last set", key=f"remove_set_{exercise['exercise_key']}"):
                try:
                    live_workout_service.remove_last_set(workout_id, exercise["exercise_key"])
                    st.rerun()
                except ValueError as error:
                    st.warning(str(error))
            if st.button("Remove exercise", key=f"remove_exercise_{exercise['exercise_key']}"):
                try:
                    live_workout_service.remove_exercise(workout_id, exercise["exercise_key"])
                    st.rerun()
                except ValueError as error:
                    st.warning(str(error))

    with st.expander("Add exercise"):
        common_exercises = ["Bench Press", "Squat", "Deadlift", "Overhead Press", "Barbell Row", "Pull-Up", "Lat Pulldown", "Bicep Curl", "Tricep Pushdown", "Leg Press", "Romanian Deadlift", "Dumbbell Bench Press", "Custom"]
        name_choice = st.selectbox("Exercise", common_exercises, key="live_add_name")
        exercise_name = st.text_input("Custom name", key="live_add_custom") if name_choice == "Custom" else name_choice
        add_cols = st.columns(4)
        target_min = add_cols[0].number_input("Target reps, min", 1, 100, 8, key="live_add_min")
        target_max = add_cols[1].number_input("Target reps, max", 1, 100, 12, key="live_add_max")
        set_count = add_cols[2].number_input("Sets", 1, 30, 3, key="live_add_sets")
        weight = add_cols[3].number_input("Starting weight (kg)", 0.0, 1000.0, 20.0, key="live_add_weight")
        if st.button("Add to workout", key="live_add_commit"):
            try:
                exercise = LiveExerciseInput(
                    exercise_name=exercise_name.strip(), target_reps_min=target_min,
                    target_reps_max=target_max, rest_seconds=active["default_rest_seconds"],
                    sets=[LiveSetInput(weight_kg=weight) for _ in range(int(set_count))],
                )
                live_workout_service.add_exercise(workout_id, exercise, active["default_rest_seconds"])
                st.rerun()
            except Exception as error:
                st.error(f"Exercise not added: {error}")

    st.caption(f"Completed volume: {volume_kg:,.0f} kg · {completed_sets} sets")
    finish_col, discard_col = st.columns(2)
    if finish_col.button("Finish workout", type="primary", key=f"finish_{workout_id}"):
        live_workout_service.finish_workout(workout_id)
        st.session_state["live_last_summary"] = {
            "sets": completed_sets, "volume_kg": volume_kg, "name": active["session_name"],
        }
        st.rerun()
    confirm_discard = discard_col.checkbox("Confirm discard", key=f"confirm_discard_{workout_id}")
    if discard_col.button("Discard workout", disabled=not confirm_discard, key=f"discard_{workout_id}"):
        live_workout_service.discard_workout(workout_id)
        st.rerun()

if active is None and st.session_state.get("live_last_summary"):
    summary = st.session_state["live_last_summary"]
    st.success(f"{summary['name']} complete · {summary['sets']} sets · {summary['volume_kg']:,.0f} kg volume")
    if st.button("Dismiss summary"):
        del st.session_state["live_last_summary"]
        st.rerun()