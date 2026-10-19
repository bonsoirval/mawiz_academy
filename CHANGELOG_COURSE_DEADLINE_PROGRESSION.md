# Course Progression and Deadline Start Fix

- Course deadlines now start from the learner's individual enrollment/start timestamp, not account registration.
- Courses that have not been started no longer show a running deadline.
- Completing all course requirements allows progression based on completion and stage rules, regardless of the completed course's deadline status.
- The next course's clock begins when the learner starts/enrolls in that course; paid courses start after Paystack payment is verified.
- Existing registration-based deadlines are re-anchored to the enrollment start. Verified deadline-penalty extensions are preserved.
- Updated course catalog and course page wording to explain the deadline behavior.

Validation: Python compilation and Jinja template compilation passed. Full Flask integration tests and live payment workflow tests were not run in this environment because Flask dependencies were unavailable.
