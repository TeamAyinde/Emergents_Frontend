"""Host live door dashboard and last-minute deals for waitlisted guests."""
from datetime import datetime, timedelta, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routes.features import _aware, _own_event, HostDep
from routes.push import notify
from routes.staff import is_door_staff
from server import current_user, db

router = APIRouter(prefix="/api")
UserDep = Annotated[dict, Depends(current_user)]
DEAL_PCTS = (10, 20, 30, 50)
DEAL_HOURS = (1, 2, 4, 8)


class HourCount(BaseModel):
    hour: datetime
    count: int


class Arrival(BaseModel):
    name: str
    quantity: int
    at: datetime
    vip: bool = False


class DealOut(BaseModel):
    pct: int
    sent_to: int
    sent_at: datetime
    expires_at: Optional[datetime] = None
    expired: bool = False
    buyers: int = 0  # waitlisted guests who bought while the deal ran
    tickets: int = 0
    revenue: float = 0.0


class GuestHit(BaseModel):
    ticket_id: str
    name: str
    email: str
    quantity: int
    checked_in: bool
    checked_in_at: Optional[datetime] = None
    vip: bool = False
    vip_note: Optional[str] = None
    user_id: Optional[str] = None  # owners/admins only (to flag VIPs)


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
    is_staff_view: bool = False


async def _deal(ev: dict) -> Optional[DealOut]:
    d = ev.get("deal")
    if not d:
        return None
    exp = d.get("expires_at")
    window = {"$gte": d["sent_at"], **({"$lte": exp} if exp else {})}
    rows = await db.tickets.aggregate([
        {"$match": {"event_id": ev.get("id"), "user_id": {"$in": d.get("user_ids", [])}, "created_at": window}},
        {"$group": {"_id": "$user_id", "q": {"$sum": "$quantity"},
                    "r": {"$sum": {"$add": [{"$ifNull": ["$total_paid", 0]}, {"$ifNull": ["$credit_used", 0]}]}}}},
    ]).to_list(None) if ev.get("id") else []
    return DealOut(pct=d["pct"], sent_to=len(d.get("user_ids", [])), sent_at=d["sent_at"], expires_at=exp,
                   expired=bool(exp) and _aware(exp) <= datetime.now(timezone.utc),
                   buyers=len(rows), tickets=sum(r["q"] for r in rows), revenue=round(sum(r["r"] for r in rows), 2))


async def _live_access(eid: str, user: dict) -> tuple[dict, bool]:
    """(event, staff_only) — owners/admins get everything, door staff get the counter only."""
    if user["role"] in ("venue_owner", "admin"):
        try:
            return await _own_event(eid, user), False
        except HTTPException as e:
            if e.status_code != 403:
                raise
    ev = await db.events.find_one({"id": eid}, {"_id": 0})
    if not ev:
        raise HTTPException(404, "Event not found")
    if not await is_door_staff(ev.get("venue_id"), user["id"], eid):
        raise HTTPException(403, "Not your event or not your shift")
    return ev, True


@router.get("/host/events/{eid}/live", response_model=LiveOut)
async def live(eid: str, user: UserDep):
    ev, staff_only = await _live_access(eid, user)
    hours = await db.tickets.aggregate([
        {"$match": {"event_id": eid, "checked_in": True, "checked_in_at": {"$ne": None}}},
        {"$group": {"_id": {"$dateTrunc": {"date": "$checked_in_at", "unit": "hour"}}, "n": {"$sum": "$quantity"}}},
        {"$sort": {"_id": 1}},
    ]).to_list(48)
    from routes.venueops import vip_ids  # noqa: E402

    recent = []
    last = await db.tickets.find({"event_id": eid, "checked_in": True}, {"_id": 0}).sort("checked_in_at", -1).limit(8).to_list(8)
    vips = await vip_ids(ev.get("venue_id"), [t["user_id"] for t in last])
    for t in last:
        u = await db.users.find_one({"id": t["user_id"]}, {"_id": 0, "full_name": 1})
        name = (u or {}).get("full_name") or "Guest"
        parts = name.split()
        recent.append(Arrival(name=parts[0] + (f" {parts[1][0]}." if len(parts) > 1 else ""), quantity=t["quantity"],
                              at=t.get("checked_in_at") or t["created_at"], vip=t["user_id"] in vips))
    total = sum(h["n"] for h in hours)
    if not hours:  # older check-ins without a timestamp
        agg = await db.tickets.aggregate([{"$match": {"event_id": eid, "checked_in": True}},
                                          {"$group": {"_id": None, "n": {"$sum": "$quantity"}}}]).to_list(1)
        total = agg[0]["n"] if agg else 0
    return LiveOut(
        event_id=eid, title=ev["title"], date=ev["date"], capacity=ev.get("capacity") or 200,
        tickets_sold=ev.get("tickets_sold", 0), checked_in=total,
        waitlist=await db.event_requests.count_documents({"event_id": eid, "kind": "waitlist", "status": "pending"}),
        by_hour=[HourCount(hour=h["_id"], count=h["n"]) for h in hours], recent=recent,
        deal=None if staff_only else await _deal(ev), is_staff_view=staff_only,
    )


