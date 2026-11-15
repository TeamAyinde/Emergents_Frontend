"""Iteration 17: inspects leftover table bookings / tickets on seeded events used by test_nocturne_features."""
import os
import sys

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

for title in ("Velvet Sessions w/ DJ Nyx", "Rooftop Reverie", "Industry Fridays"):
    for ev in DB.events.find({"title": title}, {"_id": 0, "id": 1, "capacity": 1, "tickets_sold": 1, "venue_id": 1}):
        print("EVENT", title, ev)
        for b in DB.table_bookings.find({"event_id": ev["id"]}, {"_id": 0, "id": 1, "table_id": 1, "user_id": 1, "status": 1, "created_at": 1}):
            u = DB.users.find_one({"id": b["user_id"]}, {"_id": 0, "email": 1})
            print("  BOOKING", b, u)
        for t in DB.tickets.find({"event_id": ev["id"]}, {"_id": 0, "id": 1, "quantity": 1, "user_id": 1, "created_at": 1}):
            u = DB.users.find_one({"id": t["user_id"]}, {"_id": 0, "email": 1})
            print("  TICKET", t, u)
        for r in DB.event_requests.find({"event_id": ev["id"]}, {"_id": 0, "id": 1, "status": 1, "user_id": 1, "kind": 1}):
            u = DB.users.find_one({"id": r["user_id"]}, {"_id": 0, "email": 1})
            print("  REQUEST", r, u)
if len(sys.argv) > 1:
    print("TEST users:", DB.users.count_documents({"email": {"$regex": "^test_", "$options": "i"}}))
