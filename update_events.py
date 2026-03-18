"""
Weekly Local Events Updater
Fetches events for 2 Seattle locations via Claude AI
and generates a beautiful static index.html hosted via GitHub Pages.
"""

import os
import json
import time
import re
import requests
from datetime import datetime, timedelta
from urllib.parse import quote_plus


ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

LOCATIONS = [
    {"id": "wallingford",  "label": "Wallingford, Seattle"},
    {"id": "alki",         "label": "Alki Beach, Seattle"},
]

API_TIMEOUT = 45

CATEGORY_PHOTOS = {
    "music":    "photo-1493225457124-a3eb161ffa5f",
    "concert":  "photo-1470229722913-7c0e2dbbafd3",
    "festival": "photo-1533174072545-7a4b6ad7a6c3",
    "food":     "photo-1555939594-58d7cb561ad1",
    "market":   "photo-1488459716781-31db52582fe9",
    "farmers":  "photo-1488459716781-31db52582fe9",
    "outdoor":  "photo-1441974231531-c6227db76b6e",
    "hike":     "photo-1551632811-561732d1e306",
    "park":     "photo-1500534314209-a25ddb2bd429",
    "art":      "photo-1578926375605-eaf7559b1458",
    "gallery":  "photo-1531058020387-3be344556be6",
    "theater":  "photo-1507003211169-0a1dd7228f2d",
    "sports":   "photo-1471295253337-3ceaaedca402",
    "family":   "photo-1536640712-4d4c36ff0e4e",
    "beach":    "photo-1507525428034-b723cf961d3e",
    "water":    "photo-1548438294-1ad5d5f4f063",
    "seattle":  "photo-1502175353174-a7a70e73b362",
    "default":  "photo-1496442226666-8d4d0e62e6e9",
}

def get_photo_url(event_name, description):
    text = (event_name + " " + description).lower()
    for keyword, photo_id in CATEGORY_PHOTOS.items():
        if keyword in text:
            return f"https://images.unsplash.com/{photo_id}?w=600&q=80&fit=crop"
    return f"https://images.unsplash.com/{CATEGORY_PHOTOS['default']}?w=600&q=80&fit=crop"

def get_category_label(event_name, description):
    text = (event_name + " " + description).lower()
    if any(w in text for w in ["concert", "music", "band", "live"]):
        return ("🎵", "Music")
    if any(w in text for w in ["food", "restaurant", "eat", "taste", "chef", "dining"]):
        return ("🍴", "Food & Drink")
    if any(w in text for w in ["market", "farmers", "bazaar", "craft"]):
        return ("🛍️", "Market")
    if any(w in text for w in ["festival", "fest", "fair", "celebration"]):
        return ("🎉", "Festival")
    if any(w in text for w in ["hike", "trail", "outdoor", "nature", "park", "kayak"]):
        return ("🌿", "Outdoors")
    if any(w in text for w in ["art", "gallery", "exhibit", "museum"]):
        return ("🎨", "Arts")
    if any(w in text for w in ["sport", "run", "race", "game", "tournament"]):
        return ("🏅", "Sports")
    if any(w in text for w in ["family", "kid", "child"]):
        return ("👨‍👩‍👧", "Family")
    return ("📍", "Local Event")

def make_search_url(event_name, location_label):
    """Always-working Google search URL for the event."""
    query = f"{event_name} {location_label} event"
    return f"https://www.google.com/search?q={quote_plus(query)}"


