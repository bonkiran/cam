from __future__ import annotations

from datetime import date
from pathlib import Path

import app.academy_dashboard_enrollment_api as dashboard_enrollments

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_monthly_enrollments_uses_academy_local_completion_date(monkeypatch):
    rows = [
        {
            "enrollment_id": 101,
            "completed_at": "2026-08-21T00:50:00+00:00",
            "player_id": 11,
            "player_name": "Jr Sumo verma",
            "batch_membership_id": None,
            "batch_id": None,
            "batch_name": None,
            "batch_status": None,
            "batch_joined_on": None,
        },
        {
            "enrollment_id": 102,
            "completed_at": "2026-09-01T05:00:00+00:00",
            "player_id": 12,
            "player_name": "September Player",
            "batch_membership_id": None,
            "batch_id": None,
            "batch_name": None,
            "batch_status": None,
            "batch_joined_on": None,
        },
    ]
    monkeypatch.setattr(dashboard_enrollments, "fetch_all", lambda *args, **kwargs: rows)

    result = dashboard_enrollments._monthly_enrollments(
        {"id": 1, "timezone": "America/New_York"},
        date(2026, 8, 20),
    )

    assert result["period"] == "2026-08"
    assert result["period_label"] == "August 2026"
    assert result["count"] == 1
    assert result["players"] == [
        {
            "enrollment_id": 101,
            "player_id": 11,
            "player_name": "Jr Sumo verma",
            "enrolled_at": "2026-08-21T00:50:00+00:00",
            "enrolled_date": "2026-08-20",
            "batch_membership_id": None,
            "batch_id": None,
            "batch_name": None,
            "batch_status": None,
            "batch_joined_on": None,
        }
    ]


def test_monthly_enrollments_exposes_current_batch_assignment(monkeypatch):
    rows = [
        {
            "enrollment_id": 201,
            "completed_at": "2026-08-20T18:30:00+00:00",
            "player_id": 21,
            "player_name": "Assigned Player",
            "batch_membership_id": 301,
            "batch_id": 401,
            "batch_name": "U15 Evening",
            "batch_status": "active",
            "batch_joined_on": "2026-08-20",
        }
    ]
    monkeypatch.setattr(dashboard_enrollments, "fetch_all", lambda *args, **kwargs: rows)

    result = dashboard_enrollments._monthly_enrollments(
        {"id": 1, "timezone": "America/New_York"},
        date(2026, 8, 20),
    )

    player = result["players"][0]
    assert player["batch_membership_id"] == 301
    assert player["batch_id"] == 401
    assert player["batch_name"] == "U15 Evening"
    assert player["batch_status"] == "active"
    assert player["batch_joined_on"] == "2026-08-20"


def test_dashboard_ui_uses_requested_header_and_inline_batch_assignment():
    js = (REPO_ROOT / "app" / "static" / "academy_dashboard_enrollments_v1.js").read_text(encoding="utf-8")
    css = (REPO_ROOT / "app" / "static" / "academy_dashboard_enrollments_v1.css").read_text(encoding="utf-8")
    html = (REPO_ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")

    assert "/api/academy/dashboard/new-player-enrollments" in js
    assert "${esc(periodLabel)} - New Enrollment : ${count}" in js
    assert "New Player Registrations" in js
    assert "Enrolled ${esc(dateLabel(player.enrolled_date))}" in js
    assert ">Assign Batch</button>" in js
    assert "/api/academy/batches" in js
    assert "/players`" in js
    assert "Confirm Assignment" in js
    assert "waitlist_if_full:false" in js
    assert "cam-new-enrollment-actions" in css
    assert "academy_dashboard_enrollments_v1.css" in html
    assert "academy_dashboard_enrollments_v1.js?v=2" in html


def test_dashboard_readability_and_enrollment_dedupe_assets_are_loaded():
    readability = (REPO_ROOT / "app" / "static" / "academy_dashboard_readability_v1.css").read_text(encoding="utf-8")
    dedupe = (REPO_ROOT / "app" / "static" / "academy_dashboard_enrollment_dedupe_v1.js").read_text(encoding="utf-8")
    html = (REPO_ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")

    assert 'data-dashboard-v2="1"' in readability
    assert ".panel-head p" in readability
    assert ".academy-stat small" in readability
    assert ".cam-weather-primary small" in readability
    assert "font-size: 13px" in readability
    assert "font-size: 12px" in readability
    assert "min-font-size" not in readability

    assert ".cam-new-player-enrollments" in dedupe
    assert "enrollmentPanels.forEach" in dedupe
    assert "panel.remove()" in dedupe
    assert "legacy.remove()" in dedupe

    assert "academy_dashboard_readability_v1.css?v=1" in html
    assert "academy_dashboard_enrollment_dedupe_v1.js?v=1" in html
