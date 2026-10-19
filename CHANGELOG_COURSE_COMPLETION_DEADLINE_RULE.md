# Course completion and deadline rule

- Course progress is now calculated from completed modules, including their lesson requirements, published quizzes, and required assignments, instead of lesson counts alone.
- A course is treated as complete when all its modules and required materials are complete; the completion timestamp is synced when the course page is loaded or a lesson is completed.
- A completed course is not considered expired, even if the stored progress/deadline state was stale.
- Next-course enrollment and stage progression check actual material completion rather than relying only on the saved percentage.
- Active-course detection skips courses whose materials are already complete, so learners can proceed to the next eligible course.
