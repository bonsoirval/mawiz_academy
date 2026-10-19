# Career Path Course Management

## Changes
- Added Career Path to the full-page course-management stage selector. It now opens `/admin/courses?stage=career_path` instead of the general projects page.
- Enabled `career_path` as a valid course stage, allowing administrators and instructors to create career-path courses without changing the database schema.
- Added Career Path course setup for Entrepreneurship, Job & Freelance, and general career development.
- Expanded the shared course-management workspace to support creating and editing course details, modules, lessons, quizzes, quiz questions, and assignments; setting course prices and durations; mapping completion skills; and publishing/unpublishing courses, quizzes, and assignments.
- Preserved the active stage after nested course, module, lesson, quiz, and assignment actions so managers remain in the Career Path workspace.
- Kept the existing permission decorators, CSRF form tokens, audit events, course/module/lesson relationships, and existing learning-management routes.
- Allowed stored YouTube privacy-enhanced embed URLs when editing lessons.

## Verification
- Python source compilation passed with `python -m compileall -q app`.
- Jinja syntax parsing passed for the modified course-management and tab templates.
- Full Flask tests were not run in this environment because Flask is not installed in the available Python runtime.
