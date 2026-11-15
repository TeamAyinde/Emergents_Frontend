"""Seeds/cleans TEST_ data for iteration-20 UI checks (host live, deal card, deal banner, tables deep link).
Usage: python iter20_ui_seed.py seed|clean. Creates TEST_ guest/promoter users via API; everything removed by id."""
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
STATE = "/tmp/iter20_ui_seed.json"
TABLES = [{"id": "T1", "name": "T1", "section": "Main", "capacity": 6, "min_spend": 300.0, "x": 20, "y": 40, "min_level": "bronze"},
          {"id": "T2", "name": "T2", "section": "Main", "capacity": 6, "min_spend": 500.0, "x": 60, "y": 40, "min_level": "bronze"}]


def login(email, pw):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": pw}).json()


def reg(role, name):
    r = requests.post(f"{API}/auth/register", json={
        "email": f"test_ui20_{uuid.uuid4().hex[:6]}@nocturne.app", "password": "TestPass123!", "role": role,
        "full_name": name, "membership_tier": "member", "marketing_opt_in": False}).json()
    return r


def seed():
    now = datetime.now(timezone.utc)
    venue = login("venue@nocturne.app", "VenuePass123!")
    VEN = DB.venues.find_one({"owner_id": venue["user"]["id"]}, {"_id": 0, "id": 1, "name": 1})
    g = reg("guest", "TEST_ Wendy Wait")
    p = reg("promoter", "TEST_ Pat Promo")
    st = {"users": [g["user"]["id"], p["user"]["id"]], "events": [], "tickets": [], "requests": []}

    def ev(title, **kw):
        d = {"id": str(uuid.uuid4()), "title": title, "venue_id": VEN["id"], "venue_name": VEN["name"], "city": "Los Angeles",
             "date": now + timedelta(hours=5), "price": 50.0, "tags": ["TEST"], "tickets_sold": 4, "created_at": now,
             "min_level": "bronze", "approval_required": False, "capacity": 10, "guest_list_visible": True,
             "has_tables": True, "plus_one_limit": 3, "tables": TABLES, "created_by": venue["user"]["id"],
             "image_url": "https://images.unsplash.com/photo-1545128485-c400e7702796?w=1400&q=80",
             "description": "TEST_ event. " * 40}
        d.update(kw)
        DB.events.insert_one(dict(d))
        st["events"].append(d["id"])
        return d

    e = ev("TEST_ Deal Night")
    hr = now.replace(minute=10, second=0, microsecond=0)
    for qty, at in ((2, hr - timedelta(hours=1)), (3, hr)):
        t = {"id": str(uuid.uuid4()), "event_id": e["id"], "event_title": e["title"], "event_date": e["date"],
             "venue_name": e["venue_name"], "user_id": p["user"]["id"], "promoter_id": None, "quantity": qty,
             "total_paid": 0.0, "credit_used": 0.0, "platform_fee": 0.0, "promoter_earning": 0.0, "venue_share": 0.0,
             "checked_in": True, "checked_in_at": at, "created_at": now, "table_offer_sent": True, "night_alert_sent": True}
        DB.tickets.insert_one(dict(t))
        st["tickets"].append(t["id"])
    r = {"id": str(uuid.uuid4()), "event_id": e["id"], "event_title": e["title"], "user_id": g["user"]["id"],
         "user_name": "TEST_ Wendy Wait", "user_level": "bronze", "quantity": 1, "kind": "waitlist", "status": "pending",
         "note": "", "promoter_code": None, "created_at": now}
    DB.event_requests.insert_one(dict(r))
    st["requests"].append(r["id"])
    # guest ticket on an event-day table event (TableUpsell)
    e2 = ev("TEST_ Upsell Table Night", price=0, tickets_sold=1, capacity=100)
    t2 = {"id": str(uuid.uuid4()), "event_id": e2["id"], "event_title": e2["title"], "event_date": e2["date"],
          "venue_name": e2["venue_name"], "user_id": g["user"]["id"], "promoter_id": None, "quantity": 1, "total_paid": 0.0,
          "credit_used": 0.0, "platform_fee": 0.0, "promoter_earning": 0.0, "venue_share": 0.0, "checked_in": False,
          "created_at": now, "table_offer_sent": True, "night_alert_sent": True}
    DB.tickets.insert_one(dict(t2))
    st["tickets"].append(t2["id"])
    st.update(deal_event=e["id"], upsell_event=e2["id"], upsell_ticket=t2["id"], guest_token=g["access_token"],
              promoter_token=p["access_token"], venue_token=venue["access_token"])
    json.dump(st, open(STATE, "w"))
    print(json.dumps({k: v for k, v in st.items() if "token" not in k}))


def clean():
    st = json.load(open(STATE))
    print(DB.tickets.delete_many({"id": {"$in": st["tickets"]}}).deleted_count,
          DB.event_requests.delete_many({"id": {"$in": st["requests"]}}).deleted_count,
          DB.events.delete_many({"id": {"$in": st["events"]}}).deleted_count,
          DB.points_ledger.delete_many({"user_id": {"$in": st["users"]}}).deleted_count,
          DB.users.delete_many({"id": {"$in": st["users"]}}).deleted_count)


if __name__ == "__main__":
    seed() if sys.argv[1] == "seed" else clean()