class DealIn(BaseModel):
    pct: int
    hours: int = 2


@router.post("/host/events/{eid}/deal", response_model=DealOut)
async def send_deal(eid: str, body: DealIn, user: HostDep):
    if body.pct not in DEAL_PCTS:
        raise HTTPException(400, "Pick 10, 20, 30 or 50% off")
    if body.hours not in DEAL_HOURS:
        raise HTTPException(400, "Pick 1, 2, 4 or 8 hours")
    ev = await _own_event(eid, user)
    now = datetime.now(timezone.utc)
    if _aware(ev["date"]) < now:
        raise HTTPException(400, "This event has already happened")
    if ev.get("tickets_sold", 0) >= ev.get("capacity", 10**6):
        raise HTTPException(400, "The event is full — raise capacity or approve from the waitlist")
    reqs = await db.event_requests.find({"event_id": eid, "kind": "waitlist", "status": "pending"}, {"user_id": 1, "quantity": 1}).to_list(500)
    if not reqs:
        raise HTTPException(400, "Nobody is on the waitlist")
    ids = [r["user_id"] for r in reqs]
    expires = min(now + timedelta(hours=body.hours), _aware(ev["date"]))
    deal = {"pct": body.pct, "user_ids": ids, "user_qty": {r["user_id"]: r.get("quantity", 1) for r in reqs},
            "sent_at": now, "expires_at": expires, "by": user["id"]}
    res = await db.events.update_one({"id": eid, "deal": {"$exists": False}}, {"$set": {"deal": deal}})
    if not res.modified_count:
        raise HTTPException(409, "A deal was already sent for this event")
    left = round((expires - now).total_seconds() / 3600, 1)
    notify(ids, f"{body.pct}% off {ev['title']} ⚡",
           f"A spot just opened and the price dropped — just for you, for the next {left:g} hour{'s' if left != 1 else ''}. Tap to grab it.",
           f"/event/{eid}", key=f"deal-{eid}", kind="updates")
    return await _deal({"deal": deal})


@router.get("/events/{eid}/my-deal")
async def my_deal(eid: str, user: UserDep):
    ev = await db.events.find_one({"id": eid}, {"_id": 0, "deal": 1})
    d = (ev or {}).get("deal") or {}
    exp = d.get("expires_at")
    live_ = user["id"] in d.get("user_ids", []) and not (exp and _aware(exp) <= datetime.now(timezone.utc))
    if not live_:
        return {"pct": 0, "qty": 0, "expires_at": None}
    return {"pct": d["pct"], "qty": (d.get("user_qty") or {}).get(user["id"], 1), "expires_at": exp}


@router.get("/host/events/{eid}/guests", response_model=List[GuestHit])
async def search_guests(eid: str, user: UserDep, q: str = ""):
    """Door lookup by guest name or email when a ticket won't scan (owners, admins, door staff)."""
    _, staff_only = await _live_access(eid, user)
    q = q.strip().lower()
    if len(q) < 2:
        return []
    from routes.venueops import vip_ids  # noqa: E402

    ev = await db.events.find_one({"id": eid}, {"_id": 0, "venue_id": 1})
    tickets = await db.tickets.find({"event_id": eid}, {"_id": 0}).to_list(None)
    vips = await vip_ids((ev or {}).get("venue_id"), list({t["user_id"] for t in tickets}))
    users = {u["id"]: u async for u in db.users.find({"id": {"$in": list({t["user_id"] for t in tickets})}},
                                                     {"_id": 0, "id": 1, "full_name": 1, "email": 1})}
    out = []
    for t in tickets:
        u = users.get(t["user_id"], {})
        name, email = u.get("full_name") or "Guest", u.get("email", "")
        if q not in name.lower() and q not in email.lower():
            continue
        if staff_only and "@" in email:  # door staff see enough to confirm identity, not the full address
            local, domain = email.split("@", 1)
            email = f"{local[:2]}•••@{domain}"
        out.append(GuestHit(ticket_id=t["id"], name=name, email=email, quantity=t["quantity"],
                            checked_in=bool(t.get("checked_in")), checked_in_at=t.get("checked_in_at"),
                            vip=t["user_id"] in vips, vip_note=vips.get(t["user_id"]),
                            user_id=None if staff_only else t["user_id"]))
        if len(out) >= 25:
            break
    return sorted(out, key=lambda g: (g.checked_in, not g.vip, g.name.lower()))


class NightTotals(BaseModel):
    sold: int
    arrived: int
    no_shows: int
    tables: int
    revenue: float
    show_rate: Optional[float] = None


class SummaryOut(BaseModel):
    event_id: str
    title: str
    date: datetime
    night: NightTotals
    peak: Optional[str] = None
    baseline: Optional[NightTotals] = None  # average of the venue's previous 4 events
    compared: int = 0
    change: dict = {}  # metric -> % change vs baseline


@router.get("/host/events/{eid}/summary", response_model=SummaryOut)
async def event_summary(eid: str, user: HostDep):
    from routes.alerts import night_report  # noqa: E402

    ev = await _own_event(eid, user)
    return SummaryOut(**await night_report(ev))
