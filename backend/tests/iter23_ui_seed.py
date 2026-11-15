"""Seeds/cleans TEST_ data for iteration-23 UI checks (shifts card, VIP star, schedule toggle, month report, deal leaderboard).
Usage: python iter23_ui_seed.py seed|clean. Everything is removed by id."""
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
STATE = "/tmp/iter23_ui_seed.json"
IMG = "https://images.unsplash.com/photo-1545128485-c400e7702796?w=1400&q=80"


def _ev(st, owner, ven, title, date, **kw):
    doc = {"id": str(uuid.uuid4()), "title": title, "venue_id": ven["id"], "venue_name": ven["name"], "city": "Los Angeles",
           "date": date, "price": 40.0, "tags": ["TEST"], "tickets_sold": 3, "created_at": date - timedelta(days=3),
           "min_level": "bronze", "approval_required": False, "capacity": 20, "plus_one_limit": 5, "tables": [],
           "created_by": owner, "image_url": IMG, "description": "TEST_ event", "summary_sent": True}
    doc.update(kw)
    DB.events.insert_one(doc)
    st["events"].append(doc["id"])
    return doc


def _tk(st, ev, uid, qty, created, paid=0.0, checked=False):
    tid = str(uuid.uuid4())
    DB.tickets.insert_one({"id": tid, "event_id": ev["id"], "event_title": ev["title"], "event_date": ev["date"],
                           "venue_name": ev["venue_name"], "user_id": uid, "promoter_id": None, "quantity": qty, "total_paid": paid,
                           "credit_used": 0.0, "platform_fee": 0.0, "promoter_earning": 0.0, "venue_share": 0.0,
                           "checked_in": checked, "checked_in_at": created if checked else None, "created_at": created})
    st["tickets"].append(tid)
    return tid


def _reg(st, name):
    r = requests.post(f"{API}/auth/register", json={
        "email": f"test_ui23_{uuid.uuid4().hex[:6]}@nocturne.app", "password": "TestPass123!", "role": "guest",
        "full_name": name, "membership_tier": "member", "marketing_opt_in": False}).json()
    st["users"].append(r["user"]["id"])
    return r


def seed():
    now = datetime.now(timezone.utc)
    owner = DB.users.find_one({"email": "venue@nocturne.app"}, {"_id": 0, "id": 1})["id"]
    st = {"users": [], "events": [], "tickets": [], "venues": [], "staff": []}
    ven = {"id": f"TEST_v_{uuid.uuid4().hex[:8]}", "name": "TEST_ Iter23 Lounge", "owner_id": owner, "city": "Los Angeles",
           "created_at": now, "state": "CA", "category": "Nightclub", "image_url": IMG, "rating": 4.5, "price_range": "$$$",
           "description": "TEST_ venue", "min_level": "bronze"}
    DB.venues.insert_one(dict(ven))
    st["venues"].append(ven["id"])
    staff_u = _reg(st, "TEST_ Dana Door")
    vip_u, norm_u = _reg(st, "TEST_ Vera Vip"), _reg(st, "TEST_ Norm Guest")
    login = requests.post(f"{API}/auth/login", json={"email": "venue@nocturne.app", "password": "VenuePass123!"}).json()
    hv = {"Authorization": f"Bearer {login['access_token']}"}
    r = requests.post(f"{API}/host/staff", json={"venue_id": ven["id"], "email": staff_u["user"]["email"]}, headers=hv).json()
    st["staff"].append(r["id"])
    ev = _ev(st, owner, ven, "TEST_ Iter23 Tonight", now + timedelta(hours=4))
    st["tonight"] = ev["id"]
    st["t_vip"] = _tk(st, ev, vip_u["user"]["id"], 2, now - timedelta(minutes=20), checked=True)
    st["t_norm"] = _tk(st, ev, norm_u["user"]["id"], 1, now - timedelta(minutes=10), checked=True)
    DB.venue_vips.update_one({"venue_id": ven["id"], "user_id": vip_u["user"]["id"]},
                             {"$set": {"note": "Birthday", "active": True, "flagged_by": owner, "updated_at": now}}, upsert=True)
    # past deals for the leaderboard
    w = [f"TEST_w{i}" for i in range(4)]
    for pct, users, buyers in ((20, w, w[:1]), (30, w[:2], w[:2])):
        sent = now - timedelta(days=3)
        pe = _ev(st, owner, ven, f"TEST_ Iter23 Deal {pct}", now - timedelta(days=2),
                 deal={"pct": pct, "user_ids": users, "sent_at": sent, "expires_at": sent + timedelta(hours=2)})
        for b in buyers:
            _tk(st, pe, b, 2, sent + timedelta(minutes=15), paid=60.0)
    st["staff_token"] = staff_u["access_token"]
    st["owner_token"] = login["access_token"]
    json.dump(st, open(STATE, "w"))
    print(json.dumps(st))


def clean():
    st = json.load(open(STATE))
    DB.door_staff.update_many({"id": {"$in": st["staff"]}}, {"$set": {"active": False}})
    DB.door_staff.delete_many({"id": {"$in": st["staff"]}})
    DB.venue_vips.delete_many({"venue_id": {"$in": st["venues"]}})
    DB.tickets.delete_many({"id": {"$in": st["tickets"]}})
    DB.events.delete_many({"id": {"$in": st["events"]}})
    DB.venues.delete_many({"id": {"$in": st["venues"]}})
    DB.users.delete_many({"id": {"$in": st["users"]}})
    print("cleaned")


if __name__ == "__main__":
    {"seed": seed, "clean": clean}[sys.argv[1]]()
