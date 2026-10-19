# Lesson completion button fix

- Made the learner lesson-completion form explicitly submit to the lesson endpoint using a named submit button; no client-side JavaScript is required.
- Added an on-page list of incomplete required quizzes and assignments, with direct links, so learners can see why completion is blocked.
- Server-side validation now identifies the exact required checkpoints still pending.
- Made repeated lesson-completion submissions idempotent so the original completion timestamp is preserved.
- Course progress is recalculated after successful completion, and course completion is recorded once progress reaches 100%.
- The existing course deadline, enrollment, and payment rules remain in effect.
