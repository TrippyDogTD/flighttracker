import os, json, random
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from shapely.geometry import Point, Polygon
from FlightRadar24 import FlightRadar24API

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

fr = FlightRadar24API()

AREA_FILE = "area.json"
LAST_FLIGHT_FILE = "last_flight.json"


def load_area():
    if os.path.exists(AREA_FILE):
        with open(AREA_FILE, "r") as f:
            return json.load(f)
    return None


@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
    <head>
        <title>Live Flight Board</title>
        <link rel="stylesheet" href="/static/styles.css">
    </head>
    <body>
        <div class="flipboard">
            <div class="header">✈ LIVE FLIGHT BOARD ✈</div>

            <div class="flight-panel">
                <div class="logo-frame">
                    <img id="logo" src="/static/logos/default.png" alt="Logo">
                </div>

                <div class="info">
                    <div class="flip-row"><span class="label">Flight:</span><span id="flight" class="flip">--</span></div>
                    <div class="flip-row"><span class="label">Destination:</span><span id="destination" class="flip">--</span></div>
                    <div class="flip-row"><span class="label">Aircraft:</span><span id="aircraft" class="flip">--</span></div>
                    <div class="flip-row"><span class="label">Altitude:</span><span id="altitude" class="flip">--</span></div>
                </div>

                <div class="clock-frame">
                    <div class="clock-label">UTC</div>
                    <div id="utc-clock" class="clock-flip">--:--:--</div>
                </div>
            </div>

            <button onclick="window.location='/map'">✏ Edit Tracking Area</button>

            <div class="signature">Designed by <span>TrippyDog ✈</span></div>
        </div>

        <script>
            function flipText(el, newText) {
                if (el.innerText === newText) return;
                el.classList.remove('flip-anim');
                void el.offsetWidth;
                el.classList.add('flip-anim');
                setTimeout(() => { el.innerText = newText; }, 250);
            }

            async function updateFlight() {
                try {
                    const res = await fetch('/flight');
                    const data = await res.json();

                    const flightEl = document.getElementById('flight');
                    flipText(flightEl, data.flight || '--');
                    flipText(document.getElementById('destination'), data.destination || '--');
                    flipText(document.getElementById('aircraft'), data.aircraft || '--');
                    flipText(document.getElementById('altitude'), data.altitude || '--');
                    document.getElementById('logo').src = data.logo;

                    // blinking if no traffic
                    if (data.flight && data.flight.includes("No traffic")) {
                        flightEl.classList.add("blink");
                    } else {
                        flightEl.classList.remove("blink");
                    }
                } catch {
                    console.warn('Update failed');
                }
            }

            function updateClock() {
                const now = new Date();
                const utc = now.toISOString().slice(11, 19);
                flipText(document.getElementById("utc-clock"), utc);
            }

            updateClock();
            setInterval(updateClock, 1000);
            updateFlight();
            setInterval(updateFlight, 6000);
        </script>
    </body>
    </html>
    """


@app.get("/map", response_class=HTMLResponse)
async def map_editor():
    area_data = None
    if os.path.exists(AREA_FILE):
        with open(AREA_FILE, "r") as f:
            area_data = json.load(f)

    points_js = (
        json.dumps([(p["lat"], p["lng"]) for p in area_data["points"]])
        if area_data and "points" in area_data
        else "[]"
    )

    return f"""
    <html>
    <head>
        <title>Edit Tracking Area</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <link rel="stylesheet" href="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script src="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.js"></script>
    </head>
    <body style="margin:0">
        <div id="map" style="height:100vh;width:100vw"></div>
        <script>
            const map = L.map('map').setView([4.7, -74.1], 11);
            L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png').addTo(map);

            let currentPolygon = null;
            const savedPoints = {points_js};
            if (savedPoints.length > 0) {{
                currentPolygon = L.polygon(savedPoints, {{color:'cyan'}}).addTo(map);
                map.fitBounds(currentPolygon.getBounds());
            }}

            const drawControl = new L.Control.Draw({{
                draw: {{ polygon:true, polyline:false, circle:false, rectangle:false, marker:false }},
                edit: {{ featureGroup: currentPolygon ? L.featureGroup([currentPolygon]) : L.featureGroup() }}
            }});
            map.addControl(drawControl);

            map.on(L.Draw.Event.CREATED, e => {{
                if (currentPolygon) map.removeLayer(currentPolygon);
                currentPolygon = e.layer;
                map.addLayer(currentPolygon);
                saveArea(currentPolygon.getLatLngs()[0]);
            }});

            map.on(L.Draw.Event.EDITED, e => {{
                const layer = e.layers.getLayers()[0];
                if (layer) saveArea(layer.getLatLngs()[0]);
            }});

            async function saveArea(points) {{
                const coords = points.map(p => ({{lat:p.lat, lng:p.lng}}));
                await fetch('/update-area', {{
                    method:'POST',
                    headers:{{'Content-Type':'application/json'}},
                    body:JSON.stringify({{points:coords}})
                }});
                alert('✅ Area saved!');
            }}
        </script>
    </body>
    </html>
    """


@app.post("/update-area")
async def update_area(request: Request):
    data = await request.json()
    points = data.get("points")
    if not points:
        return {"error": "No points provided"}

    latitudes = [p["lat"] for p in points]
    longitudes = [p["lng"] for p in points]
    bounds = {
        "tl_y": max(latitudes),
        "tl_x": min(longitudes),
        "br_y": min(latitudes),
        "br_x": max(longitudes),
    }

    with open(AREA_FILE, "w") as f:
        json.dump({"points": points, "bounds": bounds}, f)

    return {"status": "saved"}


@app.get("/flight")
async def get_flight():
    try:
        area_data = load_area()
        if not area_data:
            raise Exception("No area defined")

        polygon = Polygon([(p["lng"], p["lat"]) for p in area_data["points"]])
        b = area_data["bounds"]
        bounds_str = f"{b['tl_y']},{b['tl_x']},{b['br_y']},{b['br_x']}"

        flights = fr.get_flights(bounds=bounds_str)
        valid = []

        for f in flights:
            try:
                if (
                    f.longitude
                    and f.latitude
                    and polygon.contains(Point(f.longitude, f.latitude))
                    and f.altitude > 2000
                    and f.heading is not None
                    and (f.heading >= 340 or f.heading <= 90)
                ):
                    valid.append(f)
            except Exception:
                continue

        if not valid:
            print("ℹ No northbound flights detected.")
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
        airline_code = chosen.airline_iata or "default"
        logo_path = f"static/logos/{airline_code}.png"
        logo_url = f"/static/logos/{airline_code}.png" if os.path.exists(logo_path) else "/static/logos/default.png"

        data = {
            "flight": chosen.callsign or chosen.id or "--",
            "destination": chosen.destination_airport_iata or "--",
            "aircraft": chosen.aircraft_code or "--",
            "altitude": f"{int(chosen.altitude)} ft",
            "logo": logo_url,
        }

        with open(LAST_FLIGHT_FILE, "w") as f:
            json.dump(data, f)

        print(f"✅ {data['flight']} → {data['destination']} ({data['aircraft']}) {data['altitude']}")
        return data

    except Exception as e:
        print("❌ Flight error:", e)
        if os.path.exists(LAST_FLIGHT_FILE):
            with open(LAST_FLIGHT_FILE, "r") as f:
                return json.load(f)
        return JSONResponse(content={"error": str(e)}, status_code=500)
