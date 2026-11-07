from datetime import datetime, timezone

import pytest

from pathlib import Path

from services.timer_service import (
    adjust_deadline,
    format_remaining,
    make_deadline,
    notification_fallback_message,
    pause_remaining,
    remaining_seconds,
    resume_deadline,
)
from utils.browser_notifications import rest_timer_html


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


def test_rest_countdown_ticks_in_the_page_and_alerts_once() -> None:
    deadline = "2026-11-07T12:01:30+00:00"
    running = rest_timer_html(7, deadline, None)
    assert deadline in running
    assert "setInterval" in running
    assert "localStorage" in running
    assert "run_every" not in running
    assert running.count("new Notification") == 1
    assert "Notifications unavailable here; use the in-app timer." in running
    assert "Notifications blocked; use the in-app timer." in running

    paused = rest_timer_html(7, None, 45)
    assert "Paused" in paused
    assert "00:45" in paused
    assert "setInterval" not in paused
    assert "new Notification" not in paused

    expired = rest_timer_html(7, "2020-01-01T00:00:00+00:00", None)
    assert "Rest is over. Ready for your next set?" in expired


def test_live_workout_page_does_not_rerun_the_timer() -> None:
    source = (Path(__file__).resolve().parents[1] / "pages" / "3_Live_Workout.py").read_text(encoding="utf-8")
    assert "run_every" not in source
    assert "rest_timer_html" in source