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
