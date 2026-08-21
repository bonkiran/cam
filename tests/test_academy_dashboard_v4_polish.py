from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_v4_polish_matches_approved_prototype_changes():
    js = (REPO_ROOT / "app" / "static" / "academy_dashboard_v4_polish_v1.js").read_text(encoding="utf-8")
    css = (REPO_ROOT / "app" / "static" / "academy_dashboard_v4_polish_v1.css").read_text(encoding="utf-8")
    html = (REPO_ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")

    assert "$('.c17-links-card', grid)?.remove()" in js
    assert "${monthLabelFromDashboard(root)} - Enrollment Tracker : ${count}" in js
    assert "c17-tracker-full" in js
    assert ".c17-enrollment-grid.c17-tracker-full" in css

    assert "c17-finance-row" in js
    assert "row.append(receipts, payments)" in js
    assert ".c17-finance-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr)" in css

    assert "#academyWorkspace>.academy-primary-nav" in css
    assert "#academyWorkspace>.academy-tabs" in css
    assert "display:none!important" in css

    assert "userPlus" in js
    assert "Players in Programs" in js
    assert "New Enrollment" in js
    assert "Enrollment Tracker" in js
    assert "Upcoming Events" in js
    assert "Session Attendance" in js
    assert "Academy Receipts" in js
    assert "Academy Payments" in js
    assert "c17-program-person" in js
    assert "c17-nav-svg" in css
    assert "c17-title-svg" in css

    v4_css = html.index('/static/academy_dashboard_v4.css?v=1')
    polish_css = html.index('/static/academy_dashboard_v4_polish_v1.css?v=1')
    v4_js = html.index('/static/academy_dashboard_v4.js?v=1')
    polish_js = html.index('/static/academy_dashboard_v4_polish_v1.js?v=1')
    assert polish_css > v4_css
    assert polish_js > v4_js


def test_dashboard_v4_polish_has_idempotent_mutation_guards():
    js = (REPO_ROOT / "app" / "static" / "academy_dashboard_v4_polish_v1.js").read_text(encoding="utf-8")
    assert "dataset.prototypeIcon" in js
    assert "if (row) return" in js
    assert "if (scheduled) return" in js
    assert "requestAnimationFrame(apply)" in js


def test_c17_left_navigation_is_stable_and_clickable():
    shell = (REPO_ROOT / "app" / "static" / "academy_c17_shell_v1.js").read_text(encoding="utf-8")
    html = (REPO_ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")

    assert "NAV_SIGNATURE" in shell
    assert "holder.dataset.c17Signature !== NAV_SIGNATURE" in shell
    assert "buildAcademyNav(holder)" in shell
    assert shell.count("holder.innerHTML =") == 1

    assert "holder.addEventListener('click'" in shell
    assert "event.target.closest('[data-c17-target]')" in shell
    assert "holder.dataset.c17Wired === '1'" in shell
    assert "location.hash = target" in shell

    assert "button.classList.toggle('active', selected)" in shell
    assert "aria-current" in shell
    assert '/static/academy_c17_shell_v1.js?v=2' in html


def test_c17_dashboard_first_paint_never_exposes_legacy_overview():
    first_paint = (REPO_ROOT / "app" / "static" / "academy_dashboard_first_paint_v1.js").read_text(encoding="utf-8")
    first_paint_css = (REPO_ROOT / "app" / "static" / "academy_dashboard_first_paint_v1.css").read_text(encoding="utf-8")
    route_guard = (REPO_ROOT / "app" / "static" / "academy_route_guard.js").read_text(encoding="utf-8")
    html = (REPO_ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")

    assert "c17-overview-first-paint" in first_paint
    assert "c17DashboardFirstPaint" in first_paint
    assert "c17-fp-hero" in first_paint
    assert "c17-fp-programs" in first_paint
    assert "c17-fp-table" in first_paint
    assert "c17-fp-money" in first_paint
    assert "#academyWorkspace{display:none!important}" in first_paint_css

    assert "content.dataset.dashboardV4 !== '1'" in first_paint
    assert "content.querySelector('.c17-dashboard')" in first_paint
    assert "document.getElementById(SHELL_ID)?.remove()" in first_paint

    assert "academyTransitionSnapshot" in first_paint
    assert "academy-tab-transitioning" in first_paint

    # The first-paint layer is visual-only. It must not start API work before the
    # normal Academy/session renderers are ready, because that can race auth/data setup.
    assert "fetch('/api/academy/dashboard/v3'" not in first_paint
    assert "fetch('/api/academy/enrollments'" not in first_paint

    assert "const VERSION = '4'" in route_guard
    assert "isAcademyOverviewRoute()" in route_guard
    assert "if (isAcademyOverviewRoute())" in route_guard

    assert '/static/academy_dashboard_first_paint_v1.css?v=1' in html
    assert '/static/academy_route_guard.js?v=4' in html
    fp_js = html.index('/static/academy_dashboard_first_paint_v1.js?v=1')
    legacy_js = html.index('/static/academy_v3.js?v=3')
    assert fp_js < legacy_js
