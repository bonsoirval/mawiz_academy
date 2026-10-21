# Referral payouts HTTP 500 and Google Maps embed fix

- Added the missing `admin/referral_payouts.html` template so the admin payout route can render requests and review actions.
- Added Google Maps origins to the Content Security Policy `frame-src` directive while retaining the YouTube embed permission.
- Made the contact page use a supplied Google Maps embed URL only when it is an embed-compatible URL; ordinary Google Maps share/navigation URLs remain click-through links and the iframe falls back to a map search based on the configured address.
- Configure the real address and, where available, a Google Maps **Share → Embed a map** URL in Admin Settings. A regular map URL can be used as the clickable directions/location link.

Validation: template and Python syntax checks plus archive integrity checks. Full application/browser tests require the app's dependencies and deployment configuration.
