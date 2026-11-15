"""Privacy policy & support pages (public web URLs for the store listing) and in-app problem reports."""
import os
import uuid
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Annotated, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from routes.push import notify
from server import current_user, db, require_roles

router = APIRouter(prefix="/api")
UserDep = Annotated[dict, Depends(current_user)]
AdminDep = Annotated[dict, Depends(require_roles("admin"))]
APP_NAME = "Nocturne"
UPDATED = "June 2026"


def _support_email() -> str:
    return os.environ.get("SUPPORT_EMAIL", "").strip()


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{escape(title)} · {APP_NAME}</title><style>"
        "body{margin:0;background:#0b0b0d;color:#e9e6df;font:16px/1.6 -apple-system,Segoe UI,Roboto,Arial,sans-serif}"
        "main{max-width:760px;margin:0 auto;padding:32px 20px 64px}h1{color:#d4af37;font-size:28px;margin:0 0 4px}"
        "h2{font-size:18px;margin:28px 0 8px;color:#fff}a{color:#d4af37}.muted{color:#9a968d;font-size:14px}li{margin:4px 0}"
        f"</style></head><body><main>{body}</main></body></html>"
    )


def _contact_line() -> str:
    email = _support_email()
    mail = f' or email <a href="mailto:{escape(email)}">{escape(email)}</a>' if email else ""
    return f"use <strong>Profile → Help &amp; support → Report a problem</strong> in the app{mail}"


@router.get("/legal/privacy", response_class=HTMLResponse)
async def privacy_page():
    return _page("Privacy Policy", f"""
<h1>Privacy Policy</h1><p class="muted">{APP_NAME} · Last updated {UPDATED}</p>
<p>{APP_NAME} is a members app for nightlife and hospitality: events, tickets, VIP tables, venue reservations, memberships,
concierge requests and tools for promoters and venues. This policy explains what we collect, why, and the choices you have.</p>
<h2>What we collect</h2><ul>
<li><strong>Account details:</strong> name, email, password (stored hashed) or your Google sign-in, phone and city if you add them, your role (guest, promoter, venue).</li>
<li><strong>Bookings &amp; purchases:</strong> tickets, table and venue reservations, memberships, gifts, guest-list and waitlist requests, check-ins, reward points and credits.</li>
<li><strong>Payments:</strong> handled by Stripe. We receive the payment status and amount, never your full card number.</li>
<li><strong>Messages &amp; feedback:</strong> concierge chat messages, event ratings and comments, and problem reports you send us.</li>
<li><strong>Device data:</strong> a push notification token if you allow notifications. The camera is used only to scan ticket QR codes and no images are stored.</li>
<li><strong>Preferences:</strong> your email and notification choices and marketing opt-in.</li></ul>
<h2>How we use it</h2><ul>
<li>To run your account and deliver what you book: tickets, tables, reservations, memberships and concierge help.</li>
<li>To send booking confirmations, receipts, reminders and the alerts you choose; marketing only if you opt in.</li>
<li>To let venues and promoters manage their events: guest lists, check-ins, payouts and summaries.</li>
<li>To keep the service safe, prevent fraud, and fix problems you report.</li></ul>
<h2>Who we share it with</h2><ul>
<li><strong>Venues and promoters</strong> see the guest details they need for the events you book: your name, party size, check-in status and feedback.</li>
<li><strong>Service providers:</strong> Stripe (payments and payouts), our email provider (transactional emails), our push notification provider, Google (if you sign in with Google), and our cloud hosting.</li>
<li>Our admins can use an AI writing assistant to draft newsletters. Member personal data is not sent to it.</li>
<li>We do not sell your personal data and we do not show third-party ads.</li></ul>
<h2>How long we keep it</h2>
<p>We keep your data while your account is active. Booking and payment records may be kept longer where the law requires it, for example for tax and accounting.</p>
<h2>Your choices &amp; rights</h2><ul>
<li>Change email and notification preferences any time under <strong>Profile → Notifications</strong>.</li>
<li>Ask us for a copy of your data, or for corrections or deletion of your account and data: {_contact_line()}. We reply within 30 days.</li></ul>
<h2>Age</h2><p>{APP_NAME} is for adults aged 18 and over (21+ where venues require it). We do not knowingly collect data from children.</p>
<h2>Security</h2><p>Data is sent over encrypted connections (HTTPS), passwords are hashed, and access to personal data is limited to people who need it.</p>
<h2>Changes</h2><p>If we change this policy we will update the date above and, for significant changes, tell you in the app.</p>
<h2>Contact</h2><p>Questions about privacy: {_contact_line()}.</p>""")


