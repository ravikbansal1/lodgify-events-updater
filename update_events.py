"""
Biweekly Local Events Updater — NestInLux
"""

import os, json, time, re, requests
from datetime import datetime, timedelta
from urllib.parse import quote_plus

print("Script starting...", flush=True)

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

LOCATIONS = [
    {"id": "wallingford", "label": "Wallingford, Seattle",  "nearby": "Fremont, Capitol Hill, Queen Anne, Ballard, Seattle downtown"},
    {"id": "alki",        "label": "Alki Beach, Seattle",   "nearby": "West Seattle, Burien, SoDo, Pioneer Square, downtown Seattle"},
    {"id": "lake_hills",  "label": "Lake Hills, Bellevue",  "nearby": "Bellevue downtown, Redmond, Kirkland, Issaquah, Mercer Island"},
]

CATEGORY_PHOTOS = {
    "music": "photo-1493225457124-a3eb161ffa5f", "concert": "photo-1470229722913-7c0e2dbbafd3",
    "festival": "photo-1533174072545-7a4b6ad7a6c3", "food": "photo-1555939594-58d7cb561ad1",
    "market": "photo-1488459716781-31db52582fe9", "outdoor": "photo-1441974231531-c6227db76b6e",
    "art": "photo-1578926375605-eaf7559b1458", "theater": "photo-1507003211169-0a1dd7228f2d",
    "comedy": "photo-1527224857830-43a7acc85260", "sports": "photo-1471295253337-3ceaaedca402",
    "wine": "photo-1510812431401-41d2bd2722f3", "beer": "photo-1535958636474-b021ee887b13",
    "tour": "photo-1502175353174-a7a70e73b362", "default": "photo-1496442226666-8d4d0e62e6e9",
}

def get_photo_url(name, desc):
    text = (name + " " + desc).lower()
    for k, v in CATEGORY_PHOTOS.items():
        if k in text:
            return f"https://images.unsplash.com/{v}?w=600&q=80&fit=crop"
    return f"https://images.unsplash.com/{CATEGORY_PHOTOS['default']}?w=600&q=80&fit=crop"

def get_category(name, desc):
    text = (name + " " + desc).lower()
    if any(w in text for w in ["concert","music","band","live"]): return "🎵 Music"
    if any(w in text for w in ["comedy","stand-up","improv"]): return "🎤 Comedy"
    if any(w in text for w in ["food","taste","chef","dining"]): return "🍴 Food & Drink"
    if any(w in text for w in ["wine","winery","tasting"]): return "🍷 Wine"
    if any(w in text for w in ["beer","brewery"]): return "🍺 Brewery"
    if any(w in text for w in ["market","farmers","craft"]): return "🛍️ Market"
    if any(w in text for w in ["festival","fest","fair"]): return "🎉 Festival"
    if any(w in text for w in ["hike","trail","outdoor","kayak"]): return "🌿 Outdoors"
    if any(w in text for w in ["art","gallery","exhibit","museum"]): return "🎨 Arts"
    if any(w in text for w in ["theater","theatre","opera","ballet"]): return "🎭 Theater"
    if any(w in text for w in ["sport","game","mariners","sounders","seahawks"]): return "🏅 Sports"
    if any(w in text for w in ["tour","cruise","boat"]): return "⛵ Tours"
    return "📍 Experience"

def make_search_url(name, label):
    return f"https://www.google.com/search?q={quote_plus(name + ' ' + label + ' event')}"

