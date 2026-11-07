import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from datetime import date, timedelta

load_dotenv()

from models.schemas import ProfileInput
from services import analytics_service, database
from utils.calculations import kg_to_pounds, km_to_miles
from utils.sample_data import load_demo_data


st.set_page_config(page_title="FitPilot", page_icon="F", layout="wide")
database.init_database()
st.markdown(
    """<style>
    .stApp { background: #f5f7f4; color: #17231d; }
    [data-testid="stSidebar"] { background: #17231d; }
    [data-testid="stSidebar"] * { color: #eef4ed !important; }
    h1, h2, h3 { letter-spacing: 0; color: #17231d; }
    div[data-testid="stMetric"] { background: white; border: 1px solid #e1e8e0; padding: 16px; border-radius: 8px; }
    div[data-testid="stMetricLabel"] { color: #55665b; }
    .fitpilot-kicker { color: #258257; font-size: 0.78rem; font-weight: 700; text-transform: uppercase; }
    </style>""",
    unsafe_allow_html=True,
)

profile = database.get_profile()
st.markdown('<p class="fitpilot-kicker">TRAINING, WITH CONTEXT</p>', unsafe_allow_html=True)
st.title(f"Welcome{', ' + profile['name'] if profile else ''}")
st.caption("A clear view of your strength work, running, and weekly rhythm.")

if profile is None:
    st.subheader("Set up your athlete profile")
    with st.form("profile_setup"):
        name = st.text_input("Name or nickname")
        col1, col2 = st.columns(2)
        with col1:
            goal = st.selectbox("Primary goal", ["Strength", "Muscle Growth", "Running Endurance", "General Fitness", "Hybrid Fitness"])
            experience = st.selectbox("Experience level", ["Beginner", "Intermediate", "Advanced"])
            training_days = st.slider("Training days per week", 1, 7, 4)
            session_minutes = st.number_input("Available minutes per session", 15, 300, 60, step=15)
        with col2:
            strength_days = st.slider("Preferred strength days", 0, 7, 2)
            running_days = st.slider("Preferred running days", 0, 7, 2)
            equipment = st.text_input("Available equipment", placeholder="Full gym, dumbbells, none...")
            fitness_goals = st.text_input("Optional fitness goals")
        schedule = st.text_area("Optional existing weekly schedule")
        submitted = st.form_submit_button("Save profile", type="primary")
    if submitted:
        try:
            saved_profile = ProfileInput(
                name=name.strip(), primary_goal=goal, experience_level=experience,
                training_days=training_days, strength_days=strength_days, running_days=running_days,
                session_minutes=session_minutes, equipment=equipment,
                fitness_goals=fitness_goals, existing_schedule=schedule,
            )
            database.save_profile(saved_profile.model_dump())
            st.rerun()
        except Exception as error:
            st.error(f"Check your profile details: {error}")
    if st.button("Load demo profile and six weeks of data"):
        load_demo_data()
        st.success("Demo profile and training history added.")
        st.rerun()
    st.stop()

