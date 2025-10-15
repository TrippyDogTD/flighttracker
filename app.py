import os, json, random
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from shapely.geometry import Point, Polygon
from FlightRadar24 import FlightRadar24API

# === CONFIG ===
DATA_DIR = "data"
AREAS_FILE = os.path.join(DATA_DIR, "areas.json")
ACTIVE_AREA_FILE = os.path.join(DATA_DIR, "active_area.json")
LAST_FLIGHT_FILE = os.path.join(DATA_DIR, "last_flight.json")

# === APP INIT ===
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
fr = FlightRadar24API()


# === HELPERS ===
def load_json(path, fallback=None):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return fallback


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_areas():
    return load_json(AREAS_FILE, [])


def get_active_area():
    return load_json(ACTIVE_AREA_FILE, None)


# === PAGES ===
@app.get("/", response_class=HTMLResponse)
async def home():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/map", response_class=HTMLResponse)
async def map_editor():
    with open("static/map.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


# === AREA API ===
@app.post("/save-area")
async def save_area(request: Request):
    data = await request.json()
    name = data.get("name")
    points = data.get("points")
    if not name or not points:
        return JSONResponse({"error": "Name or points missing"}, status_code=400)

    areas = [a for a in load_areas() if a["name"] != name]
    latitudes = [p["lat"] for p in points]
    longitudes = [p["lng"] for p in points]
    bounds = {
        "tl_y": max(latitudes),
        "tl_x": min(longitudes),
        "br_y": min(latitudes),
        "br_x": max(longitudes),
    }
    areas.append({"name": name, "points": points, "bounds": bounds})
    save_json(AREAS_FILE, areas)
    return {"status": "saved", "name": name}


@app.get("/get-area")
async def get_area(name: str):
    # special query for dropdown list
    if name == "__list__":
        areas = load_areas()
        return {"areas": [a["name"] for a in areas]}

    areas = load_areas()
    for a in areas:
        if a["name"] == name:
            return a
    return JSONResponse({"error": "Area not found"}, status_code=404)


@app.delete("/delete-area")
async def delete_area(name: str):
    new_areas = [a for a in load_areas() if a["name"] != name]
    save_json(AREAS_FILE, new_areas)
    return {"status": "deleted", "name": name}


@app.post("/set-active")
async def set_active(name: str):
    for a in load_areas():
        if a["name"] == name:
            save_json(ACTIVE_AREA_FILE, a)
            return {"status": "active", "name": name}
    return JSONResponse({"error": "Area not found"}, status_code=404)


# === FLIGHT INFO ===
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
                if f.longitude and f.latitude and polygon.contains(Point(f.longitude, f.latitude)):
                    valid.append(f)
            except Exception:
                continue

        if not valid:
            data = {
                "flight": "No traffic in area",
                "destination": "--",
                "aircraft": "--",
                "altitude": "--",
                "logo": "/static/logos/default.png",
            }
            save_json(LAST_FLIGHT_FILE, data)
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
        save_json(LAST_FLIGHT_FILE, data)
        return data

    except Exception as e:
        print("❌ Flight error:", e)
        return load_json(LAST_FLIGHT_FILE, {"error": str(e)})
