# Mawiz Academy maintainer guide

## Application layout

- app/models.py defines the SQLAlchemy persistence model.
- app/common/schema.py performs safe, additive schema upgrades during startup.
- Blueprint routes live under app/auth, app/learning, app/learner, app/admin, app/projects, app/simulations, and app/portfolio.
- Templates live under app/templates; authenticated navigation is in base.html.
- app/seed.py creates development accounts and example learning content.

## Referral lifecycle

1. A learner owns one or more reusable Referral codes/links.
2. The referral short-link endpoint records a ReferralClick and saves the referral code in the visitor session.
3. Registration creates one ReferralEvent with event_type registration. A database constraint prevents a learner being credited to multiple referrers.
4. A verified Paystack course payment creates one ReferralEvent with event_type purchase. The payment ID is unique, so callback and webhook retries cannot double-credit a purchase.
5. Learner and administrator referral pages display these events in tables.

Do not use Referral.referred_user_id for new code. It remains solely for historical-database compatibility and is converted to an event on application startup.

## Payments

Only _finalize_payment in app/learning/routes.py should grant access after a paid checkout. It verifies Paystack's amount, currency, reference, and customer email before creating enrollment, coupon redemption, and referral events. Keep all three operations in its single transaction.

There is currently one purchasable material type: a course. When adding another paid material, create its local payment record, verify it server-side, and write a ReferralEvent purchase record as part of the successful transaction.

## Schema changes

New models are created by db.create_all() from ensure_schema(). For changes to an existing table, add an idempotent column/index repair to ensure_schema() and preserve existing data. Test startup against a copy of a real database before production deployment.

## Code documentation

Maintain public functions and non-obvious workflows with NumPy-style docstrings: a summary followed by Parameters, Returns, Raises, and/or Notes as appropriate. Prefer documenting invariants and reasons rather than repeating an obvious line of code.

## Deployment copy

make strip-comments OUTPUT=/path/to/output creates a separate copy of the project with Python # comments removed. It preserves docstrings and non-Python files, and never alters the working tree. Build and test that output before deploying it.
