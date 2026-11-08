import streamlit as st

from services import database, plan_service, running_service, strength_service
from services.coach_service import build_coach_prompt
from services.gemini_plan_service import GEMINI_MODELS, gemini_configured, generate_text


st.set_page_config(page_title="Trainer | FitPilot", page_icon="F", layout="wide")
database.init_database()
profile = database.get_profile()
st.title("Trainer")
st.caption("Ask about this week's training. Replies stay in this browser session and are general guidance, not medical advice.")
if profile is None:
    st.warning("Set up your athlete profile on the Dashboard before talking with your coach.")
    st.stop()

if not gemini_configured():
    st.info("Add GEMINI_API_KEY to your .env file to use the trainer.")
    st.stop()

st.selectbox(
    "Gemini model",
    GEMINI_MODELS,
    format_func=lambda model_id: (
        "Gemini 3.5 Flash-Lite" if model_id == "gemini-3.5-flash-lite" else "Gemini 3.5 Flash"
    ),
    key="trainer_gemini_model",
    help="Flash-Lite is the default. Choose Flash when Flash-Lite is busy.",
)

if "trainer_messages" not in st.session_state:
    st.session_state["trainer_messages"] = []

messages = st.session_state["trainer_messages"]
if messages:
    for message in messages:
        speaker = "You" if message["role"] == "user" else "Coach"
        st.markdown(f"**{speaker}:** {message['content']}")
else:
    st.caption("No questions yet this session.")

if st.session_state.pop("trainer_clear_input", False):
    st.session_state["trainer_question"] = ""

with st.form("trainer_question_form", clear_on_submit=False):
    question = st.text_area(
        "Question",
        key="trainer_question",
        placeholder="Ask about today's session, recovery, or how the week fits together.",
    )
    submitted = st.form_submit_button("Send", type="primary")

if submitted:
    text = question.strip()
    if text:
        prompt = build_coach_prompt(
            profile,
            plan_service.get_current_plan(),
            strength_service.list_workouts(limit=3),
            running_service.list_workouts(limit=3),
            messages,
            text,
        )
        try:
            with st.spinner("Asking your coach..."):
                reply = generate_text(prompt, model=st.session_state["trainer_gemini_model"])
            messages.append({"role": "user", "content": text})
            messages.append({"role": "coach", "content": reply.strip()})
            st.session_state["trainer_clear_input"] = True
            st.rerun()
        except Exception as error:
            st.error(f"Coach reply not generated: {error}")
