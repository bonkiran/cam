# CAM Payment Provider Architecture

CAM keeps billing logic provider-neutral. Stripe and Square are supported payment-provider types behind one CAM contract.

## CAM owns
- fee plans and monthly billing rules
- invoices, outstanding balances, allocations, receipts, refunds/reconciliation
- recurring authorization evidence
- enrollment/payment status
- provider selection per academy
- provider customer/payment-method/payment references
- non-sensitive card metadata (brand, last four, expiry)

## Payment provider owns
- raw card number/PAN
- CVC/CVV
- secure card-entry UI
- card tokenization / stored credential
- network authentication and provider payment execution

## Provider contract
Each adapter implements the same logical operations:
1. configuration/status
2. create customer
3. begin payment-method setup
4. complete payment-method setup
5. charge saved payment method
6. refund payment
7. retrieve payment status
8. webhook verification/translation (future slice)

### Stripe mapping
- secure UI: Stripe Elements / Payment Element
- save without charge: SetupIntent (`usage=off_session`)
- saved credential: Customer + PaymentMethod
- future charge: PaymentIntent against saved PaymentMethod

### Square mapping
- secure UI: Square Web Payments SDK
- save without charge: Web Payments token + Cards API `CreateCard`
- saved credential: Customer + Card on File
- future charge: Payments API using saved card ID
- Square location ID is provider-specific and remains optional in CAM's generic connection model.

## Generic CAM fields
Use generic fields instead of provider-specific columns:

- `provider`: `stripe` or `square`
- `provider_customer_id`
- `provider_payment_method_id`
- `provider_payment_id`
- `provider_merchant_id`
- `provider_location_id` (nullable)
- `environment`: `sandbox` or `live`
- `card_brand`
- `card_last4`
- `card_exp_month`
- `card_exp_year`

Never store provider secrets, full card numbers, or CVC in CAM tables.

## Current rollout
1. Build provider-neutral backend contract and tests.
2. Configure Stripe Sandbox first for Slice 2C manual testing.
3. Run the same CAM payment contract tests against Square Sandbox.
4. Keep UI/Finance/Enrollment behavior unchanged when switching providers.
