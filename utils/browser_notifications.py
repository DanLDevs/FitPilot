import json
from html import escape

from services.timer_service import format_remaining, remaining_seconds


_REST_OVER = "Rest is over. Ready for your next set?"


def rest_timer_html(
    workout_id: int,
    deadline: str | None,
    paused_remaining_seconds: int | None,
) -> str:
    """Countdown markup that ticks in the browser from a saved deadline."""
    paused = paused_remaining_seconds is not None
    remaining = remaining_seconds(deadline, paused_remaining_seconds=paused_remaining_seconds)
    if paused:
        status = "Paused"
    elif deadline and remaining == 0:
        status = _REST_OVER
    else:
        status = "Resting"
    border = "#63c58d" if status == _REST_OVER else "#3d5246"
    config = json.dumps({
        "workoutId": workout_id,
        "deadline": None if paused else deadline,
        "paused": paused,
    })
    countdown = "" if paused or not deadline else f"""
  const endAt = Date.parse(config.deadline);
  const storageKey = `fitpilot-rest-${{config.workoutId}}-${{endAt}}`;
  let notified = false;
  const format = (seconds) => {{
    const minutes = Math.floor(seconds / 60);
    const remainder = seconds % 60;
    return String(minutes).padStart(2, "0") + ":" + String(remainder).padStart(2, "0");
  }};
  const finish = () => {{
    if (window.__fitpilotRestTimer) {{
      clearInterval(window.__fitpilotRestTimer);
      window.__fitpilotRestTimer = null;
    }}
    if (status.textContent !== {_js_string(_REST_OVER)}) status.textContent = {_js_string(_REST_OVER)};
    root.style.borderColor = "#63c58d";
    if (notified) return;
    notified = true;
    try {{
      if (localStorage.getItem(storageKey)) return;
      localStorage.setItem(storageKey, "1");
    }} catch (_) {{}}
    if (supported && Notification.permission === "granted") {{
      try {{ new Notification("Rest is over", {{ body: "Ready for your next set?" }}); }} catch (_) {{}}
    }}
  }};
  const tick = () => {{
    const seconds = Math.max(0, Math.ceil((endAt - Date.now()) / 1000));
    clock.textContent = format(seconds);
    if (seconds > 0) {{
      if (status.textContent !== "Resting") status.textContent = "Resting";
      return;
    }}
    finish();
  }};
  tick();
  if (Date.now() < endAt) window.__fitpilotRestTimer = setInterval(tick, 1000);"""
    return f"""<div id="fitpilot-rest-{workout_id}" role="timer" style="background:#202825;border:1px solid {border};border-radius:12px;padding:14px 16px;margin:4px 0 12px;">
<div style="font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#9fb3a6;">Rest timer</div>
<div data-clock style="font-size:52px;line-height:1.1;font-weight:700;color:#edf3ee;font-variant-numeric:tabular-nums;">{escape(format_remaining(remaining))}</div>
<div data-status aria-live="polite" style="font-size:16px;color:#d7e2dc;margin:4px 0 12px;">{escape(status)}</div>
<div style="display:flex;flex-wrap:wrap;gap:12px;align-items:center;min-height:44px;">
<button data-enable type="button" style="background:#294234;color:#eff8f2;border:1px solid #54725f;border-radius:8px;padding:10px 12px;min-height:44px;">Enable browser notification</button>
<span data-message style="font-size:13px;color:#d7e2dc;">The in-app timer remains active.</span>
</div></div>
<script>
(() => {{
  const config = {config};
  if (window.__fitpilotRestTimer) {{
    clearInterval(window.__fitpilotRestTimer);
    window.__fitpilotRestTimer = null;
  }}
  const root = document.getElementById("fitpilot-rest-" + config.workoutId);
  if (!root) return;
  const clock = root.querySelector("[data-clock]");
  const status = root.querySelector("[data-status]");
  const button = root.querySelector("[data-enable]");
  const message = root.querySelector("[data-message]");
  const supported = "Notification" in window;
  if (!supported) {{ message.textContent = "Notifications unavailable here; use the in-app timer."; button.disabled = true; }}
  else if (Notification.permission === "granted") {{ message.textContent = "Browser notification enabled."; }}
  else if (Notification.permission === "denied") {{ message.textContent = "Notifications blocked; use the in-app timer."; button.disabled = true; }}
  button.addEventListener("click", async () => {{
    try {{
      const permission = await Notification.requestPermission();
      message.textContent = permission === "granted" ? "Browser notification enabled." : "Permission not granted; use the in-app timer.";
      if (permission !== "granted") button.disabled = true;
    }} catch (_) {{ message.textContent = "Notifications unavailable; use the in-app timer."; button.disabled = true; }}
  }});
  if (config.paused || !config.deadline) return;{countdown}
}})();
</script>"""


def _js_string(value: str) -> str:
    return json.dumps(value)

