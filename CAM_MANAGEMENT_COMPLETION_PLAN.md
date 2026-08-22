# CAM Academy Management — Completion & Operational Readiness Plan

Status: Living completion tracker
Branch baseline: `main` after Roles & Security and Player Reviews merge
Development priority: Academy Management operations only

## Current direction

CAM development is temporarily narrowed to making Academy Management operationally complete and usable by a real cricket academy.

**On hold until this tracker reaches operational readiness:**
- biomechanics
- video-analysis integration into Academy workflows
- video evidence linking
- coach report cards / Player Reviews enhancements
- automated cricket technique/scoring features

The already-merged Player Reviews feature remains in the product but is parked.

---

## Definition of "Academy Management fully functional"

CAM is operationally ready when an academy can complete the following without relying on an external spreadsheet for its core records:

1. Set up academy and users.
2. Create players and family/guardian records.
3. Create programs and enroll players.
4. Create batches, manage capacity/waitlists and assign coaches.
5. Generate recurring sessions and schedule private lessons.
6. Reschedule/cancel/create make-up sessions.
7. Take attendance.
8. Manage teams, matches and tournaments.
9. Create fees/invoices and collect partial/full payments.
10. Handle receipts, overpayments, credits and refunds.
11. View accurate outstanding/overdue receivables.
12. Provide role-appropriate self-service for coaches, parents and players.
13. Use one operational dashboard to identify today's work and exceptions.
14. Search, report and export core operational data.
15. Preserve security boundaries and audit sensitive actions.

---

# Capability status

Legend:
- ✅ Implemented and regression-tested
- 🟡 Implemented foundation but not yet operationally complete
- 🔴 Missing / must build
- ⏸ On hold

| Area | Current status | Operational gap |
|---|---|---|
| Academy profile/setup | ✅ | Minor UX validation/polish only |
| Player master records | ✅ | Search/export still needed |
| Guardians/family relationships | ✅ | Parent self-service across operational modules still needed |
| Programs | ✅ | Operational reporting/export needed |
| Enrollment | ✅ | Parent visibility and consolidated status needed |
| Batches | ✅ | Dashboard/waitlist exception surfacing needed |
| Batch roster/capacity/waitlist | ✅ | Operational dashboard + export needed |
| Coach master records | ✅ | Role-scoped experience and broader permission enforcement needed |
| Coach assignments | ✅ | Role-scoped schedule/dashboard needed |
| Recurring sessions | ✅ | Calendar/dashboard usability needs completion |
| Private sessions | ✅ | Calendar/dashboard usability needs completion |
| Reschedule/cancel/make-up | ✅ | Role enforcement and notification workflow not complete |
| Attendance | ✅ | Coach/parent/player role-scoping and reporting need completion |
| Teams | ✅ | Role-scoping/reporting needed |
| Matches | ✅ | Dashboard/calendar/reporting needed |
| Tournaments | ✅ | Dashboard/calendar/reporting needed |
| Fee plan/foundation | ✅ | Operational AR dashboard/reporting needed |
| Invoices | ✅ | Parent self-service + AR workflow needed |
| Full/partial payments | ✅ | Parent self-service + reporting needed |
| Cash/check/card/bank methods | ✅ | External payment-gateway processing is not required for core readiness |
| Receipts | ✅ | Parent retrieval/UI validation needed |
| Overpayment/family credit | ✅ | Operational reporting needed |
| Refunds/invoice reversal | ✅ | Financial audit/reporting needed |
| Payment idempotency | ✅ | Continue regression coverage |
| Access & Roles | 🟡 | Identity/session system exists; existing Academy modules still need consistent server-side role enforcement |
| Owner/Admin access | 🟡 | Needs consistent enforcement across all Academy APIs/UI |
| Coach access | 🔴 | Must be scoped to appropriate assigned operational records/actions |
| Parent portal | 🔴 | Must expose linked child schedule/attendance/enrollment/billing read-only |
| Player self-service | 🔴 | Must expose self schedule/team information read-only |
| Academy operational dashboard | 🔴 | Must build live daily KPIs + exception queues |
| Accounts receivable dashboard | 🔴 | Must build outstanding/overdue/due-soon drilldown |
| Global operational search | 🔴 | Must build permission-aware search |
| Reporting/export | 🔴 | Must add core CSV exports and date/filter support |
| Sensitive action audit | 🟡 | Access audit exists; financial/other high-risk audit should be completed |
| Communications/notifications | 🔴 | Important, but follows security/dashboard/self-service core |
| Trial/lead/registration pipeline | 🔴 | Important growth workflow; follows core operational readiness |
| Coach payroll/compensation | 🔴 | Later operational expansion unless user prioritizes it |
| Player Reviews / report cards | ⏸ | Existing feature parked; no new work |
| Video/biomechanics | ⏸ | Explicitly parked |

---

# Build sequence

## Phase A — Secure the operational core (P0)

### A1. Common Academy authorization layer
Build reusable authorization helpers so Academy APIs enforce permissions server-side instead of relying on UI visibility.

Required controls:
- Owner/Admin: full allowed Academy operational management.
- Coach: only allowed operational functions; no billing/user administration.
- Parent: read-only linked-child/family records only.
- Player: read-only self records only.
- Anonymous: no protected Academy operational data.

### A2. Apply authorization to existing Academy modules
Apply server-side role/identity checks to:
- profile/setup
- players/guardians
- programs/enrollment
- batches/sessions
- coaches
- attendance
- teams/matches/tournaments
- fees/invoices/payments

