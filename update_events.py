"""
Weekly Local Events Updater
Fetches events for 3 Seattle/Bellevue locations via Claude AI
and generates a static index.html hosted via GitHub Pages.
"""

import os
import json
import time
import re
import requests
from datetime import datetime, timedelta


ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

LOCATIONS = [
    {"id": "wallingford",  "label": "Wallingford, Seattle"},
    {"id": "alki",         "label": "Alki Beach, Seattle"},
    {"id": "lake_hills",   "label": "Lake Hills, Bellevue"},
]

# Hard timeout per location (seconds)
API_TIMEOUT = 45


def fetch_events_for_location(location_label):
    today      = datetime.now()
    week_ahead = today + timedelta(days=7)
    date_range = f"{today.strftime('%B %d')} - {week_ahead.strftime('%B %d, %Y')}"

    prompt = f"""Find 5 upcoming local events near {location_label} for the week of {date_range}.
Include: festivals, markets, concerts, outdoor activities, food events.
Return ONLY a JSON array like this, no other text:
[{{"name":"Event","date":"Sat Mar 22","time":"10am-4pm","location":"Venue","description":"Short description.","url":"https://example.com"}}]"""

    for attempt in range(2):
        try:
            print(f"  API call attempt {attempt + 1}...")
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",  # Faster, lighter model
                    "max_tokens": 1500,
                    "messages": [{"role": "user", "content": prompt}],
                    # No web search tool — avoids indefinite hangs
                },
                timeout=API_TIMEOUT,
            )

            if response.status_code == 429:
                print(f"  Rate limited. Waiting 60s...")
                time.sleep(60)
                continue

            response.raise_for_status()
            data     = response.json()
            text     = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    text = block["text"]

            # Extract JSON array from response
            clean = re.sub(r"```json|```", "", text).strip()
            match = re.search(r"\[.*?\]", clean, re.DOTALL)
            if match:
                events = json.loads(match.group(0))
                if isinstance(events, list) and len(events) > 0:
                    return events

        except requests.exceptions.Timeout:
            print(f"  Timed out after {API_TIMEOUT}s on attempt {attempt + 1}")
        except json.JSONDecodeError as e:
            print(f"  JSON error on attempt {attempt + 1}: {e}")
        except Exception as e:
            print(f"  Error on attempt {attempt + 1}: {e}")

        time.sleep(10)

    return []


def build_html(all_events):
    today      = datetime.now()
    week_ahead = today + timedelta(days=7)
    date_range = f"{today.strftime('%B %d')} - {week_ahead.strftime('%B %d, %Y')}"
    updated    = today.strftime("%A, %B %d %Y")

    options_html = ""
    for loc in LOCATIONS:
        options_html += f'<option value="{loc["id"]}">{loc["label"]}</option>\n'

    panels_html = ""
    for i, loc in enumerate(LOCATIONS):
        events = all_events.get(loc["id"], [])
        cards  = ""

        if not events:
            cards = '<p class="no-events">No events found this week. Check back next Monday!</p>'
        else:
            for e in events:
                link_open  = f'<a href="{e["url"]}" target="_blank" rel="noopener">' if e.get("url") else ""
                link_close = "</a>" if e.get("url") else ""
                time_str   = f'<span class="meta-item">🕐 {e["time"]}</span>' if e.get("time") else ""
                loc_str    = f'<span class="meta-item">📍 {e["location"]}</span>' if e.get("location") else ""
                cards += f"""
        <div class="card">
          <h3>{link_open}{e.get("name", "Event")}{link_close}</h3>
          <div class="meta">
            <span class="meta-item">📅 {e.get("date", "")}</span>
            {time_str}
            {loc_str}
          </div>
          <p>{e.get("description", "")}</p>
        </div>"""

        display = "block" if i == 0 else "none"
        panels_html += f'<div id="panel-{loc["id"]}" class="panel" style="display:{display};">{cards}</div>\n'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Local Events This Week</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background: transparent; color: #1a1a2e; padding: 16px; }}
    h2 {{ font-size: 1.4rem; margin-bottom: 4px; }}
    .subtitle {{ font-size: 0.88rem; color: #6b7280; margin-bottom: 20px; }}
    .dropdown-wrap label {{ display: block; font-size: 0.83rem; font-weight: 600; color: #374151; margin-bottom: 6px; }}
    select {{ width: 100%; max-width: 320px; padding: 10px 14px; font-size: 0.93rem; border: 1px solid #d1d5db; border-radius: 8px; background: #fff; color: #1a1a2e; cursor: pointer; margin-bottom: 24px; }}
    .card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 18px 20px; margin-bottom: 14px; transition: box-shadow 0.2s; }}
    .card:hover {{ box-shadow: 0 4px 14px rgba(0,0,0,0.07); }}
    .card h3 {{ font-size: 1rem; margin-bottom: 6px; }}
    .card h3 a {{ color: inherit; text-decoration: none; }}
    .card h3 a:hover {{ text-decoration: underline; }}
    .meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }}
    .meta-item {{ font-size: 0.8rem; color: #6b7280; }}
    .card p {{ font-size: 0.92rem; color: #374151; line-height: 1.5; }}
    .no-events {{ color: #6b7280; font-size: 0.92rem; padding: 12px 0; }}
    .footer {{ font-size: 0.72rem; color: #9ca3af; margin-top: 20px; }}
  </style>
</head>
<body>
  <h2>🗓️ Local Events This Week</h2>
  <p class="subtitle">{date_range}</p>
  <div class="dropdown-wrap">
    <label for="location-select">📍 Select a property location</label>
    <select id="location-select" onchange="showPanel(this.value)">
      {options_html}
    </select>
  </div>
  {panels_html}
  <p class="footer">Last updated: {updated} &nbsp;·&nbsp; Events subject to change — always verify with the organiser.</p>
  <script>
    function showPanel(id) {{
      document.querySelectorAll('.panel').forEach(p => p.style.display = 'none');
      var el = document.getElementById('panel-' + id);
      if (el) el.style.display = 'block';
    }}
  </script>
</body>
</html>"""


def main():
    all_events = {}

    for i, loc in enumerate(LOCATIONS):
        if i > 0:
            print("  Waiting 15s between calls...")
            time.sleep(15)

        print(f"Fetching events for {loc['label']}...")
        events = fetch_events_for_location(loc["label"])
        all_events[loc["id"]] = events
        print(f"  Found {len(events)} events")

    print("Building HTML...")
    html = build_html(all_events)

    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("Done! docs/index.html updated.")


if __name__ == "__main__":
    main()
