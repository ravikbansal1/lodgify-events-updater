"""
Monthly Local Events Updater — NestInLux
Fetches up to 100 tourist-friendly events per location for the full month,
sorted by popularity, styled to match nestinlux.com brand palette.
"""

import os
import json
import time
import re
import requests
from datetime import datetime, timedelta
from urllib.parse import quote_plus
from concurrent.futures import ThreadPoolExecutor


ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

LOCATIONS = [
    {
        "id": "wallingford", "label": "Wallingford, Seattle",
        "lat": 47.6535, "lng": -122.3366,
        "nearby": "Fremont, Capitol Hill, Queen Anne, South Lake Union, University District, Seattle downtown, Ballard"
    },
    {
        "id": "alki", "label": "Alki Beach, Seattle",
        "lat": 47.5884, "lng": -122.3949,
        "nearby": "West Seattle, Burien, White Center, SoDo, Georgetown, Pioneer Square, downtown Seattle, Vashon Island ferry"
    },
    {
        "id": "lake_hills", "label": "Lake Hills, Bellevue",
        "lat": 47.5990, "lng": -122.1389,
        "nearby": "Bellevue downtown, Redmond, Kirkland, Issaquah, Sammamish, Mercer Island, Eastside, Bothell"
    },
]

FALLBACK_TIMEOUT = 60

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
    "comedy":   "photo-1527224857830-43a7acc85260",
    "sports":   "photo-1471295253337-3ceaaedca402",
    "family":   "photo-1536640712-4d4c36ff0e4e",
    "beach":    "photo-1507525428034-b723cf961d3e",
    "water":    "photo-1548438294-1ad5d5f4f063",
    "wine":     "photo-1510812431401-41d2bd2722f3",
    "beer":     "photo-1535958636474-b021ee887b13",
    "tour":     "photo-1502175353174-a7a70e73b362",
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
    if any(w in text for w in ["concert", "music", "band", "live"]):        return ("🎵", "Music")
    if any(w in text for w in ["comedy", "stand-up", "improv"]):             return ("🎤", "Comedy")
    if any(w in text for w in ["food", "taste", "chef", "dining", "eat"]):  return ("🍴", "Food & Drink")
    if any(w in text for w in ["wine", "winery", "tasting"]):               return ("🍷", "Wine")
    if any(w in text for w in ["beer", "brewery", "brew"]):                 return ("🍺", "Brewery")
    if any(w in text for w in ["market", "farmers", "bazaar", "craft"]):    return ("🛍️", "Market")
    if any(w in text for w in ["festival", "fest", "fair", "celebration"]): return ("🎉", "Festival")
    if any(w in text for w in ["hike", "trail", "outdoor", "nature", "park", "kayak"]): return ("🌿", "Outdoors")
    if any(w in text for w in ["art", "gallery", "exhibit", "museum"]):     return ("🎨", "Arts")
    if any(w in text for w in ["theater", "theatre", "opera", "ballet"]):   return ("🎭", "Theater")
    if any(w in text for w in ["sport", "run", "race", "game", "tournament", "mariners", "sounders", "seahawks"]): return ("🏅", "Sports")
    if any(w in text for w in ["tour", "sightseeing", "cruise", "boat"]):   return ("⛵", "Tours")
    if any(w in text for w in ["family", "kid", "child"]):                  return ("👨‍👩‍👧", "Family")
    return ("📍", "Experience")

def make_search_url(event_name, location_label):
    query = f"{event_name} {location_label} event"
    return f"https://www.google.com/search?q={quote_plus(query)}"

def parse_events(text, source=""):
    if not text or not text.strip():
        print(f"    [{source}] Empty response")
        return []
    clean = re.sub(r"```json|```", "", text).strip()
    start = clean.find("[")
    end   = clean.rfind("]")
    if start == -1 or end == -1 or end <= start:
        print(f"    [{source}] No JSON array found")
        return []
    try:
        events = json.loads(clean[start:end + 1])
        if isinstance(events, list):
            print(f"    [{source}] Parsed {len(events)} events ✅")
            return events
    except json.JSONDecodeError as e:
        print(f"    [{source}] JSON error: {e}")
    return []


