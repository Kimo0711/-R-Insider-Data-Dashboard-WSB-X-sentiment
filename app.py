from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from urllib.parse import unquote
from datetime import datetime, timedelta
from typing import List
import subprocess
import yaml
import json
import os
import yfinance as yf


app = FastAPI()

# ---- Caching Setup ----
ticker_cache = {}
CACHE_PATH = "ticker_cache.json"

def load_cache():
    global ticker_cache
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r") as f:
                ticker_cache = json.load(f)
        except Exception as e:
            print("Failed to load ticker cache:", e)
            ticker_cache = {}

def save_cache():
    with open(CACHE_PATH, "w") as f:
        json.dump(ticker_cache, f)

def fetch_company_info(ticker: str) -> dict:
    if not ticker or not isinstance(ticker, str):
        return {"name": "Unknown", "industry": "Unknown"}

    ticker = ticker.upper()
    if ticker in ticker_cache:
        return ticker_cache[ticker]

    try:
        t = yf.Ticker(ticker)
        info = t.info or {}

        name = info.get("longName") or info.get("shortName")
        if not isinstance(name, str) or name.strip().isdigit():
            name = ticker  # fallback to ticker only if valid name not found

        result = {
            "name": name,
            "industry": info.get("industry", "General")
        }
        ticker_cache[ticker] = result
        save_cache()
        return result
    except Exception as e:
        print(f"yfinance failed for {ticker}: {e}")
        fallback = {"name": ticker, "industry": "General"}
        ticker_cache[ticker] = fallback
        return fallback

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

templates = Jinja2Templates(directory="Frontend/src/templates")
templates.env.filters["format_trade_size"] = format_trade_size

congress_data = []
state_lookup = {}

def load_state_lookup_from_yaml():
    path = os.path.join(os.path.dirname(__file__), "Backend/insider_dashboard/legislators-historical.yaml")
    with open(path, "r") as f:
        data = yaml.safe_load(f)

    lookup = {}
    for filename in ["Backend/insider_dashboard/legislators-current.yaml", "Backend/insider_dashboard/legislators-historical.yaml"]:
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

bio_to_committees = {}

@app.on_event("startup")
def startup_event():
    global congress_data, state_lookup, bio_to_committees
    load_cache()
    state_lookup = load_state_lookup_from_yaml()

    # Load trading data
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

    # Precompute committee mapping
    id_to_names = {}
    for entry in historical_data:
        base_id = entry.get("thomas_id")
        if not base_id:
            continue
        id_to_names[base_id] = entry.get("name", f"Committee {base_id}")
        for sub in entry.get("subcommittees", []):
            sub_id = sub.get("thomas_id", "")
            full_id = base_id + sub_id
            id_to_names[full_id] = entry.get("name", f"Committee {full_id}")

    for committee_id, members in membership_data.items():
        for member in members:
            bio = member.get("bioguide")
            if not bio:
                continue
            if bio not in bio_to_committees:
                bio_to_committees[bio] = set()
            name = id_to_names.get(committee_id)
            if name:
                bio_to_committees[bio].add(name)

    # convert sets to sorted lists for later use
    for bio, committees in bio_to_committees.items():
        bio_to_committees[bio] = sorted(committees)


@app.on_event("shutdown")
def shutdown_event():
    save_cache()

committee_membership_file = "Backend/insider_dashboard/committee-membership-current.yaml"
committees_historical_file = "Backend/insider_dashboard/committees-historical.yaml"

# Load both YAML files once
with open(committee_membership_file, "r") as f:
    membership_data = yaml.safe_load(f)

with open(committees_historical_file, "r") as f:
    historical_data = yaml.safe_load(f)

# Map thomas_id to committee name
thomas_to_name = {
    entry.get("thomas_id"): entry.get("name", "Unknown Committee")
    for entry in historical_data if "thomas_id" in entry
}

def get_committees(bioguide_id):
    return bio_to_committees.get(bioguide_id, [])

@app.get("/", response_class=HTMLResponse)
def homepage(request: Request, page: int = 1, name: str = "", party: str = "", state: str = "", committee: str = ""):
    per_page = 20
    grouped = {}
    for item in congress_data:
        person_name = item.get("Name")
        bio_id = item.get("BioGuideID")
        state_value = state_lookup.get(bio_id, "")
        committees = get_committees(bio_id)

        if person_name not in grouped:
            grouped[person_name] = {
                "name": person_name,
                "party": item.get("Party", ""),
                "chamber": item.get("Chamber", ""),
                "state": state_value,
                "committees": committees,
                "trades": 0,
                "last_traded": item.get("Traded", ""),
            }
        grouped[person_name]["trades"] += 1

    filtered = []
    for p in grouped.values():
        if name.lower() in p["name"].lower() and \
           (party == "" or p["party"] == party) and \
           (state == "" or p["state"] == state) and \
           (committee == "" or committee in p["committees"]):
            filtered.append(p)

    politicians = sorted(filtered, key=lambda x: x["trades"], reverse=True)
    total = len(politicians)
    start = (page - 1) * per_page
    end = start + per_page
    paginated = politicians[start:end]
    total_pages = (total + per_page - 1) // per_page

    parties = sorted(set(p["party"] for p in grouped.values() if p["party"]))
    states = sorted(set(p["state"] for p in grouped.values() if p["state"]))
    committees_all = sorted(set(c for p in grouped.values() for c in p["committees"]))

    return templates.TemplateResponse("home.html", {
        "request": request,
        "politicians": paginated,
        "page": page,
        "total_pages": total_pages,
        "filter_name": name,
        "filter_party": party,
        "filter_state": state,
        "filter_committee": committee,
        "party_options": parties,
        "state_options": states,
        "committee_options": committees_all,
    })

