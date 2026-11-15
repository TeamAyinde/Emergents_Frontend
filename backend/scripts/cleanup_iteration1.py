"""One-off cleanup of data created by iteration_1 test run (by exact ids, created in the last 10 min)."""
import asyncio
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
since = datetime.now(timezone.utc) - timedelta(minutes=10)


async def main():
    guest = await db.users.find_one({"email": "guest@nocturne.app"})
    venue = await db.users.find_one({"email": "venue@nocturne.app"})
    users = [u["id"] async for u in db.users.find({"email": {"$regex": "^test_(guest|promoter|venue_owner|tier|ui)_[0-9a-f]{6}@example.com$"}, "created_at": {"$gte": since}})]
    events = [e["id"] async for e in db.events.find({"title": "TEST_Event", "created_by": venue["id"], "created_at": {"$gte": since}})]
    tickets = [t async for t in db.tickets.find({"user_id": guest["id"], "created_at": {"$gte": since}})]
    res = [r["id"] async for r in db.reservations.find({"user_id": guest["id"], "created_at": {"$gte": since}})]
    print("users", len(users), "events", len(events), "tickets", len(tickets), "reservations", len(res))
    for t in tickets:
        await db.events.update_one({"id": t["event_id"]}, {"$inc": {"tickets_sold": -t["quantity"]}})
    await db.tickets.delete_many({"id": {"$in": [t["id"] for t in tickets]}})
    await db.reservations.delete_many({"id": {"$in": res}})
    await db.events.delete_many({"id": {"$in": events}})
    await db.users.delete_many({"id": {"$in": users}})
    print("cleanup done")


asyncio.run(main())
