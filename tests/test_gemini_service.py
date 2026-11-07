import json

import pytest
from google.genai import errors

from services import gemini_service


def _draft_json() -> str:
    return json.dumps({
        "name": "Upper Body A", "notes": "Leave a few reps in reserve.",
        "exercises": [{
            "exercise_name": "Bench Press", "sets": 3,
            "target_reps_min": 8, "target_reps_max": 12,
            "starting_weight_kg": None, "notes": "Controlled reps",
        }],
    })


def test_gemini_generation_is_structured_and_closes_client(monkeypatch) -> None:
    calls = {}

    class Models:
        def generate_content(self, **kwargs):
            calls.update(kwargs)
            return type("Response", (), {"text": _draft_json()})()

    class Client:
        models = Models()

        def __init__(self, api_key):
            calls["api_key"] = api_key

        def close(self):
            calls["closed"] = True

    draft = gemini_service.generate_routine_draft(
        {"primary_goal": "Strength"}, api_key="test-key", client_factory=Client,
    )
    assert draft.name == "Upper Body A"
    assert calls["api_key"] == "test-key"
    assert calls["config"].response_mime_type == "application/json"
    assert calls["closed"] is True


def test_gemini_missing_key_and_invalid_response_are_graceful(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(gemini_service, "get_gemini_api_key", lambda: None)
    with pytest.raises(gemini_service.GeminiRoutineError, match="not configured"):
        gemini_service.generate_routine_draft({})

    class Models:
        def generate_content(self, **kwargs):
            return type("Response", (), {"text": "not JSON"})()

    class Client:
        models = Models()

        def __init__(self, api_key):
            pass

        def close(self):
            pass

    with pytest.raises(gemini_service.GeminiRoutineError, match="did not pass validation"):
        gemini_service.generate_routine_draft({}, api_key="test-key", client_factory=Client)


def test_gemini_quota_and_network_errors_are_graceful() -> None:
    class QuotaModels:
        def generate_content(self, **kwargs):
            raise errors.APIError(429, {"error": {"message": "quota exhausted"}})

    class QuotaClient:
        models = QuotaModels()

        def __init__(self, api_key):
            pass

        def close(self):
            pass

    with pytest.raises(gemini_service.GeminiRoutineError, match="quota"):
        gemini_service.generate_routine_draft({}, api_key="test-key", client_factory=QuotaClient)

    class NetworkModels:
        def generate_content(self, **kwargs):
            raise ConnectionError("offline")

    class NetworkClient:
        models = NetworkModels()

        def __init__(self, api_key):
            pass

        def close(self):
            pass

    with pytest.raises(gemini_service.GeminiRoutineError, match="temporarily unavailable"):
        gemini_service.generate_routine_draft({}, api_key="test-key", client_factory=NetworkClient)