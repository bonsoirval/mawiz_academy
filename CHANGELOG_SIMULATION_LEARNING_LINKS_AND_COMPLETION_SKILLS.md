# Simulation learning links and configurable completion skills

## Simulation management
- Simulations can now be linked to one or more tracks, courses, modules, and lessons.
- Existing simulations can have those links edited or cleared from the simulation management page.
- Learner simulation cards and detail pages show the related learning content when links are configured.
- Existing simulations remain compatible: all learning links are optional.

## Completion skills
- Course-level skill assignment remains available.
- Administrators and instructors can now assign or remove skills on each module and lesson.
- A skill configured on a module appears in the learner portfolio only after that module has a completed progress record.
- A skill configured on a lesson appears in the learner portfolio only after that lesson has a completed progress record.
- Clearing all selections and saving removes the association for that course/module/lesson; it does not erase separate verified skill records or historical completion records.

## Database compatibility
- New association tables are created through the application's existing idempotent `db.create_all()` schema initialization.
- No existing columns or learner completion records are deleted.
