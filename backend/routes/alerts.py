"""Scheduled & live push alerts: door rush (hosts), waitlist spots, VIP table upsell, weekly promoter recap."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from routes.push import notify
from server import LEVEL_RANK, db, user_level

log = logging.getLogger("alerts")
ALERTS_EVERY_S = 300
DOOR_STEP = 25  # notify hosts every 25 guests through the door
UPSELL_WINDOW = (timedelta(hours=2), timedelta(hours=10))  # event day, before the 2-hour night alert
RECAP_HOUR_UTC = 16  # Mondays


def _now():
    return datetime.now(timezone.utc)


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# ---------- Door rush (called right after a check-in) ----------

async def bump_checkins(event_id: str, qty: int) -> int:
    """Atomically adds `qty` to the event's live door count; returns the new total."""
    ev = await db.events.find_one_and_update({"id": event_id, "checked_in_count": {"$exists": True}},
                                             {"$inc": {"checked_in_count": qty}}, projection={"checked_in_count": 1},
                                             return_document=ReturnDocument.AFTER)
    if ev:
        return ev["checked_in_count"]
    # first scan since this counter existed: start it from the tickets already through the door
    agg = await db.tickets.aggregate([{"$match": {"event_id": event_id, "checked_in": True}},
                                      {"$group": {"_id": None, "n": {"$sum": "$quantity"}}}]).to_list(1)
    total = agg[0]["n"] if agg else qty
    res = await db.events.update_one({"id": event_id, "checked_in_count": {"$exists": False}}, {"$set": {"checked_in_count": total}})
    return total if res.modified_count else await bump_checkins(event_id, qty)


async def door_rush(event_id: str, qty: int, total: int) -> None:
    from routes.features import host_ids  # noqa: E402

    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        return
    prev = total - qty
    cap = ev.get("capacity") or 0
    pct = f" · {round(100 * total / cap)}% of capacity" if cap else ""
    if prev <= 0 < total:
        title, msg, mark = "Doors are open 🚪", f"First guests just checked in at {ev['title']}{pct}.", "first"
    elif total // DOOR_STEP > max(prev, 0) // DOOR_STEP:
        title, msg, mark = f"{total} guests in", f"{ev['title']} is filling up{pct}.", str(total // DOOR_STEP)
    else:
        return
    notify(host_ids(ev), title, msg, f"/host/live/{event_id}", key=f"door-{event_id}-{mark}", kind="door_rush")


# ---------- Waitlist: a spot opened ----------

async def send_waitlist_spots() -> int:
    """Waitlisted guests hear once when enough spots free up for their party (open-entry events only)."""
    sent = 0
    async for r in db.event_requests.find({"kind": "waitlist", "status": "pending", "spot_alert_sent": {"$ne": True}}, {"_id": 0}):
        ev = await db.events.find_one({"id": r["event_id"]}, {"_id": 0})
        if not ev or ev.get("approval_required") or _aware(ev["date"]) < _now():
            continue
        if ev.get("capacity", 10**6) - ev.get("tickets_sold", 0) < r["quantity"]:
            continue
        if await db.tickets.find_one({"event_id": ev["id"], "user_id": r["user_id"]}, {"_id": 1}):
            continue
        res = await db.event_requests.update_one({"id": r["id"], "spot_alert_sent": {"$ne": True}}, {"$set": {"spot_alert_sent": True}})
        if not res.modified_count:
            continue
        notify([r["user_id"]], "A spot just opened ✨", f"There's room for you at {ev['title']}. Tap to grab it before it's gone.",
               f"/event/{ev['id']}", key=f"spot-{r['id']}", kind="updates")
        sent += 1
    return sent


# ---------- VIP table upsell on event day ----------

async def send_table_offers() -> int:
    now = _now()
    sent = 0
    async for t in db.tickets.find({"event_date": {"$gt": now + UPSELL_WINDOW[0], "$lte": now + UPSELL_WINDOW[1]},
                                    "table_offer_sent": {"$ne": True}}, {"_id": 0}):
        ev = await db.events.find_one({"id": t["event_id"]}, {"_id": 0, "tables": 1, "title": 1, "venue_name": 1})
        user = await db.users.find_one({"id": t["user_id"]}, {"_id": 0})
        if not ev or not ev.get("tables") or not user:
            continue
        if await db.table_bookings.find_one({"event_id": t["event_id"], "user_id": t["user_id"], "status": "confirmed"}, {"_id": 1}):
            continue
        booked = {b["table_id"] async for b in db.table_bookings.find({"event_id": t["event_id"], "status": "confirmed"}, {"table_id": 1})}
        rank = LEVEL_RANK.get(user_level(user), 0)
        open_ = [x for x in ev["tables"] if x["id"] not in booked and LEVEL_RANK.get(x.get("min_level", "bronze"), 0) <= rank]
        if not open_:
            continue
        res = await db.tickets.update_one({"id": t["id"], "table_offer_sent": {"$ne": True}}, {"$set": {"table_offer_sent": True}})
        if not res.modified_count:
            continue
        low = min(x["min_spend"] for x in open_)
        notify([t["user_id"]], "VIP tables still open tonight 🥂",
               f"Upgrade your night at {ev.get('venue_name') or ev['title']} — {len(open_)} table{'s' if len(open_) > 1 else ''} left from ${low:,.0f}.",
               f"/event/{t['event_id']}?tables=1", key=f"upsell-{t['id']}", kind="table_offers")
        sent += 1
    return sent


# ---------- Weekly promoter recap (Mondays) ----------

async def send_promoter_recap(force: bool = False) -> int:
    from routes.growth import _rank  # noqa: E402

    now = _now()
    week = now.strftime("%G-W%V")
    if not force:
        if now.weekday() != 0 or now.hour < RECAP_HOUR_UTC:
            return 0
        try:  # once per ISO week, even with several workers
            await db.settings.update_one({"_id": "promoter_recap", "week": {"$ne": week}}, {"$set": {"week": week}}, upsert=True)
        except DuplicateKeyError:
            return 0
    since = now - timedelta(days=7)
    rows = await db.tickets.aggregate([
        {"$match": {"promoter_id": {"$ne": None}, "created_at": {"$gte": since}}},
        {"$group": {"_id": "$promoter_id", "guests": {"$sum": "$quantity"}, "earnings": {"$sum": "$promoter_earning"}}},
    ]).to_list(None)
    week_stats = {r["_id"]: r for r in rows}
    ranks = {e.user_id: i + 1 for i, e in enumerate(await _rank(now.strftime("%Y-%m"), 200))}
    days = await _daily_earnings(since)
    sent = 0
    emails = []
    async for p in db.users.find({"role": "promoter"}, {"_id": 0, "id": 1, "email": 1, "full_name": 1, "email_prefs": 1}):
        s = week_stats.get(p["id"])
        rank = f" · #{ranks[p['id']]} this month" if p["id"] in ranks else ""
        if s and s["guests"]:
            msg = f"Last week: {s['guests']} guest{'s' if s['guests'] > 1 else ''} · ${s['earnings']:,.2f} earned{rank}. Keep it going!"
        else:
            msg = f"Quiet week{rank}. Share your link tonight to climb the leaderboard."
        notify([p["id"]], "Your weekly recap 📈", msg, "/(tabs)/promote", key=f"recap-{week}-{p['id']}", kind="sales")
        if p.get("email") and (p.get("email_prefs") or {}).get("recap", True):
            emails.append((p, s or {"guests": 0, "earnings": 0.0}, ranks.get(p["id"]), days.get(p["id"], {})))
        sent += 1
    if emails:
        from routes.notify import background  # noqa: E402

        background(_recap_emails(emails, since))
    return sent


async def _daily_earnings(since: datetime) -> dict:
    """{promoter_id: {YYYY-MM-DD: (guests, earnings)}} for the last 7 days (UTC)."""
    rows = await db.tickets.aggregate([
        {"$match": {"promoter_id": {"$ne": None}, "created_at": {"$gte": since}}},
        {"$group": {"_id": {"p": "$promoter_id", "d": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}}},
                    "g": {"$sum": "$quantity"}, "e": {"$sum": "$promoter_earning"}}},
    ]).to_list(None)
    out: dict = {}
    for r in rows:
        out.setdefault(r["_id"]["p"], {})[r["_id"]["d"]] = (r["g"], r["e"])
    return out


