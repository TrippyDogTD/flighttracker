✈️ FlightTracker
<p align="center"> <img src="https://img.shields.io/badge/Platform-Render-46a2f1?logo=render&logoColor=white" alt="Render"> <img src="https://img.shields.io/badge/Framework-FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI"> <img src="https://img.shields.io/badge/Map-Leaflet-199900?logo=leaflet&logoColor=white" alt="Leaflet"> <img src="https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white" alt="Python"> <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License"> </p>

FlightTracker is a modern FastAPI-based web app that displays live flight data from FlightRadar24
, allows you to define and visualize tracking zones on a map, and manage preset areas via a private console interface.

🧩 Features

✅ Live Flight Board
Displays the most recent flight in the active tracking zone, with automatic updates every few seconds.

✅ Map Area Editor (/map)
Create, name, and manage custom tracking zones visually on a map using Leaflet Draw.

✅ Preset Console (/console)
Edit and reshape predefined North Departures (cyan) and South Departures (orange) areas directly on a map.

“💾 Save All” overwrites the defaults in /data/areas.json

“♻ Reset Defaults” restores them from app.py

✅ Persistent Storage
All your tracking zones, active areas, and last-flight data are stored in /data/, which persists across restarts on Render.

✅ Render-Ready
Configured for automatic deployment with render.yaml and persistent disk storage.

⚙️ Project Structure
flighttracker/
│
├── app.py                # FastAPI backend
├── requirements.txt      # Dependencies
├── render.yaml           # Render deployment config
├── .gitignore            # Clean ignore rules
├── README.md             # Project documentation
│
├── static/               # Frontend files
│   ├── index.html        # Main flight board
│   ├── map.html          # Area editor
│   ├── styles.css        # Styling for UI
│   └── logos/            # Airline logos (optional)
│
└── data/                 # Persistent JSON storage
    ├── areas.json        # All saved areas
    ├── active_area.json  # Currently active area
    └── last_flight.json  # Cached last flight info

🛠️ Local Setup
1️⃣ Create a virtual environment
python -m venv .venv
source .venv/bin/activate    # (Mac/Linux)
.venv\Scripts\activate       # (Windows)

2️⃣ Install dependencies
pip install -r requirements.txt

3️⃣ Run locally
uvicorn app:app --reload

4️⃣ Open in browser

Flight board: http://127.0.0.1:8000

Map editor: http://127.0.0.1:8000/map

Preset console: http://127.0.0.1:8000/console

🚀 Render Deployment
1️⃣ Commit and push to GitHub

Make sure you have:

render.yaml

.gitignore

requirements.txt

app.py

Then push:

git add .
git commit -m "Deploy-ready version of FlightTracker"
git push

2️⃣ Create a new Render Web Service

Go to Render.com

Choose New Web Service

Connect your GitHub repo

Render automatically detects render.yaml

3️⃣ Wait for the build to finish

When the build succeeds, your app will be available at:

https://<your-service-name>.onrender.com

4️⃣ Persistent storage

The /data/ folder is mounted as a persistent disk — your areas and flight logs will remain after redeploys.

🌍 API Endpoints
Endpoint	Method	Description
/	GET	Main flight board
/map	GET	Area editor UI (create/delete zones)
/console	GET	Preset editor UI (North/South)
/save-area	POST	Save a new custom area
/get-area	GET	Retrieve area by name
/delete-area	DELETE	Remove an area
/set-active	POST	Set area as active
/update-all-presets	POST	Overwrite all preset areas
/reset-presets	POST	Reset presets to defaults
/flight	GET	Fetch latest flight in active area
✨ Color Legend
Preset	Color	Purpose
North Departures	🟦 Cyan	Northern tracking zone
South Departures	🟧 Orange	Southern tracking zone
💾 Data Persistence

All data is written to JSON files inside /data/.
Render mounts this directory persistently, so your tracking areas and flight history survive restarts.

areas.json: All user and preset zones

active_area.json: Currently selected area for tracking

last_flight.json: Most recent flight data

🧠 Notes

The console is private — only accessible via direct link (/console), not from the main UI.

The defaults in app.py are never overwritten — they act as fallbacks for “Reset Defaults.”

You can add more custom areas freely via /map.

🧑‍✈️ Credits

Developed by TrippyDog ✈
Built with FastAPI, Leaflet.js, and FlightRadar24API