"""Venue operations: door shifts, deal leaderboard, VIP arrival alerts, monthly venue report."""
from datetime import datetime, timedelta, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from routes.features import _aware, _own_event, HostDep
from routes.push import notify
from server import current_user, db

router = APIRouter(prefix="/api")
UserDep = Annotated[dict, Depends(current_user)]


# ---------- Door shifts ----------

class ShiftStaff(BaseModel):
    staff_id: str
    name: str
    email: str
    status: str
    every_night: bool
    on_shift: bool


class ShiftIn(BaseModel):
    on: bool


def on_shift(row: dict, event_id: Optional[str]) -> bool:
    """Every-night staff cover all events; scheduled staff only the nights they were assigned."""
    return row.get("every_night", True) or (event_id in (row.get("shift_event_ids") or []))


@router.get("/host/events/{eid}/shifts", response_model=List[ShiftStaff])
async def event_shifts(eid: str, user: HostDep):
    ev = await _own_event(eid, user)
    return [ShiftStaff(staff_id=s["id"], name=s["name"], email=s["email"], status=s.get("status", "active"),
                       every_night=s.get("every_night", True), on_shift=on_shift(s, eid))
            async for s in db.door_staff.find({"venue_id": ev.get("venue_id"), "active": True}, {"_id": 0}).sort("created_at", 1)]


