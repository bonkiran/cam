from __future__ import annotations

from datetime import date
from pathlib import Path

import app.academy_dashboard_v3_api as dashboard_v3

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_program_bucket_maps_requested_academy_groups():
    assert dashboard_v3._program_bucket("Beginners") == "Beginners"
    assert dashboard_v3._program_bucket("U11 Academy") == "U11"
    assert dashboard_v3._program_bucket("Under 13 Development") == "U13"
    assert dashboard_v3._program_bucket("Elite", code="U14") == "U14"
    assert dashboard_v3._program_bucket("Performance", age_group="Under 15") == "U15"
    assert dashboard_v3._program_bucket("Adult Cricket") is None


def test_new_enrollment_uses_local_month_and_exposes_parent(monkeypatch):
    rows = [
        {
            "enrollment_id": 101,
            "completed_at": "2026-08-21T00:50:00+00:00",
            "player_id": 11,
            "player_name": "Jr Sumo verma",
            "parent_first_name": "sumo",
            "parent_last_name": "verma",
            "batch_id": None,
            "batch_name": None,
            "batch_status": None,
        },
        {
            "enrollment_id": 102,
            "completed_at": "2026-09-01T05:00:00+00:00",
            "player_id": 12,
            "player_name": "September Player",
            "parent_first_name": "September",
            "parent_last_name": "Parent",
            "batch_id": None,
            "batch_name": None,
            "batch_status": None,
        },
    ]
    monkeypatch.setattr(dashboard_v3, "fetch_all", lambda *args, **kwargs: rows)
    result = dashboard_v3._new_enrollments({"id": 1, "timezone": "America/New_York"}, date(2026, 8, 20))
    assert result["count"] == 1
    assert result["players"][0]["player_name"] == "Jr Sumo verma"
    assert result["players"][0]["parent_name"] == "sumo verma"
    assert result["players"][0]["enrolled_date"] == "2026-08-20"


