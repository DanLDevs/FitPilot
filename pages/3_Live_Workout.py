from datetime import date
from uuid import uuid4

import streamlit as st

from models.schemas import LiveExerciseInput, LiveSetInput, LiveWorkoutInput
from services import (
    database, live_run_service, live_workout_service, plan_service,
    progression_service, routine_service, strength_service, timer_service,
)
from services.running_cue import format_run_clock
from utils.browser_notifications import rest_timer_html
from utils.run_clock import run_clock_html
from utils.calculations import kg_to_pounds, km_to_miles, miles_to_km, pounds_to_kg


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


def _run_label(day: dict, used: set[str]) -> str:
    weekday = (day.get("weekday") or "").strip()
    title = day["title"]
    label = f"{weekday} · {title}" if weekday else title
    if label in used:
        label = f"{label} · {int(day['position']) + 1}"
    used.add(label)
    return label


def _display_distance(distance_km: float, unit: str) -> float:
    value = km_to_miles(distance_km) if unit == "mi" else float(distance_km)
    return round(value, 2)


def _kilometers(display: float, unit: str) -> float:
    return miles_to_km(display) if unit == "mi" else float(display)


def _save_run(run_id: int) -> None:
    unit = st.session_state["live_run_unit"]
    live_run_service.update_run(
        run_id,
        st.session_state["live_run_date"],
        _kilometers(st.session_state["live_run_distance"], unit),
        float(st.session_state["live_run_duration"]),
        unit,
        int(st.session_state["live_run_rpe"]),
        st.session_state["live_run_notes"],
        bool(st.session_state["live_run_pain"]),
    )


def _change_run_unit(run_id: int) -> None:
    new_unit = st.session_state["live_run_unit"]
    current = live_run_service.get_active_run()
    kilometers = float(current["distance_km"]) if current and current["distance_km"] is not None else 0.0
    st.session_state["live_run_distance"] = _display_distance(kilometers, new_unit)
    live_run_service.update_run(
        run_id,
        st.session_state["live_run_date"],
        kilometers,
        float(st.session_state["live_run_duration"]),
        new_unit,
        int(st.session_state["live_run_rpe"]),
        st.session_state["live_run_notes"],
        bool(st.session_state["live_run_pain"]),
    )


def _render_strength_start() -> None:
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


def _render_run_start() -> None:
    plan = plan_service.get_current_plan()
    running_days = [
        day for day in (plan["days"] if plan else []) if day["session_kind"] == "running"
    ]
    if not running_days:
        st.info("Save a weekly plan with a running day to start a live run.")
        st.page_link("pages/4_Workout_Routines.py", label="Create a weekly plan")
        return
    used_labels: set[str] = set()
    labels = {_run_label(day, used_labels): day["position"] for day in running_days}
    selected_label = st.selectbox("Planned run", list(labels), key="start_run_day")
    workout_date = st.date_input("Date", date.today(), key="start_run_date")
    if st.button("Start run", type="primary"):
        try:
            live_run_service.start_from_plan_day(labels[selected_label], workout_date)
            st.rerun()
        except Exception as error:
            st.error(f"Could not start run: {error}")


