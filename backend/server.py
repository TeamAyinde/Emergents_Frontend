"""Nocturne API — hospitality + nightlife events + promoter payouts."""
import asyncio
import logging
import os
import re
import uuid
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, List, Optional

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field
from pymongo import ASCENDING, DESCENDING, IndexModel
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = "HS256"
JWT_ISSUER = "nocturne-api"
JWT_EXPIRE_MINUTES = 60 * 24 * 7  # one week

ALLOWED_ROLES = {"guest", "promoter", "venue_owner", "admin"}
MEMBERSHIP_TIERS = {"free_girl", "trial_male", "member", "premium", "venue", "corporate"}
SELF_SERVE_TIERS = {"free_girl", "trial_male", "member"}
LEVEL_RANK = {"bronze": 0, "silver": 1, "gold": 2}
LEVEL_PRICE = {"bronze": 14.99, "silver": 49.0, "gold": 149.0}
LEVEL_BOOKING_FEE = {"bronze": 0.25, "silver": 0.20, "gold": 0.15}
LEVEL_TICKET_DISCOUNT = {"bronze": 0.0, "silver": 0.10, "gold": 0.20}
SERVICE_PRICES = {"table": 200.0, "booth": 400.0, "bottle": 800.0}
PLATFORM_FEE_PCT = 0.15  # 15% platform fee on tickets / reservations
WITHDRAWAL_FEE = 2.00

client = AsyncIOMotorClient(MONGO_URL, tz_aware=True)
db = client[DB_NAME]
security = HTTPBearer(auto_error=False)

INDEXES: dict[str, list[IndexModel]] = {
    "users": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("email", ASCENDING)], name="email", unique=True),
        IndexModel([("referral_code", ASCENDING)], name="referral_code"),
    ],
    "events": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("date", ASCENDING)], name="date_asc"),
        IndexModel([("venue_id", ASCENDING)], name="venue"),
    ],
    "venues": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("city", ASCENDING)], name="city"),
    ],
    "tickets": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("user_id", ASCENDING)], name="user"),
        IndexModel([("event_id", ASCENDING)], name="event"),
        IndexModel([("promoter_id", ASCENDING)], name="promoter"),
    ],
    "reservations": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("user_id", ASCENDING)], name="user"),
    ],
}


async def ensure_indexes() -> None:
    for collection, models in INDEXES.items():
        for model in models:
            try:
                await db[collection].create_indexes([model])
            except Exception as exc:
                logging.getLogger(__name__).error("index %s: %s", model.document["name"], exc)


app = FastAPI(title="Nocturne API")


