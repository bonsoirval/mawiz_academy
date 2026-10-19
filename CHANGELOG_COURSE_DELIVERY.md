# Course delivery update

- Preserved the existing lesson authoring support for written text, YouTube video, or both.
- Kept course duration self-paced and configurable in days, weeks, months, or years.
- Enrollment calculates a target deadline from the configured duration.
- Improved the learner catalog to show the active course, progress, start date, and target deadline.
- Other courses stay visible for planning but are marked locked while a different course is active.
- Completed courses can be revisited; the server continues to block enrollment in a second unfinished course.
- Added regression tests for deadline calculation, one-course-at-a-time enrollment, and catalog lock presentation.


## Enrollment date robustness fix

- Made the active-course catalog template safe when an older enrollment has no `started_at` value.
- The course catalog repairs missing start dates for unfinished enrollments and calculates a missing deadline where course duration data is available.
