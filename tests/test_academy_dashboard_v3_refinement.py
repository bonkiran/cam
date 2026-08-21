from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_c17_dashboard_refinement_matches_approved_followup():
    js = (REPO_ROOT / "app" / "static" / "academy_dashboard_v3_refinement_v1.js").read_text(encoding="utf-8")
    css = (REPO_ROOT / "app" / "static" / "academy_dashboard_v3_refinement_v1.css").read_text(encoding="utf-8")
    html = (REPO_ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    logo = REPO_ROOT / "app" / "static" / "c17_cricket_academy_logo.png"

    assert logo.exists()
    assert logo.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert "C17 Cricket Academy" in js
    assert "/static/c17_cricket_academy_logo.png" in js
    assert "C17 Cricket Academy Operations Dashboard" in js

    # Weather fix: Open-Meteo calls must be plain GETs with no JSON Content-Type header.
    assert "async function externalJson" in js
    assert "fetch(url,{cache:'no-store'})" in js
    assert "forecast_days:'7'" in js
    assert "geocoding-api.open-meteo.com" in js

    # Enrollment section mirrors the approved prototype and reads the same invite source as Registration.
    assert "/api/academy/registration/invites" in js
    assert "Enrollment Links Sent :" in js
    assert "Enrollment Tracker :" in js
    assert "View all enrollment links →" in js
    assert "data-c17-resend" in js
    assert "data-c17-view-registration" in js
    assert "cam-v3-enrollment-prototype" in css

    # Operational order: Upcoming Events and Attendance are moved above full-width Receipts/Payments.
    assert "cam-v3-finance-stack" in js
    assert "root.insertBefore(events,finance)" in js
    assert "root.insertBefore(attendance,finance)" in js
    assert ".cam-v3-finance-grid.cam-v3-finance-stack{grid-template-columns:1fr}" in css

    # Refinement must load immediately after Dashboard v3.
    v3 = html.index('/static/academy_dashboard_v3.js?v=1')
    refinement = html.index('/static/academy_dashboard_v3_refinement_v1.js?v=1')
    assert refinement > v3
    assert '/static/academy_dashboard_v3_refinement_v1.css?v=1' in html


def test_refinement_has_loop_guards_for_mutation_observer():
    js = (REPO_ROOT / "app" / "static" / "academy_dashboard_v3_refinement_v1.js").read_text(encoding="utf-8")
    assert "c17WeatherSignature" in js
    assert "c17EnrollmentSignature" in js
    assert "events.nextElementSibling!==attendance" in js
