# Courses page 500 compatibility fix

- Added an idempotent startup schema repair for legacy `course` tables missing the `stage` column used by the Courses management filter. Existing courses default to `hard_skills`, preserving their records.
- Added an idempotent startup schema repair for legacy `track` tables missing the `published` column used by the Tracks table. Existing tracks default to unpublished.
- The repairs run before `db.create_all()` and are safe to run repeatedly.

Validation: Python compilation, Jinja template parsing, and ZIP integrity checks passed. Full Flask/database integration tests could not be run in this environment because Flask and SQLAlchemy dependencies are unavailable and network installation is disabled.
