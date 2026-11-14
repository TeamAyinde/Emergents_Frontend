"""Journal (newsletter), luxury partners marketplace, member preferences, admin dashboard."""
import csv
import io
import os
import uuid
from datetime import datetime, timezone
from typing import Annotated, List, Optional

from emergentintegrations.llm.chat import LlmChat, StreamDone, TextDelta, UserMessage
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING

from server import (
    LEVEL_BOOKING_FEE, LEVEL_PRICE, LEVEL_RANK, LEVEL_TICKET_DISCOUNT,
    current_user, db, public_user, require_level, require_roles, user_level, UserOut,
)

router = APIRouter(prefix="/api")

PARTNER_CATEGORIES = {"hotel", "black_car", "limo", "mansion", "yacht", "jet", "helicopter", "exotic_car", "chef", "security"}
ARTICLE_CATEGORIES = {"nightlife", "travel", "luxury"}
VENUE_FEE = 99.0
AdminDep = Annotated[dict, Depends(require_roles("admin"))]
UserDep = Annotated[dict, Depends(current_user)]


# ---------- Models ----------

class PrefsIn(BaseModel):
    marketing_opt_in: bool


class PartnerOut(BaseModel):
    id: str
    name: str
    category: str
    city: str
    image_url: str
    description: str
    base_price: float
    price_unit: str
    rating: float
    public_price: float = 0.0
    min_level: str = "bronze"


class PartnerBookingIn(BaseModel):
    partner_id: str
    date: datetime
    units: int = Field(ge=1, le=14)  # nights / hours / days
    guests: int = Field(ge=1, le=100)
    notes: Optional[str] = Field(default="", max_length=500)


class PartnerBookingOut(BaseModel):
    id: str
    partner_id: str
    partner_name: str
    category: str
    user_id: str
    user_name: str
    date: datetime
    units: int
    guests: int
    price_unit: str
    base_price: float
    platform_fee: float
    total: float
    status: str
    notes: str
    created_at: datetime
    public_total: float = 0.0
    member_savings: float = 0.0


class StatusIn(BaseModel):
    status: str


class ArticleIn(BaseModel):
    title: str = Field(min_length=1, max_length=140)
    category: str
    cover_image: str = Field(min_length=1, max_length=500)
    summary: str = Field(default="", max_length=300)
    body: str = Field(min_length=1, max_length=20000)
    published: bool = False


class ArticleOut(BaseModel):
    id: str
    title: str
    category: str
    cover_image: str
    summary: str
    body: str
    published: bool
    created_at: datetime


class DraftIn(BaseModel):
    topic: str = Field(min_length=3, max_length=200)
    category: str


# ---------- Member preferences ----------

@router.patch("/me/preferences", response_model=UserOut)
async def update_prefs(body: PrefsIn, user: UserDep):
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {
            "marketing_opt_in": body.marketing_opt_in,
            "marketing_opt_in_at": datetime.now(timezone.utc) if body.marketing_opt_in else None,
        }},
    )
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return public_user(fresh)


# ---------- Partners ----------

@router.get("/partners", response_model=List[PartnerOut])
async def list_partners(category: Optional[str] = None):
    if category and category not in PARTNER_CATEGORIES:
        raise HTTPException(400, "Unknown category")
    filt = {"category": category} if category else {}
    return [PartnerOut(**p) async for p in db.partners.find(filt, {"_id": 0}).sort("rating", DESCENDING)]


@router.get("/partners/{pid}", response_model=PartnerOut)
async def get_partner(pid: str):
    p = await db.partners.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Partner not found")
    return PartnerOut(**p)


