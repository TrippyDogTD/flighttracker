import os, json, random
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from shapely.geometry import Point, Polygon
from FlightRadar24 import FlightRadar24API

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

fr = FlightRadar24API()
AREAS_FILE = "areas.json"
ACTIVE_AREA_FILE = "active_area.json"
LAST_FLIGHT_FILE = "last_flight.json"

# Helper: Load saved areas
def load_areas():
    if os.path.exists(AREAS_FILE):
        with open(AREAS_FILE, "r") as f:
            return json.load(f)
    return []

# Helper: Get active area
def get_active_area():
    if os.path.exists(ACTIVE_AREA_FILE):
        with open(ACTIVE_AREA_FILE, "r") as f:
            return json.load(f)
    return None

# ----------------------------
# FRONTEND PAGES
# ----------------------------

@app.get("/", response_class=HTMLResponse)
async def home():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/map", response_class=HTMLResponse)
async def map_editor():
    saved_areas = load_areas()
    active = get_active_area()
    active_name = active["name"] if active else ""

    return f"""
    <html>
    <head>
        <title>Edit Tracking Areas</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <link rel="stylesheet" href="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script src="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.js"></script>
    </head>
    <body style="margin:0">
        <div style="position:absolute;top:10px;left:10px;z-index:1000;background:#000a;padding:10px;border-radius:8px;color:white;font-family:sans-serif">
            <label for="areaSelect">Saved Areas:</label>
            <select id="areaSelect" onchange="loadSelectedArea()" style="margin-left:6px;">
                <option value="">-- Select Area --</option>
                {''.join(f'<option value="{a["name"]}" {"selected" if a["name"]==active_name else ""}>{a["name"]}</option>' for a in saved_areas)}
            </select>
            <button onclick="saveNewArea()" style="margin-left:10px;">💾 Save New</button>
            <button onclick="setActive()" style="margin-left:5px;">✈ Use</button>
            <button onclick="deleteArea()" style="margin-left:5px;color:red;">🗑 Delete</button>
        </div>
        <div id="map" style="height:100vh;width:100vw"></div>
        <script>
            const map = L.map('map').setView([4.7, -74.1], 11);
            L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png').addTo(map);
            let currentPolygon = null;
            const drawControl = new L.Control.Draw({{
                draw: {{ polygon:true, polyline:false, circle:false, rectangle:false, marker:false }},
                edit: {{ featureGroup: new L.FeatureGroup() }}
            }});
            map.addControl(drawControl);

            map.on(L.Draw.Event.CREATED, e => {{
                if (currentPolygon) map.removeLayer(currentPolygon);
                currentPolygon = e.layer;
                map.addLayer(currentPolygon);
            }});

            async function saveNewArea() {{
                if (!currentPolygon) {{
                    alert("❌ Draw an area first!");
                    return;
                }}
                const name = prompt("Enter a name for this area:");
                if (!name) return;
                const coords = currentPolygon.getLatLngs()[0].map(p => ({{lat:p.lat, lng:p.lng}}));
                const resp = await fetch('/save-area', {{
                    method:'POST',
                    headers:{{'Content-Type':'application/json'}},
                    body:JSON.stringify({{name, points:coords}})
                }});
                if (resp.ok) {{
                    alert("✅ Area saved!");
                    location.reload();
                }} else alert("⚠️ Failed to save area.");
            }}

            async function loadSelectedArea() {{
                const name = document.getElementById("areaSelect").value;
                if (!name) return;
                const res = await fetch(`/get-area?name=${{encodeURIComponent(name)}}`);
                const data = await res.json();
                if (currentPolygon) map.removeLayer(currentPolygon);
                currentPolygon = L.polygon(data.points, {{color:'cyan'}}).addTo(map);
                map.fitBounds(currentPolygon.getBounds());
            }}

            async function setActive() {{
                const name = document.getElementById("areaSelect").value;
                if (!name) return alert("Select an area first.");
                const res = await fetch(`/set-active?name=${{encodeURIComponent(name)}}`, {{ method:'POST' }});
                if (res.ok) {{
                    alert("✅ Active area set!");
                }} else alert("⚠️ Could not set area.");
            }}

            async function deleteArea() {{
                const name = document.getElementById("areaSelect").value;
                if (!name) return alert("Select an area first.");
                if (!confirm(`Delete area '${{name}}'?`)) return;
                const res = await fetch(`/delete-area?name=${{encodeURIComponent(name)}}`, {{ method:'DELETE' }});
                if (res.ok) {{
                    alert("🗑 Area deleted!");
                    location.reload();
                }} else alert("⚠️ Could not delete area.");
            }}

            // Auto load current active area
            if ("{active_name}") {{
                loadSelectedArea();
            }}
        </script>
    </body>
    </html>
    """

# ----------------------------
# API ROUTES FOR AREAS
# ----------------------------

@app.post("/save-area")
async def save_area(request: Request):
    data = await request.json()
    name = data.get("name")
    points = data.get("points")
    if not name or not points:
        return {"error": "Name or points missing"}

    areas = load_areas()
    areas = [a for a in areas if a["name"] != name]
    latitudes = [p["lat"] for p in points]
    longitudes = [p["lng"] for p in points]
    bounds = {
        "tl_y": max(latitudes),
        "tl_x": min(longitudes),
        "br_y": min(latitudes),
        "br_x": max(longitudes),
    }
    areas.append({"name": name, "points": points, "bounds": bounds})

    with open(AREAS_FILE, "w") as f:
        json.dump(areas, f, indent=2)
    return {"status": "saved", "name": name}

@app.get("/get-area")
async def get_area(name: str):
    areas = load_areas()
    for a in areas:
        if a["name"] == name:
            return a
    return {"error": "Area not found"}

@app.delete("/delete-area")
async def delete_area(name: str):
    areas = [a for a in load_areas() if a["name"] != name]
    with open(AREAS_FILE, "w") as f:
        json.dump(areas, f, indent=2)
    return {"status": "deleted", "name": name}

@app.post("/set-active")
async def set_active(name: str):
    areas = load_areas()
    for a in areas:
        if a["name"] == name:
            with open(ACTIVE_AREA_FILE, "w") as f:
                json.dump(a, f, indent=2)
            return {"status": "active", "name": name}
    return {"error": "Area not found"}

# ----------------------------
# FLIGHT FETCH
# ----------------------------

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
                if (
                    f.longitude and f.latitude
                    and polygon.contains(Point(f.longitude, f.latitude))
                    and (f.altitude or 0) >= 1000
                    and f.heading is not None
                    and (f.heading >= 340 or f.heading <= 90)
                ):
                    valid.append(f)
            except Exception:
                continue

        if not valid:
            data = {
                "flight": "No traffic northbound",
                "destination": "--",
                "aircraft": "--",
                "altitude": "--",
                "logo": "/static/logos/SS.png" if os.path.exists("static/logos/SS.png") else "/static/logos/default.png",
            }
            with open(LAST_FLIGHT_FILE, "w") as f:
                json.dump(data, f)
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
        with open(LAST_FLIGHT_FILE, "w") as f:
            json.dump(data, f)
        return data

    except Exception as e:
        print("❌ Flight error:", e)
        if os.path.exists(LAST_FLIGHT_FILE):
            with open(LAST_FLIGHT_FILE, "r") as f:
                return json.load(f)
        return JSONResponse(content={"error": str(e)}, status_code=500)
