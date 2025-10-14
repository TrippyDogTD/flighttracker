from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from flightradarapi import FlightRadar24API
from shapely.geometry import Point, Polygon
import base64
import requests
import io

app = FastAPI()
fr_api = FlightRadar24API()

# Static + templates
app.mount("/static", StaticFiles(directory="static"), name="static")
env = Environment(loader=FileSystemLoader("templates"))

# Your default polygon (cyan area)
polygon_coords = [
    (-74.1500, 4.6700),
    (-74.0500, 4.6700),
    (-74.0500, 4.7500),
    (-74.1500, 4.7500),
]
area_polygon = Polygon(polygon_coords)

last_flight_data = None  # Keep last departing aircraft data

def get_airline_logo(airline):
    """Fetch and return airline logo as Base64 URI"""
    try:
        logo_url = airline.get("logo") or airline.get("image")
        if not logo_url:
            return None

        if isinstance(logo_url, bytes):
            # Convert binary to base64 string
            encoded = base64.b64encode(logo_url).decode("utf-8")
            return f"data:image/png;base64,{encoded}"

        if isinstance(logo_url, str) and logo_url.startswith("http"):
            # Fetch the image and convert to base64 to make sure it always renders
            response = requests.get(logo_url, timeout=5)
            if response.status_code == 200:
                encoded = base64.b64encode(response.content).decode("utf-8")
                return f"data:image/png;base64,{encoded}"
        return None
    except Exception:
        return None


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    template = env.get_template("index.html")
    return template.render()


@app.get("/map", response_class=HTMLResponse)
async def map_page(request: Request):
    template = env.get_template("map.html")
    return template.render()


@app.get("/current-area")
async def get_current_area():
    """Returns current polygon coordinates."""
    return {"coords": list(area_polygon.exterior.coords)}


@app.post("/current-area")
async def update_area(request: Request):
    """Update the polygon area via the map editor."""
    global area_polygon
    data = await request.json()
    coords = data.get("coords", [])
    if coords:
        area_polygon = Polygon(coords)
    return {"message": "Area updated successfully", "coords": coords}


@app.get("/flight/current")
async def get_current_flight():
    """Fetch latest outbound flight heading north within the area."""
    global last_flight_data
    try:
        flights = fr_api.get_flights(bounds=fr_api.get_bounds_by_point(4.70, -74.10))
        for f in flights:
            lat, lon = f.latitude, f.longitude
            if lat is None or lon is None:
                continue

            point = Point(lon, lat)
            # Only keep outbound (northbound-ish) flights above 400ft
            if area_polygon.contains(point) and f.altitude > 400 and 0 <= f.track <= 30:
                details = fr_api.get_flight_details(f)
                airline_logo = get_airline_logo(details.get("airline", {}))
                flight_data = {
                    "flight": details.get("identification", {}).get("callsign", "Unknown"),
                    "destination": details.get("airport", {}).get("destination", {}).get("name", "Unknown"),
                    "aircraft": details.get("aircraft", {}).get("model", "Unknown"),
                    "altitude": f.altitude,
                    "logo": airline_logo,
                }
                last_flight_data = flight_data
                return JSONResponse(flight_data)

        # If no active aircraft → keep showing the last one
        if last_flight_data:
            return JSONResponse(last_flight_data)
        return JSONResponse({"message": "No outbound flights currently in area."})

    except Exception as e:
        return JSONResponse({"error": str(e)})


@app.get("/health")
def health():
    return {"status": "ok"}