with st.expander("Edit athlete profile"):
    with st.form("profile_edit"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Name or nickname", value=profile["name"])
            goal_options = ["Strength", "Muscle Growth", "Running Endurance", "General Fitness", "Hybrid Fitness"]
            goal = st.selectbox("Primary goal", goal_options, index=goal_options.index(profile["primary_goal"]))
            experience_options = ["Beginner", "Intermediate", "Advanced"]
            experience = st.selectbox("Experience level", experience_options, index=experience_options.index(profile["experience_level"]))
            training_days = st.slider("Training days per week", 1, 7, profile["training_days"])
            session_minutes = st.number_input("Available minutes per session", 15, 300, profile["session_minutes"], step=15)
        with col2:
            strength_days = st.slider("Preferred strength days", 0, 7, profile["strength_days"])
            running_days = st.slider("Preferred running days", 0, 7, profile["running_days"])
            equipment = st.text_input("Available equipment", value=profile["equipment"])
            fitness_goals = st.text_input("Fitness goals", value=profile["fitness_goals"])
            schedule = st.text_area("Existing schedule", value=profile["existing_schedule"])
        if st.form_submit_button("Update profile"):
            try:
                saved_profile = ProfileInput(
                    name=name.strip(), primary_goal=goal, experience_level=experience,
                    training_days=training_days, strength_days=strength_days, running_days=running_days,
                    session_minutes=session_minutes, equipment=equipment,
                    fitness_goals=fitness_goals, existing_schedule=schedule,
                )
                database.save_profile(saved_profile.model_dump())
                st.success("Profile updated.")
                st.rerun()
            except Exception as error:
                st.error(f"Check your profile details: {error}")

col_title, col_button = st.columns([4, 1])
with col_title:
    st.subheader("This week")
with col_button:
    if st.button("Load demo data", use_container_width=True):
        added = load_demo_data()
        st.success("Six weeks of sample sessions loaded." if added else "Demo data is already loaded.")
        st.rerun()

data = analytics_service.dashboard_data()
strength_volume = sum(row["volume_kg"] for row in data["strength_this_week"])
run_distance = sum(row["distance_km"] for row in data["running_this_week"])
all_sessions = len(data["strength_this_week"]) + len(data["running_this_week"])
planned = max(profile["training_days"], 1)
consistency = min(100, round(all_sessions / planned * 100))

metric1, metric2, metric3, metric4 = st.columns(4)
metric1.metric("Workouts completed", all_sessions)
metric2.metric("Strength volume", f"{kg_to_pounds(strength_volume):,.0f} lb")
metric3.metric("Running distance", f"{km_to_miles(run_distance):.1f} mi")
metric4.metric("Weekly consistency", f"{consistency}%", help=f"{all_sessions} sessions recorded against {planned} preferred training days.")

chart1, chart2 = st.columns(2)
with chart1:
    st.subheader("Strength volume")
    strength_fig = px.bar(data["strength_volume_weeks"], x="week", y="value", labels={"week": "Week of", "value": "Volume (kg)", "x": "Week of"}, color_discrete_sequence=["#258257"])
    strength_fig.update_layout(margin=dict(l=8, r=8, t=12, b=8), plot_bgcolor="white", paper_bgcolor="white")
    st.plotly_chart(strength_fig, use_container_width=True)
with chart2:
    st.subheader("Running distance")
    run_fig = px.bar(data["running_distance_weeks"], x="week", y="value", labels={"week": "Week of", "value": "Distance (km)"}, color_discrete_sequence=["#df7958"])
    run_fig.update_layout(margin=dict(l=8, r=8, t=12, b=8), plot_bgcolor="white", paper_bgcolor="white")
    st.plotly_chart(run_fig, use_container_width=True)

st.subheader("Workout frequency")
frequency_fig = px.bar(
    data["frequency_weeks"], x="week", y=["strength", "running"], barmode="group",
    labels={"week": "Week of", "value": "Sessions", "variable": "Activity"},
    color_discrete_map={"strength": "#258257", "running": "#df7958"},
)
frequency_fig.update_layout(margin=dict(l=8, r=8, t=12, b=8), plot_bgcolor="white", paper_bgcolor="white")
st.plotly_chart(frequency_fig, use_container_width=True)

st.subheader("This week's activity")
week_start = date.today() - timedelta(days=date.today().weekday())
calendar_rows = []
for day_offset in range(7):
    calendar_day = week_start + timedelta(days=day_offset)
    day_key = calendar_day.isoformat()
    activities = [row["session_name"] for row in data["strength"] if row["workout_date"] == day_key]
    activities += [row["run_type"] + " run" for row in data["running"] if row["workout_date"] == day_key]
    status = "Completed" if activities else ("Rest" if calendar_day <= date.today() else "Upcoming")
    calendar_rows.append({"Day": calendar_day.strftime("%a, %b %d"), "Activity": ", ".join(activities) or "-", "Status": status})
st.dataframe(calendar_rows, hide_index=True, use_container_width=True)
st.caption("Calendar shows logged activity. Planned sessions will be added with the training-plan workflow.")

left, right = st.columns([1, 1])
with left:
    st.subheader("Recent strength sessions")
    if data["strength"]:
        st.dataframe([
            {"Date": row["workout_date"], "Session": row["session_name"],
             "Sets": row["set_count"], "Volume (lb)": round(kg_to_pounds(row["volume_kg"]))}
            for row in data["strength"][:6]
        ], hide_index=True, use_container_width=True)
    else:
        st.info("Your strength sessions will appear here after your first log.")
with right:
    st.subheader("Recent runs")
    if data["running"]:
        st.dataframe([
            {"Date": row["workout_date"], "Type": row["run_type"],
             "Distance (mi)": round(km_to_miles(row["distance_km"]), 2),
             "Pace (/mi)": f"{row['duration_minutes'] / km_to_miles(row['distance_km']):.1f} min"}
            for row in data["running"][:6]
        ], hide_index=True, use_container_width=True)
    else:
        st.info("Your running sessions will appear here after your first log.")