@app.get("/health", include_in_schema=False)
@app.head("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


api = APIRouter(prefix="/api")

# ---------- Models ----------

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    full_name: str = Field(min_length=1, max_length=80)
    role: str = "guest"
    membership_tier: str = "member"
    phone: Optional[str] = Field(default=None, max_length=30)
    city: Optional[str] = Field(default=None, max_length=60)
    marketing_opt_in: bool = True


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: str
    membership_tier: str
    level: str = "bronze"
    level_since: Optional[datetime] = None
    referral_code: str
    wallet_balance: float
    points: int = 0
    credit_balance: float = 0.0
    marketing_opt_in: bool = False
    phone: Optional[str] = None
    city: Optional[str] = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class VenueOut(BaseModel):
    id: str
    name: str
    city: str
    state: str
    category: str
    image_url: str
    rating: float
    price_range: str
    description: str
    min_level: str = "bronze"


class EventOut(BaseModel):
    id: str
    title: str
    venue_id: str
    venue_name: str
    city: str
    date: datetime
    price: float
    image_url: str
    description: str
    tags: List[str]
    tickets_sold: int = 0
    min_level: str = "bronze"
    capacity: int = 200
    approval_required: bool = False
    plus_one_limit: int = 7
    guest_list_visible: bool = True
    has_tables: bool = False
    created_by: Optional[str] = None


class EventCreate(BaseModel):
    title: str
    venue_id: str
    date: datetime
    price: float
    image_url: str
    description: str
    tags: List[str] = []
    min_level: Optional[str] = None
    capacity: int = Field(default=200, ge=1, le=10000)
    approval_required: bool = False
    plus_one_limit: int = Field(default=3, ge=0, le=7)
    guest_list_visible: bool = True
    table_min_spend: Optional[float] = Field(default=None, ge=0, le=100000)


class TicketPurchaseIn(BaseModel):
    event_id: str
    promoter_code: Optional[str] = None
    quantity: int = 1


class TicketOut(BaseModel):
    id: str
    event_id: str
    event_title: str
    event_date: datetime
    venue_name: str
    user_id: str
    promoter_id: Optional[str]
    quantity: int
    total_paid: float
    platform_fee: float
    promoter_earning: float
    checked_in: bool
    created_at: datetime
    credit_used: float = 0.0


class ReservationIn(BaseModel):
    venue_id: str
    date: datetime
    party_size: int
    service_type: str  # "table" | "bottle" | "booth"
    base_price: Optional[float] = None
    notes: Optional[str] = ""


class ReservationOut(BaseModel):
    id: str
    venue_id: str
    venue_name: str
    user_id: str
    date: datetime
    party_size: int
    service_type: str
    base_price: float
    platform_fee: float
    total: float
    status: str
    notes: str
    created_at: datetime


class PromoterStats(BaseModel):
    total_earnings: float
    tickets_sold: int
    guests_checked_in: int
    referral_code: str
    rank: int


class LeaderboardEntry(BaseModel):
    user_id: str
    full_name: str
    earnings: float
    tickets_sold: int


class WithdrawIn(BaseModel):
    amount: float


# ---------- Helpers ----------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), stored.encode())
    except (ValueError, TypeError):
        return False


def issue_token(user: dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user["id"],
        "role": user["role"],
        "iss": JWT_ISSUER,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def public_user(u: dict) -> UserOut:
    return UserOut(
        id=u["id"],
        email=u["email"],
        full_name=u["full_name"],
        role=u["role"],
        membership_tier=u["membership_tier"],
        level=user_level(u),
        level_since=u.get("level_since"),
        referral_code=u["referral_code"],
        wallet_balance=round(u.get("wallet_balance", 0.0), 2),
        points=int(u.get("points", 0)),
        credit_balance=round(u.get("credit_balance", 0.0), 2),
        marketing_opt_in=u.get("marketing_opt_in", False),
        phone=u.get("phone"),
        city=u.get("city"),
    )


def _referral_code(name: str) -> str:
    base = "".join(c for c in name.upper() if c.isalpha())[:4] or "NOC"
    return f"{base}{uuid.uuid4().hex[:4].upper()}"


async def current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
) -> dict:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not credentials or credentials.scheme.lower() != "bearer":
        raise unauthorized
    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALG],
            issuer=JWT_ISSUER,
            options={"require": ["sub", "iss", "iat", "exp"]},
        )
        uid = payload["sub"]
    except (jwt.InvalidTokenError, KeyError):
        raise unauthorized
    user = await db.users.find_one({"id": uid}, {"_id": 0})
    if not user:
        raise unauthorized
    return user


def user_level(u: dict) -> str:
    if u.get("role") in ("admin", "venue_owner"):
        return "gold"
    return u.get("level", "bronze")


def require_level(u: dict, min_level: str) -> None:
    if LEVEL_RANK[user_level(u)] < LEVEL_RANK.get(min_level, 0):
        raise HTTPException(403, f"{min_level.capitalize()} membership required")


POINTS_MULTIPLIER = {"bronze": 1.0, "silver": 1.5, "gold": 2.0}


async def award_points(user: dict, amount: float, reason: str) -> int:
    """1 point per $1 spent; Silver 1.5x, Gold 2x."""
    pts = int(round(max(0.0, amount) * POINTS_MULTIPLIER[user_level(user)]))
    if pts <= 0:
        return 0
    await db.users.update_one({"id": user["id"]}, {"$inc": {"points": pts}})
    await db.points_ledger.insert_one({
        "id": str(uuid.uuid4()), "user_id": user["id"], "points": pts, "reason": reason,
        "created_at": datetime.now(timezone.utc),
    })
    return pts


