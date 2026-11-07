from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from models.schemas import RunningWorkoutInput
from services import database, running_service
from utils.calculations import km_to_miles, miles_to_km, weekly_totals


st.set_page_config(page_title="Running | FitPilot", page_icon="F", layout="wide")
database.init_database()
profile = database.get_profile()
st.title("Running")
st.caption("Track distance, effort, and pace across the kinds of runs you actually do.")
if profile is None:
    st.warning("Set up your athlete profile on the Dashboard before logging workouts.")
    st.stop()

workouts = running_service.list_workouts(limit=500)
tab_log, tab_history, tab_insights = st.tabs(["Log run", "History and edits", "Progress"])

with tab_log:
    with st.form("running_log"):
        col1, col2, col3 = st.columns(3)
        with col1:
            workout_date = st.date_input("Run date", value=date.today())
            run_type = st.selectbox("Run type", ["Easy", "Tempo", "Interval", "Long Run", "Recovery", "Other"])
            unit = st.radio("Distance unit", ["km", "mi"], horizontal=True)
        with col2:
            distance = st.number_input(f"Distance ({unit})", min_value=0.1, max_value=500.0, value=5.0, step=0.1)
            duration = st.number_input("Duration (minutes)", min_value=1.0, max_value=3000.0, value=30.0, step=1.0)
            pace = duration / distance
            st.metric(f"Average pace (min/{unit})", f"{int(pace)}:{round((pace % 1) * 60):02d}")
        with col3:
            rpe = st.slider("Perceived effort (RPE)", 1, 10, 5)
            pain = st.checkbox("Pain or discomfort")
            notes = st.text_area("Notes", placeholder="Optional")
        submitted = st.form_submit_button("Save run", type="primary")
    if submitted:
        try:
            validated = RunningWorkoutInput(
                workout_date=workout_date, run_type=run_type,
                distance_km=miles_to_km(distance) if unit == "mi" else distance,
                duration_minutes=duration, rpe=rpe, notes=notes, pain=pain,
            )
            running_service.add_workout(validated)
            st.success("Run saved.")
            st.rerun()
        except Exception as error:
            st.error(f"Run not saved: {error}")

with tab_history:
    if not workouts:
        st.info("No runs recorded yet.")
    else:
        st.dataframe([
            {"ID": row["id"], "Date": row["workout_date"], "Type": row["run_type"],
             "Distance (mi)": round(km_to_miles(row["distance_km"]), 2),
             "Duration (min)": round(row["duration_minutes"], 1),
             "Pace (min/mi)": round(row["duration_minutes"] / km_to_miles(row["distance_km"]), 2),
             "RPE": row["rpe"], "Pain": "Yes" if row["pain"] else "No"}
            for row in workouts
        ], hide_index=True, use_container_width=True)
        selected_id = st.selectbox("Select a run to edit or delete", [row["id"] for row in workouts], format_func=lambda value: next(f"{row['workout_date']} · {row['run_type']} · #{row['id']}" for row in workouts if row["id"] == value))
        selected = next(row for row in workouts if row["id"] == selected_id)
        with st.form(f"edit_run_{selected_id}"):
            cols = st.columns(3)
            edit_date = cols[0].date_input("Date", date.fromisoformat(selected["workout_date"]), key=f"run_date_{selected_id}")
            run_types = ["Easy", "Tempo", "Interval", "Long Run", "Recovery", "Other"]
            edit_type = cols[1].selectbox("Run type", run_types, index=run_types.index(selected["run_type"]), key=f"run_type_{selected_id}")
            edit_distance = cols[2].number_input("Distance (km)", 0.1, 500.0, float(selected["distance_km"]), step=0.1, key=f"run_distance_{selected_id}")
            edit_duration = cols[0].number_input("Duration (minutes)", 1.0, 3000.0, float(selected["duration_minutes"]), key=f"run_duration_{selected_id}")
            edit_rpe = cols[1].slider("RPE", 1, 10, int(selected["rpe"] or 5), key=f"run_rpe_{selected_id}")
            edit_pain = cols[2].checkbox("Pain or discomfort", bool(selected["pain"]), key=f"run_pain_{selected_id}")
            edit_notes = st.text_area("Notes", selected["notes"], key=f"run_notes_{selected_id}")
            save_edit, delete_run = st.columns(2)
            with save_edit:
                update_clicked = st.form_submit_button("Save edits", type="primary")
            with delete_run:
                delete_clicked = st.form_submit_button("Delete run")
        if update_clicked:
            try:
                updated = RunningWorkoutInput(
                    workout_date=edit_date, run_type=edit_type, distance_km=edit_distance,
                    duration_minutes=edit_duration, rpe=edit_rpe, notes=edit_notes, pain=edit_pain,
                )
                running_service.update_workout(selected_id, updated)
                st.success("Run updated.")
                st.rerun()
            except Exception as error:
                st.error(f"Run not updated: {error}")
        if delete_clicked:
            running_service.delete_workout(selected_id)
            st.success("Run deleted.")
            st.rerun()

with tab_insights:
    if not workouts:
        st.info("Log a few runs to see weekly distance and run-type summaries.")
    else:
        distance_unit = st.radio("Display distance", ["mi", "km"], horizontal=True, key="progress_distance_unit")
        multiplier = 1 if distance_unit == "km" else 1 / 1.609344
        history = [{**row, "display_distance": row["distance_km"] * multiplier} for row in workouts]
        weekly = weekly_totals(history, "display_distance", "workout_date")
        figure = px.line(weekly, x="week", y="value", markers=True, labels={"week": "Week of", "value": f"Distance ({distance_unit})"}, color_discrete_sequence=["#df7958"])
        figure.update_layout(template="plotly_dark", margin=dict(l=8, r=8, t=12, b=8), plot_bgcolor="#202825", paper_bgcolor="#151a18", font_color="#edf3ee")
        st.plotly_chart(figure, use_container_width=True)

        frame = pd.DataFrame(workouts)
        frame["pace_min_per_km"] = frame["duration_minutes"] / frame["distance_km"]
        frame["distance_mi"] = frame["distance_km"].map(km_to_miles)
        longest = frame.loc[frame["distance_km"].idxmax()]
        total_time = frame["duration_minutes"].sum()
        cards = st.columns(3)
        cards[0].metric("Longest run", f"{km_to_miles(longest['distance_km']):.1f} mi")
        cards[1].metric("Total running time", f"{total_time / 60:.1f} hr")
        cards[2].metric("Runs logged", len(frame))
        st.subheader("Comparable run types")
        by_type = frame.groupby("run_type", as_index=False).agg(
            runs=("id", "count"), average_distance_mi=("distance_mi", "mean"),
            average_pace_min_km=("pace_min_per_km", "mean"), average_rpe=("rpe", "mean"),
        )
        by_type["Average pace (min/mi)"] = by_type["average_pace_min_km"] * 1.609344
        st.dataframe(by_type[["run_type", "runs", "average_distance_mi", "Average pace (min/mi)", "average_rpe"]].rename(columns={
            "run_type": "Run type", "runs": "Sessions", "average_distance_mi": "Average distance (mi)", "average_rpe": "Average RPE",
        }).round(2), hide_index=True, use_container_width=True)