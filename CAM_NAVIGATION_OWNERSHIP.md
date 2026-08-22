# Academy Navigation Ownership

The Academy workspace has exactly one visible primary navigation owner:

`app/static/academy_primary_nav_v1.js`

Primary Owner/Admin menu:

- Dashboard
- Players
- Programs
- Coaches
- Finance
- Reports
- Settings

## Runtime contract

`academy_v3.js` still creates the historical `.cam-tabs` element as part of the legacy workspace shell. `academy_primary_nav_v1.js` is loaded immediately after it and before every Academy feature module. The primary-nav controller converts that element to `.cam-primary-nav`, replaces its contents with the seven canonical Owner/Admin items, and removes the `.cam-tabs` class.

That ordering intentionally makes historical `ensureTab()` helpers in older feature modules inert: Programs, Access & Roles, Parent Portal, Player Reviews and Reports no longer have a `.cam-tabs` target into which they can inject top-level menu items.

Feature modules may render page content or contextual subnavigation only. They must not create or reorder the Academy primary navigation.

## Retired navigation controllers

The following duplicate navigation assets are removed and must not be reintroduced:

- `academy_canonical_nav_v1.js`
- `academy_canonical_nav_v1.css`
- `academy_owner_navigation_feedback_v1.js`

A static regression test in `tests/test_cam_primary_nav_ownership.py` protects the load order and single-owner contract.
