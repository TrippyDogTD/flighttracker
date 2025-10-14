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
async def map_view(request: Request):
    return templates.TemplateResponse("map.html", {"request": request})


@app.post("/update-area")
async def update_area(area: dict):
    with open(AREA_FILE, "w") as f:
        json.dump(area, f)
    return {"status": "ok"}


@app.get("/traffic")
async def get_all_flights():
    """Return all flights detected in current area."""
    try:
        area_data = load_area()
        polygon = Polygon([(p["lng"], p["lat"]) for p in area_data["points"]])
        b = area_data["bounds"]

        # format bounds string as expected by FlightRadar24API
        bounds_str = f"{b['tl_y']},{b['tl_x']},{b['br_y']},{b['br_x']}"

        flights = fr.get_flights(bounds=bounds_str)

        inside = []
        for f in flights:
            try:
                if f.longitude and f.latitude and polygon.contains(Point(f.longitude, f.latitude)):
                    inside.append(
                        {
                            "id": f.id,
                            "altitude": f.altitude,
                            "airline": f.airline_iata,
                            "destination": f.destination_airport_iata,
                            "lat": f.latitude,
                            "lng": f.longitude,
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
                    and 300 <= f.heading <= 30  # northbound filter (wrap around 0)
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

        print(f"✅ Flight {data['flight']} Dest:{data['destination']} Alt:{data['altitude']}")
        return data

    except Exception as e:
        print("❌ Flight error:", e)
        if os.path.exists(LAST_FLIGHT_FILE):
            with open(LAST_FLIGHT_FILE, "r") as f:
                return json.load(f)
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/health")
async def health():
    return {"status": "ok"}
