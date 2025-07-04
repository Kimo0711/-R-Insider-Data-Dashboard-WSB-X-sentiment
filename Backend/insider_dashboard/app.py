from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import HTTPException
from urllib.parse import unquote
import subprocess
import yaml
import json
import os

app = FastAPI()

def format_trade_size(amount_str):
    try:
        amount = float(amount_str)
    except (ValueError, TypeError):
        return "Unknown"

    if amount < 1_000:
        return "< 1K"
    elif amount < 15_000:
        return "1K–15K"
    elif amount < 50_000:
        return "15K–50K"
    elif amount < 100_000:
        return "50K–100K"
    elif amount < 250_000:
        return "100K–250K"
    elif amount < 500_000:
        return "250K–500K"
    elif amount < 1_000_000:
        return "500K–1M"
    elif amount < 5_000_000:
        return "1M–5M"
    elif amount < 25_000_000:
        return "5M–25M"
    elif amount < 50_000_000:
        return "25M–50M"
    else:
        return "50M+"
    
templates = Jinja2Templates(directory="../../Frontend/src/templates")
templates.env.filters["format_trade_size"] = format_trade_size

congress_data = []  # Global cache
state_lookup = {}


def load_state_lookup_from_yaml():
    path = os.path.join(os.path.dirname(__file__), "legislators-historical.yaml")
    with open(path, "r") as f:
        data = yaml.safe_load(f)

    lookup = {}

    for filename in ["legislators-current.yaml", "legislators-historical.yaml"]:
        with open(filename, "r") as f:
            data = yaml.safe_load(f)
            for person in data:
                bio_id = person.get("id", {}).get("bioguide")
                terms = person.get("terms", [])
                if bio_id and terms:
                    latest_term = terms[-1]
                    state = latest_term.get("state")
                    if state:
                        lookup[bio_id] = state

    return lookup

@app.on_event("startup")
def fetch_congress_data():
    global congress_data, state_lookup
    state_lookup = load_state_lookup_from_yaml()
    curl_command = [
        "curl",
        "-s",
        "--request", "GET",
        "--url", "https://api.quiverquant.com/beta/bulk/congresstrading",
        "--header", "Accept: application/json",
        "--header", "Authorization: Bearer d95376201ee52332b90d7ab3e527076011921658"
    ]
    result = subprocess.run(curl_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        congress_data = json.loads(result.stdout)
        print(f"Loaded {len(congress_data)} records.")
    except Exception as e:
        print("Failed to parse JSON:", e)
        print("Output:", result.stdout[:300])

@app.get("/", response_class=HTMLResponse)
def homepage(request: Request, page: int = 1, name: str = "", party: str = "", state: str = ""):
    per_page = 20
    # Group by politician (simplified)
    grouped = {}
    for item in congress_data:
        person_name = item.get("Name")
        bio_id = item.get("BioGuideID")
        state_value = state_lookup.get(bio_id, "")
        if person_name not in grouped: 
            grouped[person_name] = {
                "name":person_name,
                "party": item.get("Party", ""),
                "chamber": item.get("Chamber", ""),
                "state": state_value,
                "trades": 0,
                "last_traded": item.get("Traded", ""),
            }
        grouped[person_name]["trades"] += 1
    
    # Apply filters
    filtered = []
    for p in grouped.values():
        if name.lower() in p["name"].lower() and \
           (party == "" or p["party"] == party) and \
           (state == "" or p["state"] == state):
            filtered.append(p)  
    
    # Convert to list and sort
    politicians = sorted(filtered, key=lambda x: x["trades"], reverse=True)
    total = len(politicians)
    start = (page - 1) * per_page
    end = start + per_page
    paginated = politicians[start:end]

    total_pages = (total + per_page - 1) // per_page  # ceil

    parties = sorted(set(p["party"] for p in grouped.values() if p["party"]))
    states = sorted(set(p["state"] for p in grouped.values() if p["state"]))

    return templates.TemplateResponse("home.html", {
        "request": request,
        "politicians": paginated,
        "page": page,
        "total_pages": total_pages,
        "filter_name": name,
        "filter_party": party,
        "filter_state": state,
        "party_options": parties,
        "state_options": states
    })

@app.get("/politician/{name}", response_class=HTMLResponse)
def profile(request: Request, name: str):
    decoded_name = unquote(name)
    trades = [t for t in congress_data if t.get("Name") == decoded_name]

    if not trades:
        raise HTTPException(status_code=404, detail="Politician not found")

    # Sort trades by date (newest first)
    trades.sort(key=lambda t: t.get("Traded", ""), reverse=True)
            
    bio_id = trades[0].get("BioGuideID")
    state = state_lookup.get(bio_id, "")
    
    profile_info = {
        "name": decoded_name,
        "party": trades[0].get("Party", ""),
        "chamber": trades[0].get("Chamber", ""),
        "state": state,
        "trades": trades
    }

    return templates.TemplateResponse("profile.html", {
        "request": request,
        "profile": profile_info
    })