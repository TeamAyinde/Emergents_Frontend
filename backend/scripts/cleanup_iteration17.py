"""Iteration 17: removes the records left by T1's interrupted pytest run (2026-11-15 02:54), by exact id only."""
import os

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

BOOKINGS = ["512856ef-79dc-44cf-860e-bbc68f9e97a3"]
TICKETS = ["3f0593c6-d446-4bf7-ac58-626b27e7c0bb", "320a93e9-2f2f-497a-86f1-9ee221d95c56", "dec19f5c-813b-4dcb-b339-8cb914a7063c"]

for t in DB.tickets.find({"id": {"$in": TICKETS}}):
    DB.events.update_one({"id": t["event_id"]}, {"$inc": {"tickets_sold": -t["quantity"]}})
    DB.tickets.delete_one({"id": t["id"]})
    print("deleted ticket", t["id"])
print("bookings deleted", DB.table_bookings.delete_many({"id": {"$in": BOOKINGS}}).deleted_count)
DB.venue_payables.delete_many({"record_id": {"$in": BOOKINGS + TICKETS}})

# TEST_ users created by the interrupted run (ids captured from scripts/inspect_iter17_users.py, 02:53-02:54 window)
IDS_FILE = "/tmp/iter17_ids.txt"
if os.path.exists(IDS_FILE):
    uids = [x.strip() for x in open(IDS_FILE) if x.strip()]
    for t in DB.tickets.find({"user_id": {"$in": uids}}):
        DB.events.update_one({"id": t["event_id"]}, {"$inc": {"tickets_sold": -t["quantity"]}})
        DB.tickets.delete_one({"id": t["id"]})
    recs = [b["id"] for b in DB.table_bookings.find({"user_id": {"$in": uids}}, {"id": 1})] + \
           [r["id"] for r in DB.reservations.find({"user_id": {"$in": uids}}, {"id": 1})]
    DB.venue_payables.delete_many({"record_id": {"$in": recs}})
    for coll in ("table_bookings", "reservations", "event_requests", "payment_transactions", "points_ledger", "gifts"):
        print(coll, DB[coll].delete_many({"user_id": {"$in": uids}}).deleted_count)
    DB.concierge_messages.delete_many({"member_id": {"$in": uids}})
    DB.concierge_threads.delete_many({"member_id": {"$in": uids}})
    print("users", DB.users.delete_many({"id": {"$in": uids}, "email": {"$regex": "^test_", "$options": "i"}}).deleted_count)
