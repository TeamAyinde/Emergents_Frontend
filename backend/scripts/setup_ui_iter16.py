"""UI seed for iteration 16: one TEST_ user + past Mirage ticket + feedback (5 stars). Usage: setup | cleanup <uid>"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
EV = "fc35bae2-2ac8-421e-892b-dd59914d088d"

if sys.argv[1] == "setup":
    r = requests.post(f"{API}/auth/register", json={"email": f"test_{uuid.uuid4().hex[:8]}@nocturne.app", "password": "TestPass123!",
                                                  "full_name": "TEST_Uirater Smith", "role": "guest", "membership_tier": "member"})
    d = r.json()
    tid = f"TEST_{uuid.uuid4().hex}"
    DB.tickets.insert_one({"id": tid, "event_id": EV, "event_title": "Velvet Sessions w/ DJ Nyx", "venue_name": "Mirage Lounge",
                           "event_date": datetime.now(timezone.utc) - timedelta(days=1), "user_id": d["user"]["id"], "quantity": 1,
                           "total_paid": 0.0, "checked_in": False, "created_at": datetime.now(timezone.utc)})
    f = requests.post(f"{API}/feedback/{tid}", json={"rating": 5, "comment": "TEST_ amazing sound"},
                      headers={"Authorization": f"Bearer {d['access_token']}"})
    print(d["user"]["id"], tid, f.status_code)
else:
    uid = sys.argv[2]
    tids = [t["id"] for t in DB.tickets.find({"user_id": uid})]
    DB.feedback.delete_many({"ticket_id": {"$in": tids}})
    DB.tickets.delete_many({"user_id": uid})
    DB.points_ledger.delete_many({"user_id": uid})
    DB.users.delete_one({"id": uid, "email": {"$regex": "^test_"}})
    print("cleaned", uid, len(tids))