def test_dashboard_v4_matches_approved_c17_prototype_contract():
    js = (REPO_ROOT / "app" / "static" / "academy_dashboard_v4.js").read_text(encoding="utf-8")
    css = (REPO_ROOT / "app" / "static" / "academy_dashboard_v4.css").read_text(encoding="utf-8")
    shell_js = (REPO_ROOT / "app" / "static" / "academy_c17_shell_v1.js").read_text(encoding="utf-8")
    shell_css = (REPO_ROOT / "app" / "static" / "academy_c17_shell_v1.css").read_text(encoding="utf-8")
    html = (REPO_ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    run_py = (REPO_ROOT / "run.py").read_text(encoding="utf-8")

    assert "/api/academy/dashboard/v3" in js
    assert "/api/academy/enrollments" in js
    assert "forecast_days:'7'" in js
    assert "Players in Programs" in js
    assert all(group in js for group in ["Beginners", "U11", "U13", "U14", "U15"])
    assert "New Enrollment :" in js and "Enrolled Date" in js and "Assign Batch" in js
    assert "Enrollment Links Sent" in js and "Enrollment Tracker" in js
    assert "View all enrollment links" in js

    assert "<th>Batch</th><th>Coach</th><th>Venue</th><th>Time</th>" in js
    assert "<th>Player</th><th>Coach</th><th>Venue</th><th>Time</th>" in js
    assert "row.coach_name" in js

    assert "Upcoming Events" in js
    assert "Matches" in js and "Camps / Programs" in js and "Tournaments" in js
    assert "Session Attendance" in js
    assert "<th>Scheduled</th><th>Present</th><th>Late</th><th>Absent</th><th>Not Recorded</th><th>Attendance %</th>" in js
    assert "Excused" not in js

    # Financial panels are intentionally at the bottom, after Events and Attendance.
    markup = js[js.index("function dashboardMarkup"):]
    assert markup.index("eventsMarkup(data)") < markup.index("attendanceMarkup(data)") < markup.index("receiptsMarkup(data)") < markup.index("paymentsMarkup(data)")
    assert "Academy Receipts" in js and "Academy Payments" in js

    # Cross-origin weather GET must stay a simple request (no forced JSON content-type).
    assert "if (options.body && !headers['Content-Type'])" in js
    assert "geocoding-api.open-meteo.com" in js and "api.open-meteo.com/v1/forecast" in js

    # C17 academy shell removes the academy top tab bar and supplies the approved left nav.
    assert "body.c17-academy-mode #academyWorkspace .academy-tabs{display:none!important}" in shell_css
    for label in ["Dashboard", "Registration", "Players", "Programs", "Coaches", "Finance", "Reports", "Settings", "Insights", "Help & Support"]:
        assert label in shell_js
    assert "label:'Academy'" not in shell_js
    assert "{label:'Dashboard', icon:'⌂', target:'academy'" in shell_js
    assert "active:r => r.page==='academy' && r.tab==='overview'" in shell_js
    assert "C17" in shell_js and "CRICKET ACADEMY" in shell_js
    assert "/static/c17_academy_logo.png" in shell_js

    assert "academy_c17_shell_v1.css?v=1" in html
    assert "academy_dashboard_v4.css?v=1" in html
    assert "academy_c17_shell_v1.js?v=4" in html
    assert "academy_dashboard_v4.js?v=1" in html
    assert "academy_dashboard_v3.js" not in html
    assert "academy_dashboard_v3_refinement_v1.js" not in html
    assert "academy_dashboard_enrollments_v1.js" not in html
    assert "academy_dashboard_v3_router" in run_py
    assert ".c17-enrollment-grid" in css


def test_dashboard_v3_api_attendance_does_not_expose_excused_column():
    source = (REPO_ROOT / "app" / "academy_dashboard_v3_api.py").read_text(encoding="utf-8")
    assert '"scheduled": 0, "present": 0, "late": 0, "absent": 0, "not_recorded": 0' in source
    assert '"attended"' in source
    assert '"attendance_percent"' in source
    assert '"excused"' not in source


def test_dashboard_v3_degrades_one_section_without_blank_page(monkeypatch):
    monkeypatch.setattr(
        dashboard_v3,
        "_academy_for_user",
        lambda user: {
            "id": 1,
            "name": "CAM Academy",
            "city": "Johns Creek",
            "state": "GA",
            "postal_code": "30022",
            "country": "US",
            "timezone": "America/New_York",
        },
    )
    monkeypatch.setattr(dashboard_v3, "_local_today", lambda profile: date(2026, 8, 21))

    def fail_program_counts():
        raise RuntimeError("simulated production query failure")

    monkeypatch.setattr(dashboard_v3, "_program_counts", fail_program_counts)
    monkeypatch.setattr(dashboard_v3, "_new_enrollments", lambda profile, today: {"count": 1, "players": [{"player_id": 7}]})
    monkeypatch.setattr(dashboard_v3, "_registration_tracker", lambda profile, today: {"links_sent_count": 2, "tracker_count": 2, "rows": []})
    monkeypatch.setattr(dashboard_v3, "_today_sessions", lambda today: {"group": [], "private": [], "count": 0})
    monkeypatch.setattr(dashboard_v3, "_fee_receipts", lambda today: {"group_session_fee_received_cents": 0, "group_session_fee_pending_cents": 0})
    monkeypatch.setattr(dashboard_v3, "_academy_payments", lambda today: {"coach_salary_payments_cents": 0, "facility_payments_cents": 0, "academy_expenses_cents": 0})
    monkeypatch.setattr(dashboard_v3, "_upcoming_events", lambda today: {"matches": [], "programs": [], "tournaments": []})
    monkeypatch.setattr(dashboard_v3, "_attendance_by_batch", lambda today: {"date": None, "latest_time": None, "total_scheduled": 0, "batches": []})

    result = dashboard_v3.academy_dashboard_v3({"id": 1, "display_name": "Admin", "role": "admin", "academy_id": 1})
    assert result["new_enrollments"]["count"] == 1
    assert result["registration_tracker"]["links_sent_count"] == 2
    assert result["program_counts"]["total_players"] == 0
    assert result["program_counts"]["buckets"] == {"Beginners": 0, "U11": 0, "U13": 0, "U14": 0, "U15": 0}
    assert result["degraded_sections"] == ["program_counts"]