@router.post("/partner-bookings", response_model=PartnerBookingOut, status_code=201)
async def request_partner_booking(body: PartnerBookingIn, user: UserDep):
    p = await db.partners.find_one({"id": body.partner_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Partner not found")
    d = body.date if body.date.tzinfo else body.date.replace(tzinfo=timezone.utc)
    if d < datetime.now(timezone.utc):
        raise HTTPException(400, "Date must be in the future")
    if (d - datetime.now(timezone.utc)).total_seconds() > 180 * 86400:
        raise HTTPException(400, "Bookings open up to 6 months ahead")
    require_level(user, p.get("min_level", "bronze"))
    base = round(p["base_price"] * body.units, 2)
    fee = round(base * LEVEL_BOOKING_FEE[user_level(user)], 2)
    public_total = round(p.get("public_price", p["base_price"]) * body.units, 2)
    doc = {
        "id": str(uuid.uuid4()), "partner_id": p["id"], "partner_name": p["name"],
        "category": p["category"], "user_id": user["id"], "user_name": user["full_name"],
        "date": d, "units": body.units, "guests": body.guests, "price_unit": p["price_unit"],
        "base_price": base, "platform_fee": fee, "total": round(base + fee, 2),
        "status": "requested", "notes": body.notes or "", "created_at": datetime.now(timezone.utc),
        "public_total": public_total, "member_savings": round(max(0.0, public_total - (base + fee)), 2),
    }
    await db.partner_bookings.insert_one(doc)
    doc.pop("_id", None)
    return PartnerBookingOut(**doc)


@router.get("/partner-bookings/mine", response_model=List[PartnerBookingOut])
async def my_partner_bookings(user: UserDep):
    cur = db.partner_bookings.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", DESCENDING)
    return [PartnerBookingOut(**b) async for b in cur]


# ---------- Journal (newsletter) ----------

@router.get("/journal", response_model=List[ArticleOut])
async def list_articles(category: Optional[str] = None):
    filt: dict = {"published": True}
    if category:
        filt["category"] = category
    return [ArticleOut(**a) async for a in db.articles.find(filt, {"_id": 0}).sort("created_at", DESCENDING)]


@router.get("/journal/{aid}", response_model=ArticleOut)
async def get_article(aid: str, user: UserDep):
    a = await db.articles.find_one({"id": aid}, {"_id": 0})
    if not a or (not a["published"] and user["role"] != "admin"):
        raise HTTPException(404, "Article not found")
    return ArticleOut(**a)


def _check_article(body: ArticleIn):
    if body.category not in ARTICLE_CATEGORIES:
        raise HTTPException(400, "Category must be nightlife, travel or luxury")
    if not body.cover_image.startswith("https://"):
        raise HTTPException(400, "Cover image must be an https link")


@router.post("/admin/journal", response_model=ArticleOut, status_code=201)
async def create_article(body: ArticleIn, _: AdminDep):
    _check_article(body)
    doc = {"id": str(uuid.uuid4()), **body.model_dump(), "created_at": datetime.now(timezone.utc)}
    await db.articles.insert_one(doc)
    doc.pop("_id", None)
    return ArticleOut(**doc)


@router.put("/admin/journal/{aid}", response_model=ArticleOut)
async def update_article(aid: str, body: ArticleIn, _: AdminDep):
    _check_article(body)
    res = await db.articles.update_one({"id": aid}, {"$set": body.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(404, "Article not found")
    return ArticleOut(**(await db.articles.find_one({"id": aid}, {"_id": 0})))


@router.get("/admin/journal", response_model=List[ArticleOut])
async def admin_articles(_: AdminDep):
    return [ArticleOut(**a) async for a in db.articles.find({}, {"_id": 0}).sort("created_at", DESCENDING)]


@router.post("/admin/journal/draft")
async def draft_article(body: DraftIn, user: AdminDep):
    if body.category not in ARTICLE_CATEGORIES:
        raise HTTPException(400, "Category must be nightlife, travel or luxury")
    chat = LlmChat(
        api_key=os.environ["EMERGENT_LLM_KEY"],
        session_id=f"draft-{user['id']}-{uuid.uuid4().hex[:8]}",
        system_message=(
            "You are the editor of Nocturne Journal, a members-only newsletter about nightlife, "
            "travel and the luxury lifestyle in California and beyond. Write vivid, confident, "
            "upscale copy. Output plain text only (no markdown symbols like # or *). "
            "First line: the article title. Second line: a one-sentence summary. "
            "Then a blank line and 4-6 short paragraphs (about 350 words total)."
        ),
    ).with_model("anthropic", "claude-sonnet-5-5")

    async def gen():
        try:
            async for ev in chat.stream_message(
                UserMessage(text=f"Category: {body.category}. Topic: {body.topic}")
            ):
                if isinstance(ev, TextDelta):
                    yield ev.content
                elif isinstance(ev, StreamDone):
                    break
        except Exception:
            yield "\n\n[[DRAFT_ERROR]]"

    return StreamingResponse(
        gen(), media_type="text/plain",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- Admin: members, bookings, revenue ----------

class MemberRow(BaseModel):
    id: str
    full_name: str
    email: str
    phone: Optional[str]
    city: Optional[str]
    role: str
    membership_tier: str
    marketing_opt_in: bool
    created_at: datetime


@router.get("/admin/members", response_model=List[MemberRow])
async def admin_members(_: AdminDep, opted_in: bool = False):
    filt = {"marketing_opt_in": True} if opted_in else {}
    cur = db.users.find(filt, {"_id": 0, "password_hash": 0}).sort("created_at", DESCENDING)
    return [MemberRow(**{**u, "marketing_opt_in": u.get("marketing_opt_in", False),
                         "phone": u.get("phone"), "city": u.get("city")}) async for u in cur]


def _cell(v) -> str:
    v = str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@") else v


@router.get("/admin/members/export", response_class=PlainTextResponse)
async def export_members(_: AdminDep):
    """CSV of members who agreed to marketing emails (for use in a newsletter tool)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["full_name", "email", "phone", "city", "role", "level", "perk", "opted_in_at", "joined_at"])
    async for u in db.users.find({"marketing_opt_in": True}, {"_id": 0}).sort("created_at", ASCENDING):
        w.writerow([_cell(v) for v in [u["full_name"], u["email"], u.get("phone") or "", u.get("city") or "", u["role"],
                    user_level(u), u["membership_tier"], u.get("marketing_opt_in_at") or "", u.get("created_at") or ""]])
    return PlainTextResponse(buf.getvalue(), media_type="text/csv")


@router.get("/admin/partner-bookings", response_model=List[PartnerBookingOut])
async def admin_partner_bookings(_: AdminDep):
    cur = db.partner_bookings.find({}, {"_id": 0}).sort("created_at", DESCENDING)
    return [PartnerBookingOut(**b) async for b in cur]


@router.patch("/admin/partner-bookings/{bid}", response_model=PartnerBookingOut)
async def set_booking_status(bid: str, body: StatusIn, _: AdminDep):
    if body.status not in {"confirmed", "declined"}:
        raise HTTPException(400, "Status must be confirmed or declined")
    res = await db.partner_bookings.update_one({"id": bid, "status": "requested"}, {"$set": {"status": body.status}})
    if res.matched_count == 0:
        raise HTTPException(400, "Booking not found or already handled")
    return PartnerBookingOut(**(await db.partner_bookings.find_one({"id": bid}, {"_id": 0})))


async def _sum(coll: str, field: str, match: dict) -> float:
    rows = await db[coll].aggregate([{"$match": match}, {"$group": {"_id": None, "s": {"$sum": field}}}]).to_list(1)
    return round(rows[0]["s"], 2) if rows else 0.0


@router.get("/admin/overview")
async def admin_overview(_: AdminDep):
    ticket_fees = await _sum("tickets", {"$subtract": ["$platform_fee", "$promoter_earning"]}, {})
    reservation_fees = await _sum("reservations", "$platform_fee", {})
    partner_fees = await _sum("partner_bookings", "$platform_fee", {"status": "confirmed"})
    withdrawal_fees = await _sum("withdrawals", "$fee", {})
    membership_mrr = 0.0
    by_level = {"bronze": 0, "silver": 0, "gold": 0}
    async for u in db.users.find({"role": {"$in": ["guest", "promoter"]}}, {"_id": 0}):
        lvl = user_level(u)
        by_level[lvl] += 1
        if lvl == "bronze" and _bronze_free(u):
            continue
        membership_mrr += LEVEL_PRICE[lvl]
    membership_mrr = round(membership_mrr + await db.users.count_documents({"role": "venue_owner"}) * VENUE_FEE, 2)
    return {
        "members_total": await db.users.count_documents({}),
        "members_opted_in": await db.users.count_documents({"marketing_opt_in": True}),
        "members_by_level": by_level,
        "pending_partner_requests": await db.partner_bookings.count_documents({"status": "requested"}),
        "revenue": {
            "ticket_fees": ticket_fees,
            "reservation_fees": reservation_fees,
            "partner_fees": partner_fees,
            "withdrawal_fees": withdrawal_fees,
            "membership_mrr_estimate": membership_mrr,
        },
        "revenue_total": round(ticket_fees + reservation_fees + partner_fees + withdrawal_fees, 2),
    }


# ---------- Membership levels (payments simulated) ----------

def _bronze_free(u: dict) -> bool:
    if u.get("membership_tier") == "free_girl":
        return True
    created = u.get("created_at")
    if u.get("membership_tier") == "trial_male" and created:
        created = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - created).days < 30
    return False


class UpgradeIn(BaseModel):
    level: str


@router.get("/membership/plans")
async def membership_plans():
    return [
        {"level": lvl, "price": LEVEL_PRICE[lvl], "booking_fee_pct": LEVEL_BOOKING_FEE[lvl],
         "ticket_discount_pct": LEVEL_TICKET_DISCOUNT[lvl]}
        for lvl in ("bronze", "silver", "gold")
    ]


@router.post("/membership/upgrade", response_model=UserOut)
async def change_level(body: UpgradeIn, user: UserDep):
    if body.level not in LEVEL_RANK:
        raise HTTPException(400, "Unknown level")
    if user["role"] in ("admin", "venue_owner"):
        raise HTTPException(400, "Business accounts already have full access")
    if body.level == user_level(user):
        raise HTTPException(400, "You are already on this level")
    now = datetime.now(timezone.utc)
    await db.users.update_one({"id": user["id"]}, {"$set": {"level": body.level, "level_since": now}})
    amount = 0.0 if (body.level == "bronze" and _bronze_free(user)) else LEVEL_PRICE[body.level]
    await db.membership_payments.insert_one({
        "id": str(uuid.uuid4()), "user_id": user["id"], "level": body.level,
        "amount": amount, "simulated": True, "created_at": now,
    })
    return public_user(await db.users.find_one({"id": user["id"]}, {"_id": 0}))
