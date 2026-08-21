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

    result = dashboard_v3._new_enrollments(
        {"id": 1, "timezone": "America/New_York"},
        date(2026, 8, 20),
    )

    assert result["count"] == 1
    assert result["players"][0]["player_name"] == "Jr Sumo verma"
    assert result["players"][0]["parent_name"] == "sumo verma"
    assert result["players"][0]["enrolled_date"] == "2026-08-20"


def test_dashboard_v3_matches_approved_layout_contract():
    js = (REPO_ROOT / "app" / "static" / "academy_dashboard_v3.js").read_text(encoding="utf-8")
    css = (REPO_ROOT / "app" / "static" / "academy_dashboard_v3.css").read_text(encoding="utf-8")
    html = (REPO_ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    run_py = (REPO_ROOT / "run.py").read_text(encoding="utf-8")

    assert "/api/academy/dashboard/v3" in js
    assert "forecast_days:'7'" in js
    assert "Players in Programs" in js
    assert "Beginners" in js and "U11" in js and "U13" in js and "U14" in js and "U15" in js
    assert "New Enrollment :" in js
    assert "parent_name" in js
    assert ">Assign Batch</button>" in js
    assert "Enrollment Links Sent" in js
    assert "Enrollment Tracker" in js

    # Both session tables must show coach names, including private/1-on-1 sessions.
    assert "<th>Batch</th><th>Coach</th><th>Venue</th><th>Time</th>" in js
    assert "<th>Player</th><th>Coach</th><th>Venue</th><th>Time</th>" in js
    assert "row.coach_name" in js

    assert "Academy Receipts" in js
    assert "Group Session Fee Received" in js
    assert "Group Session Fee Pending" in js
    assert "Academy Payments" in js
    assert "Coach Salary Payments" in js
    assert "Facility Payments" in js
    assert "Academy Expenses" in js
    assert "Upcoming Events" in js
    assert "Matches" in js and "Camps / Programs" in js and "Tournaments" in js

    # Dashboard attendance is intentionally batch-based and has no Excused column.
    assert "cam-v3-attendance-grid" in js
    assert "Attended ${Number(row.attended || 0)} / ${Number(row.scheduled || 0)}" in js
    assert "Excused" not in js

    # Search/Crick AI topbar is hidden only while Academy Dashboard v3 is active.
    assert "body.cam-academy-dashboard-v3-mode .topbar{display:none!important}" in css
    assert "cam-v3-legacy-sibling" in css
    assert "academy_dashboard_v3.css?v=1" in html
    assert "academy_dashboard_v3.js?v=1" in html
    assert "academy_dashboard_v2.js" not in html
    assert "academy_dashboard_v3_router" in run_py


def test_dashboard_v3_api_attendance_does_not_expose_excused_column():
    source = (REPO_ROOT / "app" / "academy_dashboard_v3_api.py").read_text(encoding="utf-8")
    assert '"scheduled": 0, "present": 0, "late": 0, "absent": 0, "not_recorded": 0' in source
    assert '"attended"' in source
    assert '"attendance_percent"' in source
    assert '"excused"' not in source
