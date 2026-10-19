# Project management and review update

- Reuses the existing `Project` model and its optional track/course/module/lesson foreign keys; no new project schema is introduced.
- Keeps project creation and editing on the existing `/admin/projects` routes. The Manage action opens a modal populated from the existing project record and saves changes through `/admin/projects/<id>/edit`.
- Adds submission counts to the project table and a per-project Review link.
- Extends the existing project review queue to filter by `project_id`, making it possible to review evidence for a specific project and return to project management.
- Preserves the selected project filter when a reviewer updates submission status.
- Validates track/course/module/lesson hierarchy on both creation and update using the existing route validation.
