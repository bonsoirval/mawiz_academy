# Lesson route HTTP 500 compatibility fix

- Added additive startup schema repairs for legacy `assignment` tables missing `required`, `published`, or `position` columns.
- Added an additive repair for legacy `quiz` tables missing `published`.
- These columns are queried by the lesson page while calculating required checkpoints and rendering lesson assignments; `db.create_all()` does not alter existing tables, so existing installations now receive the missing columns safely.
- Verified Python syntax compilation and Jinja parsing for the lesson template.
