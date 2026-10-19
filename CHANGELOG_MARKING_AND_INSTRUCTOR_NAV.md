# Changelog — Course marking, scoring and instructor workspace

- Added instructor/admin course marking queue for assignment submissions.
- Added score, maximum mark, feedback, marker identity, mark timestamp and computed letter grade fields to assignment submissions.
- Added an automatic schema upgrade for existing databases.
- Added score validation and letter-grade thresholds: A >= 90%, B >= 80%, C >= 70%, D >= 60%, F < 60%.
- Added quiz results to the marking screen; quiz scoring remains automatic from correct answers.
- Added a dedicated `Marking & grades` link to instructor navigation and dashboard.
- Removed learner-facing Learning, Profile, Projects and Simulations navigation from instructor sessions.
- Removed Home and About Mawiz links from the authenticated sidebar; public navigation remains available when logged out.
- Course authoring and management remain available to instructors and administrators.
