from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_v4_polish_matches_approved_prototype_changes():
    js = (REPO_ROOT / "app" / "static" / "cam_dashboard_v4_polish_v1.js").read_text(encoding="utf-8")
    css = (REPO_ROOT / "app" / "static" / "cam_dashboard_v4_polish_v1.css").read_text(encoding="utf-8")
    html = (REPO_ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")

    # Enrollment links card is removed and the tracker becomes a full-width month-labelled table.
    assert "$('.c17-links-card', grid)?.remove()" in js
    assert "${monthLabelFromDashboard(root)} - Enrollment Tracker : ${count}" in js
    assert "c17-tracker-full" in js
    assert ".c17-enrollment-grid.c17-tracker-full" in css

    # Receipts and Payments are recomposed into one balanced 50/50 row.
    assert "c17-finance-row" in js
    assert "row.append(receipts, payments)" in js
    assert ".c17-finance-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr)" in css

    # Academy top navigation is hidden; left navigation is the only Academy navigation surface.
    assert "#camWorkspace>.cam-primary-nav" in css
    assert "#camWorkspace>.cam-tabs" in css
    assert "display:none!important" in css

    # Prototype-style SVG icon system covers the sidebar and dashboard sections.
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

    # Readability polish is loaded after Dashboard v4 so it wins the cascade.
    v4_css = html.index('/static/cam_dashboard_v4.css?v=1')
    polish_css = html.index('/static/cam_dashboard_v4_polish_v1.css?v=1')
    v4_js = html.index('/static/cam_dashboard_v4.js?v=1')
    polish_js = html.index('/static/cam_dashboard_v4_polish_v1.js?v=1')
    assert polish_css > v4_css
    assert polish_js > v4_js


def test_dashboard_v4_polish_has_idempotent_mutation_guards():
    js = (REPO_ROOT / "app" / "static" / "cam_dashboard_v4_polish_v1.js").read_text(encoding="utf-8")
    assert "dataset.prototypeIcon" in js
    assert "if (row) return" in js
    assert "if (scheduled) return" in js
    assert "requestAnimationFrame(apply)" in js


def test_c17_left_navigation_is_stable_and_clickable():
    shell = (REPO_ROOT / "app" / "static" / "cam_c17_shell_v1.js").read_text(encoding="utf-8")
    html = (REPO_ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")

    # The shell must not replace all nav buttons on every MutationObserver pass.
    # Rebuilding repeatedly conflicted with the prototype icon-polish observer and
    # continuously destroyed/recreated the clickable elements.
    assert "NAV_SIGNATURE" in shell
    assert "holder.dataset.c17Signature !== NAV_SIGNATURE" in shell
    assert "buildAcademyNav(holder)" in shell
    assert shell.count("holder.innerHTML =") == 1

    # Use one delegated click handler on the persistent holder so icon DOM changes
    # cannot detach button navigation behavior.
    assert "holder.addEventListener('click'" in shell
    assert "event.target.closest('[data-c17-target]')" in shell
    assert "holder.dataset.c17Wired === '1'" in shell
    assert "location.hash = target" in shell

    # Active state changes without rebuilding the navigation.
    assert "button.classList.toggle('active', selected)" in shell
    assert "aria-current" in shell

    # The Academy overview is not exposed as a duplicate left-nav item. Dashboard owns it.
    assert "label:'Academy'" not in shell
    assert "{label:'Dashboard', icon:'⌂', target:'cam'" in shell

    # Cache-bust the repaired navigation script in production.
    assert '/static/cam_c17_shell_v1.js?v=4' in html
