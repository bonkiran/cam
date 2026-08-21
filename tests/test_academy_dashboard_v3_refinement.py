from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_c17_dashboard_v4_matches_approved_followup():
    js = (REPO_ROOT / "app" / "static" / "academy_dashboard_v4.js").read_text(encoding="utf-8")
    css = (REPO_ROOT / "app" / "static" / "academy_dashboard_v4.css").read_text(encoding="utf-8")
    shell_js = (REPO_ROOT / "app" / "static" / "academy_c17_shell_v1.js").read_text(encoding="utf-8")
    shell_css = (REPO_ROOT / "app" / "static" / "academy_c17_shell_v1.css").read_text(encoding="utf-8")
    html = (REPO_ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    logo = REPO_ROOT / "app" / "static" / "c17_academy_logo.png"

    assert logo.exists()
    assert logo.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert "C17" in shell_js and "CRICKET ACADEMY" in shell_js
    assert "/static/c17_academy_logo.png" in shell_js
    assert "C17 Academy Dashboard" in js

    # Weather calls are plain GETs; JSON content-type is added only for request bodies.
    assert "if (options.body && !headers['Content-Type'])" in js
    assert "forecast_days:'7'" in js
    assert "geocoding-api.open-meteo.com" in js
    assert "api.open-meteo.com/v1/forecast" in js

    # Enrollment section mirrors the approved prototype and uses Process 2 enrollment data.
    assert "/api/academy/enrollments" in js
    assert "Enrollment Links Sent :" in js
    assert "Enrollment Tracker :" in js
    assert "View all enrollment links →" in js
    assert "Completed" in js and "In Progress" in js and "Sent" in js
    assert "c17-enrollment-grid" in css

    # Operational order: Upcoming Events and Attendance precede full-width Receipts/Payments.
    markup = js[js.index("function dashboardMarkup"):]
    assert markup.index("eventsMarkup(data)") < markup.index("attendanceMarkup(data)")
    assert markup.index("attendanceMarkup(data)") < markup.index("receiptsMarkup(data)")
    assert markup.index("receiptsMarkup(data)") < markup.index("paymentsMarkup(data)")
    assert ".c17-money-grid" in css

    # Left-side academy nav replaces the horizontal academy tabs.
    assert "academy-tabs{display:none!important}" in shell_css
    assert "c17-sidebar-nav" in shell_js
    assert "academy_c17_shell_v1.js?v=1" in html
    assert "academy_dashboard_v4.js?v=1" in html
    assert "academy_dashboard_v3_refinement_v1.js" not in html


def test_c17_shell_navigation_contains_all_approved_items():
    js = (REPO_ROOT / "app" / "static" / "academy_c17_shell_v1.js").read_text(encoding="utf-8")
    for label in ["Dashboard", "Academy", "Registration", "Players", "Programs", "Coaches", "Finance", "Reports", "Settings", "Insights", "Help & Support"]:
        assert label in js
