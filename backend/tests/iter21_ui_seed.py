"""Seeds/cleans TEST_ data for iteration-21 UI checks (deal timer chips, deal banner qty limit, door staff, door duty, night-summary pref).
Usage: python iter21_ui_seed.py seed|clean. Everything is removed by id; door_staff rows created during the UI run are deactivated+deleted."""
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
STATE = "/tmp/iter21_ui_seed.json"


def seed():
    now = datetime.now(timezone.utc)
    owner = DB.users.find_one({"email": "venue@nocturne.app"}, {"_id": 0, "id": 1})
    guest = DB.users.find_one({"email": "guest@nocturne.app"}, {"_id": 0, "id": 1, "full_name": 1})
    ven = DB.venues.find_one({"owner_id": owner["id"]}, {"_id": 0, "id": 1, "name": 1}, sort=[("name", 1)])
    r = requests.post(f"{API}/auth/register", json={
        "email": f"test_ui21_{uuid.uuid4().hex[:6]}@nocturne.app", "password": "TestPass123!", "role": "guest",
        "full_name": "TEST_ Tina Ticket", "membership_tier": "member", "marketing_opt_in": False}).json()
    tu = r["user"]["id"]
    eid = str(uuid.uuid4())
    DB.events.insert_one({"id": eid, "title": "TEST_ Door Night", "venue_id": ven["id"], "venue_name": ven["name"], "city": "Los Angeles",
                          "date": now + timedelta(hours=5), "price": 40.0, "tags": ["TEST"], "tickets_sold": 4, "created_at": now,
                          "min_level": "bronze", "approval_required": False, "capacity": 10, "plus_one_limit": 5, "tables": [],
                          "created_by": owner["id"], "image_url": "https://images.unsplash.com/photo-1545128485-c400e7702796?w=1400&q=80",
                          "description": "TEST_ event"})
    rid = str(uuid.uuid4())
    DB.event_requests.insert_one({"id": rid, "event_id": eid, "event_title": "TEST_ Door Night", "user_id": guest["id"],
                                  "user_name": guest.get("full_name", "Guest"), "user_level": "gold", "quantity": 2, "kind": "waitlist",
                                  "status": "pending", "note": "", "promoter_code": None, "created_at": now})
    tid = str(uuid.uuid4())
    DB.tickets.insert_one({"id": tid, "event_id": eid, "event_title": "TEST_ Door Night", "event_date": now + timedelta(hours=5),
                           "venue_name": ven["name"], "user_id": tu, "promoter_id": None, "quantity": 2, "total_paid": 0.0,
                           "credit_used": 0.0, "platform_fee": 0.0, "promoter_earning": 0.0, "venue_share": 0.0,
                           "checked_in": False, "created_at": now})
    st = {"start": now.isoformat(), "users": [tu], "events": [eid], "requests": [rid], "tickets": [tid], "guest": guest["id"],
          "venue": ven}
    json.dump(st, open(STATE, "w"))
    print(json.dumps(st))


def clean():
    st = json.load(open(STATE))
    start = datetime.fromisoformat(st["start"]).replace(tzinfo=None)
    rows = [s["id"] for s in DB.door_staff.find({"user_id": st["guest"], "created_at": {"$gte": start}}, {"id": 1})]
    DB.door_staff.update_many({"id": {"$in": rows}}, {"$set": {"active": False}})
    DB.door_staff.delete_many({"id": {"$in": rows}})
    tix = st["tickets"] + [t["id"] for t in DB.tickets.find({"event_id": {"$in": st["events"]}}, {"id": 1})]
    DB.tickets.delete_many({"id": {"$in": tix}})
    DB.venue_payables.delete_many({"record_id": {"$in": tix}})
    DB.event_requests.delete_many({"$or": [{"id": {"$in": st["requests"]}}, {"event_id": {"$in": st["events"]}}]})
    DB.events.delete_many({"id": {"$in": st["events"]}})
    DB.users.delete_many({"id": {"$in": st["users"]}})
    print("cleaned", rows)


if __name__ == "__main__":
    {"seed": seed, "clean": clean}[sys.argv[1]]()
