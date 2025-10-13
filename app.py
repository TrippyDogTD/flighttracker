from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from FlightRadar24 import FlightRadar24API
from shapely.geometry import Point, Polygon
import base64, json, os

app = FastAPI()
fr = FlightRadar24API()

AREA_FILE = "area.json"
LAST_FLIGHT_FILE = "last_flight.json"

DEFAULT_AREA = {
    "points": [
        [4.784, -74.114],
        [4.784, -74.025],
        [4.644, -74.025],
        [4.644, -74.114]
    ]
}


# ========== Helper Functions ==========
def load_area():
    if os.path.exists(AREA_FILE):
        with open(AREA_FILE, "r") as f:
            return json.load(f)
    return DEFAULT_AREA


def save_area(data):
    with open(AREA_FILE, "w") as f:
        json.dump(data, f)


def load_last_flight():
    if os.path.exists(LAST_FLIGHT_FILE):
        with open(LAST_FLIGHT_FILE, "r") as f:
            return json.load(f)
    return None


def save_last_flight(data):
    with open(LAST_FLIGHT_FILE, "w") as f:
        json.dump(data, f)


# ========== Main Board ==========
@app.get("/")
def board():
    return HTMLResponse("""
    <html>
    <head>
      <title>Live Flight Board</title>
      <style>
        body {
          background: #000;
          color: #FFD700;
          font-family: 'Courier New', monospace;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          height: 100vh;
          margin: 0;
        }
        .title {
          font-size: 2em;
          margin-bottom: 25px;
          letter-spacing: 3px;
        }
        #board {
          display: flex;
          align-items: center;
          border: 2px solid #FFD700;
          border-radius: 12px;
          box-shadow: 0 0 20px #FFD70055;
          padding: 25px 40px;
          text-shadow: 0 0 4px #FFD70088;
          min-width: 320px;
          transition: all 0.3s ease-in-out;
        }
        #board.cached {
          border-color: #FF4444;
          box-shadow: 0 0 20px #FF444422;
          color: #FF8888;
        }
        #logo {
          width: 70px;
          height: 70px;
          margin-right: 20px;
          border-radius: 8px;
          background: rgba(255,215,0,0.08);
          display: flex;
          align-items: center;
          justify-content: center;
          overflow: hidden;
        }
        #logo img {
          max-width: 100%;
          max-height: 100%;
          object-fit: contain;
          opacity: 0;
          transition: opacity 0.6s ease-in;
        }
        #logo img.show {
          opacity: 1;
        }
        #info {
          line-height: 1.8em;
        }
        .flap {
          display: inline-block;
          transition: all 0.25s ease-in-out;
        }
        .flap.flip {
          opacity: 0;
          transform: scaleY(0.3);
        }
        #cachedLabel {
          position: absolute;
          top: 20px;
          right: 20px;
          color: #FF6666;
          font-size: 1em;
          font-family: 'Courier New', monospace;
          letter-spacing: 2px;
          display: none;
          animation: blink 1.5s infinite;
        }
        @keyframes blink {
          0%, 50%, 100% { opacity: 1; }
          25%, 75% { opacity: 0.4; }
        }
        #link {
          position: absolute;
          bottom: 20px;
          color: #999;
        }
        #link a {
          color: #FFD700;
          text-decoration: none;
        }
      </style>
    </head>
    <body>
      <div class="title">✈ LIVE FLIGHT BOARD</div>
      <div id="cachedLabel">CACHED DATA</div>
      <div id="board">
        <div id="logo"></div>
        <div id="info">Loading flight data...</div>
      </div>
      <div id="link"><a href="/map" target="_blank">🗺 Open Map / Edit Area</a></div>

      <script>
        let lastData = {};
        function flipChanged(el, newValue) {
          if (el.textContent !== newValue) {
            el.classList.add('flip');
            setTimeout(() => {
              el.textContent = newValue;
              el.classList.remove('flip');
            }, 150);
          }
        }

        function renderBoard(data) {
          const info = document.getElementById('info');
          const logoDiv = document.getElementById('logo');
          const board = document.getElementById('board');
          const cachedLabel = document.getElementById('cachedLabel');

          if (data.status === 'no_flights') {
            info.textContent = "No flights currently in area.";
            board.classList.remove('cached');
            cachedLabel.style.display = 'none';
            return;
          }

          if (!info.dataset.ready) {
            info.innerHTML = `
              Flight: <span id='fnum' class='flap'></span><br>
              To: <span id='fdest' class='flap'></span><br>
              Aircraft: <span id='faircraft' class='flap'></span><br>
              Altitude: <span id='falt' class='flap'></span>
            `;
            info.dataset.ready = true;
          }

          flipChanged(document.getElementById('fnum'), data.flight_number);
          flipChanged(document.getElementById('fdest'), data.destination);
          flipChanged(document.getElementById('faircraft'), data.aircraft);
          flipChanged(document.getElementById('falt'), data.altitude + " ft");

          if (data.logo && data.logo !== lastData.logo) {
            logoDiv.innerHTML = `<img src="${data.logo}" alt="logo">`;
            setTimeout(() => {
              const img = logoDiv.querySelector('img');
              if (img) img.classList.add('show');
            }, 50);
          }

          if (data.status === "cached") {
            board.classList.add('cached');
            cachedLabel.style.display = 'block';
          } else {
            board.classList.remove('cached');
            cachedLabel.style.display = 'none';
          }

          lastData = data;
        }

        async function update() {
          const res = await fetch('/flight/current');
          const data = await res.json();
          renderBoard(data);
        }

        setInterval(update, 500);
        update();
      </script>
    </body>
    </html>
    """)


