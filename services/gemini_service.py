import os

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from models.schemas import WorkoutRoutineInput


load_dotenv()


class GeminiRoutineError(RuntimeError):
    pass


def get_gemini_api_key() -> str | None:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if api_key:
        return api_key
    try:
        import streamlit as st

        return st.secrets.get("GEMINI_API_KEY") or st.secrets.get("GOOGLE_API_KEY")
    except Exception:
        return None


def generate_routine_draft(
    profile: dict,
    api_key: str | None = None,
    client_factory=None,
    model_name: str | None = None,
) -> WorkoutRoutineInput:
    key = api_key or get_gemini_api_key()
    if not key:
        raise GeminiRoutineError(
            "Gemini is not configured. Add GEMINI_API_KEY to your local .env or Streamlit secrets, or create a routine manually."
        )

    prompt = (
        "Create one safe, editable strength workout routine for the athlete profile below. "
        "Use only their available equipment, keep the session within their stated duration, "
        "use conservative set and rep prescriptions, and avoid diagnosing or treating injuries. "
        "Set target rep ranges for every exercise. Starting weights may be null when not supported by the profile. "
        "The response is a draft for user review, not medical advice.\n\n"
        f"Athlete profile: {profile}"
    )

    try:
        client = (client_factory or genai.Client)(api_key=key)
        try:
            response = client.models.generate_content(
                model=model_name or os.getenv("GEMINI_MODEL", "gemini-3.5-flash"),
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=WorkoutRoutineInput.model_json_schema(),
                    temperature=0.4,
                ),
            )
        finally:
            client.close()
        if not response.text:
            raise GeminiRoutineError("Gemini returned an empty routine draft. Please try again.")
        return WorkoutRoutineInput.model_validate_json(response.text)
    except GeminiRoutineError:
        raise
    except ValidationError as error:
        raise GeminiRoutineError("Gemini returned a routine that did not pass validation. Please try again.") from error
    except errors.APIError as error:
        if getattr(error, "code", None) == 429:
            message = "Gemini rate limit or quota reached. Please try again later, or create a routine manually."
        else:
            message = "Gemini could not generate a routine right now. Please try again, or create one manually."
        raise GeminiRoutineError(message) from error
    except Exception as error:
        raise GeminiRoutineError("Gemini is temporarily unavailable. You can still create a routine manually.") from error