# First-login learner welcome email

- Learners receive a welcome email after their first successful sign-in. If email-based two-factor authentication is enabled, this happens only after the verification code is accepted.
- The message is sent through the application's existing email backend and includes the learner's first name, the platform name, and a link to the learner dashboard.
- Administrators can edit the subject and message under Admin → Email Management. Supported placeholders are `{first_name}`, `{dashboard_link}`, and `{site_name}`.
- Added `user.welcome_email_sent_at` to record successful delivery and `user.welcome_email_eligible` to distinguish newly registered learners from pre-existing accounts. Existing databases receive both columns through the startup schema compatibility routine; pre-existing accounts are not sent retroactive welcome emails. Failed sends leave new accounts eligible so a later sign-in can retry.
- Email sending errors are logged and do not prevent the learner from signing in.
- For real email delivery, configure `MAIL_BACKEND=smtp` and the SMTP environment variables. The default `console` backend writes messages to the configured development mail sink rather than delivering them to an inbox.
