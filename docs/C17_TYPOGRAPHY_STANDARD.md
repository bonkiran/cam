# C17 Dashboard Typography Standard

The C17 Dashboard is the visual source of truth for typography across all academy pages.

## Standard scale

- Page title: 24px / 900 / #123b27
- Page subtitle: 13px / 800 / #177447
- Panel title: 15px / 900 / #123f2a
- Section title: 12px / 900 / #244f37
- Body: 12px / 400 / #294936
- Strong body: 12px / 700 / #294936
- Supporting copy: 11px / 400 / #61766a
- Meta/secondary: 10px / 400 / #839188
- Table header: 10px / 900 / #506b5a
- Form label: 10px / 800 / #355d47
- Action/button: 11px / 800
- KPI label: 11px / 800 / #355d47
- KPI value: 22px / 900 / #155336

## Reusable classes

Use these classes on new or refactored C17 pages rather than creating page-specific font sizes:

- `.c17-type-page-title`
- `.c17-type-page-subtitle`
- `.c17-type-panel-title`
- `.c17-type-section-title`
- `.c17-type-body`
- `.c17-type-strong`
- `.c17-type-support`
- `.c17-type-meta`
- `.c17-type-table-head`
- `.c17-type-label`
- `.c17-type-action`
- `.c17-type-kpi-label`
- `.c17-type-kpi-value`

The implementation lives in `app/static/academy_c17_typography_v1.css`. Existing C17 operational pages are normalized there so legacy page-specific CSS does not introduce a different type scale.
