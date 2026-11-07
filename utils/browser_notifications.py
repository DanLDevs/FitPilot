import json


def rest_notification_html(workout_id: int, deadline: str) -> str:
    workout = json.dumps(workout_id)
    end = json.dumps(deadline)
    return f"""<div style="font: 13px sans-serif; color: #d7e2dc; display: flex; flex-wrap: wrap; gap: 12px; align-items: center; min-height: 44px;">
<button id="enable" style="background:#294234;color:#eff8f2;border:1px solid #54725f;border-radius:6px;padding:8px 10px;">Enable browser notification</button>
<span id="message">The in-app timer remains active.</span></div>
<script>
(() => {{
  const endAt = Date.parse({end});
  const storageKey = `fitpilot-rest-${{ {workout} }}-${{endAt}}`;
  const button = document.getElementById('enable');
  const message = document.getElementById('message');
  const supported = 'Notification' in window;
  if (!supported) {{ message.textContent = 'Notifications unavailable here; use the in-app timer.'; button.disabled = true; }}
  else if (Notification.permission === 'granted') {{ message.textContent = 'Browser notification enabled.'; }}
  else if (Notification.permission === 'denied') {{ message.textContent = 'Notifications blocked; use the in-app timer.'; button.disabled = true; }}
  button.addEventListener('click', async () => {{
    try {{
      const permission = await Notification.requestPermission();
      message.textContent = permission === 'granted' ? 'Browser notification enabled.' : 'Permission not granted; use the in-app timer.';
      if (permission !== 'granted') button.disabled = true;
    }} catch (_) {{ message.textContent = 'Notifications unavailable; use the in-app timer.'; button.disabled = true; }}
  }});
  const tick = () => {{
    if (Date.now() < endAt) return;
    try {{
      if (localStorage.getItem(storageKey)) return;
      localStorage.setItem(storageKey, '1');
    }} catch (_) {{}}
    if (supported && Notification.permission === 'granted') {{
      try {{ new Notification('Rest is over', {{ body: 'Ready for your next set?' }}); }} catch (_) {{}}
    }}
  }};
  tick();
  const interval = setInterval(tick, 1000);
  setTimeout(() => clearInterval(interval), Math.max(1000, endAt - Date.now() + 60000));
}})();
</script>"""