"""Concierge chat, table map bookings, guest list / approval / waitlist, host studio."""
import uuid
from datetime import datetime, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING

from server import (
    award_points, LEVEL_BOOKING_FEE, TicketOut, VenueOut, amount_due, current_user, db, issue_ticket,
    record_venue_share, require_level, require_roles, ticket_price, user_level,
)

router = APIRouter(prefix="/api")
UserDep = Annotated[dict, Depends(current_user)]
AdminDep = Annotated[dict, Depends(require_roles("admin"))]
HostDep = Annotated[dict, Depends(require_roles("venue_owner", "admin"))]


def _now():
    return datetime.now(timezone.utc)


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# ---------- Concierge chat ----------

class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class MessageOut(BaseModel):
    id: str
    member_id: str
    sender: str  # "member" | "concierge"
    sender_name: str
    text: str
    created_at: datetime


class ThreadOut(BaseModel):
    member_id: str
    member_name: str
    member_level: str
    last_text: str
    last_at: datetime
    unread: int


async def _post(member: dict, sender: str, sender_name: str, text: str) -> MessageOut:
    doc = {
        "id": str(uuid.uuid4()), "member_id": member["id"], "sender": sender,
        "sender_name": sender_name, "text": text.strip(), "created_at": _now(),
        "read_by_concierge": sender == "concierge", "read_by_member": sender == "member",
    }
    await db.concierge_messages.insert_one(doc)
    await db.concierge_threads.update_one(
        {"member_id": member["id"]},
        {"$set": {"member_id": member["id"], "member_name": member["full_name"], "member_level": user_level(member),
                  "last_text": doc["text"], "last_at": doc["created_at"]}},
        upsert=True,
    )
    return MessageOut(**doc)


@router.get("/concierge/messages", response_model=List[MessageOut])
async def my_messages(user: UserDep):
    await db.concierge_messages.update_many({"member_id": user["id"], "sender": "concierge"}, {"$set": {"read_by_member": True}})
    cur = db.concierge_messages.find({"member_id": user["id"]}, {"_id": 0}).sort("created_at", ASCENDING)
    return [MessageOut(**m) async for m in cur]


@router.get("/concierge/unread")
async def my_unread(user: UserDep):
    n = await db.concierge_messages.count_documents({"member_id": user["id"], "sender": "concierge", "read_by_member": False})
    return {"unread": n}


@router.post("/concierge/messages", response_model=MessageOut, status_code=201)
async def send_message(body: MessageIn, user: UserDep):
    if not body.text.strip():
        raise HTTPException(400, "Message is empty")
    first = await db.concierge_messages.count_documents({"member_id": user["id"]}) == 0
    msg = await _post(user, "member", user["full_name"], body.text)
    if first:
        await _post(user, "concierge", "Nocturne Concierge",
                    f"Welcome, {user['full_name'].split()[0]}. Your lifestyle manager has your request and will reply shortly. "
                    "Gold members are answered first.")
    return msg


@router.get("/admin/concierge/threads", response_model=List[ThreadOut])
async def threads(_: AdminDep):
    out = []
    async for t in db.concierge_threads.find({}, {"_id": 0}).sort("last_at", DESCENDING):
        unread = await db.concierge_messages.count_documents({"member_id": t["member_id"], "sender": "member", "read_by_concierge": False})
        out.append(ThreadOut(**t, unread=unread))
    rank = {"gold": 0, "silver": 1, "bronze": 2}
    out.sort(key=lambda t: (t.unread == 0, rank.get(t.member_level, 3)))
    return out


@router.get("/admin/concierge/{member_id}/messages", response_model=List[MessageOut])
async def thread_messages(member_id: str, _: AdminDep):
    await db.concierge_messages.update_many({"member_id": member_id, "sender": "member"}, {"$set": {"read_by_concierge": True}})
    cur = db.concierge_messages.find({"member_id": member_id}, {"_id": 0}).sort("created_at", ASCENDING)
    return [MessageOut(**m) async for m in cur]


@router.post("/admin/concierge/{member_id}/messages", response_model=MessageOut, status_code=201)
async def reply(member_id: str, body: MessageIn, admin: AdminDep):
    member = await db.users.find_one({"id": member_id}, {"_id": 0})
    if not member:
        raise HTTPException(404, "Member not found")
    return await _post(member, "concierge", f"{admin['full_name'].split()[0]} · Concierge", body.text)


# ---------- Table map ----------

class TableOut(BaseModel):
    id: str
    name: str
    section: str
    capacity: int
    min_spend: float
    x: float
    y: float
    min_level: str
    booked: bool


class TableBookIn(BaseModel):
    party_size: int = Field(ge=1, le=30)


