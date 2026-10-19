# Email verification and Email Management updates

- Normalized password-change timestamps to UTC before token creation and validation, fixing verification links rejected because SQLite returns naive datetimes.
- Added a resend-verification page and a link from the sign-in screen. Responses are generic to avoid revealing whether an email address has an account.
- Added Admin → Email Management to edit subjects and message bodies for email verification, password reset, and sign-in verification-code messages.
- Added placeholders: `{site_name}`, `{link}`, `{code}`, and `{email}`. Keep `{link}` or `{code}` in the relevant template.
- Password-reset messages initiated by administrators now use the editable password-reset template too.

Email verification links remain time-limited according to `EMAIL_VERIFY_MAX_AGE`; users can request a fresh link if the old one expires.


## Resend verification actions
- Added a separate resend-verification form to the registration page for people who already registered but have not verified their email.
- Added email verification status and a resend action to Admin → User Management, plus a resend action on each user detail page.
- Admin resend is limited to active, unverified accounts and uses the editable verification email template.
