# Deployment Notes — Programs, Referrals and MGSC

## Before deploying

1. Take a full backup of the production database and current application directory.
2. Deploy to staging first. The application startup schema helper adds the new tables and additive columns. It also performs a one-time legacy program-price migration: where the `track.price_amount` column is newly introduced, the starting program price is inferred from the sum of existing course prices assigned to that program. Review every inferred price before publishing programs.
3. Do not copy the uploaded archive's `.env` or `instance/mawiz.db` into deployment. Use the server's existing environment variables and production database configuration.
4. Keep the current Paystack secret key only in the server environment. Rotate it if it was ever shared outside the server or source-control secret store.

## Deploy

1. Install the application requirements in the project's supported Python 3.11 environment.
2. Configure the same production environment variables and database URI as the current deployment.
3. Back up the database again immediately before the application is started with the new code.
4. Start/restart the Flask service. Startup schema checks create the new program, payment, referral-event and MGSC tables and add missing columns.
5. Log in as administrator and review **Admin → Courses / Programs**. Set the intended price for each program and ensure each published program contains its intended published courses.
6. Review **Admin → Referrals**. Create separate Ambassador and SUG codes, assign the correct account, and configure validity dates where needed. The ambassador and SUG program-purchase share percentages are separately configurable in Settings.
7. Review **Admin → Growth Share Campaigns**. Assign each campaign to a beneficiary account that owns the referral codes whose attributed signups and program purchases should count. Set dates, minimum/maximum counts and share percentage.
8. Run the acceptance checks below before making the program catalog public.

## Acceptance checks

- A published program displays the correct price and assigned published courses.
- An authenticated learner can purchase a program through Paystack and is granted access only after server-side verification.
- A learner cannot open another program's course through a direct course, module or lesson URL.
- Course deadlines are calculated from the verified program purchase timestamp using each course's configured duration.
- The My Programs dashboard shows only entitled program courses and their deadlines.
- A second program purchase preserves the first program's progress and access records.
- Program purchase and payment history appear in learner and admin views.
- Ambassador and SUG codes remain separate and program purchase commissions are recorded once per verified program order.
- MGSC counts only the beneficiary's attributed signup and program-purchase events; thresholds count purchase orders, not money amounts.
- MGSC eligibility updates live once both ranges are satisfied and the share estimate reflects total eligible system revenue in the campaign window.

## Known follow-up work before real beneficiary payouts

The current MGSC screen calculates and records an estimate, but this revision does not implement a complete final reconciliation, approval and payout workflow or automatic refund/chargeback reversals. Treat estimates as informational, not payable balances, until that workflow is completed and tested. The app's existing individual course-payment history remains for audit; new individual course checkout is disabled.

## Tests

Run `python -m pytest -q` in the supported Python 3.11 environment. The editing environment used to prepare this archive had Python 3.13 and an archived Python 3.11 virtual environment, so runtime tests could not be executed here. Python syntax compilation and Jinja template parsing passed.
