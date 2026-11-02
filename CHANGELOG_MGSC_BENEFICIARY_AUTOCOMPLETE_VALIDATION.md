# MGSC Beneficiary Autocomplete and Validation Fix

## Changes
- Added an administrator-permission-protected autocomplete endpoint for existing non-administrator accounts. Search matches username or email and returns username, role and display-name context.
- Updated the Growth Share Campaign form to suggest matching existing usernames as the administrator types. Administrator accounts are excluded from both suggestions and server-side beneficiary selection.
- Added server-side validation messages identifying the exact invalid field rather than returning the generic campaign validation error.
- Aligned count input minimums with server validation: minimum signups and minimum program purchases must be at least one; maximums must be greater than or equal to minimums.
- Added explicit checks for missing dates, end date not after start date, campaign name and share percentage range.

## Validation performed
- Python syntax compilation passed (`python -m compileall -q app`).
- Full Flask runtime tests were not run in this build environment because Flask is not installed in the system Python. Run the application's test suite in its supported virtual environment before deployment.

## Deployment
Deploy the updated `app/admin/routes.py` and `app/templates/admin/growth_share_campaigns.html`. No database schema change is required for these fixes. Restart the Flask service and test the campaign form with a non-admin learner, instructor and mentor account, then verify that an administrator account cannot be selected.