class TableBookingOut(BaseModel):
    id: str
    event_id: str
    event_title: str
    event_date: datetime
    venue_name: str
    table_id: str
    section: str
    user_id: str
    user_name: str
    party_size: int
    min_spend: float
    platform_fee: float
    total: float
    status: str
    created_at: datetime


async def _event(eid: str) -> dict:
    ev = await db.events.find_one({"id": eid}, {"_id": 0})
    if not ev:
        raise HTTPException(404, "Event not found")
    return ev


@router.get("/events/{eid}/tables", response_model=List[TableOut])
async def event_tables(eid: str):
    ev = await _event(eid)
    booked = {b["table_id"] async for b in db.table_bookings.find({"event_id": eid, "status": "confirmed"}, {"table_id": 1})}
    return [TableOut(**t, booked=t["id"] in booked) for t in ev.get("tables", [])]


async def quote_table(eid: str, tid: str, party_size: int, user: dict) -> tuple[dict, dict, float]:
    """Validates a table booking; returns (event, table, platform fee)."""
    ev = await _event(eid)
    if _aware(ev["date"]) < _now():
        raise HTTPException(400, "This event has already happened")
    table = next((t for t in ev.get("tables", []) if t["id"] == tid), None)
    if not table:
        raise HTTPException(404, "Table not found")
    require_level(user, table["min_level"])
    if party_size > table["capacity"]:
        raise HTTPException(400, f"This table seats up to {table['capacity']}")
    if await db.table_bookings.find_one({"event_id": eid, "table_id": tid, "status": "confirmed"}, {"_id": 1}):
        raise HTTPException(409, "Someone just booked this table — pick another")
    return ev, table, round(table["min_spend"] * LEVEL_BOOKING_FEE[user_level(user)], 2)


@router.post("/events/{eid}/tables/{tid}/book", response_model=TableBookingOut, status_code=201)
async def book_table(eid: str, tid: str, body: TableBookIn, user: UserDep):
    _, table, fee = await quote_table(eid, tid, body.party_size, user)
    if table["min_spend"] + fee > 0:
        raise HTTPException(402, "Payment required — continue to checkout")
    return await save_table(eid, tid, body.party_size, user)


async def save_table(eid: str, tid: str, party_size: int, user: dict, payment_session: Optional[str] = None) -> TableBookingOut:
    ev, table, fee = await quote_table(eid, tid, party_size, user)
    doc = {
        "id": str(uuid.uuid4()), "event_id": eid, "event_title": ev["title"], "event_date": ev["date"],
        "venue_name": ev["venue_name"], "table_id": tid, "section": table["section"], "user_id": user["id"],
        "user_name": user["full_name"], "party_size": party_size, "min_spend": table["min_spend"],
        "platform_fee": fee, "total": round(table["min_spend"] + fee, 2), "status": "confirmed",
        "payment_session": payment_session, "created_at": _now(),
    }
    try:
        await db.table_bookings.insert_one(doc)
    except Exception:
        raise HTTPException(409, "Someone just booked this table — pick another")
    await record_venue_share(ev.get("venue_id"), table["min_spend"], "table", doc["id"])
    await award_points(user, doc["total"], f"Table {tid} · {ev['title']}")
    doc.pop("_id", None)
    return TableBookingOut(**doc)


@router.get("/table-bookings/mine", response_model=List[TableBookingOut])
async def my_tables(user: UserDep):
    cur = db.table_bookings.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", DESCENDING)
    return [TableBookingOut(**b) async for b in cur]


# ---------- Guest list, approval, waitlist ----------

class JoinIn(BaseModel):
    quantity: int = Field(default=1, ge=1, le=8)
    promoter_code: Optional[str] = None
    note: Optional[str] = Field(default="", max_length=300)


class RequestOut(BaseModel):
    id: str
    event_id: str
    event_title: str
    user_id: str
    user_name: str
    user_level: str
    quantity: int
    kind: str  # approval | waitlist
    status: str  # pending | approved | declined
    note: str
    created_at: datetime


class JoinOut(BaseModel):
    result: str  # ticket | pending | waitlisted
    ticket: Optional[TicketOut] = None
    request: Optional[RequestOut] = None


async def approved_request(eid: str, uid: str) -> Optional[dict]:
    """An approved request the guest still has to pay for (paid events)."""
    return await db.event_requests.find_one({"event_id": eid, "user_id": uid, "status": "approved", "ticket_issued": {"$ne": True}}, {"_id": 0})


