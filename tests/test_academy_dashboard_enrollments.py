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
        },
        {
            "enrollment_id": 102,
            "completed_at": "2026-09-01T05:00:00+00:00",
            "player_id": 12,
            "player_name": "September Player",
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
        }
    ]


def test_dashboard_ui_replaces_registration_language_with_completed_enrollments():
    js = (REPO_ROOT / "app" / "static" / "academy_dashboard_enrollments_v1.js").read_text(encoding="utf-8")
    html = (REPO_ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")

    assert "/api/academy/dashboard/new-player-enrollments" in js
    assert "New Player Enrolled:" in js
    assert "New Player Registrations" in js
    assert "Enrolled ${esc(dateLabel(player.enrolled_date))}" in js
    assert "academy_dashboard_enrollments_v1.js" in html