def fetch_events(loc):
    label  = loc["label"]
    nearby = loc["nearby"]
    today  = datetime.now()
    start  = today.strftime("%B %d")
    end    = (today + timedelta(days=14)).strftime("%B %d, %Y")
    dates  = f"{start} – {end}"

    prompt = f"""Find up to 50 fun tourist-friendly events near {label} ({nearby}) for {dates}.
Only include: concerts, shows, festivals, food events, sports games, tours, art, comedy.
Sort by popularity (most popular first).
Return ONLY a JSON array:
[{{"name":"Event","date":"Sat Apr 5","time":"7pm","location":"Venue, City","description":"Why tourists love it.","price":"Free or $25","popularity":90}}]
No markdown, no explanation. JSON array only."""

    print(f"  Calling API for {label}...", flush=True)
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": 8192,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=45,
        )
        print(f"  Status: {r.status_code}", flush=True)
        if r.status_code != 200:
            print(f"  Error body: {r.text[:300]}", flush=True)
            return []

        text = ""
        for block in r.json().get("content", []):
            if block.get("type") == "text":
                text += block["text"]

        clean = re.sub(r"```json|```", "", text).strip()
        s, e  = clean.find("["), clean.rfind("]")
        if s == -1 or e == -1:
            print(f"  No JSON array found. Response: {text[:200]}", flush=True)
            return []

        events = json.loads(clean[s:e+1])
        # Sort by date
        import calendar
        MONTHS = {m[:3].lower(): i for i, m in enumerate(calendar.month_abbr) if m}
        DAYS   = {d[:3].lower(): i for i, d in enumerate(calendar.day_abbr) if d}
        def parse_date(e):
            raw = e.get("date", "").strip().lower()
            for abbr, num in MONTHS.items():
                if abbr in raw:
                    import re as _re
                    day_match = _re.search(r"\d+", raw)
                    day = int(day_match.group()) if day_match else 99
                    return (num, day)
            return (99, 99)
        events.sort(key=parse_date)
        print(f"  Got {len(events)} events ✅", flush=True)
        return events[:50]

    except requests.exceptions.Timeout:
        print(f"  Timed out!", flush=True)
        return []
    except Exception as ex:
        print(f"  Exception: {ex}", flush=True)
        return []


def build_html(all_events):
    today  = datetime.now()
    dates  = f"{today.strftime('%B %d')} – {(today + timedelta(days=14)).strftime('%B %d, %Y')}"
    updated = today.strftime("%B %d, %Y")

    tabs = ""
    for i, loc in enumerate(LOCATIONS):
        active = "active" if i == 0 else ""
        count  = len(all_events.get(loc["id"], []))
        tabs  += f'<button class="tab {active}" onclick="switchTab(\'{loc["id"]}\', this)">{loc["label"]} <span class="tc">{count}</span></button>\n'

    panels = ""
    for i, loc in enumerate(LOCATIONS):
        events  = all_events.get(loc["id"], [])
        display = "grid" if i == 0 else "none"
        cards   = ""
        if not events:
            cards = '<div class="empty">No events found. Check back soon!</div>'
        else:
            for e in events:
                photo = get_photo_url(e.get("name",""), e.get("description",""))
                cat   = get_category(e.get("name",""), e.get("description",""))
                url   = make_search_url(e.get("name",""), loc["label"])
                price = e.get("price","")
                is_free = price.strip().lower() in ("free","free!")
                pbadge = ""
                if price:
                    pc = "pf" if is_free else "pp"
                    pl = "Free" if is_free else price
                    pbadge = f'<span class="pb {pc}">{pl}</span>'
                t = f'<span>🕐 {e["time"]}</span>' if e.get("time") else ""
                l = f'<span>📍 {e["location"]}</span>' if e.get("location") else ""
                cards += f"""<a href="{url}" target="_blank" rel="noopener" class="cl">
<div class="card">
  <div class="ci" style="background-image:url('{photo}')">
    <span class="cb">{cat}</span>{pbadge}
  </div>
  <div class="cd">
    <h3>{e.get("name","Event")}</h3>
    <div class="meta"><span>📅 {e.get("date","")}</span>{t}{l}</div>
    <p>{e.get("description","")}</p>
    <span class="cta">Find tickets &amp; details →</span>
  </div>
</div></a>"""

        panels += f'<div id="panel-{loc["id"]}" class="panel" style="display:{display};">{cards}</div>\n'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Local Events | NestInLux</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet"/>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Inter',sans-serif;background:#f9f7f4;color:#1c1812}}
