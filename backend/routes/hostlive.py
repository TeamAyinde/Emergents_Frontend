"""Host live door dashboard and last-minute deals for waitlisted guests."""
from datetime import datetime, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routes.features import _aware, _own_event, HostDep
from routes.push import notify
from server import current_user, db

router = APIRouter(prefix="/api")
UserDep = Annotated[dict, Depends(current_user)]
DEAL_PCTS = (10, 20, 30, 50)


class HourCount(BaseModel):
    hour: datetime
    count: int


class Arrival(BaseModel):
    name: str
    quantity: int
    at: datetime


class DealOut(BaseModel):
    pct: int
    sent_to: int
    sent_at: datetime


class LiveOut(BaseModel):
    event_id: str
    title: str
    date: datetime
    capacity: int
    tickets_sold: int
    checked_in: int
    waitlist: int
    by_hour: List[HourCount]
    recent: List[Arrival]
    deal: Optional[DealOut] = None


def _deal(ev: dict) -> Optional[DealOut]:
    d = ev.get("deal")
    return DealOut(pct=d["pct"], sent_to=len(d.get("user_ids", [])), sent_at=d["sent_at"]) if d else None


@router.get("/host/events/{eid}/live", response_model=LiveOut)
async def live(eid: str, user: HostDep):
    ev = await _own_event(eid, user)
    hours = await db.tickets.aggregate([
        {"$match": {"event_id": eid, "checked_in": True, "checked_in_at": {"$ne": None}}},
        {"$group": {"_id": {"$dateTrunc": {"date": "$checked_in_at", "unit": "hour"}}, "n": {"$sum": "$quantity"}}},
        {"$sort": {"_id": 1}},
    ]).to_list(48)
    recent = []
    async for t in db.tickets.find({"event_id": eid, "checked_in": True}, {"_id": 0}).sort("checked_in_at", -1).limit(8):
        u = await db.users.find_one({"id": t["user_id"]}, {"_id": 0, "full_name": 1})
        name = (u or {}).get("full_name") or "Guest"
        parts = name.split()
        recent.append(Arrival(name=parts[0] + (f" {parts[1][0]}." if len(parts) > 1 else ""), quantity=t["quantity"],
                              at=t.get("checked_in_at") or t["created_at"]))
    total = sum(h["n"] for h in hours)
    if not hours:  # older check-ins without a timestamp
        agg = await db.tickets.aggregate([{"$match": {"event_id": eid, "checked_in": True}},
                                          {"$group": {"_id": None, "n": {"$sum": "$quantity"}}}]).to_list(1)
        total = agg[0]["n"] if agg else 0
    return LiveOut(
        event_id=eid, title=ev["title"], date=ev["date"], capacity=ev.get("capacity") or 200,
        tickets_sold=ev.get("tickets_sold", 0), checked_in=total,
        waitlist=await db.event_requests.count_documents({"event_id": eid, "kind": "waitlist", "status": "pending"}),
        by_hour=[HourCount(hour=h["_id"], count=h["n"]) for h in hours], recent=recent, deal=_deal(ev),
    )


class DealIn(BaseModel):
    pct: int


@router.post("/host/events/{eid}/deal", response_model=DealOut)
async def send_deal(eid: str, body: DealIn, user: HostDep):
    if body.pct not in DEAL_PCTS:
        raise HTTPException(400, "Pick 10, 20, 30 or 50% off")
    ev = await _own_event(eid, user)
    if _aware(ev["date"]) < datetime.now(timezone.utc):
        raise HTTPException(400, "This event has already happened")
    if ev.get("tickets_sold", 0) >= ev.get("capacity", 10**6):
        raise HTTPException(400, "The event is full — raise capacity or approve from the waitlist")
    ids = [r["user_id"] async for r in db.event_requests.find({"event_id": eid, "kind": "waitlist", "status": "pending"}, {"user_id": 1})]
    if not ids:
        raise HTTPException(400, "Nobody is on the waitlist")
    deal = {"pct": body.pct, "user_ids": ids, "sent_at": datetime.now(timezone.utc), "by": user["id"]}
    res = await db.events.update_one({"id": eid, "deal": {"$exists": False}}, {"$set": {"deal": deal}})
    if not res.modified_count:
        raise HTTPException(409, "A deal was already sent for this event")
    notify(ids, f"{body.pct}% off {ev['title']} ⚡", "A spot just opened and the price dropped — just for you. Tap to grab it.",
           f"/event/{eid}", key=f"deal-{eid}", kind="updates")
    return DealOut(pct=body.pct, sent_to=len(ids), sent_at=deal["sent_at"])


@router.get("/events/{eid}/my-deal")
async def my_deal(eid: str, user: UserDep):
    ev = await db.events.find_one({"id": eid}, {"_id": 0, "deal": 1})
    d = (ev or {}).get("deal") or {}
    return {"pct": d.get("pct", 0) if user["id"] in d.get("user_ids", []) else 0}