async def record_venue_share(venue_id: Optional[str], amount: float, source: str, record_id: str) -> None:
    """Nocturne collected the money; log what it owes the venue (paid out by the admin)."""
    if not venue_id or amount <= 0:
        return
    venue = await db.venues.find_one({"id": venue_id}, {"_id": 0, "name": 1})
    await db.venue_payables.insert_one({
        "id": str(uuid.uuid4()), "venue_id": venue_id, "venue_name": (venue or {}).get("name", ""),
        "amount": round(amount, 2), "source": source, "record_id": record_id, "status": "owed",
        "created_at": datetime.now(timezone.utc),
    })


def make_tables(base: float, min_level: str) -> list:
    """Default floor plan: 4 main-floor tables, 3 VIP booths, 1 stage-side skybox (positions in %)."""
    plan = [
        ("T1", "Main Floor", 6, 1.0, 15, 62), ("T2", "Main Floor", 6, 1.0, 38, 62),
        ("T3", "Main Floor", 6, 1.0, 62, 62), ("T4", "Main Floor", 6, 1.0, 85, 62),
        ("V1", "VIP", 8, 2.0, 15, 85), ("V2", "VIP", 8, 2.0, 50, 85), ("V3", "VIP", 8, 2.0, 85, 85),
        ("S1", "Stage Skybox", 12, 4.0, 85, 30),
    ]
    tier_up = {"bronze": "silver", "silver": "gold", "gold": "gold"}
    return [
        {"id": tid, "name": tid, "section": sec, "capacity": cap, "min_spend": round(base * mult, 2),
         "x": x, "y": y, "min_level": tier_up[min_level] if sec != "Main Floor" else min_level}
        for (tid, sec, cap, mult, x, y) in plan
    ]


def require_roles(*roles: str):
    async def dep(user: Annotated[dict, Depends(current_user)]):
        if user["role"] not in roles:
            raise HTTPException(403, "Insufficient role")
        return user

    return dep


# ---------- Auth ----------

@api.post("/auth/register", response_model=TokenOut, status_code=201)
async def register(body: RegisterIn):
    if body.role not in ALLOWED_ROLES or body.role == "admin":
        raise HTTPException(400, "Role not allowed for self-registration")
    if body.role == "venue_owner":
        body.membership_tier = "venue"
    elif body.membership_tier not in SELF_SERVE_TIERS:
        raise HTTPException(400, "This membership tier requires payment")
    existing = await db.users.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(409, "Email already registered")
    doc = {
        "id": str(uuid.uuid4()),
        "email": body.email.lower(),
        "password_hash": hash_password(body.password),
        "full_name": body.full_name.strip(),
        "role": body.role,
        "membership_tier": body.membership_tier,
        "level": "bronze",
        "level_since": datetime.now(timezone.utc),
        "referral_code": _referral_code(body.full_name),
        "wallet_balance": 0.0,
        "phone": (body.phone or "").strip() or None,
        "city": (body.city or "").strip() or None,
        "marketing_opt_in": body.marketing_opt_in,
        "marketing_opt_in_at": datetime.now(timezone.utc) if body.marketing_opt_in else None,
        "created_at": datetime.now(timezone.utc),
    }
    await db.users.insert_one(doc)
    doc.pop("_id", None)
    return {"access_token": issue_token(doc), "user": public_user(doc)}


@api.post("/auth/login", response_model=TokenOut)
async def login(body: LoginIn):
    user = await db.users.find_one({"email": body.email.lower()}, {"_id": 0})
    if not user or not verify_password(body.password, user.get("password_hash") or ""):
        raise HTTPException(401, "Incorrect email or password")
    return {"access_token": issue_token(user), "user": public_user(user)}


class GoogleSessionIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=512)


@api.post("/auth/session", response_model=TokenOut)
async def google_session(body: GoogleSessionIn):
    """Exchanges the one-time Emergent Google `session_id` for a Nocturne token."""
    import httpx

    async with httpx.AsyncClient(timeout=15) as http:
        r = await http.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": body.session_id},
        )
    if r.status_code != 200:
        raise HTTPException(401, "Google sign-in failed — try again")
    data = r.json()
    email = (data.get("email") or "").lower()
    if not email:
        raise HTTPException(401, "Google sign-in failed — try again")
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        name = (data.get("name") or email.split("@")[0]).strip()[:80]
        user = {
            "id": str(uuid.uuid4()), "email": email, "password_hash": None, "full_name": name,
            "role": "guest", "membership_tier": "member", "level": "bronze",
            "level_since": datetime.now(timezone.utc), "referral_code": _referral_code(name),
            "wallet_balance": 0.0, "phone": None, "city": None, "picture": data.get("picture"),
            "auth_provider": "google", "marketing_opt_in": True,
            "marketing_opt_in_at": datetime.now(timezone.utc), "created_at": datetime.now(timezone.utc),
        }
        await db.users.insert_one(user)
        user.pop("_id", None)
    return {"access_token": issue_token(user), "user": public_user(user)}


