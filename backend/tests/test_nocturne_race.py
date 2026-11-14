"""Race check: concurrent joins on a capacity-1 event should issue at most 1 ticket (oversell check). Self-cleaning."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
USERS = [("guest@nocturne.app", "GuestPass123!"), ("promoter@nocturne.app", "PromoterPass123!"),
         ("venue@nocturne.app", "VenuePass123!"), ("admin@nocturne.app", "AdminPass123!")]


def tok(c):
    return requests.post(f"{API}/auth/login", json={"email": c[0], "password": c[1]}).json()["access_token"]


def test_concurrent_join_no_oversell():
    toks = [tok(c) for c in USERS]
    vid = next(v["id"] for v in requests.get(f"{API}/venues").json() if v["name"] == "Mirage Lounge")
    ev = requests.post(f"{API}/events", headers={"Authorization": f"Bearer {toks[2]}"}, json={
        "title": "TEST_Race", "venue_id": vid, "date": (datetime.now(timezone.utc) + timedelta(days=9)).isoformat(),
        "price": 10, "image_url": "https://images.unsplash.com/photo-1", "description": "TEST", "capacity": 1}).json()
    try:
        def join(t):
            return requests.post(f"{API}/events/{ev['id']}/join", json={"quantity": 1},
                                 headers={"Authorization": f"Bearer {t}"}).json().get("result")
        with ThreadPoolExecutor(8) as ex:
            results = list(ex.map(join, toks * 2))
        sold = DB.events.find_one({"id": ev["id"]})["tickets_sold"]
        print("results", results, "tickets_sold", sold)
        assert sold <= 1, f"oversold: {sold} tickets on capacity 1"
    finally:
        DB.tickets.delete_many({"event_id": ev["id"]})
        DB.event_requests.delete_many({"event_id": ev["id"]})
        DB.events.delete_one({"id": ev["id"]})
