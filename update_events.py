"""
Weekly Local Events Updater for Lodgify — Multi-Location Dropdown
Fetches events for multiple property locations via Claude AI (web search),
then updates a single Lodgify page with a location dropdown.
"""

import os
import json
import requests
from datetime import datetime, timedelta


# ── Config (set these as GitHub Secrets / Variables) ─────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
LODGIFY_API_KEY   = os.environ["LODGIFY_API_KEY"]
LODGIFY_PAGE_ID   = os.environ["LODGIFY_PAGE_ID"]

# The three property locations
LOCATIONS = [
    {"id": "wallingford",  "label": "Wallingford, Seattle"},
    {"id": "alki",         "label": "Alki Beach, Seattle"},
    {"id": "lake_hills",   "label": "Lake Hills, Bellevue"},
]


# ── Step 1: Fetch events for one location via Claude ─────────────────────────
def fetch_events_for_location(location_label: str) -> list:
    today      = datetime.now()
    week_ahead = today + timedelta(days=7)
    date_range = f"{today.strftime('%B %d')} - {week_ahead.strftime('%B %d, %Y')}"

    prompt = f"""
Search the web and find 5-6 interesting upcoming local events near {location_label}
for the week of {date_range}.

Include a variety: festivals, farmers markets, concerts, outdoor activities, food events, etc.
For each event return ONLY a JSON array (no markdown, no extra text) with objects like:
{{
  "name": "Event Name",
  "date": "Saturday, March 22",
  "time": "10:00 AM - 4:00 PM",
  "location": "Venue Name",
  "description": "One sentence about why guests would enjoy this.",
  "url": "https://..." 
}}
Return ONLY the JSON array, nothing else.
"""

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 2000,
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()

    # Extract last text block (after tool use rounds)
    text = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            text = block["text"]

    clean = text.replace("```json", "").replace("```", "").strip()
    try:
        events = json.loads(clean)
        if isinstance(events, list):
            return events
    except json.JSONDecodeError as e:
        print(f"Warning: JSON parse error for {location_label}: {e}")

    return []


# ── Step 2: Build HTML with dropdown ─────────────────────────────────────────
def build_html(all_events):
    today      = datetime.now()
    week_ahead = today + timedelta(days=7)
    date_range = f"{today.strftime('%B %d')} - {week_ahead.strftime('%B %d, %Y')}"

    # Build dropdown options
    options_html = ""
    for loc in LOCATIONS:
        options_html += f'<option value="{loc["id"]}">{loc["label"]}</option>\n'

    # Build event panels for each location
    panels_html = ""
    for i, loc in enumerate(LOCATIONS):
        events = all_events.get(loc["id"], [])
        cards  = ""

        if not events:
            cards = '<p style="color:#6b7280;">No events found for this location this week.</p>'
        else:
            for e in events:
                link_open  = f'<a href="{e["url"]}" target="_blank" rel="noopener" style="color:inherit;text-decoration:none;">' if e.get("url") else ""
                link_close = "</a>" if e.get("url") else ""
                time_str = f" &nbsp;&middot;&nbsp; {e['time']}" if e.get('time') else ""
                loc_str  = f" &nbsp;&middot;&nbsp; {e['location']}" if e.get('location') else ""
                cards += f"""
                <div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px 24px;margin-bottom:16px;">
                  <h3 style="margin:0 0 6px;font-size:1.05rem;color:#1a1a2e;">
                    {link_open}{e.get('name', 'Event')}{link_close}
                  </h3>
                  <p style="margin:0 0 8px;font-size:0.82rem;color:#6b7280;line-height:1.6;">
                    {e.get('date', '')}{time_str}{loc_str}
                  </p>
                  <p style="margin:0;font-size:0.93rem;color:#374151;line-height:1.5;">
                    {e.get('description', '')}
                  </p>
                </div>"""

        display = "block" if i == 0 else "none"
        panels_html += f"""
        <div id="panel-{loc['id']}" style="display:{display};">
          {cards}
        </div>"""

    return f"""
<section style="font-family:'Helvetica Neue',Arial,sans-serif;max-width:780px;margin:0 auto;padding:16px 0;">
  <h2 style="font-size:1.5rem;color:#1a1a2e;margin-bottom:4px;">Local Events This Week</h2>
  <p style="color:#6b7280;margin-bottom:20px;font-size:0.9rem;">{date_range}</p>

  <div style="margin-bottom:24px;">
    <label for="location-select" style="display:block;font-size:0.85rem;font-weight:600;color:#374151;margin-bottom:6px;">
      Select a property location
    </label>
    <select id="location-select"
            onchange="showPanel(this.value)"
            style="width:100%;max-width:340px;padding:10px 14px;font-size:0.95rem;
                   border:1px solid #d1d5db;border-radius:8px;background:#fff;
                   color:#1a1a2e;cursor:pointer;">
      {options_html}
    </select>
  </div>

  {panels_html}

  <p style="font-size:0.75rem;color:#9ca3af;margin-top:24px;">
    Updated automatically every Monday. Events subject to change — always verify with the organiser.
  </p>
</section>

<script>
function showPanel(locationId) {{
  var panels = document.querySelectorAll('[id^="panel-"]');
  panels.forEach(function(p) {{ p.style.display = 'none'; }});
  var target = document.getElementById('panel-' + locationId);
  if (target) target.style.display = 'block';
}}
</script>
"""


# ── Step 3: Update Lodgify page ───────────────────────────────────────────────
def update_lodgify_page(html_content):
    url = f"https://api.lodgify.com/v2/website/pages/{LODGIFY_PAGE_ID}/sections"
    headers = {
        "X-ApiKey": LODGIFY_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {"type": "text", "content": html_content}

    response = requests.put(url, headers=headers, json=payload, timeout=30)

    if response.status_code in (200, 204):
        print("Lodgify page updated successfully.")
    else:
        print(f"Lodgify API error {response.status_code}: {response.text}")
        response.raise_for_status()


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    all_events = {}

    for loc in LOCATIONS:
        print(f"Fetching events for {loc['label']}...")
        events = fetch_events_for_location(loc["label"])
        all_events[loc["id"]] = events
        print(f"  Found {len(events)} events")

    print("Building HTML with dropdown...")
    html = build_html(all_events)

    print("Updating Lodgify page...")
    update_lodgify_page(html)
    print("Done!")


if __name__ == "__main__":
    main()
