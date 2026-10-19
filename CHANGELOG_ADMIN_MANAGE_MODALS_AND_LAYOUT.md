# Admin resource editing and layout update

- Kept the administrator **Courses** sidebar item highlighted while viewing Career Path content management.
- Made the project-management listing fit the available page width; columns wrap content and row actions wrap instead of forcing a horizontal page scrollbar.
- Changed the Manage dialogs for tracks, courses, modules, lessons, assignments, quizzes, simulations, projects, and Career Path content to provide editable forms for the resource content, in addition to existing controls.
- Added permission-protected edit handlers for tracks, courses, modules, lessons, assignments, and quizzes.
- Simulation Manage now saves title, scenario, learner task and learning-content links together.
- No database schema changes introduced.

Validation: Python source compilation and Jinja template parsing passed. Full integration tests were not run in this environment.
