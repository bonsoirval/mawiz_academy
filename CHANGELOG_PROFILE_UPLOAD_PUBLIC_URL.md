# Profile image upload and public learner profile fixes

- Fixed image signature validation for JPEG and PNG uploads. The prior checks compared against escaped backslash text instead of the actual image signature bytes, rejecting valid files.
- Kept extension, size, and file-signature checks; uploads are stored under `static/uploads/profile_pictures` with unique filenames.
- Added the canonical public learner profile URL `/learner/<username>`.
- Kept `/learners/<username>` as a permanent redirect for older shared links.
- Refreshed the profile editor into clear photo, introduction, background, and skills sections with responsive layouts.
- Made the canonical public profile URL visible and shareable from the profile editor.
