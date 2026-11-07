from datetime import datetime, timezone

import pytest

from services.timer_service import (
    adjust_deadline,
    format_remaining,
    make_deadline,
    notification_fallback_message,
    pause_remaining,
    remaining_seconds,
    resume_deadline,
)


def test_rest_timer_remaining_pause_resume_and_expiry() -> None:
    now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
    deadline = make_deadline(90, now)
    assert remaining_seconds(deadline, now) == 90
    assert remaining_seconds(deadline, datetime(2026, 11, 7, 12, 0, 30, tzinfo=timezone.utc)) == 60
    assert pause_remaining(deadline, datetime(2026, 11, 7, 12, 0, 30, tzinfo=timezone.utc)) == 60
    resumed = resume_deadline(60, now)
    assert remaining_seconds(resumed, now) == 60
    assert remaining_seconds(deadline, datetime(2026, 11, 7, 12, 2, tzinfo=timezone.utc)) == 0
    assert format_remaining(65) == "01:05"


def test_rest_timer_adjustment_and_invalid_values() -> None:
    now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
    deadline = make_deadline(60, now)
    assert remaining_seconds(adjust_deadline(deadline, 15, now), now) == 75
    assert remaining_seconds(adjust_deadline(deadline, -30, now), now) == 30
    with pytest.raises(ValueError):
        make_deadline(-1, now)


def test_notifications_have_an_in_app_fallback() -> None:
    assert "unavailable" in notification_fallback_message(False, "default")
    assert "blocked" in notification_fallback_message(True, "denied")
    assert "in-app timer" in notification_fallback_message(True, "granted")