def build_prompt(location_label, lat, lng, nearby, month_label):
    return f"""Find up to 100 tourist-friendly ENTERTAINMENT and FUN events happening in {month_label} near {location_label}.

Search ALL of these areas within 20 miles: {location_label}, {nearby}.
CRITICAL: Return as many events as possible — target 100 if they exist. Never return empty.

ONLY include events tourists would love:
✅ Live music, concerts, comedy shows, theater, opera, ballet
✅ Food & drink festivals, wine/beer tastings, night markets, pop-up dinners
✅ Outdoor adventures, scenic hikes, kayaking, boat tours, whale watching
✅ Art exhibitions, museum events, cultural festivals, street fairs
✅ Sports games (Mariners, Sounders, Seahawks, Storm, etc.)
✅ Unique local experiences (tours, classes, immersive events)

❌ NO volunteer events, community cleanups, civic meetings, school events

Sort by POPULARITY (most attended/well-known first, niche events last).
Include a mix of FREE and PAID events.

Return ONLY a JSON array, no markdown:
[{{
  "name": "Event Name",
  "date": "Sat Apr 5",
  "time": "7:30pm",
  "location": "Venue Name, City",
  "popularity": 95,
  "description": "One sentence why a tourist would love this.",
  "price": "Free" or "$25"
}}]
popularity is 1-100 (100 = most popular). Return ONLY the JSON array."""


def fetch_events_for_location(loc):
    label    = loc["label"]
    lat      = loc["lat"]
    lng      = loc["lng"]
    nearby   = loc["nearby"]
    today    = datetime.now()
    # Get first and last day of current month
    first_day = today.replace(day=1)
    if today.month == 12:
        last_day = today.replace(day=31)
    else:
        last_day = (today.replace(month=today.month + 1, day=1) - timedelta(days=1))
    month_label = f"{first_day.strftime('%B %Y')} ({first_day.strftime('%b %d')} – {last_day.strftime('%b %d')})"

    print(f"\n{'='*55}")
    print(f"Fetching events for {label} — {month_label}...")

    for attempt in range(3):
        if attempt > 0:
            wait = 30 * attempt
            print(f"  Retry {attempt} — waiting {wait}s...")
            time.sleep(wait)

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
                    "max_tokens": 16000,
                    "messages": [{"role": "user", "content": build_prompt(
                        label, lat, lng, nearby, month_label
                    )}],
                },
                timeout=FALLBACK_TIMEOUT,
            )

            print(f"  HTTP status: {response.status_code}")

            if response.status_code == 429:
                print(f"  Rate limited, will retry...")
                continue

            response.raise_for_status()
            data   = response.json()
            text   = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    text += block["text"]

            events = parse_events(text, source=label)
            if events:
                # Sort by popularity descending
                def safe_pop(e):
                    try: return -float(e.get("popularity") or 0)
                    except: return 0
                events.sort(key=safe_pop)
                return events[:100]

        except requests.exceptions.Timeout:
            print(f"  Timed out on attempt {attempt + 1}")
        except Exception as e:
            print(f"  Error: {e}")

    return []


