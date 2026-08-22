from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_sessions_expose_take_attendance_deep_link():
    dashboard = (ROOT / "app" / "static" / "cam_dashboard_v4.js").read_text(encoding="utf-8")
    attendance = (ROOT / "app" / "static" / "cam_attendance_v1.js").read_text(encoding="utf-8")
    assert "Take Attendance" in dashboard
    assert "cam?tab=attendance&session_id=" in dashboard
    assert "sessionIdFromHash" in attendance
    assert "['present','late','absent']" in attendance
    assert "['present','absent','late','excused']" not in attendance
