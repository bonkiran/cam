# CAM Academy Parent Billing — Sandbox Test Matrix

Status: Active development test specification

## Purpose

Validate a parent can securely sign in, view only their linked family billing, manage sandbox payment methods, pay invoices, receive receipts, and never expose raw card data to CAM persistence.

## Test parent

- Email: `parent.qa@cam.test`
- Suggested password: `ParentTest!123`
- Role: `parent`
- Must be linked to a real guardian record with `billing_contact=true` for at least one player.

## CAM sandbox card set

These numbers are accepted only when `CAM_PAYMENT_MODE=sandbox`.

| Scenario | Test card | CAM sandbox behavior |
|---|---|---|
| Successful save/payment | `4242 4242 4242 4242` | Saves masked method; payment succeeds |
| Insufficient funds | `4000 0000 0000 9995` | Saves masked method; payment is declined and ledger remains unchanged |
| Saved card later fails | `4000 0000 0000 0341` | Saves masked method; later payment is declined |
| Setup authentication | `4000 0025 0000 3155` | Sandbox refuses save until authentication flow exists |
| Charge authentication | `4000 0027 6000 3184` | Saves masked method; payment requires authentication |

Use a future expiry such as `12/34` and a sandbox CVC such as `123`.

## Persistence rule

CAM may persist only:
- provider identifier
- provider payment-method reference/token
- card brand
- last four digits
- expiration month/year
- default flag
- status

CAM must never persist:
- full PAN/card number
- CVC/CVV

## Core regression scenarios

### PB-001 Parent authentication
1. Parent logs in with valid credentials.
2. Parent billing endpoint returns only linked-family data.
3. Anonymous request returns 401.

### PB-002 Family isolation
1. Create Parent A + Player A + Billing Account A.
2. Create Parent B + Player B + Billing Account B.
3. Parent A cannot pay Parent B invoice.
4. Parent A summary never contains Player B or Account B.

### PB-003 Save successful sandbox card
1. Add `4242` sandbox card.
2. Response shows `Visa •••• 4242` and expiry.
3. Full card number/CVC are absent from response and persistence.
4. Card can be made default.

### PB-004 Reject non-approved number
1. Enter a number not in the CAM sandbox whitelist.
2. Request is rejected.
3. No payment-method record is created.

### PB-005 Failed charge invariants
1. Save `9995` card.
2. Attempt payment.
3. Payment returns decline.
4. Invoice balance is unchanged.
5. No receipt/payment ledger row is created.

### PB-006 Partial then final payment
1. Create $175 invoice.
2. Pay $100 using `4242`.
3. Balance becomes $75; receipt is issued.
4. Pay final $75.
5. Invoice becomes paid with $0 balance.
6. Additional payment is rejected.

### PB-007 Remove payment method
1. Add two sandbox methods.
2. Remove one.
3. Removed method is no longer returned.
4. Default method remains or is reassigned safely.

### PB-008 Audit
Verify add-card, default-card, remove-card, and parent invoice payment events are written without full card data.

## Production transition

The sandbox adapter is for CAM QA only. Production card entry must use a PCI-compliant provider-hosted/tokenized card component. The parent portal should keep the same CAM-facing API model while replacing the sandbox tokenization adapter with the production provider adapter.
