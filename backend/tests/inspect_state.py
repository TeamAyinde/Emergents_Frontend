"""Quick read-only DB state inspection for feature tests."""
import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
for e in db.events.find({}, {"_id": 0, "title": 1, "min_level": 1, "capacity": 1, "tickets_sold": 1, "approval_required": 1,
                             "guest_list_visible": 1, "venue_name": 1, "date": 1, "plus_one_limit": 1, "tables": 1}):
    print(e["title"], "|", e["venue_name"], "|", e.get("min_level"), "| cap", e.get("capacity"), "sold", e.get("tickets_sold"),
          "| appr", e.get("approval_required"), "| vis", e.get("guest_list_visible"), "| +1", e.get("plus_one_limit"),
          "| tables", len(e.get("tables", [])), "|", e["date"])
for u in db.users.find({"email": {"$regex": "@nocturne.app$"}}, {"_id": 0, "email": 1, "role": 1, "level": 1, "wallet_balance": 1}):
    print(u)
print("counts", {c: db[c].count_documents({}) for c in ["tickets", "table_bookings", "event_requests", "concierge_messages", "concierge_threads", "venues"]})
