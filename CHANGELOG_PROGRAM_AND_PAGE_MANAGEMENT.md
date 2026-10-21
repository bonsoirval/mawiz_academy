# Program labels and public page management

- Updated public and admin-facing Track labels to Program where they describe the learning-program concept, while retaining existing database/model identifiers and routes for compatibility.
- Added an admin Page Management entry under MANAGEMENT.
- Added administrator CRUD for public content pages with unique URL slugs, draft/published state, audit events, and CSRF-protected forms.
- Added the public `/pages/<slug>` route and included published managed pages in the sitemap. Reserved slugs `home`, `about`, `programs`, `how-it-works`, and `pricing` allow published content to replace those built-in public pages. Page content is rendered as escaped plain text with preserved line breaks.
- Added the `page_content` database table through the existing `db.create_all()` schema flow.