@router.put("/host/events/{eid}/shifts/{sid}", response_model=ShiftStaff)
async def set_shift(eid: str, sid: str, body: ShiftIn, user: HostDep):
    ev = await _own_event(eid, user)
    s = await db.door_staff.find_one({"id": sid, "venue_id": ev.get("venue_id"), "active": True}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Staff member not found for this venue")
    if body.on:
        upd = {"$addToSet": {"shift_event_ids": eid}}
    elif s.get("every_night", True):
        upd = {"$set": {"every_night": False, "shift_event_ids": []}}  # switch to scheduled shifts, starting empty
    else:
        upd = {"$pull": {"shift_event_ids": eid}}
    await db.door_staff.update_one({"id": sid}, upd)
    s = await db.door_staff.find_one({"id": sid}, {"_id": 0})
    if body.on and s.get("user_id") and not s.get("every_night", True):
        when = _aware(ev["date"]).strftime("%a %b %-d")
        notify([s["user_id"]], "New door shift 🎟️", f"You're on the door for {ev['title']} · {when}.", "/door",
               key=f"shift-{sid}-{eid}", kind="updates")
    return ShiftStaff(staff_id=sid, name=s["name"], email=s["email"], status=s.get("status", "active"),
                      every_night=s.get("every_night", True), on_shift=on_shift(s, eid))


class EveryNightIn(BaseModel):
    every_night: bool


@router.put("/host/staff/{sid}/schedule")
async def set_every_night(sid: str, body: EveryNightIn, user: HostDep):
    s = await db.door_staff.find_one({"id": sid, "active": True}, {"_id": 0})
    v = await db.venues.find_one({"id": (s or {}).get("venue_id")}, {"_id": 0, "owner_id": 1})
    if not s or (user["role"] != "admin" and (v or {}).get("owner_id") != user["id"]):
        raise HTTPException(404, "Staff member not found")
    await db.door_staff.update_one({"id": sid}, {"$set": {"every_night": body.every_night}})
    return {"every_night": body.every_night}


# ---------- Deal leaderboard ----------

class DealLevel(BaseModel):
    pct: int
    deals: int
    sent_to: int
    buyers: int
    tickets: int
    revenue: float
    conversion: float  # % of waitlisted guests who bought


async def _host_event_filter(user: dict) -> dict:
    if user["role"] == "admin":
        return {}
    venue_ids = [v["id"] async for v in db.venues.find({"owner_id": user["id"]}, {"id": 1})]
    return {"$or": [{"venue_id": {"$in": venue_ids}}, {"created_by": user["id"]}]}


@router.get("/host/deals/leaderboard", response_model=List[DealLevel])
async def deal_leaderboard(user: HostDep):
    from routes.hostlive import _deal  # noqa: E402

    levels: dict = {}
    async for ev in db.events.find({**await _host_event_filter(user), "deal": {"$exists": True}}, {"_id": 0}):
        d = await _deal(ev)
        if not d.expired and _aware(ev["date"]) > datetime.now(timezone.utc):
            continue  # still running — would count as 0 buyers and skew the ranking
        row = levels.setdefault(d.pct, {"pct": d.pct, "deals": 0, "sent_to": 0, "buyers": 0, "tickets": 0, "revenue": 0.0})
        row["deals"] += 1
        row["sent_to"] += d.sent_to
        row["buyers"] += d.buyers
        row["tickets"] += d.tickets
        row["revenue"] = round(row["revenue"] + d.revenue, 2)
    out = [DealLevel(**r, conversion=round(100 * r["buyers"] / r["sent_to"], 1) if r["sent_to"] else 0.0) for r in levels.values()]
    return sorted(out, key=lambda r: (-r.conversion, -r.revenue))


# ---------- VIP guests ----------

class VipIn(BaseModel):
    note: Optional[str] = None


async def _own_venue(vid: str, user: dict) -> dict:
    v = await db.venues.find_one({"id": vid}, {"_id": 0, "id": 1, "name": 1, "owner_id": 1})
    if not v or (user["role"] != "admin" and v.get("owner_id") != user["id"]):
        raise HTTPException(403, "Not your venue")
    return v


@router.put("/host/venues/{vid}/vips/{uid}")
async def flag_vip(vid: str, uid: str, body: VipIn, user: HostDep):
    await _own_venue(vid, user)
    if not await db.users.find_one({"id": uid}, {"_id": 1}):
        raise HTTPException(404, "Guest not found")
    note = (body.note or "").strip()[:120] or None
    await db.venue_vips.update_one({"venue_id": vid, "user_id": uid},
                                   {"$set": {"note": note, "active": True, "flagged_by": user["id"], "updated_at": datetime.now(timezone.utc)}},
                                   upsert=True)
    return {"vip": True, "note": note}


@router.delete("/host/venues/{vid}/vips/{uid}")
async def unflag_vip(vid: str, uid: str, user: HostDep):
    await _own_venue(vid, user)
    await db.venue_vips.update_one({"venue_id": vid, "user_id": uid}, {"$set": {"active": False, "updated_at": datetime.now(timezone.utc)}})
    return {"vip": False}


async def vip_ids(venue_id: Optional[str], user_ids: list) -> dict:
    """{user_id: note} for active VIPs at this venue."""
    if not venue_id or not user_ids:
        return {}
    return {v["user_id"]: v.get("note") async for v in db.venue_vips.find({"venue_id": venue_id, "user_id": {"$in": user_ids}, "active": True})}


async def vip_arrival(ticket: dict) -> None:
    """Background: a flagged VIP just checked in — tell the hosts and the door team on shift."""
    from routes.features import host_ids  # noqa: E402

    ev = await db.events.find_one({"id": ticket["event_id"]}, {"_id": 0})
    if not ev:
        return
    vips = await vip_ids(ev.get("venue_id"), [ticket["user_id"]])
    if ticket["user_id"] not in vips:
        return
    u = await db.users.find_one({"id": ticket["user_id"]}, {"_id": 0, "full_name": 1})
    name = (u or {}).get("full_name") or "Your VIP"
    party = f" (+{ticket['quantity'] - 1})" if ticket["quantity"] > 1 else ""
    note = f" · {vips[ticket['user_id']]}" if vips[ticket["user_id"]] else ""
    staff = [s["user_id"] async for s in db.door_staff.find({"venue_id": ev.get("venue_id"), "active": True, "user_id": {"$ne": None}}, {"_id": 0})
             if on_shift(s, ev["id"])]
    notify(await host_ids(ev) + staff, f"⭐ VIP arrived: {name}{party}", f"Just checked in at {ev['title']}{note}",
           f"/host/live/{ev['id']}", key=f"vip-{ticket['id']}", kind="door_rush")


# ---------- Monthly venue report ----------

REPORT_DAY_HOUR_UTC = 16  # 1st of the month


def _month_bounds(d: datetime) -> tuple[datetime, datetime]:
    """Calendar month in venue (California) time, returned as UTC instants."""
    from routes.alerts import VENUE_TZ  # noqa: E402

    local = (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(VENUE_TZ)
    start = datetime(local.year, local.month, 1, tzinfo=VENUE_TZ)
    nxt = start + timedelta(days=32)
    end = datetime(nxt.year, nxt.month, 1, tzinfo=VENUE_TZ)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


async def venue_month(venue_id: str, start: datetime, end: datetime) -> dict:
    from routes.alerts import night_stats  # noqa: E402

    # only nights that have happened — upcoming pre-sales would drag the show-up rate down
    events = await db.events.find({"venue_id": venue_id, "date": {"$gte": start, "$lt": min(end, datetime.now(timezone.utc))}},
                                  {"_id": 0}).to_list(None)
    sold = arrived = 0
    for ev in events:
        s = await night_stats(ev)
        sold += s["sold"]
        arrived += s["arrived"]
    rev = await db.venue_payables.aggregate([{"$match": {"venue_id": venue_id, "created_at": {"$gte": start, "$lt": end}}},
                                             {"$group": {"_id": None, "n": {"$sum": "$amount"}}}]).to_list(1)
    fb = await db.feedback.aggregate([{"$match": {"venue_id": venue_id, "created_at": {"$gte": start, "$lt": end}}},
                                      {"$group": {"_id": None, "avg": {"$avg": "$rating"}, "n": {"$sum": 1}}}]).to_list(1)
    return {"events": len(events), "sold": sold, "arrived": arrived,
            "show_rate": round(100 * arrived / sold, 1) if sold else None,
            "revenue": round(rev[0]["n"], 2) if rev else 0.0,
            "rating": round(fb[0]["avg"], 2) if fb else None, "ratings": fb[0]["n"] if fb else 0}


def _local(d: datetime) -> datetime:
    from routes.alerts import VENUE_TZ  # noqa: E402

    return d.astimezone(VENUE_TZ)


def _chg(now, before) -> Optional[int]:
    return round(100 * (now - before) / before) if now is not None and before else None


async def venue_report(venue: dict, month_start: datetime) -> dict:
    prev_start, _ = _month_bounds(month_start - timedelta(days=1))
    cur = await venue_month(venue["id"], *_month_bounds(month_start))
    prev = await venue_month(venue["id"], prev_start, month_start)
    change = {k: _chg(cur[k], prev[k]) for k in ("arrived", "revenue", "show_rate", "rating")}
    return {"venue_id": venue["id"], "venue_name": venue["name"], "month": _local(month_start).strftime("%B %Y"),
            "current": cur, "previous": prev, "change": {k: v for k, v in change.items() if v is not None}}


def report_html(owner_name: str, reports: list) -> str:
    from html import escape

    def cell(v, kind):
        if v is None:
            return "—"
        return f"${v:,.2f}" if kind == "revenue" else f"{v:g}%" if kind == "show_rate" else f"{v:.2f}★" if kind == "rating" else str(v)

    def chg(c):
        if c is None:
            return ""
        color = "#15803d" if c > 0 else "#b91c1c" if c < 0 else "#666"
        return f'<span style="color:{color};font-weight:bold">{"+" if c > 0 else ""}{c}%</span>'

    blocks = ""
    for r in reports:
        cur, prev, c = r["current"], r["previous"], r["change"]
        rows = "".join(
            f'<tr><td style="padding:6px 16px 6px 0;color:#666">{label}</td><td style="padding:6px 16px 6px 0;font-weight:bold">{cell(cur[k], k)}</td>'
            f'<td style="padding:6px 16px 6px 0;color:#666">{cell(prev[k], k)}</td><td>{chg(c.get(k))}</td></tr>'
            for k, label in (("events", "Events"), ("arrived", "Guests in"), ("show_rate", "Show-up rate"), ("revenue", "Your revenue"), ("rating", "Guest rating")))
        blocks += (f'<h3 style="margin:20px 0 6px">{escape(r["venue_name"])}</h3><table role="presentation">'
                   '<tr><td></td><td style="color:#666;font-size:12px">This month</td><td style="color:#666;font-size:12px">Month before</td><td></td></tr>'
                   f"{rows}</table>")
    month = reports[0]["month"] if reports else ""
    return ('<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#111">'
            f'<h2 style="margin:0 0 8px">Your {escape(month)} report</h2><p>Hi {escape(owner_name.split(" ")[0])}, here is how your venues did.</p>'
            f'{blocks}<p style="font-size:12px;color:#888;margin-top:24px">Turn off monthly reports under Profile &rarr; Notifications.</p>'
            "</td></tr></table>")


async def send_monthly_reports(force_month: Optional[datetime] = None) -> int:
    """1st of each month: every venue owner gets last month's report (push + email), once per month."""
    from routes.engage import wants  # noqa: E402
    from routes.notify import background  # noqa: E402
    from services.emailer import send_email  # noqa: E402

    now = datetime.now(timezone.utc)
    if force_month is None:
        if now.day != 1 or now.hour < REPORT_DAY_HOUR_UTC:
            return 0
        month_start, _ = _month_bounds(now - timedelta(days=1))
        key = _local(month_start).strftime("%Y-%m")
        try:
            await db.settings.update_one({"_id": "venue_report", "month": {"$ne": key}}, {"$set": {"month": key}}, upsert=True)
        except DuplicateKeyError:
            return 0
    else:
        month_start, _ = _month_bounds(force_month)
    owners: dict = {}
    async for v in db.venues.find({"owner_id": {"$ne": None}}, {"_id": 0, "id": 1, "name": 1, "owner_id": 1}):
        owners.setdefault(v["owner_id"], []).append(v)
    sent = 0
    for owner_id, venues in owners.items():
        owner = await db.users.find_one({"id": owner_id}, {"_id": 0})
        if not owner:
            continue
        reports = [await venue_report(v, month_start) for v in venues]
        guests = sum(r["current"]["arrived"] for r in reports)
        revenue = sum(r["current"]["revenue"] for r in reports)
        notify([owner_id], f"Your {reports[0]['month']} report 📊", f"{guests} guests · ${revenue:,.2f} across {len(venues)} venue{'s' if len(venues) > 1 else ''}. Tap for trends.",
               "/host", key=f"report-{_local(month_start):%Y-%m}-{owner_id}", kind="updates")
        if owner.get("email") and wants(owner, "monthly"):
            background(send_email(to=owner["email"], subject=f"Your {reports[0]['month']} venue report",
                                  html=report_html(owner.get("full_name") or "there", reports)))
        sent += 1
    return sent


class MonthReport(BaseModel):
    venue_id: str
    venue_name: str
    month: str
    current: dict
    previous: dict
    change: dict


@router.get("/host/report", response_model=List[MonthReport])
async def my_report(user: HostDep, month: Optional[str] = None):
    """In-app copy of the monthly report. `month` = YYYY-MM (default: current month so far)."""
    try:
        d = datetime.strptime(month, "%Y-%m").replace(day=15, tzinfo=timezone.utc) if month else datetime.now(timezone.utc)
    except ValueError:
        raise HTTPException(400, "Month must look like 2026-05")
    start, _ = _month_bounds(d)
    filt = {} if user["role"] == "admin" else {"owner_id": user["id"]}
    return [MonthReport(**await venue_report(v, start)) async for v in db.venues.find(filt, {"_id": 0, "id": 1, "name": 1})]


@router.get("/host/report.csv")
async def my_report_csv(user: HostDep, month: Optional[str] = None):
    """Spreadsheet of a month for accounting: one row per event, then a total row per venue."""
    import csv
    import io

    from fastapi.responses import Response

    from routes.alerts import VENUE_TZ, night_stats  # noqa: E402

    try:
        d = datetime.strptime(month, "%Y-%m").replace(day=15, tzinfo=timezone.utc) if month else datetime.now(timezone.utc)
    except ValueError:
        raise HTTPException(400, "Month must look like 2026-05")
    start, end = _month_bounds(d)
    held_until = min(end, datetime.now(timezone.utc))

    def safe(v):  # stop spreadsheet apps from running titles like "=HYPERLINK(...)" as formulas
        return f"'{v}" if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Month", "Venue", "Date", "Event", "Tickets sold", "Guests in", "Show-up %", "No-shows", "Tables booked",
                "Ticket & table revenue (USD)", "Avg rating", "Ratings"])
    filt = {} if user["role"] == "admin" else {"owner_id": user["id"]}
    label = start.astimezone(VENUE_TZ).strftime("%Y-%m")
    async for v in db.venues.find(filt, {"_id": 0, "id": 1, "name": 1}).sort("name", 1):
        async for ev in db.events.find({"venue_id": v["id"], "date": {"$gte": start, "$lt": held_until}}, {"_id": 0}).sort("date", 1):
            s = await night_stats(ev)
            fb = await db.feedback.aggregate([{"$match": {"event_id": ev["id"]}},
                                              {"$group": {"_id": None, "avg": {"$avg": "$rating"}, "n": {"$sum": 1}}}]).to_list(1)
            w.writerow([label, safe(v["name"]), _aware(ev["date"]).astimezone(VENUE_TZ).strftime("%Y-%m-%d %H:%M"), safe(ev["title"]),
                        s["sold"], s["arrived"], round(100 * s["arrived"] / s["sold"], 1) if s["sold"] else "",
                        s["no_shows"], s["tables"], f"{s['revenue']:.2f}", round(fb[0]["avg"], 2) if fb else "", fb[0]["n"] if fb else 0])
        m = await venue_month(v["id"], start, end)
        w.writerow([label, safe(v["name"]), "TOTAL", f"{m['events']} events held so far (revenue incl. reservations)", m["sold"], m["arrived"],
                    m["show_rate"] if m["show_rate"] is not None else "", max(0, m["sold"] - m["arrived"]), "",
                    f"{m['revenue']:.2f}", m["rating"] if m["rating"] is not None else "", m["ratings"]])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="nocturne-report-{label}.csv"'})