@router.post("/events/{eid}/join", response_model=JoinOut)
async def join_event(eid: str, body: JoinIn, user: UserDep):
    ev = await _event(eid)
    if _aware(ev["date"]) < _now():
        raise HTTPException(400, "This event has already happened")
    require_level(user, ev.get("min_level", "bronze"))
    limit = 1 + ev.get("plus_one_limit", 7)
    if body.quantity > limit:
        raise HTTPException(400, f"Max {limit} spots per guest (you + {limit - 1})")
    if await db.tickets.find_one({"event_id": eid, "user_id": user["id"]}, {"_id": 1}):
        raise HTTPException(400, "You're already on the guest list — see your ticket in Profile")
    approved = await approved_request(eid, user["id"])
    if approved or (not ev.get("approval_required")
                    and ev.get("tickets_sold", 0) + body.quantity <= ev.get("capacity", 10**6)):
        qty = approved["quantity"] if approved else body.quantity
        if amount_due(ticket_price(ev, user, qty)[2], user) > 0:
            return JoinOut(result="payment_required")
    sold_out = ev.get("tickets_sold", 0) + body.quantity > ev.get("capacity", 10**6)
    if approved:
        ticket = await issue_ticket(ev, user, approved["quantity"], approved.get("promoter_code"), override=True)
        await db.event_requests.update_one({"id": approved["id"]}, {"$set": {"ticket_issued": True}})
        return JoinOut(result="ticket", ticket=ticket)
    if not ev.get("approval_required") and not sold_out:
        try:
            return JoinOut(result="ticket", ticket=await issue_ticket(ev, user, body.quantity, body.promoter_code))
        except HTTPException as exc:
            if exc.status_code != 409:
                raise
            sold_out = True
    existing = await db.event_requests.find_one({"event_id": eid, "user_id": user["id"], "status": "pending"}, {"_id": 0})
    if existing:
        raise HTTPException(400, "You already have a pending request for this event")
    doc = {
        "id": str(uuid.uuid4()), "event_id": eid, "event_title": ev["title"], "user_id": user["id"],
        "user_name": user["full_name"], "user_level": user_level(user), "quantity": body.quantity,
        "kind": "waitlist" if sold_out else "approval", "status": "pending", "note": body.note or "",
        "promoter_code": (body.promoter_code or "").strip().upper() or None, "created_at": _now(),
    }
    await db.event_requests.insert_one(doc)
    doc.pop("_id", None)
    return JoinOut(result="waitlisted" if sold_out else "pending", request=RequestOut(**doc))


@router.get("/event-requests/mine", response_model=List[RequestOut])
async def my_requests(user: UserDep):
    cur = db.event_requests.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", DESCENDING)
    return [RequestOut(**r) async for r in cur]


class GuestsOut(BaseModel):
    count: int
    visible: bool
    names: List[str]


@router.get("/events/{eid}/guests", response_model=GuestsOut)
async def event_guests(eid: str, _: UserDep):
    ev = await _event(eid)
    count = ev.get("tickets_sold", 0)
    if not ev.get("guest_list_visible", True):
        return GuestsOut(count=count, visible=False, names=[])
    names: List[str] = []
    async for t in db.tickets.find({"event_id": eid}, {"_id": 0, "user_id": 1}).sort("created_at", ASCENDING).limit(40):
        u = await db.users.find_one({"id": t["user_id"]}, {"_id": 0, "full_name": 1})
        if u:
            parts = u["full_name"].split()
            short = parts[0] + (f" {parts[1][0]}." if len(parts) > 1 else "")
            if short not in names:
                names.append(short)
    return GuestsOut(count=count, visible=True, names=names[:12])


# ---------- Host studio ----------

class VenueIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    city: str = Field(min_length=2, max_length=60)
    category: str = Field(min_length=2, max_length=40)
    image_url: str
    description: str = Field(default="", max_length=600)
    price_range: str = "$$$"


async def _own_event(eid: str, user: dict) -> dict:
    ev = await _event(eid)
    if user["role"] != "admin" and ev.get("created_by") != user["id"]:
        venue = await db.venues.find_one({"id": ev["venue_id"]}, {"_id": 0, "owner_id": 1})
        if not venue or venue.get("owner_id") != user["id"]:
            raise HTTPException(403, "Not your event")
    return ev


@router.get("/host/venues", response_model=List[VenueOut])
async def host_venues(user: HostDep):
    filt = {} if user["role"] == "admin" else {"owner_id": user["id"]}
    return [VenueOut(**v) async for v in db.venues.find(filt, {"_id": 0}).sort("name", ASCENDING)]


@router.post("/host/venues", response_model=VenueOut, status_code=201)
async def create_venue(body: VenueIn, user: HostDep):
    if not body.image_url.startswith("https://"):
        raise HTTPException(400, "Image must be an https link")
    doc = {
        "id": str(uuid.uuid4()), **body.model_dump(), "state": "CA", "rating": 5.0,
        "min_level": "bronze", "owner_id": user["id"], "created_at": _now(),
    }
    await db.venues.insert_one(doc)
    doc.pop("_id", None)
    return VenueOut(**doc)


class HostEventOut(BaseModel):
    id: str
    title: str
    venue_name: str
    date: datetime
    price: float
    tickets_sold: int
    capacity: int
    approval_required: bool
    pending_requests: int
    tables_booked: int
    tables_total: int
    checked_in: int


