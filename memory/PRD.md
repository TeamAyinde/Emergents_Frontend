# Nocturne — PRD

## Original problem statement
Money-making hospitality app (founder has construction/club/nightlife/lounge/restaurant/chef experience). Event planning, marketing/promotion, promoters getting paid. Users: promoters, venues/clubs/restaurants, guests, event planners, corporate clients. Revenue: ticketing % fee, venue booking marketplace, table/bottle reservations (15–25% fee on top), $2 withdrawal fee, monthly membership (free for women, first month free for men, business owners pay, premium guests pay more). Sign in with email, phone, Google, Apple. Emulate Partiful, Eventbrite, Kickback. Dark black/gold/neon + dark red. Full list of California hospitality businesses, nationwide later.

## Architecture
- Expo Router (SDK 58) frontend, FastAPI + MongoDB backend, JWT email/password auth (bcrypt), token in SecureStore (localStorage on web)
- Seed data (seed.py, idempotent on startup): 4 test users, 8 CA venues, 8 events

## Implemented (Nov 2026)
- Welcome / sign-in / 3-step sign-up (role → tier → details); paid tiers can't be self-assigned
- Tabs: Home (event feed + filter chips), Promote (earnings stats, referral code + QR, share, leaderboard), Venues (search, grid), Profile (tier badge, wallet + withdraw for staff, tickets, reservations, sign out)
- Event details: quantity, promoter code, 15% fee breakdown, buy → ticket QR screen
- Venue details: table/booth/bottle (server-priced), night picker, party size, notes, 15% fee
- Promoter earns 40% of platform fee; no self-referral; $2 withdrawal fee; atomic wallet updates
- Staff check-in by short code or full ticket id (atomic)
- PAYMENTS ARE SIMULATED (no real charges yet)

## Backlog
- P0: Real payments (Stripe) for tickets/reservations/memberships; Stripe Connect payouts to promoters
- P0: Google / Apple / phone sign-in
- P1: Camera QR scanning for check-in; venue owner event creation UI; admin dashboard (approvals, commissions)
- P1: In-app chat venue ↔ promoter; membership billing (trial expiry, premium perks)
- P2: Full California venue directory import; event planner / corporate booking flow; guest deals & discounts

## Iteration 3 — Newsletter, Luxe partners, Admin
- In-app Nocturne Journal (nightlife / travel / luxury), AI drafts (Claude Sonnet, streamed) that the admin edits and publishes
- Marketing opt-in at sign-up (ticked by default) + Profile toggle; admin-only CSV export of opted-in members (phone, city, level). Bulk email blasts are NOT sent from the app (Emergent email is transactional-only)
- Luxe Services marketplace: hotels, black cars, limos, exotic cars, mansions, yachts, private jets, helicopters, private chefs, security; booking requests confirmed by the admin
- Admin dashboard: revenue by source, members by level, concierge inbox, journal, luxe requests

## Iteration 4 — Bronze / Silver / Gold
- Bronze $14.99 (free for women, first month free for men), Silver $49, Gold $149 (upgrade simulated)
- Silver-only and Gold-only venues, events and services; concierge fee 25/20/15%; ticket discount 0/10/20%; public rate vs member rate with savings shown

## Iteration 5 — Copied from competitors (Velocity Black, Posh, Tablelist, Partiful, DICE)
- Personal concierge chat (member ↔ admin team, Gold answered first, unread badges, 4s polling)
- Interactive table map per event (Main Floor / VIP / Stage Skybox, min spend, tier-locked sections, one booking per table)
- Guest list: approval-only events, +1 limits, who's going, waitlist when sold out; atomic capacity (no overselling)
- Host Studio for venue owners: post events (cover, date/time, price, capacity, tier, +1s, tags, approval, tables), manage requests, guest list, table bookings
- Timezone-correct dates (UTC with Z)

## Backlog
- P0: Real payments (Stripe) for tickets, tables, luxe, memberships; Stripe Connect promoter payouts
- P0: Google / Apple / phone sign-in
- P1: Camera QR scanning for check-in; reward points; members perks wallet; event photo albums
- P2: Real California business directory import; event planner / corporate packages