@api.get("/auth/me", response_model=UserOut)
async def me(user: Annotated[dict, Depends(current_user)]):
    return public_user(user)


# ---------- Venues ----------

@api.get("/venues", response_model=List[VenueOut])
async def list_venues(city: Optional[str] = None, q: Optional[str] = None):
    filt: dict = {}
    if city:
        filt["city"] = city
    if q:
        filt["name"] = {"$regex": re.escape(q), "$options": "i"}
    cursor = db.venues.find(filt, {"_id": 0}).sort("rating", DESCENDING)
    return [VenueOut(**v) async for v in cursor]


@api.get("/venues/{venue_id}", response_model=VenueOut)
async def get_venue(venue_id: str):
    v = await db.venues.find_one({"id": venue_id}, {"_id": 0})
    if not v:
        raise HTTPException(404, "Venue not found")
    return VenueOut(**v)


# ---------- Events ----------

@api.get("/events", response_model=List[EventOut])
async def list_events(city: Optional[str] = None, upcoming: bool = True):
    filt: dict = {}
    if city:
        filt["city"] = city
    if upcoming:
        filt["date"] = {"$gte": datetime.now(timezone.utc)}
    cursor = db.events.find(filt, {"_id": 0}).sort("date", ASCENDING)
    return [EventOut(**e) async for e in cursor]


@api.get("/events/{event_id}", response_model=EventOut)
async def get_event(event_id: str):
    e = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not e:
        raise HTTPException(404, "Event not found")
    return EventOut(**e)


@api.post("/events", response_model=EventOut, status_code=201)
async def create_event(
    body: EventCreate,
    user: Annotated[dict, Depends(require_roles("venue_owner", "admin"))],
):
    venue = await db.venues.find_one({"id": body.venue_id}, {"_id": 0})
    if not venue:
        raise HTTPException(404, "Venue not found")
    if user["role"] != "admin" and venue.get("owner_id") != user["id"]:
        raise HTTPException(403, "You can only post events for your own venues")
    ev_date = body.date if body.date.tzinfo else body.date.replace(tzinfo=timezone.utc)
    if ev_date < datetime.now(timezone.utc):
        raise HTTPException(400, "Event date must be in the future")
    if not body.title.strip() or body.price < 0 or body.price > 10000:
        raise HTTPException(400, "Title and a price between $0 and $10,000 are required")
    if not body.image_url.startswith("https://"):
        raise HTTPException(400, "Image must be an https link")
    min_level = body.min_level or venue.get("min_level", "bronze")
    if min_level not in LEVEL_RANK:
        raise HTTPException(400, "Unknown level")
    tables = make_tables(body.table_min_spend, min_level) if body.table_min_spend else []
    doc = {
        "id": str(uuid.uuid4()),
        "title": body.title,
        "venue_id": body.venue_id,
        "venue_name": venue["name"],
        "city": venue["city"],
        "date": body.date,
        "price": body.price,
        "image_url": body.image_url,
        "description": body.description,
        "tags": body.tags,
        "tickets_sold": 0,
        "min_level": min_level,
        "capacity": body.capacity,
        "approval_required": body.approval_required,
        "plus_one_limit": body.plus_one_limit,
        "guest_list_visible": body.guest_list_visible,
        "tables": tables,
        "has_tables": bool(tables),
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc),
    }
    await db.events.insert_one(doc)
    doc.pop("_id", None)
    return EventOut(**doc)


# ---------- Tickets ----------

