from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_legacy_academy_overview_is_guarded_before_dashboard_v4_loads():
    html = (REPO_ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    guard = (REPO_ROOT / "app" / "static" / "academy_dashboard_transition_guard_v1.js").read_text(encoding="utf-8")

    academy_index = html.index('/static/academy_v3.js?v=3')
    guard_index = html.index('/static/academy_dashboard_transition_guard_v1.js?v=1')
    dashboard_v4_index = html.index('/static/cam_dashboard_v4.js?v=1')

    # Register the guard after the legacy Academy renderer but before Dashboard v4.
    # academy_v3 is async, so the MutationObserver is active before its old overview can paint.
    assert academy_index < guard_index < dashboard_v4_index

    # The old Academy overview is replaced in the same mutation cycle with a prototype-style
    # loading shell. Dashboard v4 remains the final owner of the content surface.
    assert "new MutationObserver(schedule)" in guard
    assert ":scope > .cam-hero" in guard
    assert ":scope > .cam-stats" in guard
    assert ":scope > .cam-dashboard-grid" in guard
    assert "content.innerHTML = loadingMarkup()" in guard
    assert "data-c17-transition-guard" in guard
    assert "content.dataset.dashboardV4 === '1'" in guard
    assert "c17-dashboard" in guard
