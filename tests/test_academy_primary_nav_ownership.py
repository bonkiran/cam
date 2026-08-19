from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "app" / "static" / "index.html"
PRIMARY_NAV = ROOT / "app" / "static" / "academy_primary_nav_v1.js"


def test_only_one_loaded_academy_primary_nav_controller():
    html = INDEX.read_text(encoding="utf-8")

    assert "academy_primary_nav_v1.js" in html
    assert "academy_canonical_nav_v1.js" not in html
    assert "academy_owner_navigation_feedback_v1.js" not in html


def test_primary_nav_loads_before_legacy_feature_modules():
    html = INDEX.read_text(encoding="utf-8")
    primary = html.index("academy_primary_nav_v1.js")

    # These older feature modules historically injected their own top-level tabs.
    # The single-owner nav must take the .academy-tabs hook before they load.
    for script in (
        "academy_programs_v1.js",
        "academy_access_v1.js",
        "academy_parent_portal_v1.js",
        "academy_reviews_v1.js",
        "academy_reports_tab_v1.js",
        "academy_owner_console_v1.js",
    ):
        assert primary < html.index(script), script


def test_primary_nav_has_exact_owner_admin_menu():
    source = PRIMARY_NAV.read_text(encoding="utf-8")
    for label in (
        "Dashboard",
        "Players",
        "Programs",
        "Coaches",
        "Finance",
        "Reports",
        "Settings",
    ):
        assert f"'{label}'" in source

    assert "academy-primary-nav" in source
    assert "classList.remove('academy-tabs')" in source
    assert "CAM_ACADEMY_PRIMARY_NAV_OWNER" in source
