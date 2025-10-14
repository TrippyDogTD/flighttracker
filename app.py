from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from flightradarapi import FlightRadar24API
from shapely.geometry import Point, Polygon
import requests
import math
import os

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

fr_api = FlightRadar24API()

# Default cyan area (Bogotá)
AREA = {
    "points": [
        [4.665, -74.160],
        [4.665, -74.050],
        [4.775, -74.050],
        [4.775, -74.160],
    ]
}

last_flight_data = None  # store last departing flight


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/map", response_class=HTMLResponse)
async def map_page(request: Request):
    return templates.TemplateResponse("map.html", {"request": request, "area": AREA})


@app.get("/current-area")
async def current_area():
    return AREA


@app.post("/update-area")
async def update_area(request: Request):
    global AREA
    data = await request.json()
    AREA = data
    return {"status": "Area updated"}


@app.get("/flight/current")
async def current_flight():
    """
    Fetch flights in area, filter for those departing and heading northbound,
    above 400 ft AGL.
    """
    global last_flight_data

    bounds = _get_bounds_from_area(AREA)
    flights = fr_api.get_flights(bounds=bounds)

    selected = None
    for f in flights:
        if not f.latitude or not f.longitude:
            continue
        # altitude filter
        if f.altitude is None or f.altitude < 400:
            continue

        # heading north (roughly between 300°–60°)
        heading = getattr(f, "heading", 0)
        if heading is None or not (300 <= heading or heading <= 60):
            continue

        point = Point(f.latitude, f.longitude)
        poly = Polygon(AREA["points"])
        if poly.contains(point):
            selected = f
            break

    if selected:
        last_flight_data = _build_flight_info(selected)
        return last_flight_data

    # return last known flight if no active one
    return last_flight_data or {}


def _get_bounds_from_area(area):
    lats = [p[0] for p in area["points"]]
    lons = [p[1] for p in area["points"]]
    return {
        "fa": min(lats),
        "fo": min(lons),
        "la": max(lats),
        "lo": max(lons),
    }


def _build_flight_info(f):
    airline = f.airline_name or "Unknown"
    logo_url = _get_airline_logo(f.airline_icao or "")

    return {
        "flight": f.number or "N/A",
        "destination": f.destination_airport_name or "Unknown",
        "aircraft": f.aircraft_code or "N/A",
        "altitude": f.altitude,
        "airline": airline,
        "logo": logo_url,
    }


def _get_airline_logo(icao):
    if not icao:
        return "/static/logos/default.png"
    url = f"https://content.airhex.com/content/logos/airlines_{icao}_200_200_s.png?proportions=keep"
    try:
        response = requests.head(url, timeout=2)
        if response.status_code == 200:
            return url
    except:
        pass
    return "/static/logos/default.png"
