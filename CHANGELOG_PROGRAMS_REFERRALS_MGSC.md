# Program Purchases, Referral Types and MGSC Enhancement

## Implemented in this working revision

- Added program-level price fields to the existing `Track` entity (the app's existing program/path entity).
- Added `ProgramPayment` and `ProgramEnrollment` models.
- Added program checkout and Paystack verification using the existing payment client, callback and webhook endpoints.
- Program payment verification creates an entitlement and enrols the learner in the program's courses.
- Course deadlines for newly purchased program courses are anchored to the verified program purchase timestamp and use each course's configured duration.
- Added a learner-facing My Programs page and program-specific public detail page.
- Updated the public program catalog to list programs instead of treating courses as purchasable products.
- Disabled individual course checkout and individual course enrolment for new enrolments.
- Enforced program entitlement when opening a course and when resolving course enrolments for protected learning routes.
- Filtered the learner course list to courses belonging to the learner's active programs, with a legacy exception for existing enrolled standalone courses.
- Scoped staged progression checks to courses in the relevant owned program where a course context is available.
- Added separate Ambassador and SUG referral-code types, display labels and optional validity windows.
- Added per-program-order referral commission records so multiple program purchases can be attributed without relying on the legacy one-purchase-per-user constraint.
- Added MGSC campaign, event and share-ledger models, an admin campaign-creation screen, pause/resume/cancel controls and a beneficiary dashboard permission.
- MGSC counts only signups and program purchases attributed to the campaign beneficiary's referral codes. It grants eligibility live when both configured count ranges are satisfied.
- MGSC share basis is the total eligible system revenue during the campaign window, calculated from verified program payments after the provider fee reported by Paystack. The estimate is refreshed when program revenue events occur.
- Added startup schema compatibility changes and seed permission definitions for new features.
- Added initial tests for program-only access and purchase-date course deadlines.

## Important notes before production deployment

- Review the inferred legacy program prices produced during the one-time schema migration. The first migration uses the sum of existing course prices assigned to a program as a starting price, to avoid making all existing programs free. Administrators should confirm each program's intended price before publication.
- Existing individual course payments remain in the database for audit/history; they are no longer a valid way to unlock courses assigned to a program.
- Full end-to-end tests must run in the project's supported Python 3.11 environment. The execution environment used for this change had Python 3.13 while the archived virtual environment contained Python 3.11 binaries, so the test suite could not be run here. Syntax compilation and Jinja template parsing were run.
- Refund/chargeback integration for program payments and final payout execution/reconciliation for MGSC still require production policy and workflow integration. Current MGSC figures are live estimates; do not treat them as approved payouts until a final reconciliation/approval workflow is completed.
- Confirm the intended treatment of provider fees, taxes, refunds, chargebacks, currency conversions and the final campaign-close reconciliation before paying beneficiaries.
