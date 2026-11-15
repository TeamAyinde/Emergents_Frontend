"""Seeds/cleans TEST_ data for iteration-24 UI checks (DealCard best-deal tip, Host Studio report download).
Usage: python iter24_ui_seed.py seed [two|one|none] | clean. Everything is removed by id."""
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
STATE = "/tmp/iter24_ui_seed.json"


def _ev(st, owner, ven, title, date, **kw):
    doc = {"id": str(uuid.uuid4()), "title": title, "venue_id": ven["id"], "venue_name": ven["name"], "city": "Los Angeles",
           "date": date, "price": 40.0, "tags": ["TEST"], "tickets_sold": 3, "created_at": date - timedelta(days=3),
           "min_level": "bronze", "approval_required": False, "capacity": 20, "plus_one_limit": 5, "tables": [],
           "created_by": owner, "image_url": "", "description": "TEST_ event", "summary_sent": True}
    doc.update(kw)
    DB.events.insert_one(doc)
    st["events"].append(doc["id"])
    return doc


def _tk(st, ev, uid, qty, created, paid=0.0):
    tid = str(uuid.uuid4())
    DB.tickets.insert_one({"id": tid, "event_id": ev["id"], "event_title": ev["title"], "event_date": ev["date"],
                           "venue_name": ev["venue_name"], "user_id": uid, "promoter_id": None, "quantity": qty, "total_paid": paid,
                           "credit_used": 0.0, "platform_fee": 0.0, "promoter_earning": 0.0, "venue_share": 0.0,
                           "checked_in": False, "checked_in_at": None, "created_at": created})
    st["tickets"].append(tid)


def seed(mode="two"):
    now = datetime.now(timezone.utc)
    owner = DB.users.find_one({"email": "venue@nocturne.app"}, {"_id": 0, "id": 1})["id"]
    st = {"events": [], "tickets": [], "venues": [], "requests": []}
    ven = {"id": f"TEST_v_{uuid.uuid4().hex[:8]}", "name": "TEST_ Iter24 Lounge", "owner_id": owner, "city": "Los Angeles",
           "created_at": now, "state": "CA", "category": "Nightclub", "image_url": "", "rating": 4.5, "price_range": "$$$",
           "description": "TEST_ venue", "min_level": "bronze"}
    DB.venues.insert_one(dict(ven))
    st["venues"].append(ven["id"])
    up = _ev(st, owner, ven, "TEST_ Iter24 Upcoming", now + timedelta(days=2))
    st["upcoming"] = up["id"]
    for i in range(3):
        rid = str(uuid.uuid4())
        DB.event_requests.insert_one({"id": rid, "event_id": up["id"], "event_title": up["title"], "user_id": f"TEST_wl{i}",
                                      "user_name": f"TEST_ WL {i}", "user_level": "bronze", "quantity": 1, "kind": "waitlist",
                                      "status": "pending", "note": "", "promoter_code": None, "created_at": now})
        st["requests"].append(rid)
    w = [f"TEST_w{i}" for i in range(4)]
    levels = {"two": ((20, w, w[:1]), (30, w[:2], w[:2])), "one": ((20, w, w[:1]),), "none": ()}[mode]
    for pct, users, buyers in levels:
        sent = now - timedelta(days=3)
        pe = _ev(st, owner, ven, f"TEST_ Iter24 Deal {pct}", now - timedelta(days=2),
                 deal={"pct": pct, "user_ids": users, "sent_at": sent, "expires_at": sent + timedelta(hours=2)})
        for b in buyers:
            _tk(st, pe, b, 2, sent + timedelta(minutes=15), paid=60.0)
    json.dump(st, open(STATE, "w"))
    print(json.dumps(st))


def clean():
    st = json.load(open(STATE))
    DB.event_requests.delete_many({"id": {"$in": st["requests"]}})
    DB.tickets.delete_many({"id": {"$in": st["tickets"]}})
    DB.events.delete_many({"id": {"$in": st["events"]}})
    DB.venues.delete_many({"id": {"$in": st["venues"]}})
    print("cleaned")


if __name__ == "__main__":
    seed(sys.argv[2] if len(sys.argv) > 2 else "two") if sys.argv[1] == "seed" else clean()