# ========== Map Page ==========
@app.get("/map")
def map_page():
    return HTMLResponse("""
    <html>
    <head>
      <title>Area Editor</title>
      <link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css"/>
      <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet-draw@1.0.4/dist/leaflet.draw.css"/>
      <script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
      <script src="https://cdn.jsdelivr.net/npm/leaflet-draw@1.0.4/dist/leaflet.draw.js"></script>
      <style>
        body, html { margin:0; padding:0; height:100%; width:100%; }
        #map { height:100%; width:100%; }
        #saveBtn {
          position: absolute;
          top: 10px;
          right: 10px;
          z-index: 1000;
          background-color: #00BFFF;
          color: white;
          border: none;
          border-radius: 6px;
          padding: 10px 20px;
          font-family: 'Courier New', monospace;
          cursor: pointer;
          box-shadow: 0 0 6px #000;
        }
        #saveBtn:hover { background-color: #1E90FF; }
      </style>
    </head>
    <body>
      <button id="saveBtn">💾 Save Area</button>
      <div id="map"></div>
      <script>
        let map = L.map('map').setView([4.7, -74.1], 12);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          attribution: '© OpenStreetMap'
        }).addTo(map);

        let editableLayer = new L.FeatureGroup();
        map.addLayer(editableLayer);

        let currentPolygon = null;

        fetch('/current-area').then(res => res.json()).then(area => {
          if (area.points) {
            currentPolygon = L.polygon(area.points, {color:'cyan', fillColor:'cyan', fillOpacity:0.2}).addTo(editableLayer);
            map.fitBounds(currentPolygon.getBounds());
          }
        });

        const drawControl = new L.Control.Draw({
          edit: { featureGroup: editableLayer },
          draw: { polygon: true, marker: false, circle: false, polyline: false, rectangle: false }
        });
        map.addControl(drawControl);

        map.on(L.Draw.Event.CREATED, e => {
          editableLayer.clearLayers();
          currentPolygon = e.layer;
          editableLayer.addLayer(currentPolygon);
        });

        map.on(L.Draw.Event.EDITED, e => {
          e.layers.eachLayer(l => currentPolygon = l);
        });

        document.getElementById('saveBtn').addEventListener('click', () => {
          if (currentPolygon) {
            const pts = currentPolygon.getLatLngs()[0].map(p => [p.lat, p.lng]);
            fetch('/update-area', {
              method: 'POST',
              headers: {'Content-Type':'application/json'},
              body: JSON.stringify({points: pts})
            }).then(() => alert('✅ Area saved!'));
          } else {
            alert('Draw a polygon first.');
          }
        });
      </script>
    </body>
    </html>
    """)


# ========== API ==========
@app.get("/current-area")
def current_area():
    return load_area()


@app.post("/update-area")
async def update_area(req: Request):
    data = await req.json()
    save_area(data)
    return JSONResponse({"status": "updated"})


@app.get("/flight/current")
async def get_flight():
    area = load_area()
    poly = Polygon(area["points"])
    center = poly.centroid
    lats = [p[0] for p in area["points"]]
    lons = [p[1] for p in area["points"]]
    bounds = f"{max(lats)},{min(lons)},{min(lats)},{max(lons)}"
    flights = fr.get_flights(bounds=bounds)

    closest, min_dist = None, float("inf")
    for f in flights:
        lat, lon = getattr(f, "latitude", None), getattr(f, "longitude", None)
        altitude = getattr(f, "altitude", 0)
        if lat and lon and altitude > 400:  # Ignore low aircraft
            d = center.distance(Point(lat, lon))
            if d < min_dist:
                closest, min_dist = f, d

    if not closest:
        last = load_last_flight()
        if last:
            last["status"] = "cached"
            return last
        else:
            return {"status": "no_flights"}

    # ✅ Try to get airline logo
    logo = ""
    try:
        iata = getattr(closest, "airline_iata", "")
        icao = getattr(closest, "airline_icao", "")
        logo_data = fr.get_airline_logo(iata, icao)

        if isinstance(logo_data, bytes):  # direct PNG bytes
            logo = "data:image/png;base64," + base64.b64encode(logo_data).decode()
        elif isinstance(logo_data, str):
            if logo_data.startswith("http"):  # full URL
                logo = logo_data
            elif logo_data.startswith("/"):  # relative path (common)
                logo = f"https://www.flightradar24.com{logo_data}"
    except Exception:
        logo = ""

    if not logo:
        # 🟡 Fallback SVG if no logo found
        placeholder_svg = """
        <svg xmlns='http://www.w3.org/2000/svg' width='64' height='64' viewBox='0 0 24 24' fill='#FFD700'>
        <path d='M2 16l20-8-20-8v6l12 2-12 2z'/>
        </svg>
        """
        logo = "data:image/svg+xml;base64," + base64.b64encode(placeholder_svg.encode()).decode()

    flight_data = {
        "airline": getattr(closest, "airline_iata", "Unknown"),
        "flight_number": getattr(closest, "callsign", "N/A"),
        "destination": getattr(closest, "destination_airport_iata", ""),
        "aircraft": getattr(closest, "aircraft_code", ""),
        "altitude": getattr(closest, "altitude", 0),
        "logo": logo,
        "status": "live"
    }

    save_last_flight(flight_data)
    return flight_data

