from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from FlightRadar24 import FlightRadar24API
from shapely.geometry import Point, Polygon
import json, random, os

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

fr = FlightRadar24API()

AREA_FILE = "area.json"
LAST_FLIGHT_FILE = "last_flight.json"


def load_area():
    """Load or create default area."""
    if not os.path.exists(AREA_FILE):
        area = {
            "points": [
                {"lat": 4.74, "lng": -74.16},
                {"lat": 4.74, "lng": -74.05},
                {"lat": 4.66, "lng": -74.05},
                {"lat": 4.66, "lng": -74.16},
            ],
            "bounds": {"tl_y": 4.74, "tl_x": -74.16, "br_y": 4.66, "br_x": -74.05},
        }
        with open(AREA_FILE, "w") as f:
            json.dump(area, f)
        return area
    with open(AREA_FILE, "r") as f:
        return json.load(f)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/map", response_class=HTMLResponse)
async def map_editor():
    """Interactive map to draw and save the tracking area."""
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
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script src="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.js"></script>
        <link rel="stylesheet" href="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.css" />
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
                draw: {{ polygon: true, polyline:false, circle:false, rectangle:false, marker:false }},
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
async def update_area(area: dict):
    with open(AREA_FILE, "w") as f:
        json.dump(area, f)
    return {"status": "ok"}


from fastapi.responses import HTMLResponse

@app.get("/traffic")
async def get_all_flights():
    """Return all flights detected in current area (for backend use)."""
    try:
        area_data = load_area()
        polygon = Polygon([(p["lng"], p["lat"]) for p in area_data["points"]])
        b = area_data["bounds"]
        bounds_str = f"{b['tl_y']},{b['tl_x']},{b['br_y']},{b['br_x']}"

        flights = fr.get_flights(bounds=bounds_str)
        inside = []

        for f in flights:
            try:
                # only outbound flights, ignore inbound and low altitude
                if (
                    f.longitude
                    and f.latitude
                    and polygon.contains(Point(f.longitude, f.latitude))
                    and f.altitude > 2000
                    and f.heading is not None
                    and (f.heading >= 340 or f.heading <= 140)
                    and f.latitude > 4.68
                ):
                    inside.append(
                        {
                            "id": f.id,
                            "altitude": f.altitude,
                            "airline": f.airline_iata,
                            "destination": f.destination_airport_iata,
                            "lat": f.latitude,
                            "lng": f.longitude,
                            "heading": f.heading,
                        }
                    )
            except Exception:
                continue

        return {"count": len(inside), "flights": inside}

    except Exception as e:
        print("❌ Traffic error:", e)
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/flight")
async def get_flight():
    """Pick one visible northbound flight (>400 ft)."""
    try:
        area_data = load_area()
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
                    and f.altitude > 400
                    and f.heading is not None
                    and (300 <= f.heading <= 360 or 0 <= f.heading <= 30)
                ):
                    valid.append(f)
            except Exception:
                continue

        if not valid:
            print("⚠ No outbound flights found.")
            if os.path.exists(LAST_FLIGHT_FILE):
                with open(LAST_FLIGHT_FILE, "r") as f:
                    return json.load(f)
            return {
                "flight": "--",
                "destination": "--",
                "aircraft": "--",
                "altitude": 0,
                "logo": "/static/logos/default.png",
            }

        chosen = random.choice(valid)
        airline_code = chosen.airline_iata or "default"

        data = {
            "flight": chosen.id or "--",
            "destination": chosen.destination_airport_iata or "--",
            "aircraft": chosen.aircraft_code or "--",
            "altitude": int(chosen.altitude),
            "logo": f"/static/logos/{airline_code}.png"
            if os.path.exists(f"static/logos/{airline_code}.png")
            else "/static/logos/default.png",
        }

        with open(LAST_FLIGHT_FILE, "w") as f:
            json.dump(data, f)

        print(f"✅ Outbound flight {data['flight']} to {data['destination']} at {data['altitude']} ft")
        return data

    except Exception as e:
        print("❌ Flight error:", e)
        if os.path.exists(LAST_FLIGHT_FILE):
            with open(LAST_FLIGHT_FILE, "r") as f:
                return json.load(f)
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/traffic-map", response_class=HTMLResponse)
async def traffic_map():
    """Visual debug map for area and live flights."""
    area_data = load_area()
    points = [(p["lat"], p["lng"]) for p in area_data["points"]]
    polygon_js = json.dumps(points)
    return f"""
    <html>
    <head>
        <title>Traffic Map</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    </head>
    <body style="margin:0">
        <div id="map" style="height:100vh;width:100vw"></div>
        <script>
            const map = L.map('map').setView([{points[0][0]}, {points[0][1]}], 12);
            L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png').addTo(map);

            const polygon = L.polygon({polygon_js}, {{color: 'cyan'}}).addTo(map);
            map.fitBounds(polygon.getBounds());

            async function updateFlights() {{
                const res = await fetch('/traffic');
                const data = await res.json();
                if (data.flights) {{
                    data.flights.forEach(f => {{
                        L.circleMarker([f.lat, f.lng], {{
                            radius: 6,
                            color: 'yellow'
                        }}).bindTooltip(`${{f.airline || '??'}} → ${{f.destination || '--'}}`).addTo(map);
                    }});
                }}
            }}
            updateFlights();
            setInterval(updateFlights, 8000);
        </script>
    </body>
    </html>
    """


@app.get("/health")
async def health():
    return {"status": "ok"}
