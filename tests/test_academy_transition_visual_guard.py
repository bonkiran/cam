from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_transition_snapshot_never_paints_previous_page_panels():
    css = (REPO_ROOT / "app" / "static" / "academy_ui_cleanup_v1.css").read_text(encoding="utf-8")
    html = (REPO_ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")

    # The navigation-performance layer still uses a temporary transition snapshot,
    # but the snapshot must be a neutral opaque cover. Never render the cloned
    # outgoing Academy page inside it, otherwise Dashboard/Registration cards can
    # be visible behind the incoming page during a route change.
    assert "#academyTransitionSnapshot > .academy-content" in css
    assert "display:none !important" in css
    assert "#academyTransitionSnapshot{" in css
    assert "background:#f7fbf9 !important" in css

    # The moving progress bar and outgoing-page clone are intentionally hidden so
    # the transition cannot expose stacked/ghosted panels for even one frame.
    assert "#academyTransitionSnapshot .academy-transition-progress" in css
    assert "academyTransitionSnapshot::before" in css
    assert "academyTransitionSnapshot::after" in css

    # Cache-bust the CSS so production browsers receive the visual guard immediately.
    assert "/static/academy_ui_cleanup_v1.css?v=4" in html
