# Mawiz Academy Paystack Payment Flow Rebuild

## Summary

The existing Paystack payment integration, payment ledger, callback verification,
webhook signature verification, coupon handling, deadline-penalty payment, referral
attribution, and enrollment logic are retained.

The payment-start POST routes now render a same-origin bridge page instead of issuing
an immediate redirect from the form POST to Paystack. A same-origin external JavaScript
file navigates to the hosted checkout, and the page provides a manual link as a fallback.
This is designed to avoid browser-specific CSP handling of a cross-origin redirect
following a form submission while retaining the existing `script-src 'self'` policy.

The server validates that the authorization URL is HTTPS and uses exactly
`checkout.paystack.com` before rendering it. No secret key is exposed to browser code.

## Files changed

- `app/learning/routes.py`
  - Validates the hosted checkout URL.
  - Renders the bridge page for course purchases and deadline-extension payments.
- `app/templates/learning/payment_redirect.html`
  - Same-origin transition page with a fallback link.
- `app/static/js/paystack-redirect.js`
  - External JavaScript redirect, compatible with `script-src 'self'`.
- `tests/test_app.py`
  - Updates the course checkout test for the bridge response.
- `tests/payments/test_paystack_client.py`
  - Tests trusted URL acceptance and unsafe URL rejection.

## Test plan

1. Run `pytest`.
2. Configure a Paystack test secret in the server-side `.env` (never in browser code).
3. Test a paid course in Chrome and Firefox.
4. Test deadline-extension checkout.
5. Complete a test payment and confirm the callback performs server-side verification,
   marks the payment successful, and activates exactly one enrollment.
6. Test an abandoned payment and confirm no enrollment is granted.
7. Test a failed initialization and confirm the learner sees the existing error feedback.
8. Verify Paystack webhook signature handling still works.

## Deploy safely

- Back up the existing app directory and database before deployment.
- Do not replace the deployed app until the tests and test-mode checkout pass.
- Do not copy `.env`, `.git`, local databases, uploads, logs, or virtual environments
  from this archive into production.
- No database migration is included or required by these changes.
- Keep the existing `PAYSTACK_SECRET_KEY`, `DATABASE_URL`, and `SECRET_KEY` in the server's
  current environment configuration.


## HTTP 403 diagnostic rebuild (v2)

The Paystack API adapter now sends `User-Agent: MawizAcademy-Payments/1.0` and
`Connection: close`, matching the explicit request-header pattern in the working
reference integrations. It continues to send the secret only in the server-side
Authorization header; credentials and request payloads are never logged.

HTTP error handling now distinguishes a JSON provider response from a non-JSON
response (such as an HTML 403 page). Non-JSON 403 responses are reported as a
possible outbound proxy/WAF/network filter or endpoint configuration issue instead
of being automatically described as an invalid secret key. The diagnostic message
is sanitized and length-limited.

Regression tests cover the headers and both JSON and non-JSON HTTP 403 responses.
No database schema or migration changes are included. The existing checkout bridge,
server-side payment verification, webhook signature check, coupon/referral behavior,
and enrollment fulfillment remain in place.


## Administrator email management update

The admin user detail page now lets administrators change an account's email address. The server validates email syntax, prevents reuse of another account's address (case-insensitively), records an audit event, and resets email verification whenever the address changes. A new verification link can then be sent from the existing verification panel. Regression tests cover successful changes, invalid addresses, duplicate addresses, and verification reset.
