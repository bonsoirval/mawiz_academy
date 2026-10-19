# Sidebar collapse fix (iteration 3)

- Changed the sidebar toggle to a document-level capture-phase click handler so unrelated page click handlers cannot prevent the toggle from receiving the click.
- Kept the behavior external-JavaScript-only for compatibility with the application's `script-src 'self'` Content Security Policy.
- Added explicit title/accessible state labels and an asset version bump to force browsers to request the latest CSS and JavaScript. Fixed mobile stacking order so the menu toggle remains clickable above the open drawer.
- Preserved desktop icon-rail collapse, local preference persistence, and mobile slide-in navigation.
- Validation includes JavaScript syntax checks and Chromium interaction tests using the shipped CSS and sidebar controller at desktop and mobile viewport widths. Full Flask integration and authenticated end-to-end testing were not available because Flask dependencies are absent from this environment.
