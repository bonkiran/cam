# CAM Academy Management — Parent Billing & Saved Payment Method Use Case

Status: Required P0/P1 Academy Management capability
Development scope: Academy Management only
Related priorities: Parent login, billing self-service, payment reminders, payment confirmations, late-payment notices

## Goal

A parent/guardian must be able to sign in to CAM and manage the billing information for only the family account and children linked to that parent identity.

The parent portal must support secure payment-method management without CAM storing raw card credentials.

## Parent billing journey

1. Parent receives/inherits a CAM parent account linked to the correct guardian/family record.
2. Parent signs in using the existing CAM Academy authentication flow.
3. Parent opens **My Family > Billing**.
4. Parent can see:
   - linked children
   - active programs/enrollments
   - open invoices
   - due dates
   - amount due
   - overdue balance
   - family credit
   - payment history
   - receipt history
   - saved payment-method summary
5. Parent selects **Add payment method** or **Update card**.
6. Card collection is handled by the configured payment provider's secure hosted/embedded payment field.
7. CAM stores only the provider references and safe display metadata needed for the portal.
8. Parent can select a default payment method.
9. Parent may explicitly opt in to future/off-session charges or automatic payment where the Academy enables that option.
10. Parent can replace or remove a saved payment method subject to business rules.
11. When a payment is received, CAM updates the invoice/payment ledger and sends the configured payment confirmation/receipt notice.
12. If a scheduled/off-session payment fails, CAM records the failure and exposes a clear action for the parent to update the payment method.

## Security and storage rules

CAM must NOT store:
- full card number/PAN
- CVV/CVC/security code
- magnetic-stripe/track data
- PIN data

CAM may store payment-provider identifiers and safe display metadata such as:
- provider customer ID
- provider payment-method ID/token
- card brand
- last four digits
- expiration month/year
- billing name
- billing postal code where appropriate
- whether the payment method is the default
- provider status
- created/updated timestamps

The parent must never be able to view another family's payment data. Academy staff should see only masked payment-method information needed for support, not raw credentials.

## Suggested initial provider architecture

CAM should keep a provider abstraction:

CAM Billing Service
→ Payment Provider Adapter
→ Provider-hosted card collection

Recommended initial sandbox implementation: Stripe test mode using SetupIntent/PaymentMethod-style tokenization. The CAM database should remain provider-neutral so another provider can be substituted later.

## Parent portal screens

### Billing overview
- Current balance
- Overdue amount
- Upcoming due amount
- Open invoices
- Recent payments
- Family credit
- Default payment method

### Payment methods
- Card brand + last 4
- Expiration
- Default indicator
- Add card
- Replace/update card
- Set as default
- Remove card

### Payment history
- Date
- Amount
- Method
- Receipt number
- Invoice allocation
- Refund status where applicable

### Communication preferences
- billing email
- mobile/SMS number
- payment-due reminders
- overdue notices
- payment confirmation/receipt notifications

## Payment communication lifecycle

Suggested default sequence:
- 7 days before due: payment reminder
- due date: due-today reminder
- after due date: overdue/late-payment notice according to academy policy
- payment received: confirmation + receipt
- partial payment: confirmation + remaining balance
- payment failure: failed-payment notice + update-card action
- full payment: stop future reminders for that invoice

All messages should be logged with:
- family/account
- invoice
- message type
- channel
- destination (masked where appropriate)
- sent timestamp
- delivery/provider status
- error/retry information

## Sandbox test cases

When Stripe test mode is used, include at minimum these scenarios:

1. Successful card save and payment.
2. Card requiring authentication during setup.
3. Saved card that later fails when charged.
4. Insufficient-funds failure.
5. Replace expired/failed card with a working card.
6. Set a new default card.
7. Remove a non-default card.
8. Prevent removal of a payment method when a business rule requires a replacement/default first.
9. Parent A cannot access Parent B payment methods or invoices.
10. Parent cannot call Academy admin billing APIs.
11. Payment success updates invoice balance and creates receipt.
12. Partial payment leaves correct remaining balance.
13. Payment failure does not reduce the invoice balance.
14. Successful payment suppresses later reminders for the paid invoice.
15. Payment-method update is audit logged.

## Acceptance criteria

This use case is complete when:

- Parent authentication is server-side enforced.
- Parent can see only their linked family/children.
- Parent can add/save/update/default/remove a sandbox payment method through the provider UI.
- CAM never receives or persists raw card number or CVV in its own database/logs.
- Saved card information renders only as masked metadata.
- Parent can pay an invoice with the saved method in test mode.
- Successful, partial, failed and authentication-required payment cases are regression tested.
- Payment and receipt history reconcile to the existing CAM payment ledger.
- Billing reminders/late notices/payment confirmations can use the parent email/mobile contact and are logged.
- SQLite and PostgreSQL API regressions plus Chromium parent-portal tests are green before merge.
