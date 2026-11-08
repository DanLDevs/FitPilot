import json
from html import escape

from services.timer_service import format_remaining, remaining_seconds


def run_clock_html(
    run_id: int,
    deadline: str | None,
    paused_remaining_seconds: int | None,
    idle_seconds: int,
) -> str:
    """Countdown markup for a run clock. It does not send a notification."""
    paused = paused_remaining_seconds is not None
    if paused:
        remaining = remaining_seconds(None, paused_remaining_seconds=paused_remaining_seconds)
        status = "Paused"
    elif deadline:
        remaining = remaining_seconds(deadline)
        status = "Time is up" if remaining == 0 else "Running"
    else:
        remaining = max(0, idle_seconds)
        status = "Ready"
    border = "#63c58d" if status == "Time is up" else "#3d5246"
    config = json.dumps({
        "runId": run_id,
        "deadline": None if paused or not deadline else deadline,
    })
    countdown = ""
    if deadline and not paused:
        countdown = """
  const endAt = Date.parse(config.deadline);
  const format = (seconds) => {
    const minutes = Math.floor(seconds / 60);
    const remainder = seconds % 60;
    return String(minutes).padStart(2, "0") + ":" + String(remainder).padStart(2, "0");
  };
  const tick = () => {
    const seconds = Math.max(0, Math.ceil((endAt - Date.now()) / 1000));
    clock.textContent = format(seconds);
    if (seconds > 0) {
      status.textContent = "Running";
      return;
    }
    status.textContent = "Time is up";
    root.style.borderColor = "#63c58d";
    if (window.__fitpilotRunTimer) {
      clearInterval(window.__fitpilotRunTimer);
      window.__fitpilotRunTimer = null;
    }
  };
  tick();
  if (Date.now() < endAt) window.__fitpilotRunTimer = setInterval(tick, 1000);"""
    return f"""<div id="fitpilot-run-{run_id}" role="timer" style="background:#202825;border:1px solid {border};border-radius:12px;padding:14px 16px;margin:4px 0 12px;">
<div style="font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#9fb3a6;">Run clock</div>
<div data-clock style="font-size:52px;line-height:1.1;font-weight:700;color:#edf3ee;font-variant-numeric:tabular-nums;">{escape(format_remaining(remaining))}</div>
<div data-status aria-live="polite" style="font-size:16px;color:#d7e2dc;margin:4px 0 8px;">{escape(status)}</div>
</div>
<script>
(() => {{
  const config = {config};
  if (window.__fitpilotRunTimer) {{
    clearInterval(window.__fitpilotRunTimer);
    window.__fitpilotRunTimer = null;
  }}
  const root = document.getElementById("fitpilot-run-" + config.runId);
  if (!root) return;
  const clock = root.querySelector("[data-clock]");
  const status = root.querySelector("[data-status]");
  if (!config.deadline) return;{countdown}
}})();
</script>"""
