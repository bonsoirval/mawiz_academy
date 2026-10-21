# What Clients Say Management

- Added an administrator-managed Testimonial model with client name, role, quote, star rating, publication status, display order, and timestamps.
- Added admin create, edit, publish/unpublish, ordering, and delete workflows in a table with modal forms.
- Added What Clients Say to the admin sidebar and dashboard management shortcuts.
- Replaced the hard-coded homepage testimonial examples with published testimonials from the database. Unpublished entries remain hidden from visitors.
- New database table is created by the application's existing schema initialization (`db.create_all()`).