def fetch_events_for_location(location_label):
    today      = datetime.now()
    week_ahead = today + timedelta(days=7)
    date_range = f"{today.strftime('%B %d')} - {week_ahead.strftime('%B %d, %Y')}"

    prompt = f"""Find 6 upcoming local events near {location_label} for the week of {date_range}.
Include a mix of FREE and PAID events. Include variety: festivals, markets, concerts, outdoor activities, food events.
Return ONLY a JSON array, no other text:
[{{
  "name": "Event Name",
  "date": "Sat Mar 22",
  "time": "10am-4pm",
  "location": "Venue Name",
  "description": "One engaging sentence about why visitors would love this.",
  "price": "Free" or "$15 per person"
}}]
Do not include any URLs — only the fields above. Return ONLY the JSON array."""

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
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 1500,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=API_TIMEOUT,
            )

            if response.status_code == 429:
                print(f"  Rate limited. Waiting 60s...")
                time.sleep(60)
                continue

            response.raise_for_status()
            data = response.json()
            text = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    text = block["text"]

            clean = re.sub(r"```json|```", "", text).strip()
            match = re.search(r"\[.*?\]", clean, re.DOTALL)
            if match:
                events = json.loads(match.group(0))
                if isinstance(events, list) and len(events) > 0:
                    return events

        except requests.exceptions.Timeout:
            print(f"  Timed out on attempt {attempt + 1}")
        except json.JSONDecodeError as e:
            print(f"  JSON error on attempt {attempt + 1}: {e}")
        except Exception as e:
            print(f"  Error on attempt {attempt + 1}: {e}")

        time.sleep(10)

    return []