@api.post("/tickets/purchase", response_model=TicketOut, status_code=201)
async def purchase_ticket(
    body: TicketPurchaseIn, user: Annotated[dict, Depends(current_user)]
):
    event = await db.events.find_one({"id": body.event_id}, {"_id": 0})
    if not event:
        raise HTTPException(404, "Event not found")
    if not 1 <= body.quantity <= 8:
        raise HTTPException(400, "Quantity must be between 1 and 8")
    ev_date = event["date"] if event["date"].tzinfo else event["date"].replace(tzinfo=timezone.utc)
    if ev_date < datetime.now(timezone.utc):
        raise HTTPException(400, "This event has already happened")
    require_level(user, event.get("min_level", "bronze"))
    if body.quantity > 1 + event.get("plus_one_limit", 7):
        raise HTTPException(400, f"Max {1 + event.get('plus_one_limit', 7)} tickets per guest")
    if event.get("approval_required"):
        raise HTTPException(409, "This event needs host approval — request to join")
    if amount_due(ticket_price(event, user, body.quantity)[2], user) > 0:
        raise HTTPException(402, "Payment required — continue to checkout")
    return await issue_ticket(event, user, body.quantity, body.promoter_code)


def ticket_price(event: dict, user: dict, qty: int) -> tuple[float, float, float]:
    """(base after member discount, platform fee, total) for `qty` tickets."""
    base = round(event["price"] * qty * (1 - LEVEL_TICKET_DISCOUNT[user_level(user)]), 2)
    fee = round(base * PLATFORM_FEE_PCT, 2)
    return base, fee, round(base + fee, 2)


def amount_due(total: float, user: dict) -> float:
    """What the member still owes after their reward credit."""
    return round(max(0.0, total - user.get("credit_balance", 0.0)), 2)


async def issue_ticket(
    event: dict, user: dict, qty: int, promoter_code: Optional[str], override: bool = False,
    credit_used: Optional[float] = None, payment_session: Optional[str] = None,
) -> "TicketOut":
    """Atomically reserves `qty` spots (unless the host overrides capacity), then writes the ticket.
    When `credit_used` is given the credit was already taken at checkout."""
    cond = {"id": event["id"]}
    if not override:
        cond["$expr"] = {"$lte": [{"$add": [{"$ifNull": ["$tickets_sold", 0]}, qty]}, {"$ifNull": ["$capacity", 1000000]}]}
    res = await db.events.update_one(cond, {"$inc": {"tickets_sold": qty}})
    if res.modified_count == 0:
        raise HTTPException(409, "Sold out — join the waitlist")
    base, platform_fee, total = ticket_price(event, user, qty)
    prepaid = credit_used is not None
    credit_used = credit_used or 0.0
    if not prepaid and user.get("credit_balance", 0) > 0 and total > 0:
        credit_used = round(min(user["credit_balance"], total), 2)
        res_c = await db.users.update_one({"id": user["id"], "credit_balance": {"$gte": credit_used}},
                                          {"$inc": {"credit_balance": -credit_used}})
        if res_c.modified_count == 0:
            credit_used = 0.0

    promoter_id = None
    promoter_earning = 0.0
    if promoter_code:
        promoter = await db.users.find_one(
            {"referral_code": promoter_code.upper(), "role": {"$in": ["promoter", "venue_owner", "admin"]}},
            {"_id": 0},
        )
        if promoter and promoter["id"] != user["id"]:
            promoter_id = promoter["id"]
            # promoter gets 40% of the platform fee
            promoter_earning = round(platform_fee * 0.4, 2)

    doc = {
        "id": str(uuid.uuid4()),
        "event_id": event["id"],
        "event_title": event["title"],
        "event_date": event["date"],
        "venue_name": event["venue_name"],
        "user_id": user["id"],
        "promoter_id": promoter_id,
        "quantity": qty,
        "total_paid": round(total - credit_used, 2),
        "credit_used": credit_used,
        "platform_fee": platform_fee,
        "promoter_earning": promoter_earning,
        "venue_share": base,
        "payment_session": payment_session,
        "checked_in": False,
        "created_at": datetime.now(timezone.utc),
    }
    await db.tickets.insert_one(doc)
    await record_venue_share(event.get("venue_id"), base, "ticket", doc["id"])
    await award_points(user, doc["total_paid"], f"Tickets · {event['title']}")
    if promoter_id and promoter_earning > 0:
        await db.users.update_one(
            {"id": promoter_id}, {"$inc": {"wallet_balance": promoter_earning}}
        )
    doc.pop("_id", None)
    return TicketOut(**doc)


