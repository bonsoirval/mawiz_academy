# Course completion, working buttons, and strict learning-stage order

- Fixed quiz submission validation to check accessibility against the quiz's parent lesson, not the quiz object itself.
- Recalculated enrollment progress after lesson completion, quiz attempts, assignment submissions, and when opening a course.
- Course progress now reflects completed modules, including required lessons, lesson quizzes, required lesson assignments, module quizzes, and required module assignments. This prevents a course from reaching 100% while module requirements remain unfinished and supports modules without lessons when their required work is complete.
- Learning-stage gates now evaluate calculated completion instead of potentially stale saved percentages.
- Enforced the required order: Hard Skills → Soft Skills → Work Simulation → Career Path. Career Path stays locked until there is at least one in-scope published simulation and all such simulations have been attempted.
- Updated Learning Path stage progress to use the calculated course progress.

Validation: Python compilation and Jinja template parsing passed. Full Flask integration tests were not run in this environment.
