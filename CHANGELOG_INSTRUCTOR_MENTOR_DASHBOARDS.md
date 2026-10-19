# Instructor and mentor workspace update

- Added seeded demo instructor/facilitator and mentor identities.
- Added a role-specific instructor dashboard for course delivery, course/module/lesson counts, drafts/published courses, and recent enrollments.
- Added a role-specific mentor dashboard for learner roster overview, in-progress enrollments, pending submissions, and recent project submissions.
- Moved instructor-facing course management navigation to an explicit Course management entry and retained full course management in the administrator area.
- Granted instructors course and quiz publishing permissions as well as authoring permissions.
- Removed course authoring and publishing grants from the mentor role; synchronized seeded role grants so removed permissions do not linger after reseeding.
- Added regression tests and documentation for demo identities and role boundaries.

## Limitations

Course ownership and mentor-to-learner assignment are not represented in the current data model. Instructor course management and mentor learner visibility are therefore platform-wide, not scoped to individually assigned courses or mentees.

## Demo accounts (development only)

- `instructor@mawiz.local` / `ChangeMe!Instructor123`
- `mentor@mawiz.local` / `ChangeMe!Mentor123`

Change these credentials or disable these accounts before production deployment.