@api.get("/tickets/mine", response_model=List[TicketOut])
async def my_tickets(user: Annotated[dict, Depends(current_user)]):
    cursor = db.tickets.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", DESCENDING)
    return [TicketOut(**t) async for t in cursor]


@api.post("/tickets/{ticket_id}/checkin", response_model=TicketOut)
async def check_in(
    ticket_id: str,
    user: Annotated[dict, Depends(require_roles("promoter", "venue_owner", "admin"))],
):
    code = ticket_id.strip().lstrip("#").lower()
    if len(code) == 36:
        t = await db.tickets.find_one({"id": code}, {"_id": 0})
    elif len(code) >= 6:
        matches = await db.tickets.find({"id": {"$regex": f"^{re.escape(code)}"}}, {"_id": 0}).to_list(2)
        t = matches[0] if len(matches) == 1 else None
    else:
        t = None
    if not t:
        raise HTTPException(404, "Ticket not found")
    res = await db.tickets.update_one(
        {"id": t["id"], "checked_in": False},
        {"$set": {"checked_in": True, "checked_in_at": datetime.now(timezone.utc)}},
    )
    if res.modified_count == 0:
        raise HTTPException(400, "Already checked in")
    t["checked_in"] = True
    return TicketOut(**t)


# ---------- Promoter ----------

@api.get("/promoter/stats", response_model=PromoterStats)
async def promoter_stats(
    user: Annotated[dict, Depends(require_roles("promoter", "venue_owner", "admin"))],
):
    pipeline = [
        {"$match": {"promoter_id": user["id"]}},
        {
            "$group": {
                "_id": "$promoter_id",
                "earnings": {"$sum": "$promoter_earning"},
                "tickets": {"$sum": "$quantity"},
                "checked_in": {"$sum": {"$cond": ["$checked_in", "$quantity", 0]}},
            }
        },
    ]
    stats_doc = await db.tickets.aggregate(pipeline).to_list(1)
    earnings = stats_doc[0]["earnings"] if stats_doc else 0.0
    tickets = stats_doc[0]["tickets"] if stats_doc else 0
    checked = stats_doc[0]["checked_in"] if stats_doc else 0

    # rank
    all_rank = await db.tickets.aggregate(
        [
            {"$match": {"promoter_id": {"$ne": None}}},
            {"$group": {"_id": "$promoter_id", "earnings": {"$sum": "$promoter_earning"}}},
            {"$sort": {"earnings": -1}},
        ]
    ).to_list(None)
    rank = next((i + 1 for i, r in enumerate(all_rank) if r["_id"] == user["id"]), len(all_rank) + 1)

    return PromoterStats(
        total_earnings=round(earnings, 2),
        tickets_sold=tickets,
        guests_checked_in=checked,
        referral_code=user["referral_code"],
        rank=rank,
    )


@api.get("/promoter/leaderboard", response_model=List[LeaderboardEntry])
async def leaderboard():
    rows = await db.tickets.aggregate(
        [
            {"$match": {"promoter_id": {"$ne": None}}},
            {
                "$group": {
                    "_id": "$promoter_id",
                    "earnings": {"$sum": "$promoter_earning"},
                    "tickets": {"$sum": "$quantity"},
                }
            },
            {"$sort": {"earnings": -1}},
            {"$limit": 20},
        ]
    ).to_list(20)
    out: List[LeaderboardEntry] = []
    for r in rows:
        u = await db.users.find_one({"id": r["_id"]}, {"_id": 0})
        if not u:
            continue
        out.append(
            LeaderboardEntry(
                user_id=u["id"],
                full_name=u["full_name"],
                earnings=round(r["earnings"], 2),
                tickets_sold=r["tickets"],
            )
        )
    return out


