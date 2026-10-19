# Deadline Lockout, Penalty Resume, and Lesson Numbers

- Lesson pages now display the course-wide lesson number, module number, and lesson number within the module.
- Deadline countdowns are color-coded: green when more than seven days remain, yellow when seven or fewer days remain, and red when due/expired.
- Course access is enforced server-side: expired, incomplete learner enrollments cannot open modules, lessons, quizzes, or assignments.
- Expired learners see a lockout screen on the course page and can start a Paystack penalty checkout.
- Admins can configure the penalty amount and extension duration in Admin → Settings. Extension days set to `0` restores access for the course's original configured duration from verified payment time.
- Penalty payments use a distinct purpose and apply the extension only after Paystack verifies the transaction. The payment callback is idempotent and does not repeatedly extend the deadline.
- Existing databases are upgraded additively with `course_payment.purpose` and `course_payment.extension_days`.
- Paid deadline extensions are preserved when catalog/course pages reconcile legacy registration-based deadlines.
