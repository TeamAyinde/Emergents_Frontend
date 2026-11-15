"""Seeds/cleans TEST_ data for iteration-22 UI checks (invited staff badge, deal results, guest search, summary trends).
Usage: python iter22_ui_seed.py seed|clean. Everything is removed by id."""
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
STATE = "/tmp/iter22_ui_seed.json"
IMG = "https://images.unsplash.com/photo-1545128485-c400e7702796?w=1400&q=80"


def _ev(st, owner, ven, title, date, **kw):
    eid = str(uuid.uuid4())
    doc = {"id": eid, "title": title, "venue_id": ven["id"], "venue_name": ven["name"], "city": "Los Angeles", "date": date,
           "price": 40.0, "tags": ["TEST"], "tickets_sold": 0, "created_at": date - timedelta(days=3), "min_level": "bronze",
           "approval_required": False, "capacity": 20, "plus_one_limit": 5, "tables": [], "created_by": owner, "image_url": IMG,
           "description": "TEST_ event", "summary_sent": True}
    doc.update(kw)
    DB.events.insert_one(doc)
    st["events"].append(eid)
    return doc


def _tk(st, ev, uid, qty, created, paid=0.0, checked_at=None, payable=None):
    tid = str(uuid.uuid4())
    DB.tickets.insert_one({"id": tid, "event_id": ev["id"], "event_title": ev["title"], "event_date": ev["date"],
                           "venue_name": ev["venue_name"], "user_id": uid, "promoter_id": None, "quantity": qty, "total_paid": paid,
                           "credit_used": 0.0, "platform_fee": 0.0, "promoter_earning": 0.0, "venue_share": 0.0,
                           "checked_in": bool(checked_at), "checked_in_at": checked_at, "created_at": created})
    st["tickets"].append(tid)
    if payable:
        pid = str(uuid.uuid4())
        DB.venue_payables.insert_one({"id": pid, "venue_id": ev["venue_id"], "venue_name": "TEST_", "amount": payable, "source": "ticket",
                                      "record_id": tid, "status": "owed", "created_at": created})
        st["payables"].append(pid)
    return tid


def seed():
    now = datetime.now(timezone.utc)
    owner = DB.users.find_one({"email": "venue@nocturne.app"}, {"_id": 0, "id": 1})["id"]
    guest = DB.users.find_one({"email": "guest@nocturne.app"}, {"_id": 0, "id": 1})["id"]
    st = {"users": [], "events": [], "tickets": [], "payables": [], "venues": [], "staff": []}
    ven = {"id": f"TEST_v_{uuid.uuid4().hex[:8]}", "name": "TEST_ Iter22 Lounge", "owner_id": owner, "city": "Los Angeles", "created_at": now,
           "state": "CA", "category": "Nightclub", "image_url": IMG, "rating": 4.5, "price_range": "$$$", "description": "TEST_ venue",
           "min_level": "bronze"}  # full VenueOut fields so GET /host/venues doesn't 500
    DB.venues.insert_one(dict(ven))
    st["venues"].append(ven["id"])
    r = requests.post(f"{API}/auth/register", json={
        "email": f"test_ui22_{uuid.uuid4().hex[:6]}@nocturne.app", "password": "TestPass123!", "role": "guest",
        "full_name": "TEST_ Zara Doorley", "membership_tier": "member", "marketing_opt_in": False}).json()
    zara = r["user"]["id"]
    st["users"].append(zara)
    # invited (pending) door staff row
    sid = str(uuid.uuid4())
    DB.door_staff.insert_one({"id": sid, "venue_id": ven["id"], "venue_name": ven["name"], "user_id": None,
                              "name": "test_ui22_pending@nocturne.app", "email": "test_ui22_pending@nocturne.app", "status": "invited",
                              "created_by": owner, "created_at": now, "active": True})
    st["staff"].append(sid)
    # upcoming event with an active deal + one buyer
    up = _ev(st, owner, ven, "TEST_ Deal Night", now + timedelta(hours=5), tickets_sold=4,
             deal={"pct": 20, "user_ids": [guest], "user_qty": {guest: 2}, "sent_at": now - timedelta(minutes=10),
                   "expires_at": now + timedelta(hours=2), "by": owner})
    _tk(st, up, guest, 2, now - timedelta(minutes=5), paid=64.0)
    st["zara_ticket"] = _tk(st, up, zara, 2, now - timedelta(hours=2))
    # previous nights at the venue (baseline: arrived 4 of 8, $100 each)
    for i in range(2):
        pe = _ev(st, owner, ven, f"TEST_ Prev Night {i}", now - timedelta(days=7 * (i + 1)), tickets_sold=8)
        _tk(st, pe, zara, 4, pe["date"] - timedelta(days=1))
        _tk(st, pe, zara, 4, pe["date"] - timedelta(days=1), checked_at=pe["date"] + timedelta(hours=1), payable=100.0)
    # last night: past event with an expired deal, 5 of 6 in, $150
    past = _ev(st, owner, ven, "TEST_ Last Night", now - timedelta(hours=12), tickets_sold=6,
               deal={"pct": 30, "user_ids": [guest], "user_qty": {guest: 1}, "sent_at": now - timedelta(hours=16),
                     "expires_at": now - timedelta(hours=14), "by": owner})
    _tk(st, past, guest, 1, now - timedelta(hours=15), paid=31.0)
    _tk(st, past, zara, 4, now - timedelta(days=1), checked_at=now - timedelta(hours=11), payable=150.0)
    st.update(up=up["id"], past=past["id"], staff_id=sid, venue=ven["id"])
    json.dump(st, open(STATE, "w"), default=str)
    print(json.dumps({k: st[k] for k in ("up", "past", "staff_id", "zara_ticket")}))


def clean():
    st = json.load(open(STATE))
    DB.door_staff.update_many({"id": {"$in": st["staff"]}}, {"$set": {"active": False}})
    DB.door_staff.delete_many({"id": {"$in": st["staff"]}})
    tix = st["tickets"] + [t["id"] for t in DB.tickets.find({"event_id": {"$in": st["events"]}}, {"id": 1})]
    DB.venue_payables.delete_many({"$or": [{"id": {"$in": st["payables"]}}, {"record_id": {"$in": tix}}]})
    DB.tickets.delete_many({"id": {"$in": tix}})
    DB.event_requests.delete_many({"event_id": {"$in": st["events"]}})
    DB.events.delete_many({"id": {"$in": st["events"]}})
    DB.venues.delete_many({"id": {"$in": st["venues"]}})
    DB.points_ledger.delete_many({"user_id": {"$in": st["users"]}})
    DB.users.delete_many({"id": {"$in": st["users"]}})
    print("cleaned")


if __name__ == "__main__":
    seed() if sys.argv[1] == "seed" else clean()