@api.post("/promoter/withdraw")
async def withdraw(
    body: WithdrawIn,
    user: Annotated[dict, Depends(require_roles("promoter", "venue_owner", "admin"))],
):
    if body.amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    fee = WITHDRAWAL_FEE
    net = round(body.amount - fee, 2)
    if net <= 0:
        raise HTTPException(400, f"Amount must exceed ${fee:.2f} withdrawal fee")
    res = await db.users.update_one(
        {"id": user["id"], "wallet_balance": {"$gte": body.amount}},
        {"$inc": {"wallet_balance": -body.amount}},
    )
    if res.modified_count == 0:
        raise HTTPException(400, "Insufficient balance")
    await db.withdrawals.insert_one({
        "id": str(uuid.uuid4()), "user_id": user["id"], "user_name": user["full_name"],
        "amount": body.amount, "fee": fee, "net": net, "status": "pending",
        "created_at": datetime.now(timezone.utc),
    })
    return {"withdrawn": body.amount, "fee": fee, "net": net, "status": "pending"}


# ---------- Reservations ----------

async def quote_reservation(body: "ReservationIn", user: dict) -> tuple[dict, float, float]:
    """Validates a reservation request; returns (venue, platform fee, total)."""
    venue = await db.venues.find_one({"id": body.venue_id}, {"_id": 0})
    if not venue:
        raise HTTPException(404, "Venue not found")
    if body.service_type not in SERVICE_PRICES:
        raise HTTPException(400, "Unknown service type")
    if not 1 <= body.party_size <= 30:
        raise HTTPException(400, "Party size must be between 1 and 30")
    body.base_price = SERVICE_PRICES[body.service_type]
    res_date = body.date if body.date.tzinfo else body.date.replace(tzinfo=timezone.utc)
    if res_date < datetime.now(timezone.utc):
        raise HTTPException(400, "Reservation date must be in the future")
    require_level(user, venue.get("min_level", "bronze"))
    fee = round(body.base_price * LEVEL_BOOKING_FEE[user_level(user)], 2)
    return venue, fee, round(body.base_price + fee, 2)


@api.post("/reservations", response_model=ReservationOut, status_code=201)
async def create_reservation(body: ReservationIn, user: Annotated[dict, Depends(current_user)]):
    _, _, total = await quote_reservation(body, user)
    if total > 0:
        raise HTTPException(402, "Payment required — continue to checkout")
    return await save_reservation(body, user)


async def save_reservation(body: "ReservationIn", user: dict, payment_session: Optional[str] = None) -> "ReservationOut":
    venue, fee, total = await quote_reservation(body, user)
    doc = {
        "id": str(uuid.uuid4()),
        "venue_id": body.venue_id,
        "venue_name": venue["name"],
        "user_id": user["id"],
        "date": body.date,
        "party_size": body.party_size,
        "service_type": body.service_type,
        "base_price": body.base_price,
        "platform_fee": fee,
        "total": total,
        "status": "confirmed",
        "notes": body.notes or "",
        "payment_session": payment_session,
        "created_at": datetime.now(timezone.utc),
    }
    await db.reservations.insert_one(doc)
    await record_venue_share(venue["id"], body.base_price, "reservation", doc["id"])
    await award_points(user, doc["total"], f"Reservation · {venue['name']}")
    doc.pop("_id", None)
    return ReservationOut(**doc)


@api.get("/reservations/mine", response_model=List[ReservationOut])
async def my_reservations(user: Annotated[dict, Depends(current_user)]):
    cursor = db.reservations.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", DESCENDING)
    return [ReservationOut(**r) async for r in cursor]


# ---------- Routes mounting ----------

from extras import router as extras_router  # noqa: E402
from features import ensure_feature_indexes, router as features_router  # noqa: E402
from rewards import router as rewards_router  # noqa: E402
from payments import router as payments_router  # noqa: E402

app.include_router(api)
app.include_router(extras_router)
app.include_router(features_router)
app.include_router(rewards_router)
app.include_router(payments_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


@app.on_event("startup")
async def _startup():
    app.state.index_task = asyncio.create_task(ensure_indexes())
    app.state.feature_index_task = asyncio.create_task(ensure_feature_indexes())
    # seed in background so boot is not blocked
    from seed import seed_all  # local
    app.state.seed_task = asyncio.create_task(seed_all(db))


@app.on_event("shutdown")
async def _shutdown():
    app.state.index_task.cancel()
    with suppress(asyncio.CancelledError):
        await app.state.index_task
    client.close()
