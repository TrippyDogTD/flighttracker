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
    """Load polygon area or create a default one."""
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
    """Main flight board."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/map", response_class=HTMLResponse)
async def map_view(request: Request):
    """Map view for editing area."""
    return templates.TemplateResponse("map.html", {"request": request})


@app.post("/update-area")
async def update_area(area: dict):
    """Save new editable area."""
    with open(AREA_FILE, "w") as f:
        json.dump(area, f)
    return {"status": "ok"}


@app.get("/flight")
async def get_flight():
    """Fetch latest flight data within selected area."""
    try:
        area_data = load_area()
        polygon = Polygon([(p["lng"], p["lat"]) for p in area_data["points"]])
        bounds = area_data["bounds"]

        flights = fr.get_flights(bounds=bounds)

        valid_flights = []
        for f in flights:
            try:
                point = Point(f.longitude, f.latitude)
                if polygon.contains(point) and f.altitude > 400 and 270 <= f.track <= 360:
                    valid_flights.append(f)
            except Exception:
                continue

        if not valid_flights:
            print("⚠ No outbound northbound flights found.")
            if os.path.exists(LAST_FLIGHT_FILE):
                with open(LAST_FLIGHT_FILE, "r") as f:
                    return json.load(f)
            return JSONResponse(content={"error": "No flights found"}, status_code=200)

        chosen = random.choice(valid_flights)
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

        print(f"✅ Showing flight {data['flight']} to {data['destination']}")
        return data

    except Exception as e:
        print(f"❌ Error: {e}")
        if os.path.exists(LAST_FLIGHT_FILE):
            with open(LAST_FLIGHT_FILE, "r") as f:
                return json.load(f)
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/health")
async def health():
    """Render health check route."""
    return {"status": "ok"}
