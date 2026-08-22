# CAM Academy Management — End-to-End Use Cases

Status: Living operational specification
Scope: Academy Management only
Explicitly on hold: video analysis, biomechanics, coach report cards/player reviews enhancements, video evidence linking

## Product objective
CAM Academy Management should allow a cricket academy owner and staff to run the academy's daily administrative operations from one system without depending on spreadsheets for core records.

The operational system of record covers:
- academy setup
- players and guardians/families
- programs and enrollment
- batches and scheduled/private sessions
- coaches and assignments
- attendance and make-up handling
- teams, matches and tournaments
- fees, invoices, payments, credits and refunds
- user access and role-based permissions
- operational dashboard, search, reporting and export
- parent/player self-service for information that belongs to them

## Actors

### Owner
Full academy authority. Configures the academy, manages users, programs, coaches, billing rules, reporting and all operational records.

### Admin
Runs day-to-day front-office operations. Similar operational authority to Owner except ownership/bootstrap-level actions.

### Coach
Works with assigned batches/sessions and players. Needs schedule, roster and attendance capabilities. Must not receive unrelated billing/admin privileges.

### Parent / Guardian
Read-only/self-service access to linked child information: enrollment, schedule, attendance, invoices, balances, receipts and academy communications where supported.

### Player
Read-only/self-service access to the player's own schedule, team/match information and other player-facing operational information where appropriate.

---

# UC-001 — Configure the academy

**Primary actor:** Owner/Admin

**Goal:** Establish the academy master profile before operational records are created.

**Flow:**
1. Enter academy name, contact information, address and timezone.
2. Save the academy profile.
3. System uses the academy timezone for sessions and scheduling.
4. Existing player records without an academy association are attached to the configured academy where applicable.

**Success criteria:**
- Academy profile persists.
- Profile can be edited.
- Timezone is consistently used for Academy scheduling.

---

# UC-002 — Create a player and family/guardian record

**Primary actor:** Owner/Admin

**Goal:** Create the operational master record for a student.

**Flow:**
1. Add player identity, DOB, cricket profile, contact details, emergency contact and status.
2. Add one or more guardians.
3. Mark primary guardian, billing contact and pickup authorization.
4. Save the record.
5. Search/open the player later and update details.

**Success criteria:**
- Player is unique and retrievable.
- Multiple guardians are supported.
- Guardian-to-player relationships persist.
- Primary/billing/pickup designations are retained.
- Inactive/waitlisted status can be represented.

---

# UC-003 — Create programs and enroll players

**Primary actor:** Owner/Admin

**Goal:** Define what the academy sells and enroll students into the correct program.

**Flow:**
1. Create a program with name, description, fee basis and active dates/status.
2. Select a player.
3. Enroll the player into the program.
4. Apply allowed discount/fee rules.
5. System prevents invalid duplicate/current enrollment states.

**Success criteria:**
- Active/inactive programs are distinguishable.
- Player enrollment history is retained.
- Enrollment can drive billing/invoice creation.

---

# UC-004 — Create a batch and manage roster capacity

**Primary actor:** Owner/Admin

**Goal:** Group players into recurring training cohorts.

**Flow:**
1. Create a batch linked to a program.
2. Set capacity, location/resource and operating dates.
3. Add active players.
4. When capacity is reached, optionally waitlist additional players.
5. Assign a primary/support coach.

**Success criteria:**
- Capacity cannot be silently exceeded.
- Active and waitlisted players are distinct.
- Coach assignments persist.
- Duplicate current batch memberships are prevented.

---

# UC-005 — Generate recurring training sessions

**Primary actor:** Owner/Admin

**Goal:** Generate the academy calendar from a batch schedule.

**Flow:**
1. Select batch.
2. Enter date range, weekdays, start time and duration.
3. System generates sessions in the academy timezone.
4. Current batch roster is attached to generated sessions.
5. Primary coach is associated with generated sessions.

**Success criteria:**
- Duplicate sessions are not generated for the same batch/date/time.
- Coach scheduling conflicts are prevented.
- Session roster is persisted.

---

# UC-006 — Schedule a private lesson

**Primary actor:** Owner/Admin

**Goal:** Schedule a one-to-one session outside the recurring batch schedule.

**Flow:**
1. Select active player.
2. Select active coach.
3. Enter date, time, duration, location/resource and notes.
4. System checks coach availability.
5. Session is created with the selected player attached.

**Success criteria:**
- Inactive player/coach cannot be scheduled.
- Coach conflicts are blocked.
- Private session is visible in schedule/workload.

---

# UC-007 — Reschedule, cancel and create a make-up session