def _render_active_run(run: dict) -> None:
    run_id = run["id"]
    if st.session_state.get("live_run_widget_id") != run_id:
        for key in list(st.session_state):
            if key.startswith("live_run_"):
                del st.session_state[key]
        st.session_state["live_run_widget_id"] = run_id
    unit = run.get("distance_unit") or "km"
    distance_km = float(run["distance_km"] if run["distance_km"] is not None else run["target_distance_km"])
    st.session_state.setdefault("live_run_date", date.fromisoformat(run["workout_date"]))
    st.session_state.setdefault("live_run_unit", unit)
    st.session_state.setdefault("live_run_distance", _display_distance(distance_km, unit))
    st.session_state.setdefault(
        "live_run_duration",
        float(run["duration_minutes"] if run["duration_minutes"] is not None else run["target_duration_minutes"]),
    )
    st.session_state.setdefault("live_run_rpe", 5 if run["rpe"] is None else int(run["rpe"]))
    st.session_state.setdefault("live_run_pain", bool(run["pain"]))
    st.session_state.setdefault("live_run_notes", run["notes"] or "")

    st.subheader(run["title"])
    st.caption(run["run_type"])
    st.info(live_run_service.session_message(run))
    header = st.columns([1.2, 1, 1])
    header[0].date_input("Run date", key="live_run_date", on_change=_save_run, args=(run_id,))
    header[1].radio(
        "Distance unit", ["km", "mi"], horizontal=True, key="live_run_unit",
        on_change=_change_run_unit, args=(run_id,),
    )
    display_unit = st.session_state["live_run_unit"]
    distance_max = round(km_to_miles(500), 2) if display_unit == "mi" else 500.0
    fields = st.columns(3)
    fields[0].number_input(
        f"Distance ({display_unit})", min_value=0.01, max_value=distance_max, step=0.1,
        key="live_run_distance", on_change=_save_run, args=(run_id,),
    )
    fields[1].number_input(
        "Duration (minutes)", min_value=1.0, max_value=3000.0, step=1.0,
        key="live_run_duration", on_change=_save_run, args=(run_id,),
    )
    logged_distance = st.session_state["live_run_distance"]
    logged_duration = float(st.session_state["live_run_duration"])
    if logged_distance > 0:
        fields[2].metric(
            f"Pace (min/{display_unit})",
            format_run_clock(logged_duration / logged_distance),
        )
    st.caption("Distance and duration here are what gets saved. The message above stays on the plan.")
    idle_seconds = int(round(float(run["duration_minutes"] or run["target_duration_minutes"]) * 60))
    st.html(run_clock_html(
        run_id, run["timer_ends_at"], run["timer_paused_remaining_seconds"], idle_seconds,
    ), unsafe_allow_javascript=True)
    st.caption("The clock counts down from the duration when you press Start.")
    clock_actions = st.columns(2)
    timer_idle = run["timer_ends_at"] is None and run["timer_paused_remaining_seconds"] is None
    if timer_idle:
        if clock_actions[0].button("Start", key=f"run_clock_start_{run_id}"):
            _save_run(run_id)
            live_run_service.start_timer(run_id)
            st.rerun()
    elif run["timer_paused_remaining_seconds"] is not None:
        if clock_actions[0].button("Resume", key=f"run_clock_resume_{run_id}"):
            live_run_service.resume_timer(run_id)
            st.rerun()
    elif clock_actions[0].button("Pause", key=f"run_clock_pause_{run_id}"):
        live_run_service.pause_timer(run_id)
        st.rerun()
    if not timer_idle and clock_actions[1].button("Reset", key=f"run_clock_reset_{run_id}"):
        live_run_service.reset_timer(run_id)
        st.rerun()

    effort = st.columns([1, 1, 2])
    effort[0].slider("Perceived effort (RPE)", 1, 10, key="live_run_rpe", on_change=_save_run, args=(run_id,))
    effort[1].checkbox("Pain or discomfort", key="live_run_pain", on_change=_save_run, args=(run_id,))
    st.text_area("Notes", key="live_run_notes", on_change=_save_run, args=(run_id,))

    finish_col, discard_col = st.columns(2)
    if finish_col.button("Finish run", type="primary", key=f"finish_run_{run_id}"):
        try:
            _save_run(run_id)
            live_run_service.finish_run(run_id)
            saved_unit = st.session_state["live_run_unit"]
            st.session_state["live_last_run_summary"] = {
                "title": run["title"],
                "distance": _display_distance(
                    _kilometers(st.session_state["live_run_distance"], saved_unit), saved_unit,
                ),
                "unit": saved_unit,
                "duration": format_run_clock(float(st.session_state["live_run_duration"])),
            }
            st.rerun()
        except Exception as error:
            st.error(f"Run not saved: {error}")
    confirm_discard = discard_col.checkbox("Confirm discard", key=f"confirm_discard_run_{run_id}")
    if discard_col.button("Discard run", disabled=not confirm_discard, key=f"discard_run_{run_id}"):
        live_run_service.discard_run(run_id)
        st.rerun()


active = live_workout_service.get_active_workout()
active_run = None if active is not None else live_run_service.get_active_run()
if active is None and active_run is None:
    session_kind = st.radio("Session", ["Strength", "Run"], horizontal=True, key="live_session_kind")
    if session_kind == "Run":
        _render_run_start()
    else:
        _render_strength_start()
elif active is not None:
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
else:
    _render_active_run(active_run)

if active is None and active_run is None and st.session_state.get("live_last_summary"):
    summary = st.session_state["live_last_summary"]
    st.success(f"{summary['name']} complete · {summary['sets']} sets · {summary['volume_kg']:,.0f} kg volume")
    if st.button("Dismiss summary"):
        del st.session_state["live_last_summary"]
        st.rerun()

if active is None and active_run is None and st.session_state.get("live_last_run_summary"):
    summary = st.session_state["live_last_run_summary"]
    st.success(
        f"{summary['title']} saved · {summary['distance']:.1f} {summary['unit']} · {summary['duration']}"
    )
    if st.button("Dismiss run summary"):
        del st.session_state["live_last_run_summary"]
        st.rerun()