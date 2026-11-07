from datetime import datetime, timedelta, timezone


def _utc_now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def make_deadline(seconds: int, now: datetime | None = None) -> str:
    if seconds < 0:
        raise ValueError("Rest duration cannot be negative")
    return (_utc_now(now) + timedelta(seconds=seconds)).isoformat()


def remaining_seconds(
    deadline: str | None,
    now: datetime | None = None,
    paused_remaining_seconds: int | None = None,
) -> int:
    if paused_remaining_seconds is not None:
        return max(0, paused_remaining_seconds)
    if deadline is None:
        return 0
    end = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
    return max(0, int((end - _utc_now(now)).total_seconds() + 0.999))


def pause_remaining(deadline: str | None, now: datetime | None = None) -> int:
    return remaining_seconds(deadline, now)


def resume_deadline(seconds: int, now: datetime | None = None) -> str:
    return make_deadline(seconds, now)


def adjust_deadline(deadline: str | None, adjustment_seconds: int, now: datetime | None = None) -> str:
    if deadline is None:
        raise ValueError("Cannot adjust a timer that is not running")
    current = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
    updated = current + timedelta(seconds=adjustment_seconds)
    return max(updated, _utc_now(now)).isoformat()


def notification_fallback_message(supported: bool, permission: str) -> str:
    if not supported:
        return "Browser notifications are unavailable; keep the in-app timer visible."
    if permission == "denied":
        return "Browser notifications are blocked; the in-app timer will alert you."
    if permission not in {"granted", "default"}:
        return "The in-app timer will alert you when rest ends."
    return "The in-app timer remains active if browser notifications are disabled."


def format_remaining(seconds: int) -> str:
    minutes, remainder = divmod(max(0, seconds), 60)
    return f"{minutes:02d}:{remainder:02d}"