def build_html(all_events):
    today      = datetime.now()
    first_day  = today.replace(day=1)
    month_name = first_day.strftime("%B %Y")
    updated    = today.strftime("%B %d, %Y")

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tabs_html = ""
    for i, loc in enumerate(LOCATIONS):
        active = "active" if i == 0 else ""
        count  = len(all_events.get(loc["id"], []))
        tabs_html += f'''<button class="tab {active}" onclick="switchTab('{loc["id"]}', this)">
          {loc["label"]} <span class="tab-count">{count}</span>
        </button>\n'''

    # ── Panels ────────────────────────────────────────────────────────────────
    panels_html = ""
    for i, loc in enumerate(LOCATIONS):
        events  = all_events.get(loc["id"], [])
        cards   = ""
        display = "grid" if i == 0 else "none"

        if not events:
            cards = '<div class="no-events"><p>No events found this month. Check back next update.</p></div>'
        else:
            for e in events:
                photo_url    = get_photo_url(e.get("name", ""), e.get("description", ""))
                icon, cat    = get_category_label(e.get("name", ""), e.get("description", ""))
                search_url   = make_search_url(e.get("name", ""), loc["label"])
                price        = e.get("price", "")
                is_free      = price.strip().lower() in ("free", "free!")
                price_html   = ""
                if price:
                    price_class = "price-free" if is_free else "price-paid"
                    price_label = "Free" if is_free else price
                    price_html  = f'<span class="price-badge {price_class}">{price_label}</span>'
                time_str = f'<span>🕐 {e["time"]}</span>' if e.get("time") else ""
                loc_str  = f'<span>📍 {e["location"]}</span>' if e.get("location") else ""

                cards += f"""
            <a href="{search_url}" target="_blank" rel="noopener" class="card-link">
            <div class="card">
              <div class="card-img" style="background-image:url('{photo_url}')">
                <span class="cat-badge">{icon} {cat}</span>
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
                <span class="cta">Find tickets &amp; details →</span>
              </div>
            </div>
            </a>"""

        panels_html += f'<div id="panel-{loc["id"]}" class="panel" style="display:{display};">{cards}</div>\n'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Local Events — {month_name} | NestInLux</title>
  <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet"/>
  <style>
    /* ── Reset & Base ── */
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', sans-serif;
      background: #f9f7f4;
      color: #1c1812;
    }}

    /* ── Hero ── */
    .hero {{
      background: linear-gradient(160deg, #1c1812 0%, #2d2418 55%, #3d3020 100%);
      color: #f9f7f4;
      padding: 52px 24px 44px;
      text-align: center;
    }}
    .hero-eyebrow {{
      font-family: 'Inter', sans-serif;
      font-size: 0.72rem;
      font-weight: 500;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: #b8965a;
      margin-bottom: 12px;
    }}
    .hero h1 {{
      font-family: 'Cormorant Garamond', serif;
      font-size: 2.6rem;
      font-weight: 500;
      letter-spacing: -0.02em;
      color: #f9f7f4;
      margin-bottom: 10px;
      line-height: 1.15;
    }}
    .hero p {{
      font-size: 0.9rem;
      color: rgba(249,247,244,0.6);
      margin-bottom: 18px;
    }}
    .month-pill {{
      display: inline-block;
      background: rgba(184,150,90,0.18);
      border: 1px solid rgba(184,150,90,0.4);
      color: #d4a96a;
      padding: 6px 20px;
      border-radius: 999px;
      font-size: 0.8rem;
      letter-spacing: 0.08em;
    }}

    /* ── Tabs ── */
    .tabs-wrap {{
      background: #fff;
      border-bottom: 1px solid #e8e0d5;
      display: flex;
      justify-content: center;
      gap: 0;
      overflow-x: auto;
      padding: 0 16px;
    }}
    .tab {{
      font-family: 'Inter', sans-serif;
      padding: 16px 24px;
      border: none;
      background: none;
      font-size: 0.84rem;
      font-weight: 500;
      color: #8a7f72;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      white-space: nowrap;
      transition: all 0.2s;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .tab:hover {{ color: #1c1812; }}
    .tab.active {{
      color: #1c1812;
      border-bottom-color: #b8965a;
      font-weight: 600;
    }}
    .tab-count {{
      background: #f0ebe3;
      color: #8a7f72;
      font-size: 0.72rem;
      font-weight: 600;
      padding: 2px 7px;
      border-radius: 999px;
    }}
    .tab.active .tab-count {{
      background: #b8965a;
      color: #fff;
    }}

    /* ── Content ── */
    .content {{
      max-width: 1160px;
      margin: 0 auto;
      padding: 36px 20px 56px;
    }}

    /* ── Grid ── */
    .panel {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
      gap: 24px;
    }}

    /* ── Card ── */
    .card-link {{ text-decoration: none; color: inherit; display: block; }}
    .card {{
      background: #fff;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid #e8e0d5;
      box-shadow: 0 1px 4px rgba(28,24,18,0.05);
      transition: transform 0.25s ease, box-shadow 0.25s ease;
      height: 100%;
    }}
    .card-link:hover .card {{
      transform: translateY(-5px);
      box-shadow: 0 16px 40px rgba(28,24,18,0.12);
    }}
    .card-img {{
      height: 190px;
      background-size: cover;
      background-position: center;
      position: relative;
    }}
    .card-img::after {{
      content: '';
      position: absolute;
      inset: 0;
      background: linear-gradient(to bottom, transparent 50%, rgba(28,24,18,0.35) 100%);
    }}
    .cat-badge {{
      position: absolute;
      top: 12px;
      left: 12px;
      background: rgba(28,24,18,0.6);
      backdrop-filter: blur(8px);
      color: #f9f7f4;
      font-size: 0.7rem;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 999px;
      letter-spacing: 0.04em;
      z-index: 1;
    }}
    .price-badge {{
      position: absolute;
      top: 12px;
      right: 12px;
      font-size: 0.7rem;
      font-weight: 700;
      padding: 4px 10px;
      border-radius: 999px;
      z-index: 1;
    }}
    .price-free {{ background: #d4edda; color: #155724; }}
    .price-paid {{ background: #fef3e2; color: #7d5a00; }}

    .card-body {{ padding: 18px 20px 20px; }}
    .card-body h3 {{
      font-family: 'Cormorant Garamond', serif;
      font-size: 1.15rem;
      font-weight: 600;
      margin-bottom: 8px;
      line-height: 1.35;
      color: #1c1812;
    }}
    .meta {{
      display: flex;
      flex-direction: column;
      gap: 3px;
      margin-bottom: 10px;
    }}
    .meta span {{ font-size: 0.76rem; color: #8a7f72; }}
    .card-body p {{
      font-size: 0.87rem;
      color: #4a4035;
      line-height: 1.55;
      margin-bottom: 14px;
    }}
    .cta {{
      font-size: 0.78rem;
      font-weight: 600;
      color: #b8965a;
      letter-spacing: 0.03em;
    }}

    /* ── Empty state ── */
    .no-events {{
      grid-column: 1/-1;
      text-align: center;
      padding: 80px 0;
      color: #8a7f72;
    }}

    /* ── Footer ── */
    .footer {{
      text-align: center;
      font-size: 0.71rem;
      color: #8a7f72;
      padding: 0 20px 40px;
      letter-spacing: 0.02em;
    }}
    .footer a {{ color: #b8965a; text-decoration: none; }}

    /* ── Responsive ── */
    @media (max-width: 640px) {{
      .hero h1 {{ font-size: 1.9rem; }}
      .panel {{ grid-template-columns: 1fr; }}
      .tab {{ padding: 14px 16px; font-size: 0.78rem; }}
    }}
  </style>
</head>
<body>

  <div class="hero">
    <p class="hero-eyebrow">NestInLux · Local Guide</p>
    <h1>Events This Month</h1>
    <p>Handpicked experiences near each of our properties</p>
    <span class="month-pill">📅 {month_name}</span>
  </div>

  <div class="tabs-wrap">
    {tabs_html}
  </div>

  <div class="content">
    {panels_html}
  </div>

  <div class="footer">
    Updated {updated} &nbsp;·&nbsp; Sorted by popularity &nbsp;·&nbsp;
    Events subject to change — always verify with the organiser &nbsp;·&nbsp;
    <a href="https://nestinlux.com" target="_blank">nestinlux.com</a>
  </div>

  <script>
    function switchTab(id, btn) {{
      document.querySelectorAll('.panel').forEach(p => p.style.display = 'none');
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      document.getElementById('panel-' + id).style.display = 'grid';
      btn.classList.add('active');
    }}
  </script>

</body>
</html>"""


def main():
    all_events = {}

    for i, loc in enumerate(LOCATIONS):
        if i > 0:
            print(f"\n  Waiting 25s before next location...")
            time.sleep(25)

        events = fetch_events_for_location(loc)
        all_events[loc["id"]] = events

    print("\nBuilding HTML...")
    html = build_html(all_events)

    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("\n── Results ──────────────────────────────────")
    for loc in LOCATIONS:
        count = len(all_events.get(loc["id"], []))
        print(f"  {loc['label']}: {count} events")
    print("\nDone! docs/index.html updated.")


if __name__ == "__main__":
    main()
