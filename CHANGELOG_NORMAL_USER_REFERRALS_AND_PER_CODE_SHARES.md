# Normal User Referral Codes and Per-Code Shares

## Changes
- Every new registration receives a normal `MAWIZ-<USERNAME>` referral code and shareable link.
- Referral settings now include separate default percentages for normal users, Ambassadors, and SUGs.
- Each referral code stores its own share percentage. Changing a global default applies to newly created codes only and does not rewrite existing code rates.
- Existing referral codes receive a one-time share-rate snapshot when the application schema compatibility check runs.
- Admins can create normal, Ambassador, or SUG referral codes and optionally specify a per-code percentage.
- Every referral row has a **Manage** action to update its type, individual share percentage, display label, validity window, and status.
- Referral commissions for both course payments and program purchases use the code's stored share percentage. Existing commission event amounts are not recalculated when a code is edited.
- Existing automatically generated `MAWIZ-...` codes with no label are normalized to the `normal` type during the schema update.

## Deployment
1. Back up the application and database.
2. Replace the application files with this version.
3. Restart the Flask/Gunicorn service. The app's idempotent schema check adds `referral.share_percent` and snapshots current configured defaults for existing codes.
4. Verify Settings → Referral program & payouts, then Admin → Referrals and test a new code and its Manage page.

Python syntax compilation and Jinja template parsing were checked. A full production database integration test has not been run in this environment.
