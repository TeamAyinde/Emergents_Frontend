"""Cleanup of iteration-6 test data created by seeded test users since SINCE (ids listed, then deleted), plus
points_ledger / perk_claims of seeded users and reset of seeded user balances (points, credit, wallet, level)."""
import os
from datetime import datetime

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
SINCE = datetime(2026, 11, 14, 8, 35)
emails = ["guest@nocturne.app", "promoter@nocturne.app", "venue@nocturne.app", "admin@nocturne.app"]
uids = [u["id"] for u in db.users.find({"email": {"$in": emails}}, {"id": 1})]
ui_events = [e["id"] for e in db.events.find({"title": {"$regex": "^TEST_"}, "created_by": {"$in": uids}, "created_at": {"$gte": SINCE}}, {"id": 1})]
tix = list(db.tickets.find({"user_id": {"$in": uids}, "created_at": {"$gte": SINCE}}, {"_id": 0, "id": 1, "event_id": 1, "quantity": 1}))
for t in tix:
    db.events.update_one({"id": t["event_id"]}, {"$inc": {"tickets_sold": -t["quantity"]}})
print("tickets", db.tickets.delete_many({"id": {"$in": [t["id"] for t in tix]}}).deleted_count)
bk = [b["id"] for b in db.table_bookings.find({"user_id": {"$in": uids}, "created_at": {"$gte": SINCE}}, {"id": 1})]
print("bookings", db.table_bookings.delete_many({"id": {"$in": bk}}).deleted_count)
rq = [r["id"] for r in db.event_requests.find({"user_id": {"$in": uids}, "created_at": {"$gte": SINCE}}, {"id": 1})]
print("requests", db.event_requests.delete_many({"id": {"$in": rq}}).deleted_count)
led = [r["id"] for r in db.points_ledger.find({"user_id": {"$in": uids}}, {"id": 1})]
print("ledger", db.points_ledger.delete_many({"id": {"$in": led}}).deleted_count)
pc = [r["id"] for r in db.perk_claims.find({"user_id": {"$in": uids}}, {"id": 1})]
print("perk_claims", db.perk_claims.delete_many({"id": {"$in": pc}}).deleted_count)
print("events", db.events.delete_many({"id": {"$in": ui_events}}).deleted_count)
db.users.update_many({"email": {"$in": emails}}, {"$set": {"level": "bronze", "wallet_balance": 0, "points": 0, "credit_balance": 0}})
db.events.update_many({"title": "Rooftop Reverie"}, {"$set": {"capacity": 2}})
