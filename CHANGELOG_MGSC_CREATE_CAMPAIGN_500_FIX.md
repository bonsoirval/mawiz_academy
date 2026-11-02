# MGSC Create Campaign HTTP 500 Fix

## Cause
The campaign creation route read the submitted beneficiary identifier into `beneficiary_identifier`, but the validation block referenced the undefined variable `beneficiary_username`. This raised a `NameError` on valid POST requests and caused HTTP 500 before the campaign could be saved.

## Fix
The validation now checks `beneficiary_identifier`, the variable populated from the form. This preserves existing username/email beneficiary resolution and the existing validation rules.

## Validation performed
- `app/admin/routes.py` passed Python syntax compilation (`py_compile`).
- Full application/database integration tests were not run in this environment.
