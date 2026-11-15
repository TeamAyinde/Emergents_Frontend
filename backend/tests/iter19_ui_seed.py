"""Seeds/cleans TEST_ data for iteration-19 table-upsell UI check. Usage: python iter19_ui_seed.py seed|clean"""
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
STATE = "/tmp/iter19_ui_seed.json"
TABLES = [{"id": "T1", "name": "T1", "section": "Main", "capacity": 6, "min_spend": 300.0, "x": 20, "y": 40, "min_level": "bronze"},
          {"id": "T2", "name": "T2", "section": "Main", "capacity": 6, "min_spend": 500.0, "x": 60, "y": 40, "min_level": "bronze"},
          {"id": "V1", "name": "V1", "section": "VIP", "capacity": 8, "min_spend": 900.0, "x": 50, "y": 80, "min_level": "gold"}]


def seed():
    now = datetime.now(timezone.utc)
    g = DB.users.find_one({"email": "guest@nocturne.app"}, {"_id": 0})
    v = DB.venues.find_one({"name": "Club Noire"}, {"_id": 0}) or {}
    st = {"events": [], "tickets": [], "bookings": []}

    def ev(hours, title, tables):
        d = {"id": str(uuid.uuid4()), "title": title, "venue_id": v.get("id"), "venue_name": v.get("name", "TEST_"),
             "city": "Los Angeles", "date": now + timedelta(hours=hours), "price": 0, "tags": [], "tickets_sold": 1,
             "created_at": now, "min_level": "bronze", "approval_required": False, "capacity": 100,
             "guest_list_visible": True, "has_tables": bool(tables), "plus_one_limit": 3, "tables": tables,
             "image_url": "https://images.unsplash.com/photo-1545128485-c400e7702796?w=1400&q=80", "description": "TEST_"}
        DB.events.insert_one(dict(d))
        st["events"].append(d["id"])
        t = {"id": str(uuid.uuid4()), "event_id": d["id"], "event_title": title, "event_date": d["date"],
             "venue_name": d["venue_name"], "user_id": g["id"], "promoter_id": None, "quantity": 1, "total_paid": 0.0,
             "credit_used": 0.0, "platform_fee": 0.0, "promoter_earning": 0.0, "venue_share": 0.0,
             "checked_in": False, "created_at": now, "table_offer_sent": True, "night_alert_sent": True}
        DB.tickets.insert_one(dict(t))
        st["tickets"].append(t["id"])
        return d, t

    _, t_ok = ev(5, "TEST_ Upsell Tonight", TABLES)
    _, t_far = ev(20, "TEST_ Upsell Tomorrow", TABLES)
    e_bk, t_bk = ev(5, "TEST_ Upsell Booked", TABLES)
    _, t_gold = ev(5, "TEST_ Upsell GoldOnly", [TABLES[2]])
    b = {"id": str(uuid.uuid4()), "event_id": e_bk["id"], "event_title": e_bk["title"], "event_date": e_bk["date"],
         "table_id": "T1", "table_name": "T1", "section": "Main", "user_id": g["id"], "user_name": g["full_name"],
         "party_size": 2, "min_spend": 300.0, "venue_name": e_bk["venue_name"], "platform_fee": 0.0, "total": 300.0, "status": "confirmed", "created_at": now}
    DB.table_bookings.insert_one(dict(b))
    st["bookings"].append(b["id"])
    st.update(ok=t_ok["id"], far=t_far["id"], booked=t_bk["id"], gold=t_gold["id"], ok_event=t_ok["event_id"])
    json.dump(st, open(STATE, "w"))
    print(json.dumps(st))


def clean():
    st = json.load(open(STATE))
    print(DB.tickets.delete_many({"id": {"$in": st["tickets"]}}).deleted_count,
          DB.table_bookings.delete_many({"id": {"$in": st["bookings"]}}).deleted_count,
          DB.events.delete_many({"id": {"$in": st["events"]}}).deleted_count)


if __name__ == "__main__":
    {"seed": seed, "clean": clean}[sys.argv[1]]()
