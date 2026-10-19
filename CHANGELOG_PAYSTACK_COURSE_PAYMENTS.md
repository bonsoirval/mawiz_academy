# Paystack Course Payments

- Confirmed the existing hosted Paystack checkout and server-side verification workflow, including verification of success status, transaction reference, amount, currency, and customer email before course enrollment.
- Added a server-side stage-lock check to checkout so a direct POST cannot bypass staged course progression.
- Added an administrator payment ledger at **Admin → Payments**, with search, status filtering, transaction references, and totals.
- Added a learner-only **Payment History** page and navigation link.
- Added Paystack environment variables to `.env.example` and expanded setup and webhook guidance in the README.
- Added status styles and regression tests for checkout initialization, administrator payment visibility, and learner payment history.

## Configuration

Set `PAYSTACK_SECRET_KEY` to a Paystack test secret key in `.env` for testing. In the Paystack dashboard, configure the webhook URL as `https://YOUR-DOMAIN/learning/payments/paystack/webhook`. Switch to a live secret key only after end-to-end testing and deployment over HTTPS. Never expose a secret key in browser code or source control.
