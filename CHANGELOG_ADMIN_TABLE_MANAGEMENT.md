# Admin table-first management update

- Reorganized track, course, module, lesson, assignment, and quiz inventories into tables.
- Added Manage dialogs to keep detailed controls out of the main listing and reduce page clutter.
- Added publish/unpublish and delete actions to relevant inventory rows.
- Reorganized simulation and Career Path content listings into tables with Manage dialogs.
- Added guarded deletion endpoints for tracks, courses, modules, lessons, assignments, quizzes, and simulations. Failed deletions roll back and display a user-facing message rather than leaving a partial operation.
- Kept existing create workflows and the horizontal management tabs.