**Primary actor:** Owner/Admin; Coach where permission allows

**Goal:** Handle real-world schedule changes without losing history.

**Flow:**
1. Open scheduled session.
2. Reschedule date/time/coach/resource OR cancel with reason.
3. If needed, create a make-up session linked to the original.
4. Copy the affected player roster into the make-up session.

**Success criteria:**
- Original session history remains visible.
- Cancellation reason is retained.
- Make-up references the original session.
- New coach conflicts are checked.

---

# UC-008 — Coach daily schedule and workload

**Primary actor:** Coach; Owner/Admin

**Goal:** Know what the coach is responsible for today/upcoming.

**Flow:**
1. Coach signs in.
2. Coach sees only assigned/allowed sessions.
3. Session shows time, batch/private lesson, location and roster.
4. Admin can view coach workload totals.

**Success criteria:**
- Coach cannot edit unrelated academy records.
- Workload reflects non-cancelled assigned sessions.

---

# UC-009 — Take session attendance

**Primary actor:** Coach; Owner/Admin

**Goal:** Record actual attendance efficiently during or after a session.

**Flow:**
1. Open a session roster.
2. Mark each player present, absent, late, excused or applicable supported status.
3. Add attendance notes where required.
4. Save once for the roster.
5. Correct an attendance entry later with audit/history as supported.

**Success criteria:**
- Attendance is tied to player + session.
- Duplicate attendance records are prevented or updated deterministically.
- Session attendance summary is available.
- Parent/player visibility is limited to linked/self records.

---

# UC-010 — Create/manage Academy teams

**Primary actor:** Owner/Admin

**Goal:** Build competition teams independently of training batches.

**Flow:**
1. Create team.
2. Add eligible players to team roster.
3. Add/remove players without destroying historical match records.
4. Associate matches with the team.

**Success criteria:**
- Team roster is visible.
- Duplicate active membership is prevented.
- Historical membership/match integrity is retained.

---

# UC-011 — Schedule and manage matches

**Primary actor:** Owner/Admin; Coach where permission allows

**Goal:** Track academy fixtures and results.

**Flow:**
1. Create opponent/date/time/location/match details.
2. Link Academy team.
3. Track status from scheduled through completed/cancelled where supported.
4. Save result/score information.

**Success criteria:**
- Upcoming and completed matches are distinguishable.
- Match remains linked to the correct Academy team.

---

# UC-012 — Manage tournaments

**Primary actor:** Owner/Admin

**Goal:** Track multi-match competition commitments.

**Flow:**
1. Create tournament with dates/location/status.
2. Associate relevant Academy teams/entries.
3. Track tournament operational information.

**Success criteria:**
- Upcoming/current/completed tournament records are manageable.
- Tournament data is usable from operational dashboard/reporting.

---

# UC-013 — Configure fees and generate invoices

**Primary actor:** Owner/Admin

**Goal:** Convert program enrollment into a collectable family/player balance.

**Flow:**
1. Configure fee plan/rules.
2. Associate fee with program/enrollment/family as supported.
3. Generate unique invoices.
4. Apply discounts according to configured rules.
5. Present amount due and due date.

**Success criteria:**
- Invoice number is unique.
- Same charge is not unintentionally duplicated.
- Discounts are transparent.
- Family/player balance reconciles to invoice lines.

---

# UC-014 — Record full or partial payment

**Primary actor:** Owner/Admin

**Goal:** Accurately collect academy dues.

**Flow:**
1. Open family/player balance.
2. Select invoice(s).
3. Record cash, check, card or bank payment method.
4. Support full or partial amount.
5. Generate a unique receipt.
6. Update remaining balance.

**Success criteria:**
- Payment retry cannot double-post the transaction.
- Remaining amount updates correctly.
- Payment history and receipt are retrievable.

---

# UC-015 — Handle overpayment/family credit

**Primary actor:** Owner/Admin

**Goal:** Reconcile payments greater than the currently due amount.

**Flow:**
1. Record payment larger than open invoice balance.
2. If overpayment is allowed, apply required amount to invoices.
3. Store remaining amount as family credit.
4. Apply credit to future invoice.

**Success criteria:**
- Family account reconciles exactly.
- Overpayment-disabled configuration rejects invalid payment.
- Credit cannot be double-applied.

---

# UC-016 — Refund a payment

**Primary actor:** Owner/Admin

**Goal:** Reverse money while preserving financial history.

**Flow:**
1. Locate original payment/receipt.
2. Enter refund amount/reason.
3. Create refund transaction.
4. Reverse/reopen invoice balance as appropriate.
5. Preserve original transaction and refund linkage.