def recap_html(name: str, stats: dict, rank, days: dict, since: datetime) -> str:
    from html import escape

    from services.emailer import EMAIL_FROM_NAME

    labels = [(since + timedelta(days=i + 1)) for i in range(7)]
    vals = [days.get(d.strftime("%Y-%m-%d"), (0, 0.0)) for d in labels]
    top = max([v[1] for v in vals] + [0.01])
    bars = "".join(
        f'<td valign="bottom" align="center" style="padding:0 4px;font-size:11px;color:#666">'
        f'<div style="font-size:10px;color:#111">{"$" + format(e, ",.0f") if e else ""}</div>'
        f'<div style="width:28px;height:{max(2, round(110 * e / top))}px;background:{"#d4af37" if e else "#e5e5e5"};border-radius:4px 4px 0 0"></div>'
        f'{d.strftime("%a")}</td>' for d, (_, e) in zip(labels, vals))
    rank_line = f"<p>You're <strong>#{rank}</strong> on this month's leaderboard.</p>" if rank else ""
    nudge = ("<p>Keep the momentum — share your link before the weekend.</p>" if stats["guests"]
             else "<p>Quiet week. Share your link tonight to start climbing the leaderboard.</p>")
    brand = escape(EMAIL_FROM_NAME)
    return (
        '<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#111">'
        f'<h2 style="margin:0 0 12px">Your weekly recap</h2><p>Hi {escape(name.split(" ")[0])}, here is your last 7 days.</p>'
        f'<table role="presentation" style="margin:8px 0 16px"><tr>'
        f'<td style="padding-right:24px"><div style="font-size:12px;color:#666">Guests</div><div style="font-size:24px;font-weight:bold">{stats["guests"]}</div></td>'
        f'<td><div style="font-size:12px;color:#666">Earned</div><div style="font-size:24px;font-weight:bold">${stats["earnings"]:,.2f}</div></td>'
        f'</tr></table><table role="presentation" style="border-bottom:1px solid #ddd"><tr>{bars}</tr></table>'
        f'{rank_line}{nudge}<p style="font-size:12px;color:#888;margin-top:24px">Sent by {brand}. Turn off the weekly recap under '
        "Profile &rarr; Notifications.</p></td></tr></table>"
    )


async def _recap_emails(items: list, since: datetime) -> None:
    from services.emailer import send_email  # noqa: E402

    for p, stats, rank, days in items:
        try:
            await send_email(to=p["email"], subject=f"Your week: {stats['guests']} guests · ${stats['earnings']:,.2f} earned",
                             html=recap_html(p.get("full_name") or "there", stats, rank, days, since))
        except Exception:
            log.exception("recap email failed for %s", p["id"])
        await asyncio.sleep(0.6)  # stay under the email provider's rate limit


async def alerts_loop() -> None:
    while True:
        for job in (send_waitlist_spots, send_table_offers, send_promoter_recap):
            try:
                await job()
            except Exception:
                log.exception("%s failed", job.__name__)
        await asyncio.sleep(ALERTS_EVERY_S)