## Iteration 6 — Rewards, Perks, Camera check-in
- Reward points: 1 pt per $1 (Silver 1.5×, Gold 2×) on tickets, tables, reservations, confirmed luxe bookings; redeem 100 pts = $5 credit, auto-applied to tickets
- Members perks wallet: 9 partner perks gated by tier; claim reveals code
- Camera QR scanning on /checkin (expo-camera, pre-permission screen, Open Settings when blocked, manual fallback)
- Event page shows "You're going · View ticket" when the member already has a ticket

## Still to do (needs user setup)
- Stripe real payments (tickets, tables, luxe, memberships) + Stripe Connect promoter payouts — needs the user's Stripe account
- Google login (Emergent managed) and Apple login (needs Apple Developer account + native build)

## Iteration 7 — Real payments (Stripe test mode), Google sign-in, payouts
- Stripe Checkout (hosted page; works on web + Expo Go) for tickets, table deposits, venue reservations, membership upgrades (30 days). Server-side pricing, webhook + status polling, idempotent fulfilment
- Marketplace money flow: guest pays Nocturne → Nocturne keeps fees, logs venue share in `venue_payables`, promoter commission in wallet
- Reward credit reserved at checkout, refunded on cancel/expiry/failure; one open checkout per item; paid-but-unfulfillable flagged `needs_refund`
- Direct paid endpoints return 402; paid approval events: host approves → guest pays → ticket
- Admin Payouts screen (venues owed, pending promoter withdrawals, mark paid); host `/api/host/payouts`
- Emergent-managed Google sign-in (welcome + sign-in) alongside email/password; issues the same JWT
- Backlog: Stripe Connect automatic bank payouts (needs the owner's own Stripe account with Connect), recurring membership billing, Apple sign-in (native build)

## Iteration 8 — Own Stripe key, subscriptions, boosts, Connect payouts
- stripe_core.py: uses owner's STRIPE_API_KEY when it's a secret key (sk_/rk_), else falls back to the Emergent test proxy. Auto-registers webhook with own key. Webhook re-fetches every object from Stripe (no payload trust)
- Memberships are monthly Stripe subscriptions (auto-renew); gentlemen (trial_male) get 7-day free trial on Bronze with card upfront, then $14.99/mo. Cancel/resume auto-renew in Membership screen. Free Bronze for ladies
- Featured venue boosts: $49/7 days, $149/30 days (Host Studio). Featured venues + their events sorted first with FEATURED badge
- Stripe Connect Express for promoters & venue owners (/payout-settings). Withdrawals auto-transfer when bank linked; admin "settle" transfers to venue owner when linked. Requires own secret key + Connect enabled (preview currently uses proxy → shows "Coming soon")
- PENDING: user's STRIPE_API_KEY currently holds a publishable key (pk_live) in live slot and empty test slot — needs sk_test_/sk_live_ secret keys

## Iteration 11 — Earnings, Yearly Gold, Spotlight
- Host Studio Earnings card (/api/host/earnings): owed, paid, by source, recent
- Gold yearly plan $1,490/year (Stripe yearly subscription); monthly/yearly toggle on Gold
- Promoter Event Spotlight $39/3 days, $79/7 days; spotlighted events top of feed with SPOTLIGHT badge
- STILL PENDING: real Stripe secret key (user skipped secure card twice; key pasted in chat was masked and unusable)

## Iteration 12 — Leaderboard, Spotlight limits, Gifts (growth.py)
- Monthly promoter leaderboard by guests (/api/promoter/leaderboard/monthly); last month's winner auto-awarded $100 wallet bonus once (leaderboard_awards _id=month)
- Spotlight: promoter must have brought ≥1 guest with their code to that event; cap 2 spotlights/day (/api/spotlight/eligibility/{id})
- Gift memberships: checkout kind=gift (Silver $49 / Gold $149, 1 month) → GIFT-XXXXXX code; /api/gifts/mine, /api/gifts/redeem; user_level honours active gift_level/gift_until. Screen /gifts (Profile → Gifts)
- Saved STRIPE_API_KEY (both slots) starts with mk_ — not a Stripe secret key; app keeps using test proxy until an sk_/rk_ key is saved

## Iteration 13 — Gift email, gift status, monthly rank
- emailer.py (Emergent managed email, from_name Nocturne); gift codes emailed to recipient_email with escaped buyer note; gifts.email_status
- UserOut gift_level/gift_until (active only) → Profile shows 'Gifted Gold until …'
- Promoter stats rank = position on this month's leaderboard

## Iteration 14 — Emails
- notify.py: booking confirmation emails (ticket w/ QR image /api/tickets/{id}/qr.png, table, reservation) sent in background after paid fulfilment; winner announcement email on monthly award; POST /api/gifts/{id}/email resend/change recipient (max 3 successful sends, atomic)
- emailer skips seed/test addresses (@nocturne.app, test_*, @example.com) and treats rate_limited as pause

## Iteration 15 — Reminder, receipt, payout emails (notify.py)
- reminder_loop (every 15 min): tickets with event 20–28h away get a day-before email with QR (once per ticket, claim flag reminder_sent)
- Renewal receipts on invoice.paid billing_reason=subscription_cycle (own key only; invoice re-fetched; dedupe via receipts _id=invoice id)
- Venue payout summary email to owner after admin settle (by source, total, Stripe vs manual)
- settings.public_origin saved from https checkouts for QR image links

## Iteration 16 — Email prefs, feedback, win-back (engage.py)
- GET/PUT /api/me/email-prefs (reminders, receipts, feedback, offers; newsletter=marketing_opt_in); reminders & receipts honour prefs; booking confirmations always sent. Screen /email-settings (Profile → Email preferences)
- feedback_loop (30 min): tickets 8–36h after event get one 'Rate your night' email linking {public_origin}/feedback/{ticket_id}; POST /api/feedback/{ticket_id} rating 1–5 → +50 points once
- Win-back: cancelling auto-renew emails one-time 30% off (once per member); resuming applies a once-only Stripe coupon (own key only)
- Iter16 fixes: AuthGate remembers deep link (pendingPath) and returns after sign-in; feedback can_rate flag; partial prefs PUT; feedback retry off; email-settings rows tappable

## Iteration 17 — Venue ratings, host feedback, referrals
- feedback docs store venue_id/event_title/user_name; VenueOut guest_rating + guest_rating_count (list & detail); directory/venue page show guest average
- GET /api/host/feedback (owner's venues, guest first name only) → Host Studio 'Guest feedback' card
- Sign-up invite_code (guest) → referred_by; first paid night (payments._complete) rewards referrer 200 / friend 100 points once; GET /api/me/invites; Profile 'Invite friends' share row
- Iter17 fixes: referral reward outside fulfilment try; guest_rating shown only from 3 ratings, directory sorted by shown rating; invite copy-to-clipboard fallback (expo-clipboard); cleaned 19 orphan venue_payables, recomputed tickets_sold, reset negative wallet

## Session (June 2026) — pre-publish
- Backend reorganised: feature routers in `backend/routes/` (extras, features, rewards, payments, billing, growth, notify, engage, push); shared services in `backend/services/` (stripe_core, emailer, seed); ad-hoc helper scripts in `backend/scripts/`.
- Push notifications (Emergent managed relay): `POST /api/register-push` (auth, own user only); fire-and-forget pushes for new guest-list/waitlist requests & table bookings (to venue owner/event creator), request approved/declined (to guest), new reservations (to venue owner), concierge replies (to member). Frontend: `src/push.ts` (pre-permission prompt, weekly Settings nudge), handlers/channel/tap routing in `app/_layout.tsx`, `expo-notifications` plugin in app.json.
- Pending: user to add `google-services.json` (Firebase, package com.emergent.mymobileapp.qqzfhs) and set `expo.android.googleServicesFile` for Android push. Push works only in real builds (not Expo Go / web).
- Full regression passed (iteration 16/17).
- Added (iteration 17-18): push prefs `GET/PUT /api/me/push-prefs` {event_night, updates, concierge, sales}; event-night alert loop (push 2h before doors, once per ticket → /ticket/{id}); promoter sale push in `issue_ticket`; Notifications screen (`/email-settings`) with Phone alerts + Emails sections.
- Android push: frontend/google-services.json (Firebase project nocturne-276ce) wired via expo.android.googleServicesFile; API key sourced from secret FIREBASE_ANDROID_API_KEY.
- Added (iteration 19): `routes/alerts.py` — door rush pushes to hosts on check-in (first guests, every 25), waitlist "spot opened" push (open-entry events, once per request), event-day VIP table offer push (2–10h before, once per ticket) + in-app `TableUpsell` card on ticket screen, weekly promoter recap push (Mondays 16:00 UTC, once per ISO week). New push prefs: door_rush (hosts), table_offers.
- Added (iteration 20): table-offer push/card deep-link `/event/{id}?tables=1` auto-scrolls to table map; Monday recap email with 7-day earnings bar chart (email pref `recap`, promoters); host live door dashboard `/host/live/[id]` (GET /api/host/events/{eid}/live: count, capacity %, arrivals by hour, latest arrivals, waitlist; 5s refresh; door-rush push opens it); last-minute deals (POST /api/host/events/{eid}/deal pct 10/20/30/50, once per event, only when not full and waitlist exists; discount applied in ticket_price for those guests; GET /api/events/{eid}/my-deal; banner + breakdown row on event screen; DealCard on host event screen).
- Added (iteration 21): deal expiry (DealIn.hours 1/2/4/8, expires_at ≤ event start; ticket_price ignores expired deals; DealOut expires_at/expired); deal party limit (deal.user_qty from waitlist request quantity — discount only on up to that many tickets); door staff (`routes/staff.py`: GET/POST /api/host/staff, DELETE /api/host/staff/{id} soft-deactivates, GET /api/staff/duty; staff can check in tickets only for their venues and view /host/live (no deal info); `app/door.tsx`, DoorStaffCard in Host Studio, "Door duty" row on profile); morning-after night summary (alerts.send_night_summaries: events 10–36h past, once per event, push + email to hosts, email pref `summary`).
- Added (iteration 22): door-staff invites for people without an account (door_staff status "invited", user_id null; invite email with /sign-up?email= link when public_origin known; claimed on register & Google sign-up via routes.staff.claim_invites); deal results (DealOut buyers/tickets/revenue from deal guests' tickets bought between sent_at and expires_at; shown in DealCard, also after the event); door guest search GET /api/host/events/{eid}/guests?q= (owners/admin/staff) + GuestSearch card with manual check-in on /host/live; summary trends (alerts.night_report vs venue's previous 4 events; % change for guests/revenue/show-up rate in push, email and GET /api/host/events/{eid}/summary → SummaryCard on past host events).
- Added (iteration 23, `routes/venueops.py`): door shifts (door_staff.every_night default true; shift_event_ids; GET /api/host/events/{eid}/shifts, PUT /api/host/events/{eid}/shifts/{sid} {on}, PUT /api/host/staff/{sid}/schedule {every_night}; check-in, live view and /staff/duty respect shifts; ShiftsCard on host event screen); deal leaderboard GET /api/host/deals/leaderboard (per pct: deals, sent_to, buyers, tickets, revenue, conversion; Host Studio card); VIP guests (venue_vips; PUT/DELETE /api/host/venues/{vid}/vips/{uid}; star toggle in host guest list; VIP badges in live arrivals and guest search; on check-in VIP push to hosts + on-shift staff, kind door_rush); monthly venue report (1st of month 16:00 UTC, once per month via settings venue_report; push + email (pref `monthly`) with this vs previous month for guests, revenue, show-up rate, rating; GET /api/host/report?month= → MonthReportCard in Host Studio).
- Added (iteration 24): best-deal tip in DealCard (uses /api/host/deals/leaderboard; tip text + "★ Best" on top level when ≥2 levels tried); monthly report spreadsheet GET /api/host/report.csv?month=YYYY-MM (per-event rows + venue TOTAL rows; Content-Disposition attachment) with month chips + "Download spreadsheet" in MonthReportCard (web download; native expo-file-system File + expo-sharing share sheet via src/share-file.ts).
- Iteration 24 fixes: report months use California calendar months; CSV rows only held events + formula-safe cells; leaderboard/tip ignore still-running deals.