@router.get("/legal/support", response_class=HTMLResponse)
async def support_page():
    email = _support_email()
    mail = f'<p>Email: <a href="mailto:{escape(email)}">{escape(email)}</a></p>' if email else ""
    return _page("Support", f"""
<h1>Help &amp; Support</h1><p class="muted">{APP_NAME}</p>
<p>The fastest way to reach us is in the app: <strong>Profile → Help &amp; support → Report a problem</strong>.
Tell us what happened and our team will follow up, usually within one business day.</p>{mail}
<h2>Common questions</h2><ul>
<li><strong>Where is my ticket?</strong> Profile → My tickets. Show the QR code at the door.</li>
<li><strong>A payment went wrong:</strong> report it in the app with the event name. Refunds go back to your original card.</li>
<li><strong>Change notifications or emails:</strong> Profile → Notifications.</li>
<li><strong>Delete my account or data:</strong> send a request from Report a problem (choose "Account &amp; privacy").</li></ul>
<p><a href="/api/legal/privacy">Privacy Policy</a></p>""")


CATEGORIES = ("bug", "payment", "booking", "concierge", "account", "other")


class ReportIn(BaseModel):
    category: Literal["bug", "payment", "booking", "concierge", "account", "other"]
    message: str = Field(min_length=5, max_length=2000)
    context: Optional[str] = Field(default=None, max_length=80)  # e.g. "concierge", "profile"


class ReportOut(BaseModel):
    id: str
    user_id: str
    user_name: str
    user_email: str
    category: str
    message: str
    context: Optional[str] = None
    status: str
    created_at: datetime
    resolved_at: Optional[datetime] = None


@router.post("/support/reports", response_model=ReportOut, status_code=201)
async def create_report(body: ReportIn, user: UserDep):
    if len(body.message.strip()) < 5:
        raise HTTPException(422, "Please describe the problem in a few words")
    since = datetime.now(timezone.utc) - timedelta(hours=1)  # rolling hour
    if await db.support_reports.count_documents({"user_id": user["id"], "created_at": {"$gte": since}}) >= 10:
        raise HTTPException(429, "You've sent a lot of reports this hour — we're on it. Please try again later.")
    doc = {"id": str(uuid.uuid4()), "user_id": user["id"], "user_name": user.get("full_name") or "", "user_email": user["email"],
           "category": body.category, "message": body.message.strip(), "context": body.context, "status": "open",
           "created_at": datetime.now(timezone.utc), "resolved_at": None}
    await db.support_reports.insert_one(doc)
    doc.pop("_id", None)
    admins = [a["id"] async for a in db.users.find({"role": "admin"}, {"id": 1})]
    notify(admins, f"New problem report · {body.category}", f"{doc['user_name'] or doc['user_email']}: {doc['message'][:120]}",
           "/admin/reports", key=f"report-{doc['id']}", kind="updates")
    return ReportOut(**doc)


@router.get("/support/reports/mine", response_model=List[ReportOut])
async def my_reports(user: UserDep):
    return [ReportOut(**r) async for r in db.support_reports.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(20)]


@router.get("/admin/reports", response_model=List[ReportOut])
async def admin_reports(user: AdminDep, status: Literal["open", "resolved", "all"] = "open"):
    filt = {} if status == "all" else {"status": status}
    return [ReportOut(**r) async for r in db.support_reports.find(filt, {"_id": 0}).sort("created_at", -1).limit(200)]


class ReportStatusIn(BaseModel):
    status: Literal["open", "resolved"]


@router.put("/admin/reports/{rid}", response_model=ReportOut)
async def set_report_status(rid: str, body: ReportStatusIn, user: AdminDep):
    upd = {"status": body.status, "resolved_at": datetime.now(timezone.utc) if body.status == "resolved" else None,
           "resolved_by": user["id"] if body.status == "resolved" else None}
    r = await db.support_reports.find_one_and_update({"id": rid}, {"$set": upd}, projection={"_id": 0}, return_document=True)
    if not r:
        raise HTTPException(404, "Report not found")
    if body.status == "resolved":
        notify([r["user_id"]], "Your report was resolved ✅", f"Thanks for letting us know: “{r['message'][:80]}”", "/support",
               key=f"report-done-{rid}", kind="updates")
    return ReportOut(**r)
