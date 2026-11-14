"""One-off check: does a credit-covered direct ticket purchase create a venue_payables row? Cleans up after itself."""
import os
import uuid

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

r = requests.post(f"{API}/auth/register", json={"email": f"test_{uuid.uuid4().hex[:8]}@nocturne.app", "password": "TestPass123!",
                                                 "full_name": "TEST_ Payables", "membership_tier": "member", "marketing_opt_in": False}).json()
tok, uid = r["access_token"], r["user"]["id"]
DB.users.update_one({"id": uid}, {"$set": {"credit_balance": 500.0}})
ev = next(e for e in requests.get(f"{API}/events").json() if e["title"] == "Velvet Sessions w/ DJ Nyx")
p = requests.post(f"{API}/tickets/purchase", json={"event_id": ev["id"], "quantity": 1}, headers={"Authorization": f"Bearer {tok}"})
print("direct purchase", p.status_code)
tid = p.json().get("id")
print("venue_payables row for credit-covered direct ticket:", DB.venue_payables.find_one({"record_id": tid}, {"_id": 0}))
# cleanup
if tid:
    DB.tickets.delete_one({"id": tid})
    DB.events.update_one({"id": ev["id"]}, {"$inc": {"tickets_sold": -1}})
DB.points_ledger.delete_many({"user_id": uid})
DB.users.delete_one({"id": uid})