def build_html(all_events):
    today      = datetime.now()
    week_ahead = today + timedelta(days=7)
    date_range = f"{today.strftime('%B %d')} – {week_ahead.strftime('%B %d, %Y')}"
    updated    = today.strftime("%B %d, %Y")

    tabs_html = ""
    for i, loc in enumerate(LOCATIONS):
        active = "active" if i == 0 else ""
        tabs_html += f'<button class="tab {active}" onclick="switchTab(\'{loc["id"]}\', this)">{loc["label"]}</button>\n'

    panels_html = ""
    for i, loc in enumerate(LOCATIONS):
        events  = all_events.get(loc["id"], [])
        cards   = ""
        display = "grid" if i == 0 else "none"

        if not events:
            cards = '<div class="no-events"><p>🔍 No events found this week. Check back next Monday!</p></div>'
        else:
            for e in events:
                photo_url  = get_photo_url(e.get("name", ""), e.get("description", ""))
                icon, cat  = get_category_label(e.get("name", ""), e.get("description", ""))
                search_url = make_search_url(e.get("name", ""), loc["label"])

                # Price badge
                price      = e.get("price", "")
                is_free    = price.strip().lower() in ("free", "free!")
                price_html = ""
                if price:
                    price_class = "price-free" if is_free else "price-paid"
                    price_label = "✨ Free" if is_free else f"🎟️ {price}"
                    price_html  = f'<span class="price-badge {price_class}">{price_label}</span>'

                time_str = f'<span>🕐 {e["time"]}</span>' if e.get("time") else ""
                loc_str  = f'<span>📍 {e["location"]}</span>' if e.get("location") else ""

                cards += f"""
            <a href="{search_url}" target="_blank" rel="noopener" class="card-link">
            <div class="card">
              <div class="card-img" style="background-image:url('{photo_url}')">
                <span class="badge">{icon} {cat}</span>
                {price_html}
              </div>
              <div class="card-body">
                <h3>{e.get("name", "Event")}</h3>
                <div class="meta">
                  <span>📅 {e.get("date", "")}</span>
                  {time_str}
                  {loc_str}
                </div>
                <p>{e.get("description", "")}</p>
                <span class="cta">Search for details →</span>
              </div>
            </div>
            </a>"""

        panels_html += f'<div id="panel-{loc["id"]}" class="panel" style="display:{display};">{cards}</div>\n'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Local Events This Week</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet"/>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Inter', sans-serif; background: #f8f9fb; color: #1a1a2e; }}

    .hero {{
      background: linear-gradient(135deg, #1a1a2e 0%, #16213e 60%, #0f3460 100%);
      color: #fff;
      padding: 48px 24px 40px;
      text-align: center;
    }}
    .hero h1 {{ font-size: 2rem; font-weight: 700; letter-spacing: -0.5px; margin-bottom: 8px; }}
    .hero p {{ font-size: 0.95rem; color: rgba(255,255,255,0.65); margin-bottom: 4px; }}
    .date-badge {{
      display: inline-block;
      background: rgba(255,255,255,0.12);
      border: 1px solid rgba(255,255,255,0.2);
      padding: 6px 16px; border-radius: 999px;
      font-size: 0.82rem; color: rgba(255,255,255,0.85); margin-top: 12px;
    }}

    .tabs-wrap {{
      background: #fff; border-bottom: 1px solid #e5e7eb;
      padding: 0 24px; display: flex; gap: 4px;
      overflow-x: auto; justify-content: center;
    }}
    .tab {{
      padding: 14px 20px; border: none; background: none;
      font-size: 0.88rem; font-weight: 500; color: #6b7280;
      cursor: pointer; border-bottom: 3px solid transparent;
      white-space: nowrap; transition: all 0.2s;
      font-family: 'Inter', sans-serif;
    }}
    .tab:hover {{ color: #1a1a2e; }}
    .tab.active {{ color: #0f3460; border-bottom-color: #0f3460; font-weight: 600; }}

    .content {{ max-width: 1100px; margin: 0 auto; padding: 32px 20px 48px; }}

    .panel {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
      gap: 24px;
    }}

    .card-link {{ text-decoration: none; color: inherit; display: block; }}
    .card {{
      background: #fff; border-radius: 16px; overflow: hidden;
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
      transition: transform 0.2s, box-shadow 0.2s; height: 100%;
    }}
    .card-link:hover .card {{
      transform: translateY(-4px);
      box-shadow: 0 12px 28px rgba(0,0,0,0.12);
    }}
    .card-img {{
      height: 180px; background-size: cover; background-position: center;
      position: relative;
    }}
    .badge {{
      position: absolute; top: 12px; left: 12px;
      background: rgba(0,0,0,0.55); backdrop-filter: blur(6px);
      color: #fff; font-size: 0.72rem; font-weight: 600;
      padding: 4px 10px; border-radius: 999px; letter-spacing: 0.3px;
    }}
    .price-badge {{
      position: absolute; top: 12px; right: 12px;
      font-size: 0.72rem; font-weight: 700;
      padding: 4px 10px; border-radius: 999px;
    }}
    .price-free {{ background: #dcfce7; color: #166534; }}
    .price-paid {{ background: #fef3c7; color: #92400e; }}

    .card-body {{ padding: 18px 20px 20px; }}
    .card-body h3 {{ font-size: 1rem; font-weight: 600; margin-bottom: 8px; line-height: 1.4; }}
    .meta {{ display: flex; flex-direction: column; gap: 3px; margin-bottom: 10px; }}
    .meta span {{ font-size: 0.78rem; color: #6b7280; }}
    .card-body p {{ font-size: 0.88rem; color: #4b5563; line-height: 1.55; margin-bottom: 12px; }}
    .cta {{ font-size: 0.82rem; font-weight: 600; color: #0f3460; }}

    .no-events {{ grid-column: 1/-1; text-align: center; padding: 60px 0; color: #9ca3af; }}
    .footer {{ text-align: center; font-size: 0.72rem; color: #9ca3af; padding: 0 20px 32px; }}

    @media (max-width: 600px) {{
      .hero h1 {{ font-size: 1.5rem; }}
      .panel {{ grid-template-columns: 1fr; }}
      .tab {{ padding: 12px 14px; font-size: 0.82rem; }}
    }}
  </style>
</head>
<body>
  <div class="hero">
    <h1>🗓️ Local Events This Week</h1>
    <p>Curated picks near each of our properties</p>
    <span class="date-badge">📅 {date_range}</span>
  </div>

  <div class="tabs-wrap">
    {tabs_html}
  </div>

  <div class="content">
    {panels_html}
  </div>

  <div class="footer">
    Last updated {updated} &nbsp;·&nbsp; Events subject to change — always verify with the organiser.
    Clicking an event searches Google for the latest details.
  </div>

  <script>
    function switchTab(id, btn) {{
      document.querySelectorAll('.panel').forEach(p => p.style.display = 'none');
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      var el = document.getElementById('panel-' + id);
      if (el) el.style.display = 'grid';
      btn.classList.add('active');
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
