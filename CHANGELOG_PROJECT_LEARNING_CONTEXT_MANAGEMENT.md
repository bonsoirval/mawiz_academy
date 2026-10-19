# Project learning-context management

- Reworked administrator project management into a table with Create, Manage, Publish/Unpublish, and Delete actions.
- Added update support for existing Project records without replacing the model or deleting existing projects/submissions.
- Added optional Track, Course, Module, and Lesson links to Project. Module and lesson selections resolve their parent course; invalid hierarchy combinations are rejected.
- Added additive, idempotent schema compatibility updates and indexes for the new nullable project links.
- Kept project submission review available and surfaced the linked learning context in the review queue.
- Scoped published linked projects to learners enrolled in the associated course or in a course belonging to the associated track. Direct access to another program's linked project returns not found. Legacy projects with no learning links remain general projects.
