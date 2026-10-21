# Referral settings, earnings and payout requests

- Added admin-configurable referral program enablement, course commission percentage, and minimum payout amount to System Settings.
- Expanded learner referral dashboard with registration and verified course-purchase activity, per-course commission, lifetime earnings, available balance, payout request form, and payout history.
- Payout requests validate bank name, account name, account number, minimum amount, and available balance; account numbers are masked in the learner's payout history.
- Added Referral Payouts navigation and dashboard shortcut for administrator review.
- Seeded the existing Home, About, Programs, How It Works, and Pricing pages as unpublished Page Management entries. Their existing live layouts remain active until an admin publishes CMS content for the page.
- Python compilation passed. Runtime tests could not be run because Flask is not installed in the current environment.