### A3. Make all Academy UI requests session-aware
All Academy module requests must consistently send the existing CAM Academy session token and handle:
- expired session
- revoked session
- disabled user
- permission denied

Avoid reintroducing abrupt timeout/logout behavior. The UI should show a clear session/access state rather than silently failing.

### A4. Authorization regression matrix
Create tests for each actor against critical API actions, including explicit forbidden-access cases.

**Exit criteria:** Unauthorized cross-role/cross-family access is blocked by the server on both SQLite and PostgreSQL.

---

## Phase B — Role-specific daily operations (P0)

### B1. Coach workspace
Minimum coach view:
- today's/upcoming assigned sessions
- batch/private session details
- allowed rosters
- attendance entry
- limited schedule information required to do the job

### B2. Parent portal
Minimum parent view:
- linked children
- active enrollment
- upcoming sessions/schedule changes
- attendance history
- invoices/current balance
- payment/receipt history
- family credit where applicable

### B3. Player self-service
Minimum player view:
- own upcoming sessions
- own team/match/tournament schedule
- own attendance where allowed

**Exit criteria:** Owner/Admin, Coach, Parent and Player can each sign in and complete their primary daily use cases without seeing unauthorized data.

---

## Phase C — Academy operational dashboard (P0)

Build a live Academy dashboard focused on exceptions and today's work.

Minimum cards/queues:
- sessions today
- attendance pending
- active player count
- active batches + capacity alerts
- waitlisted players
- coach schedule/conflict/workload alerts
- outstanding receivables
- overdue receivables
- payments today / month-to-date
- upcoming matches
- upcoming tournaments

Every aggregate must drill into the source records.

**Exit criteria:** An owner can start the day from one screen and identify schedule, attendance, roster and receivable work requiring attention.

---

## Phase D — Finance operations completion (P0/P1)

### D1. Accounts receivable workbench
- total outstanding
- overdue
- due soon
- family credit
- invoice aging
- family/player drilldown

### D2. Receipt/payment history UX
- retrieve receipt by receipt number
- parent-friendly payment history
- refund visibility

### D3. Financial audit
Audit payment/refund/credit/invoice-impacting administrative actions.

**Exit criteria:** Screen totals reconcile to the underlying invoice/payment ledger and are covered by regression tests.

---

## Phase E — Search, reporting and export (P1)

### E1. Permission-aware global Academy search
Search by supported fields such as:
- player/guardian name
- email
- phone
- invoice number
- receipt number
- team/batch where useful

### E2. CSV exports
Minimum exports:
- player/guardian directory
- enrollment
- batch roster/waitlist
- coach schedule/workload
- attendance
- accounts receivable
- payment ledger
- team/match/tournament schedule

**Exit criteria:** Exports reconcile to the filtered screen/API source.

---

## Phase F — Communication and onboarding workflows (P1)

### F1. Operational communications
Prioritize practical notices:
- session cancelled/rescheduled
- payment due/overdue reminder
- tournament/match update
- general academy announcement

The initial version may record/prepare notices without requiring an external SMS provider. Email/SMS gateway integration can follow.

### F2. Trial/lead/registration workflow
- prospect/lead record
- trial session
- trial outcome
- convert to player + guardian
- enroll into program/batch

**Exit criteria:** Academy can move a new family from inquiry to active enrollment without duplicate data entry.

---

# QA readiness gates

Every new operational slice must pass:

1. Python compile/static validation.
2. JavaScript syntax validation for affected UI.
3. Feature API regression on SQLite.
4. Feature browser/Chromium regression on SQLite.
5. Prior Academy API regression on SQLite.
6. Feature API regression on PostgreSQL.
7. Feature browser/Chromium regression on PostgreSQL.
8. Prior Academy API regression on PostgreSQL.
9. Explicit permission/privacy negative tests for any role-aware feature.
10. No merge to `main` until the relevant CI and shared Academy workflows are green.

---

# Operational acceptance scenarios

Before declaring Academy Management ready, run these complete scenarios end-to-end:

### Scenario 1 — New family onboarding
Academy setup → player + guardians → program enrollment → batch placement → generated sessions → invoice → payment → receipt.

### Scenario 2 — Normal training day
Coach login → today's assigned session → roster → attendance → owner dashboard reflects completion.

### Scenario 3 — Missed class / make-up
Session cancellation or player absence → make-up session → schedule reflects replacement → attendance recorded.

### Scenario 4 — Family billing
Invoice → partial payment → remaining balance → second payment → paid invoice → receipt history.

### Scenario 5 — Overpayment
Invoice → overpayment → invoice paid → remaining family credit → credit applied to later invoice.

### Scenario 6 — Refund
Paid invoice → refund → refund transaction → invoice/balance reversal → audit history.

### Scenario 7 — Parent self-service
Parent login → linked child only → schedule → attendance → invoices/balance → receipt history.

### Scenario 8 — Security boundary
Parent A cannot access Parent B's child/billing; Player A cannot access Player B; Coach cannot manage users/billing; unauthenticated requests cannot read protected Academy operational data.

### Scenario 9 — Competition operations
Team roster → match schedule → tournament association → owner/player appropriate views.

### Scenario 10 — Operational reporting
Owner dashboard → identify overdue account → drill to invoice → export AR; identify attendance pending → drill to session.

---

# Current next task

**P0: Common Academy authorization layer + end-to-end RBAC enforcement across existing operational modules.**

This is the next implementation slice because the identity system already exists, but operational completeness requires the server to consistently enforce it before parent/coach self-service and dashboard work are expanded.
