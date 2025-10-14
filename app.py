from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from FlightRadar24 import FlightRadar24API
from shapely.geometry import Point, Polygon
import json, random

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

fr = FlightRadar24API()

# Load cyan area from file
def load_area():
    with open("area.json", "r") as f:
        return json.load(f)

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/map", response_class=HTMLResponse)
async def map_view(request: Request):
    return templates.TemplateResponse("map.html", {"request": request})

@app.get("/flight")
async def get_flight():
    try:
        # Load polygon area
        area_data = load_area()
        polygon = Polygon([(p["lng"], p["lat"]) for p in area_data["points"]])

        bounds = area_data["bounds"]
        flights = fr.get_flights(bounds=bounds)

        # Filter flights above 400 ft and northbound
        valid_flights = []
        for f in flights:
            try:
                point = Point(f.longitude, f.latitude)
                if (
                    polygon.contains(point)
                    and f.altitude > 400
                    and 270 <= f.track <= 360
                ):
                    valid_flights.append(f)
            except Exception:
                continue

        # Load last flight if none found
        if not valid_flights:
            with open("last_flight.json", "r") as f:
                return json.load(f)

        chosen = random.choice(valid_flights)
        airline_code = chosen.airline_iata or "XX"

        flight_data = {
            "flight": chosen.id or "--",
            "destination": chosen.destination_airport_iata or "--",
            "aircraft": chosen.aircraft_code or "--",
            "altitude": int(chosen.altitude),
            "logo": f"/static/logos/{airline_code}.png"
            if airline_code
            else "/static/logos/default.png",
        }

        # Save for fallback
        with open("last_flight.json", "w") as f:
            json.dump(flight_data, f)

        return flight_data

    except Exception as e:
        print("Error fetching flight:", e)
        try:
            with open("last_flight.json", "r") as f:
                return json.load(f)
        except:
            return JSONResponse(content={"error": str(e)}, status_code=500)