@router.get("/host/events", response_model=List[HostEventOut])
async def host_events(user: HostDep):
    if user["role"] == "admin":
        filt: dict = {}
    else:
        owned = [v["id"] async for v in db.venues.find({"owner_id": user["id"]}, {"id": 1})]
        filt = {"$or": [{"created_by": user["id"]}, {"venue_id": {"$in": owned}}]}
    out = []
    async for e in db.events.find(filt, {"_id": 0}).sort("date", ASCENDING):
        checked = await db.tickets.aggregate([
            {"$match": {"event_id": e["id"], "checked_in": True}}, {"$group": {"_id": None, "n": {"$sum": "$quantity"}}},
        ]).to_list(1)
        out.append(HostEventOut(
            id=e["id"], title=e["title"], venue_name=e["venue_name"], date=e["date"], price=e["price"],
            tickets_sold=e.get("tickets_sold", 0), capacity=e.get("capacity", 200),
            approval_required=e.get("approval_required", False),
            pending_requests=await db.event_requests.count_documents({"event_id": e["id"], "status": "pending"}),
            tables_booked=await db.table_bookings.count_documents({"event_id": e["id"], "status": "confirmed"}),
            tables_total=len(e.get("tables", [])),
            checked_in=checked[0]["n"] if checked else 0,
        ))
    return out


class HostGuest(BaseModel):
    ticket_id: str
    name: str
    quantity: int
    checked_in: bool


class HostEventDetail(BaseModel):
    requests: List[RequestOut]
    guests: List[HostGuest]
    tables: List[TableBookingOut]


@router.get("/host/events/{eid}", response_model=HostEventDetail)
async def host_event_detail(eid: str, user: HostDep):
    await _own_event(eid, user)
    reqs = [RequestOut(**r) async for r in db.event_requests.find({"event_id": eid}, {"_id": 0}).sort("created_at", ASCENDING)]
    guests = []
    async for t in db.tickets.find({"event_id": eid}, {"_id": 0}).sort("created_at", ASCENDING):
        u = await db.users.find_one({"id": t["user_id"]}, {"_id": 0, "full_name": 1})
        guests.append(HostGuest(ticket_id=t["id"], name=u["full_name"] if u else "Guest", quantity=t["quantity"], checked_in=t["checked_in"]))
    tables = [TableBookingOut(**b) async for b in db.table_bookings.find({"event_id": eid}, {"_id": 0}).sort("created_at", ASCENDING)]
    return HostEventDetail(requests=reqs, guests=guests, tables=tables)


class DecisionIn(BaseModel):
    action: str  # approve | decline


@router.post("/host/requests/{rid}", response_model=RequestOut)
async def decide_request(rid: str, body: DecisionIn, user: HostDep):
    if body.action not in {"approve", "decline"}:
        raise HTTPException(400, "Action must be approve or decline")
    req = await db.event_requests.find_one({"id": rid}, {"_id": 0})
    if not req:
        raise HTTPException(404, "Request not found")
    ev = await _own_event(req["event_id"], user)
    new_status = "approved" if body.action == "approve" else "declined"
    res = await db.event_requests.update_one({"id": rid, "status": "pending"}, {"$set": {"status": new_status, "decided_at": _now()}})
    if res.modified_count == 0:
        raise HTTPException(400, "Request already handled")
    if new_status == "approved":
        guest = await db.users.find_one({"id": req["user_id"]}, {"_id": 0})
        if guest and amount_due(ticket_price(ev, guest, req["quantity"])[2], guest) > 0:
            # paid event: the guest pays at checkout, then the ticket is issued
            req["status"] = new_status
            return RequestOut(**req)
        if guest:
            try:
                await issue_ticket(ev, guest, req["quantity"], req.get("promoter_code"), override=req["kind"] == "waitlist")
            except HTTPException:
                await db.event_requests.update_one({"id": rid}, {"$set": {"status": "pending"}})
                raise HTTPException(409, "Event is full — raise capacity or approve from the waitlist")
            if req["kind"] == "waitlist":
                # host chose to add a spot: grow capacity so counts stay consistent
                await db.events.update_one({"id": ev["id"], "$expr": {"$gt": ["$tickets_sold", "$capacity"]}},
                                           [{"$set": {"capacity": "$tickets_sold"}}])
    req["status"] = new_status
    return RequestOut(**req)


async def ensure_feature_indexes():
    await db.table_bookings.create_index([("event_id", 1), ("table_id", 1)], unique=True,
                                         partialFilterExpression={"status": "confirmed"}, name="one_booking_per_table")
    await db.concierge_messages.create_index([("member_id", 1), ("created_at", 1)], name="thread")
    await db.event_requests.create_index([("event_id", 1), ("status", 1)], name="event_status")
