# Manage modal interaction fix

- Moved Manage/open and close-dialog behavior into `app/static/js/admin-manage.js`.
- Loaded the script from `base.html` as a same-origin external script to comply with the application's `Content-Security-Policy` (`script-src 'self'`).
- Replaced inline `onclick` handlers for resource Manage/close buttons with data attributes and delegated click handling.
- Normalized dialogs out of table markup before opening and retained a fallback for browsers without native dialog support.
- Restored project form cascading selection logic in the external script because inline scripts are blocked by the configured CSP.
