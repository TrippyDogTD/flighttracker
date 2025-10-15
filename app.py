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
LAST_FLIGHT_FILE = "last_flight.json"


# -------- Default Areas --------
DEFAULT_AREAS = [
    {
        "name": "North Departures",
        "points": [
            {"lat": 4.85, "lng": -74.15},
            {"lat": 4.90, "lng": -74.05},
            {"lat": 4.75, "lng": -74.00},
            {"lat": 4.70, "lng": -74.10},
        ],
    },
    {
        "name": "South Departures",
        "points": [
            {"lat": 4.65, "lng": -74.20},
            {"lat": 4.55, "lng": -74.15},
            {"lat": 4.55, "lng": -74.05},
            {"lat": 4.65, "lng": -74.00},
        ],
    },
]


def ensure_default_areas():
    """Ensure default areas exist globally."""
    if not os.path.exists(AREAS_FILE):
        with open(AREAS_FILE, "w") as f:
            json.dump(DEFAULT_AREAS, f, indent=2)


ensure_default_areas()


def load_areas():
    with open(AREAS_FILE, "r") as f:
        return json.load(f)


# -------- Home Page --------
@app.get("/", response_class=HTMLResponse)
async def home():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


# -------- Map Editor --------
@app.get("/map", response_class=HTMLResponse)
async def map_editor():
    default_areas = load_areas()

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
            <label>Active Area:</label>
            <select id="areaSelect" onchange="loadSelectedArea()" style="margin-left:6px;"></select>
            <button onclick="saveNewArea()" style="margin-left:10px;">💾 Save</button>
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

            const defaultAreas = {json.dumps(DEFAULT_AREAS)};
            let localAreas = JSON.parse(localStorage.getItem("localAreas") || "[]");
            let allAreas = [...defaultAreas, ...localAreas];
            let activeArea = localStorage.getItem("activeArea");

            function populateList() {{
                const sel = document.getElementById("areaSelect");
                sel.innerHTML = "";
                allAreas.forEach(a => {{
                    const opt = document.createElement("option");
                    opt.value = a.name;
                    opt.textContent = a.name;
                    if (a.name === activeArea) opt.selected = true;
                    sel.appendChild(opt);
                }});
            }}

            populateList();

            map.on(L.Draw.Event.CREATED, e => {{
                if (currentPolygon) map.removeLayer(currentPolygon);
                currentPolygon = e.layer;
                map.addLayer(currentPolygon);
            }});

            async function saveNewArea() {{
                if (!currentPolygon) return alert("❌ Draw an area first!");
                const name = prompt("Enter a name for this area:");
                if (!name) return;
                const coords = currentPolygon.getLatLngs()[0].map(p => ({{lat:p.lat, lng:p.lng}}));
                localAreas = localAreas.filter(a => a.name !== name);
                localAreas.push({{name, points:coords}});
                localStorage.setItem("localAreas", JSON.stringify(localAreas));
                allAreas = [...defaultAreas, ...localAreas];
                populateList();
                alert("✅ Saved locally!");
            }}

            function loadSelectedArea() {{
                const name = document.getElementById("areaSelect").value;
                const a = allAreas.find(x => x.name === name);
                if (!a) return;
                if (currentPolygon) map.removeLayer(currentPolygon);
                currentPolygon = L.polygon(a.points, {{color:'cyan'}}).addTo(map);
                map.fitBounds(currentPolygon.getBounds());
            }}

            function setActive() {{
                activeArea = document.getElementById("areaSelect").value;
                localStorage.setItem("activeArea", activeArea);
                alert("✅ Active area set!");
            }}

            function deleteArea() {{
                const name = document.getElementById("areaSelect").value;
                if (!name) return alert("Select an area first.");
                if (defaultAreas.find(a => a.name === name)) {{
                    alert("❌ Cannot delete default areas.");
                    return;
                }}
                if (!confirm(`Delete '${{name}}'?`)) return;
                localAreas = localAreas.filter(a => a.name !== name);
                localStorage.setItem("localAreas", JSON.stringify(localAreas));
                allAreas = [...defaultAreas, ...localAreas];
                populateList();
                alert("🗑 Deleted locally.");
            }}

            if (activeArea) loadSelectedArea();
        </script>
    </body>
    </html>
    """


# -------- Flight Info --------
@app.get("/flight")
async def get_flight():
    try:
        # get area points from last saved global active or fallback
        if not os.path.exists(AREAS_FILE):
            ensure_default_areas()

        with open(AREAS_FILE, "r") as f:
            default_areas = json.load(f)

        # fallback default to north departures
        active = default_areas[0]
        polygon = Polygon([(p["lng"], p["lat"]) for p in active["points"]])

        b_lats = [p["lat"] for p in active["points"]]
        b_lngs = [p["lng"] for p in active["points"]]
        bounds_str = f"{max(b_lats)},{min(b_lngs)},{min(b_lats)},{max(b_lngs)}"
        flights = fr.get_flights(bounds=bounds_str)

        valid = []
        for f in flights:
            try:
                if f.longitude and f.latitude and polygon.contains(Point(f.longitude, f.latitude)):
                    valid.append(f)
            except Exception:
                continue

        if not valid:
            data = {{
                "flight": "No traffic in area",
                "destination": "--",
                "aircraft": "--",
                "altitude": "--",
                "logo": "/static/logos/SS.png" if os.path.exists("static/logos/SS.png") else "/static/logos/default.png",
            }}
            with open(LAST_FLIGHT_FILE, "w") as f:
                json.dump(data, f)
            return data

        chosen = random.choice(valid)
        airline_code = (chosen.airline_iata or "").strip() or "default"
        logo_path = f"static/logos/{airline_code}.png"
        logo_url = f"/static/logos/{airline_code}.png" if os.path.exists(logo_path) else "/static/logos/default.png"

        data = {{
            "flight": (chosen.callsign or chosen.id or "--"),
            "destination": (chosen.destination_airport_iata or "--"),
            "aircraft": (chosen.aircraft_code or "--"),
            "altitude": f"{{int(chosen.altitude)}} ft" if chosen.altitude else "--",
            "logo": logo_url,
        }}
        with open(LAST_FLIGHT_FILE, "w") as f:
            json.dump(data, f)
        return data

    except Exception as e:
        print("❌ Flight error:", e)
        if os.path.exists(LAST_FLIGHT_FILE):
            with open(LAST_FLIGHT_FILE, "r") as f:
                return json.load(f)
        return JSONResponse(content={{"error": str(e)}}, status_code=500)