.hero{{background:linear-gradient(160deg,#1c1812 0%,#2d2418 55%,#3d3020 100%);color:#f9f7f4;padding:52px 24px 44px;text-align:center}}
.ey{{font-size:.72rem;font-weight:500;letter-spacing:.18em;text-transform:uppercase;color:#b8965a;margin-bottom:12px}}
.hero h1{{font-family:'Cormorant Garamond',serif;font-size:2.6rem;font-weight:500;color:#f9f7f4;margin-bottom:10px;line-height:1.15}}
.hero p{{font-size:.9rem;color:rgba(249,247,244,.6);margin-bottom:18px}}
.pill{{display:inline-block;background:rgba(184,150,90,.18);border:1px solid rgba(184,150,90,.4);color:#d4a96a;padding:6px 20px;border-radius:999px;font-size:.8rem;letter-spacing:.08em}}
.tabs-wrap{{background:#fff;border-bottom:1px solid #e8e0d5;display:flex;justify-content:center;overflow-x:auto;padding:0 16px}}
.tab{{font-family:'Inter',sans-serif;padding:16px 24px;border:none;background:none;font-size:.84rem;font-weight:500;color:#8a7f72;cursor:pointer;border-bottom:2px solid transparent;white-space:nowrap;transition:all .2s;display:flex;align-items:center;gap:8px}}
.tab:hover{{color:#1c1812}}
.tab.active{{color:#1c1812;border-bottom-color:#b8965a;font-weight:600}}
.tc{{background:#f0ebe3;color:#8a7f72;font-size:.72rem;font-weight:600;padding:2px 7px;border-radius:999px}}
.tab.active .tc{{background:#b8965a;color:#fff}}
.content{{max-width:1160px;margin:0 auto;padding:36px 20px 56px}}
.panel{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:24px}}
.cl{{text-decoration:none;color:inherit;display:block}}
.card{{background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e8e0d5;box-shadow:0 1px 4px rgba(28,24,18,.05);transition:transform .25s,box-shadow .25s;height:100%}}
.cl:hover .card{{transform:translateY(-5px);box-shadow:0 16px 40px rgba(28,24,18,.12)}}
.ci{{height:190px;background-size:cover;background-position:center;position:relative}}
.ci::after{{content:'';position:absolute;inset:0;background:linear-gradient(to bottom,transparent 50%,rgba(28,24,18,.35) 100%)}}
.cb{{position:absolute;top:12px;left:12px;background:rgba(28,24,18,.6);backdrop-filter:blur(8px);color:#f9f7f4;font-size:.7rem;font-weight:600;padding:4px 10px;border-radius:999px;z-index:1}}
.pb{{position:absolute;top:12px;right:12px;font-size:.7rem;font-weight:700;padding:4px 10px;border-radius:999px;z-index:1}}
.pf{{background:#d4edda;color:#155724}}
.pp{{background:#fef3e2;color:#7d5a00}}
.cd{{padding:18px 20px 20px}}
.cd h3{{font-family:'Cormorant Garamond',serif;font-size:1.15rem;font-weight:600;margin-bottom:8px;line-height:1.35;color:#1c1812}}
.meta{{display:flex;flex-direction:column;gap:3px;margin-bottom:10px}}
.meta span{{font-size:.76rem;color:#8a7f72}}
.cd p{{font-size:.87rem;color:#4a4035;line-height:1.55;margin-bottom:14px}}
.cta{{font-size:.78rem;font-weight:600;color:#b8965a;letter-spacing:.03em}}
.empty{{grid-column:1/-1;text-align:center;padding:80px 0;color:#8a7f72}}
.footer{{text-align:center;font-size:.71rem;color:#8a7f72;padding:0 20px 40px}}
.footer a{{color:#b8965a;text-decoration:none}}
@media(max-width:640px){{.hero h1{{font-size:1.9rem}}.panel{{grid-template-columns:1fr}}.tab{{padding:14px 16px;font-size:.78rem}}}}
</style>
</head>
<body>
<div class="hero">
  <p class="ey">NestInLux · Local Guide</p>
  <h1>Events Near You</h1>
  <p>Handpicked experiences near each of our properties</p>
  <span class="pill">📅 {dates}</span>
</div>
<div class="tabs-wrap">{tabs}</div>
<div class="content">{panels}</div>
<div class="footer">Updated {updated} &nbsp;·&nbsp; Sorted by date &nbsp;·&nbsp; Events subject to change &nbsp;·&nbsp; <a href="https://nestinlux.com" target="_blank">nestinlux.com</a></div>
<script>
function switchTab(id,btn){{
  document.querySelectorAll('.panel').forEach(p=>p.style.display='none');
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.getElementById('panel-'+id).style.display='grid';
  btn.classList.add('active');
}}
</script>
</body>
</html>"""


def main():
    print("Starting event fetch...", flush=True)
    all_events = {}
    for i, loc in enumerate(LOCATIONS):
        if i > 0:
            print("Waiting 10s...", flush=True)
            time.sleep(10)
        all_events[loc["id"]] = fetch_events(loc)

    print("Building HTML...", flush=True)
    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(build_html(all_events))

    print("\n── Results ──", flush=True)
    for loc in LOCATIONS:
        print(f"  {loc['label']}: {len(all_events.get(loc['id'], []))} events", flush=True)
    print("Done!", flush=True)

if __name__ == "__main__":
    main()
