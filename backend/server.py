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
SERVICE_PRICES = {"table": 200.0, "booth": 400.0, "bottle": 800.0}
PLATFORM_FEE_PCT = 0.15  # 15% platform fee on tickets / reservations
WITHDRAWAL_FEE = 2.00

client = AsyncIOMotorClient(MONGO_URL)
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


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: str
    membership_tier: str
    referral_code: str
    wallet_balance: float


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


class EventCreate(BaseModel):
    title: str
    venue_id: str
    date: datetime
    price: float
    image_url: str
    description: str
    tags: List[str] = []


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
        referral_code=u["referral_code"],
        wallet_balance=round(u.get("wallet_balance", 0.0), 2),
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
        "referral_code": _referral_code(body.full_name),
        "wallet_balance": 0.0,
        "created_at": datetime.now(timezone.utc),
    }
    await db.users.insert_one(doc)
    doc.pop("_id", None)
    return {"access_token": issue_token(doc), "user": public_user(doc)}


@api.post("/auth/login", response_model=TokenOut)
async def login(body: LoginIn):
    user = await db.users.find_one({"email": body.email.lower()}, {"_id": 0})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Incorrect email or password")
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
    ev_date = body.date if body.date.tzinfo else body.date.replace(tzinfo=timezone.utc)
    if ev_date < datetime.now(timezone.utc):
        raise HTTPException(400, "Event date must be in the future")
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
    qty = body.quantity
    base = event["price"] * qty
    platform_fee = round(base * PLATFORM_FEE_PCT, 2)
    total = round(base + platform_fee, 2)

    promoter_id = None
    promoter_earning = 0.0
    if body.promoter_code:
        promoter = await db.users.find_one(
            {"referral_code": body.promoter_code.upper(), "role": {"$in": ["promoter", "venue_owner", "admin"]}},
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
        "total_paid": total,
        "platform_fee": platform_fee,
        "promoter_earning": promoter_earning,
        "checked_in": False,
        "created_at": datetime.now(timezone.utc),
    }
    await db.tickets.insert_one(doc)
    await db.events.update_one({"id": event["id"]}, {"$inc": {"tickets_sold": qty}})
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
    return {"withdrawn": body.amount, "fee": fee, "net": net}


# ---------- Reservations ----------

@api.post("/reservations", response_model=ReservationOut, status_code=201)
async def create_reservation(body: ReservationIn, user: Annotated[dict, Depends(current_user)]):
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
    fee = round(body.base_price * PLATFORM_FEE_PCT, 2)
    total = round(body.base_price + fee, 2)
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
        "created_at": datetime.now(timezone.utc),
    }
    await db.reservations.insert_one(doc)
    doc.pop("_id", None)
    return ReservationOut(**doc)


@api.get("/reservations/mine", response_model=List[ReservationOut])
async def my_reservations(user: Annotated[dict, Depends(current_user)]):
    cursor = db.reservations.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", DESCENDING)
    return [ReservationOut(**r) async for r in cursor]


# ---------- Routes mounting ----------

app.include_router(api)

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
    # seed in background so boot is not blocked
    from seed import seed_all  # local
    app.state.seed_task = asyncio.create_task(seed_all(db))


@app.on_event("shutdown")
async def _shutdown():
    app.state.index_task.cancel()
    with suppress(asyncio.CancelledError):
        await app.state.index_task
    client.close()
