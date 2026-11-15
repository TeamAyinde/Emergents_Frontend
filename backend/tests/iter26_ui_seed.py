"""Iteration 26 UI seed: registers TEST_ users for UI delete/export tests. `python iter26_ui_seed.py` -> JSON; `clean <ids...>` removes them."""
import json
import os
import sys
import uuid

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def reg(role):
    email = f"test_i26ui_{uuid.uuid4().hex[:8]}@nocturne.app"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "TestPass123!", "role": role,
                                                     "full_name": "TEST_ I26 UI", "membership_tier": "member"})
    r.raise_for_status()
    return {"email": email, "id": r.json()["user"]["id"]}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "clean":
        ids = sys.argv[2:]
        DB.venues.delete_many({"owner_id": {"$in": ids}, "id": {"$regex": "^TEST_"}})
        DB.support_reports.delete_many({"user_id": {"$in": ids}})
        DB.deleted_accounts.delete_many({"user_id": {"$in": ids}})
        print(DB.users.delete_many({"id": {"$in": ids}}).deleted_count)
    else:
        g, v = reg("guest"), reg("venue_owner")
        real = DB.venues.find_one({"id": {"$not": {"$regex": "^TEST_"}}}, {"_id": 0})  # valid VenueOut shape
        DB.venues.insert_one({**real, "id": f"TEST_venue_{uuid.uuid4().hex[:6]}", "owner_id": v["id"], "name": "TEST_ UI venue", "rating": 0})
        print(json.dumps({"guest": g, "venue": v}))
