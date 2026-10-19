# Sidebar Toggle Visibility Fix (v4)

- Changed the compact chevron into a visible, labeled Menu/Collapse/Expand button in the authenticated top bar.
- Applied explicit high-contrast styling and visibility rules to prevent inherited CSS from hiding the control.
- Added cache-busting version `sidebar-toggle-visible-4` to stylesheet and JavaScript assets.
- Updated the sidebar controller to support every element carrying `data-sidebar-toggle` and keep labels/icons/accessibility state synchronized.
- Retained desktop icon-rail collapse and mobile drawer behavior.
