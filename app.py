from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse
from FlightRadar24 import FlightRadar24API
from shapely.geometry import Point, Polygon
import base64, time, datetime

app = FastAPI()
fr = FlightRadar24API()

# Default cyan area (Bogotá)
area_coords = {
    "tl_y": 4.7680835179814824,
    "tl_x": -74.1458266495095,
    "br_y": 4.666933604867419,
    "br_x": -74.02347176023953
}

logo_cache = {}
last_flight = None
last_seen_time = 0


def flight_in_area(flight):
    lat = getattr(flight, "latitude", None)
    lon = getattr(flight, "longitude", None)
    if lat is None or lon is None:
        return False
    polygon = Polygon([
        (area_coords["tl_x"], area_coords["tl_y"]),
        (area_coords["br_x"], area_coords["tl_y"]),
        (area_coords["br_x"], area_coords["br_y"]),
        (area_coords["tl_x"], area_coords["br_y"])
    ])
    return polygon.contains(Point(lon, lat))


def get_logo(iata, icao):
    key = (iata, icao)
    if not iata or not icao:
        return ""
    if key in logo_cache:
        return logo_cache[key]
    try:
        logo_bytes = fr.get_airline_logo(iata, icao)
        if logo_bytes:
            encoded = base64.b64encode(logo_bytes).decode("utf-8")
            logo_cache[key] = f"data:image/png;base64,{encoded}"
            return logo_cache[key]
    except Exception as e:
        print(f"Logo fetch failed for {iata}/{icao}: {e}")
    return ""


@app.get("/")
async def root():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/map")
async def map_page():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Edit Tracking Area</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script src="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.js"></script>
        <link rel="stylesheet" href="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.css"/>
        <script src="https://cdn.jsdelivr.net/npm/leaflet-easybutton@2/src/easy-button.js"></script>
        <style>html,body,#map{height:100%;margin:0}</style>
    </head>
    <body>
        <div id="map"></div>
        <script>
        const map = L.map('map').setView([4.7, -74.1], 11);
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
        let drawnLayer = null;
        const drawControl = new L.Control.Draw({
            draw: { polygon: true, rectangle: false, circle: false, marker: false, circlemarker: false, polyline: false },
            edit: { featureGroup: new L.FeatureGroup() }
        });
        map.addControl(drawControl);
        map.on(L.Draw.Event.CREATED, e => {
            if (drawnLayer) map.removeLayer(drawnLayer);
            drawnLayer = e.layer;
            map.addLayer(drawnLayer);
        });
        function saveArea() {
            if (!drawnLayer) { alert("Draw area first"); return; }
            const coords = drawnLayer.getLatLngs()[0].map(p => [p.lat, p.lng]);
            fetch('/save-area', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ points: coords })
            }).then(() => alert("Area saved!"));
        }
        L.easyButton('💾', saveArea).addTo(map);
        </script>
    </body>
    </html>
    """)


@app.post("/save-area")
async def save_area(data: dict):
    global area_coords
    points = data.get("points", [])
    if not points:
        return JSONResponse({"status": "error", "msg": "no points"})
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    area_coords = {
        "tl_y": max(lats),
        "tl_x": min(lons),
        "br_y": min(lats),
        "br_x": max(lons)
    }
    return {"status": "ok"}


@app.get("/flight/current")
async def get_current_flight():
    """Return northbound outbound flight, else idle message with UTC time."""
    global last_flight, last_seen_time

    bounds = f"{area_coords['tl_y']},{area_coords['tl_x']},{area_coords['br_y']},{area_coords['br_x']}"
    flights = fr.get_flights(bounds=bounds)

    filtered = []
    for f in flights:
        alt = getattr(f, "altitude", 0)
        vspeed = getattr(f, "vertical_speed", 0)
        heading = getattr(f, "heading", 0)
        dest = getattr(f, "destination_airport_iata", "")
        if (
            alt > 400 and
            vspeed > 0 and
            dest != "BOG" and
            (heading >= 320 or heading <= 60) and
            flight_in_area(f)
        ):
            filtered.append(f)

    if filtered:
        closest = filtered[0]
        logo_data = get_logo(getattr(closest, "airline_iata", ""), getattr(closest, "airline_icao", ""))
        last_flight = {
            "flight": getattr(closest, "callsign", "N/A"),
            "to": getattr(closest, "destination_airport_iata", "N/A"),
            "aircraft": getattr(closest, "aircraft_code", "N/A"),
            "altitude": getattr(closest, "altitude", 0),
            "logo": logo_data
        }
        last_seen_time = time.time()
        return JSONResponse(last_flight)

    # Idle message if no new flight for >30s
    if time.time() - last_seen_time > 30:
        utc_now = datetime.datetime.utcnow().strftime("%H:%MZ")
        return JSONResponse({
            "flight": f"NO TRAFFIC NORTHBOUND — {utc_now}",
            "to": "",
            "aircraft": "",
            "altitude": "",
            "logo": ""
        })

    if last_flight:
        return JSONResponse(last_flight)

    utc_now = datetime.datetime.utcnow().strftime("%H:%MZ")
    return JSONResponse({
        "flight": f"NO TRAFFIC NORTHBOUND — {utc_now}",
        "to": "",
        "aircraft": "",
        "altitude": "",
        "logo": ""
    })