**Success criteria:**
- Financial history is append-only rather than deleted.
- Invoice/family balance reconciles after refund.

---

# UC-017 — View receivables and overdue balances

**Primary actor:** Owner/Admin

**Goal:** Know what money is still outstanding.

**Flow:**
1. Open Academy financial dashboard/report.
2. View total outstanding, overdue, due soon, credits and collected amounts.
3. Drill into family/player and invoice.
4. Export/report as needed.

**Success criteria:**
- Totals reconcile to invoice/payment ledger.
- Overdue state is date-aware.
- Staff can identify exactly which account needs follow-up.

---

# UC-018 — Parent views child schedule and attendance

**Primary actor:** Parent/Guardian

**Goal:** Self-serve the operational information for linked children.

**Flow:**
1. Parent signs in.
2. System resolves children through guardian relationships.
3. Parent sees upcoming sessions and relevant schedule changes.
4. Parent sees attendance history for linked children only.

**Success criteria:**
- Parent cannot access another family's child.
- Draft/admin-only data is not exposed.

---

# UC-019 — Parent views invoices, balance and receipts

**Primary actor:** Parent/Guardian

**Goal:** Understand what is owed and what has already been paid.

**Flow:**
1. Parent signs in.
2. View linked family/player invoices.
3. View current balance, payment history, family credit and receipts.
4. No administrative edit controls are exposed.

**Success criteria:**
- Parent financial view reconciles to ledger.
- Parent cannot view another family's financial data.

---

# UC-020 — Player self-service

**Primary actor:** Player

**Goal:** See the player's own operational information.

**Flow:**
1. Player signs in.
2. View own upcoming sessions.
3. View own team/match/tournament information as applicable.
4. View own attendance where allowed.

**Success criteria:**
- Player cannot access another player's private record.
- Player cannot perform staff administration.

---

# UC-021 — Manage users and roles

**Primary actor:** Owner/Admin

**Goal:** Control who can use Academy Management and what they can do.

**Flow:**
1. Bootstrap first owner securely.
2. Create Admin/Coach/Parent/Player account.
3. Link Coach/Parent/Player account to real Academy identity.
4. Reset password, disable user or revoke sessions.
5. Audit access-management actions.

**Success criteria:**
- Passwords are never stored as plaintext.
- Disabled/revoked users cannot continue using old sessions.
- Role and identity linkage is enforced server-side.

---

# UC-022 — Academy operational dashboard

**Primary actor:** Owner/Admin

**Goal:** Start the day with a single operational picture.

**Minimum dashboard:**
- today's sessions
- attendance not yet completed
- active players
- active programs/batches
- batch capacity/waitlists
- coach schedule/workload alerts
- outstanding and overdue receivables
- payments collected today/month
- upcoming matches/tournaments
- recent operational exceptions

**Success criteria:**
- Every KPI is calculated from live Academy records.
- KPI can drill into the underlying operational records.

---

# UC-023 — Search and find operational records

**Primary actor:** Authorized staff

**Goal:** Find a player/family/session/invoice quickly without navigating many modules.

**Flow:**
1. Enter name, phone, email, invoice/receipt number or relevant supported term.
2. System returns only records the signed-in role may access.
3. Open result directly.

**Success criteria:**
- No cross-family data leakage.
- Common operational records are reachable in a few actions.

---

# UC-024 — Export operational reports

**Primary actor:** Owner/Admin

**Goal:** Obtain usable business data outside CAM when required.

**Core exports:**
- player/guardian directory
- active enrollment
- batch rosters/waitlists
- coach schedule/workload
- attendance summary
- accounts receivable
- payment ledger
- team/match/tournament schedule

**Success criteria:**
- Export reflects the active filters/date range.
- Totals reconcile to the screen/API source.

---

# UC-025 — Audit sensitive administrative actions

**Primary actor:** Owner/Admin

**Goal:** Know who changed access or financially/operationally sensitive data.

**Minimum audit targets:**
- user creation/disable/password reset/session revocation
- payment/refund/credit adjustment
- invoice-impacting changes
- attendance correction where appropriate
- other high-risk administrative changes

**Success criteria:**
- Actor, action, target and timestamp are retained.
- Audit history is not editable through normal Academy UI.

---

# Explicit hold list

The following work must not displace Academy Management completion work:
- biomechanics
- pose/keypoint work
- cricket video analysis enhancements
- video/report-card evidence linking
- coach report cards / player review enhancements
- technical batting/bowling scoring
- automated cricket technique analysis

The existing Player Reviews feature may remain in the codebase, but it is parked and should not receive new development until Academy Management operational readiness is achieved.
