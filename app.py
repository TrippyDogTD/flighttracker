import os, json, random
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from shapely.geometry import Point, Polygon
from FlightRadar24 import FlightRadar24API

# === CONFIG ===
DATA_DIR = "data"
AREAS_FILE = os.path.join(DATA_DIR, "areas.json")
ACTIVE_AREA_FILE = os.path.join(DATA_DIR, "active_area.json")
LAST_FLIGHT_FILE = os.path.join(DATA_DIR, "last_flight.json")

# === APP INIT ===
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
fr = FlightRadar24API()


# === HELPERS ===
def load_json(path, fallback=None):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return fallback


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_areas():
    return load_json(AREAS_FILE, [])


def get_active_area():
    return load_json(ACTIVE_AREA_FILE, None)


# === Ensure default areas exist ===
DEFAULT_AREAS = [
    {
        "name": "North Departures",
        "points": [
            {"lat": 4.694676974798616, "lng": -74.12439993004844},
            {"lat": 4.684072186061007, "lng": -74.10293646446759},
            {"lat": 4.760867724535295, "lng": -74.07288761265441},
            {"lat": 4.747527462828149, "lng": -74.01845626394139},
            {"lat": 4.655677928685259, "lng": -74.04884853120387},
            {"lat": 4.6880062393764375, "lng": -74.12972286951248}
        ],
        "bounds": {
            "tl_y": 4.760867724535295,
            "tl_x": -74.12972286951248,
            "br_y": 4.655677928685259,
            "br_x": -74.01845626394139
        },
    },
    {
        "name": "South Departures",
        "points": [
            {"lat": 4.597002505156178, "lng": -74.17444229221913},
            {"lat": 4.614684654851182, "lng": -74.1436588881145},
            {"lat": 4.668007332161394, "lng": -74.12899867331046},
            {"lat": 4.678969204741258, "lng": -74.09736634514647},
            {"lat": 4.657532329351648, "lng": -74.06102128289232},
            {"lat": 4.594382876125526, "lng": -74.08084841356483}
        ],
        "bounds": {
            "tl_y": 4.678969204741258,
            "tl_x": -74.17444229221913,
            "br_y": 4.594382876125526,
            "br_x": -74.06102128289232
        },
    }
]

def ensure_default_areas():
    if not os.path.exists(AREAS_FILE):
        save_json(AREAS_FILE, DEFAULT_AREAS)

# call once on startup
ensure_default_areas()


# === PAGES ===
@app.get("/", response_class=HTMLResponse)
async def home():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/map", response_class=HTMLResponse)
async def map_editor():
    with open("static/map.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/console", response_class=HTMLResponse)
async def console_page():
    areas = load_areas()
    presets = [a for a in areas if a["name"] in ["North Departures", "South Departures"]]
    json_data = json.dumps(presets, indent=2)

    return f"""
    <html>
    <head>
        <title>Preset Console ✈</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <link rel="stylesheet" href="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script src="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.js"></script>
        <style>
            body {{
                margin:0;
                background:#000;
                color:#ffd84b;
                font-family:"IBM Plex Mono", monospace;
            }}
            #map {{
                height: 90vh;
                width: 100vw;
            }}
            .toolbar {{
                position:absolute;
                top:15px;
                left:15px;
                z-index:1000;
                background:rgba(0,0,0,0.85);
                border:1px solid #ffda0040;
                border-radius:10px;
                padding:10px 15px;
                color:#ffd84b;
                box-shadow:0 0 20px #ffda0040;
            }}
            select,button {{
                font-family:inherit;
                font-size:0.9rem;
                background:#111;
                color:#ffd84b;
                border:1px solid #ffda0040;
                border-radius:6px;
                padding:5px 10px;
                margin:5px 3px;
                cursor:pointer;
            }}
            button:hover {{
                background:#222;
                box-shadow:0 0 10px #ffda0030;
            }}
        </style>
    </head>
    <body>
        <div class="toolbar">
            <h3>🖥 Preset Area Console</h3>
            <div>
                <label>Preset:</label>
                <select id="presetSelect">
                    <option value="">-- Select Preset --</option>
                    <option value="North Departures">North Departures</option>
                    <option value="South Departures">South Departures</option>
                </select>
            </div>
            <div>
                <button onclick="loadPreset()">📍 Load</button>
                <button onclick="savePreset()">💾 Save Changes</button>
                <button onclick="resetPreset()">♻ Reset Defaults</button>
                <button onclick="window.location='/'">⬅ Back</button>
            </div>
        </div>

        <div id="map"></div>

        <script>
            let map = L.map('map').setView([4.7, -74.1], 11);
            L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png').addTo(map);
            const drawnItems = new L.FeatureGroup().addTo(map);
            const drawControl = new L.Control.Draw({{
                edit: {{ featureGroup: drawnItems }},
                draw: {{ polygon: true, rectangle: false, circle: false, marker: false, polyline: false }}
            }});
            map.addControl(drawControl);

            let currentLayer = null;
            let currentPreset = null;
            let presets = {json_data};

            function loadPreset() {{
                const name = document.getElementById('presetSelect').value;
                if (!name) return alert("Select a preset first.");
                const area = presets.find(p => p.name === name);
                if (!area) return alert("Preset not found.");

                if (currentLayer) drawnItems.removeLayer(currentLayer);
                currentPreset = name;
                currentLayer = L.polygon(area.points.map(p => [p.lat, p.lng]), {{color:'cyan'}}).addTo(drawnItems);
                map.fitBounds(currentLayer.getBounds());
            }}

            map.on(L.Draw.Event.CREATED, e => {{
                if (currentLayer) drawnItems.removeLayer(currentLayer);
                currentLayer = e.layer;
                drawnItems.addLayer(currentLayer);
            }});

            async function savePreset() {{
                if (!currentLayer || !currentPreset)
                    return alert("Load or draw a preset area first.");
                const coords = currentLayer.getLatLngs()[0].map(p => ({{lat:p.lat, lng:p.lng}}));
                const res = await fetch('/update-presets', {{
                    method:'POST',
                    headers:{{'Content-Type':'application/json'}},
                    body:JSON.stringify([{{name: currentPreset, points: coords}}])
                }});
                if (res.ok) alert("✅ Preset updated!");
                else alert("⚠️ Failed to update preset.");
            }}

            async function resetPreset() {{
                if (!confirm("Reset both presets to default?")) return;
                const res = await fetch('/reset-presets', {{method:'POST'}});
                if (res.ok) {{
                    alert("✅ Presets reset!");
                    location.reload();
                }} else alert("⚠️ Failed to reset.");
            }}
        </script>
    </body>
    </html>
    """