@app.get("/politician/{name}", response_class=HTMLResponse)
def profile(request: Request, name: str, page: int = 1):
    decoded_name = unquote(name).strip()
    trades = [
        t for t in congress_data
        if isinstance(t, dict) and t.get("Name", "").strip() == decoded_name
    ]

    if not trades:
        raise HTTPException(status_code=404, detail="Politician not found")

    trades.sort(key=lambda t: t.get("Traded", ""), reverse=True)

    per_page = 50
    total_pages = (len(trades) + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page
    page_trades = trades[start:end]

    for trade in page_trades:
        ticker = trade.get("Ticker")
        info = fetch_company_info(ticker)
        trade["company_name"] = info["name"]
        trade["industry"] = info["industry"]

    bio_id = trades[0].get("BioGuideID")
    committees = get_committees(bio_id)
    state = state_lookup.get(bio_id, "")

    profile_info = {
        "name": trades[0]["Name"],
        "party": trades[0].get("Party", ""),
        "chamber": trades[0].get("Chamber", ""),
        "state": state,
        "committee" : committees,
        "trades": page_trades
    }

    return templates.TemplateResponse("profile.html", {
        "request": request,
        "profile": profile_info,
        "page": page,
        "total_pages": total_pages
    })

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    page: int = 1,
    name: str = "",
    party: str = "",
    state: str = "",
    industry: List[str] = Query(default=[]),
    committee: List[str] = Query(default=[]),
    transaction: str = "",
    range: str = "",
    after: str = ""
):
    per_page = 100
    cutoff_date = datetime.now() - timedelta(days=3 * 365)

    # Parse user-provided date filter if valid
    try:
        after_date = datetime.strptime(after, "%Y-%m-%d") if after else cutoff_date
    except ValueError:
        after_date = cutoff_date

    valid_trades = []
    industry_set = set()
    committee_set = set()
    party_set = set()
    state_set = set()
    transaction_set = set()

    for t in congress_data:
        traded_str = t.get("Traded", "")
        try:
            traded_date = datetime.strptime(traded_str, "%Y-%m-%d")
        except ValueError:
            continue

        if traded_date < after_date:
            continue

        bio = t.get("BioGuideID")
        ticker = t.get("Ticker", "").upper()

        if ticker in ticker_cache:
            info = ticker_cache[ticker]
        else:
            info = fetch_company_info(ticker)

        trade_industry = info.get("industry", "General")
        # Collect filters
        industry_set.add(trade_industry)
        for c in get_committees(bio):
            if c:
                committee_set.add(c)
        party_set.add(t.get("Party", ""))
        state_set.add(state_lookup.get(bio, ""))
        transaction_set.add(t.get("Transaction", ""))

        # Apply filters
        if name.lower() not in t.get("Name", "").lower():
            continue
        if party and t.get("Party", "") != party:
            continue
        if state and state_lookup.get(bio, "") != state:
            continue
        if industry and trade_industry not in industry:
            continue
        if transaction and t.get("Transaction", "") != transaction:
            continue
        if range and format_trade_size(t.get("Trade_Size_USD")) != range:
            continue
        committees = get_committees(bio)
        if committee and not any(c in get_committees(bio) for c in committee):
            continue

        valid_trades.append({
            "name": t.get("Name"),
            "party": t.get("Party", ""),
            "chamber": t.get("Chamber", ""),
            "state": state_lookup.get(bio, ""),
            "ticker": ticker,
            "company_name": info["name"],
            "industry": trade_industry,
            "traded": t.get("Traded"),
            "filed": t.get("Filed"),
            "price": t.get("Price"),
            "transaction": t.get("Transaction"),
            "size": format_trade_size(t.get("Trade_Size_USD")),
        })

    total = len(valid_trades)
    total_pages = (total + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page
    paginated = valid_trades[start:end]

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "trades": paginated,
        "page": page,
        "total_pages": total_pages,
        "filter_name": name,
        "filter_party": party,
        "filter_state": state,
        "filter_industry": industry,
        "filter_transaction": transaction,
        "filter_range": range,
        "filter_after": after,
        "industry_options": sorted(industry_set),
        "party_options": sorted(party_set),
        "state_options": sorted(s for s in state_set if s),
        "transaction_options": sorted(transaction_set),
        "filter_committee": committee,
        "committee_options": sorted(committee_set),
        "range_options": [
            "< 1K", "1K–15K", "15K–50K", "50K–100K",
            "100K–250K", "250K–500K", "500K–1M", "1M–5M",
            "5M–25M", "25M–50M", "50M+"
        ]
    })