# === AREA API ===
@app.post("/save-area")
async def save_area(request: Request):
    data = await request.json()
    name = data.get("name")
    points = data.get("points")
    if not name or not points:
        return JSONResponse({"error": "Name or points missing"}, status_code=400)

    areas = [a for a in load_areas() if a["name"] != name]
    latitudes = [p["lat"] for p in points]
    longitudes = [p["lng"] for p in points]
    bounds = {
        "tl_y": max(latitudes),
        "tl_x": min(longitudes),
        "br_y": min(latitudes),
        "br_x": max(longitudes),
    }
    areas.append({"name": name, "points": points, "bounds": bounds})
    save_json(AREAS_FILE, areas)
    return {"status": "saved", "name": name}


@app.get("/get-area")
async def get_area(name: str):
    # special query for dropdown list
    if name == "__list__":
        areas = load_areas()
        return {"areas": [a["name"] for a in areas]}

    areas = load_areas()
    for a in areas:
        if a["name"] == name:
            return a
    return JSONResponse({"error": "Area not found"}, status_code=404)


@app.delete("/delete-area")
async def delete_area(name: str):
    new_areas = [a for a in load_areas() if a["name"] != name]
    save_json(AREAS_FILE, new_areas)
    return {"status": "deleted", "name": name}


@app.post("/set-active")
async def set_active(name: str):
    for a in load_areas():
        if a["name"] == name:
            save_json(ACTIVE_AREA_FILE, a)
            return {"status": "active", "name": name}
    return JSONResponse({"error": "Area not found"}, status_code=404)

@app.post("/update-presets")
async def update_presets(request: Request):
    """Update North and South departure areas manually."""
    data = await request.json()
    if not isinstance(data, list):
        return JSONResponse({"error": "Invalid format"}, status_code=400)

    areas = load_areas()
    updated_names = [a["name"] for a in data]

    # Replace matching presets or add new ones
    new_list = [a for a in areas if a["name"] not in updated_names]
    new_list.extend(data)
    save_json(AREAS_FILE, new_list)
    return {"status": "updated", "count": len(data)}


@app.post("/reset-presets")
async def reset_presets():
    """Restore North and South areas to their defaults."""
    areas = load_areas()
    existing_names = [a["name"] for a in areas]

    # remove current presets if they exist
    areas = [a for a in areas if a["name"] not in ["North Departures", "South Departures"]]
    areas.extend(DEFAULT_AREAS)
    save_json(AREAS_FILE, areas)
    return {"status": "reset", "defaults": [a["name"] for a in DEFAULT_AREAS]}


# === FLIGHT INFO ===
@app.get("/flight")
async def get_flight():
    try:
        active = get_active_area()
        if not active:
            raise Exception("No active area selected")

        polygon = Polygon([(p["lng"], p["lat"]) for p in active["points"]])
        b = active["bounds"]
        bounds_str = f"{b['tl_y']},{b['tl_x']},{b['br_y']},{b['br_x']}"
        flights = fr.get_flights(bounds=bounds_str)
        valid = []

        for f in flights:
            try:
                if f.longitude and f.latitude and polygon.contains(Point(f.longitude, f.latitude)):
                    valid.append(f)
            except Exception:
                continue

        if not valid:
            data = {
                "flight": "No traffic in area",
                "destination": "--",
                "aircraft": "--",
                "altitude": "--",
                "logo": "/static/logos/default.png",
            }
            save_json(LAST_FLIGHT_FILE, data)
            return data

        chosen = random.choice(valid)
        airline_code = (chosen.airline_iata or "").strip() or "default"
        logo_path = f"static/logos/{airline_code}.png"
        logo_url = f"/static/logos/{airline_code}.png" if os.path.exists(logo_path) else "/static/logos/default.png"

        data = {
            "flight": (chosen.callsign or chosen.id or "--"),
            "destination": (chosen.destination_airport_iata or "--"),
            "aircraft": (chosen.aircraft_code or "--"),
            "altitude": f"{int(chosen.altitude)} ft" if chosen.altitude else "--",
            "logo": logo_url,
        }
        save_json(LAST_FLIGHT_FILE, data)
        return data

    except Exception as e:
        print("❌ Flight error:", e)
        return load_json(LAST_FLIGHT_FILE, {"error": str(e)})
