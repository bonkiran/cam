from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def save(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def must_replace(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Missing expected fragment for {label}")
    return text.replace(old, new)


def patch_dashboard() -> None:
    path = "app/static/cam_dashboard_v4.js"
    text = load(path)
    text = must_replace(
        text,
        "location.hash = tab === 'overview' ? 'cam' : `academy?tab=${encodeURIComponent(tab)}`;",
        "location.hash = tab === 'overview' ? 'cam' : `cam?tab=${encodeURIComponent(tab)}`;",
        "dashboard go() CAM route",
    )

    new_session_rows = '''  function sessionRows(rows = [], privateSession = false) {
    return rows.map(row => `<tr><td>${esc(privateSession ? (row.player_name || 'Player') : (row.batch_name || 'Group Session'))}</td><td>${esc(row.coach_name || 'Coach not assigned')}</td><td>${esc(row.location || 'Location not set')}</td><td>${esc(sessionTime(row.start_time, row.duration_minutes))}</td><td><button type="button" class="c17-table-action c17-take-attendance" data-session-id="${Number(row.id)}">Take Attendance</button></td></tr>`).join('');
  }
'''
    text, count = re.subn(
        r"  function sessionRows\(rows = \[\], privateSession = false\) \{.*?\n  \}\n\n  function sessionsMarkup",
        new_session_rows + "\n  function sessionsMarkup",
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("Could not replace dashboard sessionRows")

    new_sessions_markup = '''  function sessionsMarkup(data) {
    const sessions = data.sessions || {group:[], private:[], count:0};
    return `<article class="c17-card">${cardTitle('▣',esc(fmtDayDate(data.as_of))+' Sessions : '+Number(sessions.count || 0))}<div class="c17-session-grid"><section><h3>Group Sessions - ${sessions.group?.length || 0}</h3><div class="c17-table-wrap"><table><thead><tr><th>Batch</th><th>Coach</th><th>Venue</th><th>Time</th><th>Action</th></tr></thead><tbody>${sessionRows(sessions.group) || '<tr><td colspan="5">No group sessions scheduled today.</td></tr>'}</tbody></table></div></section><section><h3>1 on 1 Sessions - ${sessions.private?.length || 0}</h3><div class="c17-table-wrap"><table><thead><tr><th>Player</th><th>Coach</th><th>Venue</th><th>Time</th><th>Action</th></tr></thead><tbody>${sessionRows(sessions.private, true) || '<tr><td colspan="5">No 1 on 1 sessions scheduled today.</td></tr>'}</tbody></table></div></section></div></article>`;
  }
'''
    text, count = re.subn(
        r"  function sessionsMarkup\(data\) \{.*?\n  \}\n\n  function eventDateRange",
        new_sessions_markup + "\n  function eventDateRange",
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("Could not replace dashboard sessionsMarkup")

    anchor = "    $$('[data-dashboard-tab]', root).forEach(button => button.onclick = () => go(button.dataset.dashboardTab));\n"
    addition = anchor + "    $$('.c17-take-attendance', root).forEach(button => button.onclick = () => { const sessionId = Number(button.dataset.sessionId || 0); if (sessionId) location.hash = `cam?tab=attendance&session_id=${encodeURIComponent(sessionId)}`; });\n"
    text = must_replace(text, anchor, addition, "dashboard attendance wiring")
    save(path, text)


def patch_attendance_ui() -> None:
    path = "app/static/cam_attendance_v1.js"
    text = load(path)
    text = must_replace(
        text,
        "function statusOptions(value=''){return ['present','absent','late','excused'].map(v=>`<option value=\"${v}\" ${value===v?'selected':''}>${v[0].toUpperCase()+v.slice(1)}</option>`).join('');}",
        "function statusOptions(value=''){return ['present','late','absent'].map(v=>`<option value=\"${v}\" ${value===v?'selected':''}>${v[0].toUpperCase()+v.slice(1)}</option>`).join('');}",
        "attendance status options",
    )
    tab_fn = "function tabFromHash(){const raw=location.hash.replace(/^#/,'');const [page,query='']=raw.split('?');if(page!=='cam')return null;return new URLSearchParams(query).get('tab')||'overview';}"
    tab_plus = tab_fn + "\n  function sessionIdFromHash(){const raw=location.hash.replace(/^#/,'');const [page,query='']=raw.split('?');if(page!=='cam')return null;return Number(new URLSearchParams(query).get('session_id'))||null;}"
    text = must_replace(text, tab_fn, tab_plus, "attendance session id route parser")
    text = text.replace(
        "Attendance % uses present + late as attended, absent against the percentage, and excused outside the denominator.",
        "Attendance % uses Present + Late as attended; Absent counts against the percentage.",
    )
    text = text.replace(
        "<small>Absent / ${policy.default_makeup_for_excused?'excused enabled':'excused disabled'}</small>",
        "<small>Absent only</small>",
    )
    text = re.sub(
        r'<label class="cam-checkbox"><input name="default_makeup_for_excused" type="checkbox" \$\{policy\.default_makeup_for_excused\?\'checked\':\'\'\}> Make excused players make-up eligible by default</label>',
        '',
        text,
    )
    text = text.replace(
        "const defaultMakeup=(st==='absent'&&policy.default_makeup_for_absent)||(st==='excused'&&policy.default_makeup_for_excused);",
        "const defaultMakeup=st==='absent'&&policy.default_makeup_for_absent;",
    )
    text = text.replace(
        'placeholder="Required context for absence/excused"',
        'placeholder="Required context for absence"',
    )
    text, count = re.subn(
        r"  function updateRowForStatus\(row,policy,applyDefault=true\)\{.*?\}\n",
        "  function updateRowForStatus(row,policy,applyDefault=true){const status=$('[name=\"attendance_status\"]',row).value;const reason=$('[name=\"absence_reason\"]',row);const makeup=$('[name=\"make_up_eligible\"]',row);const isAbsent=status==='absent';reason.disabled=!isAbsent;if(!isAbsent)reason.value='';if(applyDefault){makeup.checked=isAbsent?!!policy.default_makeup_for_absent:false;}}\n",
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("Could not replace attendance row status logic")
    text = text.replace(
        ",default_makeup_for_excused:fd.has('default_makeup_for_excused')",
        "",
    )
    text = must_replace(
        text,
        "async function renderAttendance(force=false,sessionId=null){if(rendering||tabFromHash()!=='attendance')return;",
        "async function renderAttendance(force=false,sessionId=null){if(rendering||tabFromHash()!=='attendance')return;if(!selectedSessionId)selectedSessionId=sessionIdFromHash();",
        "attendance deep link selection",
    )
    save(path, text)


def patch_attendance_api() -> None:
    path = "app/cam_attendance_api.py"
    text = load(path)
    text = must_replace(text, 'AttendanceStatus = Literal["present", "absent", "late", "excused"]', 'AttendanceStatus = Literal["present", "late", "absent"]', "attendance status enum")
    text = text.replace("    default_makeup_for_excused: bool = True\n", "")
    text = text.replace('            "default_makeup_for_excused": True,\n', '')
    text = text.replace('    out["default_makeup_for_excused"] = bool(out.get("default_makeup_for_excused"))\n', '    out.pop("default_makeup_for_excused", None)\n')
    text = text.replace('    if status == "excused":\n        return bool(policy["default_makeup_for_excused"])\n', '')
    text = must_replace(
        text,
        "            UPDATE attendance_policies SET repeated_absence_threshold=?,absence_lookback_days=?,\n                   default_makeup_for_absent=?,default_makeup_for_excused=?,updated_at=CURRENT_TIMESTAMP\n            WHERE academy_id=?",
        "            UPDATE attendance_policies SET repeated_absence_threshold=?,absence_lookback_days=?,\n                   default_makeup_for_absent=?,default_makeup_for_excused=0,updated_at=CURRENT_TIMESTAMP\n            WHERE academy_id=?",
        "attendance policy SQL",
    )
    text = text.replace("                1 if payload.default_makeup_for_excused else 0,\n", "")
    text = text.replace('reason = _clean(entry.absence_reason) if entry.status in {"absent", "excused"} else None', 'reason = _clean(entry.absence_reason) if entry.status == "absent" else None')
    text = text.replace('counts = {status: 0 for status in ("present", "absent", "late", "excused")}', 'counts = {status: 0 for status in ("present", "late", "absent")}')
    text = text.replace('"calculation_rule": "present + late count as attended; absent counts against percentage; excused is excluded from the denominator",', '"calculation_rule": "present + late count as attended; absent counts against percentage",')

    migration_anchor = "    with connection() as conn:\n        conn.executescript(schema)\n"
    migration = migration_anchor + "        # Normalize historical four-state attendance into the current three-state model.\n        conn.execute(\"UPDATE player_attendance SET status='absent' WHERE status='excused'\")\n        conn.execute(\"UPDATE coach_attendance SET status='absent' WHERE status='excused'\")\n"
    text = must_replace(text, migration_anchor, migration, "legacy attendance status normalization")
    save(path, text)


def patch_player_development() -> None:
    path = "app/cam_player_development_api.py"
    text = load(path)
    text = text.replace(
        "    Present and late count as attended. Absent and excused never receive passive\n    development evidence.",
        "    Present and late count as attended. Absent never receives passive\n    development evidence.",
    )
    save(path, text)


def patch_tests() -> None:
    # MOAT-01 correction uses the supported Absent state and verifies Excused is rejected.
    path = "tests/test_cam14_player_development_api.py"
    text = load(path)
    text = text.replace(
        "    # Attendance correction removes passive evidence immediately. Excused is not\n    # treated as development exposure because the player did not attend.\n",
        "    # Attendance correction removes passive evidence immediately when a player is changed to Absent.\n",
    )
    text = text.replace('{"player_id": p2["id"], "status": "excused", "absence_reason": "Family commitment"}', '{"player_id": p2["id"], "status": "absent", "absence_reason": "Family commitment"}')
    insert = '''\n\ndef test_cam14_rejects_retired_excused_attendance_status():\n    session_id, players = _setup_session("ThreeState")\n    response = client.put(\n        f"/api/cam/sessions/{session_id}/attendance",\n        json={\n            "players": [\n                {"player_id": players[0]["id"], "status": "present"},\n                {"player_id": players[1]["id"], "status": "excused"},\n                {"player_id": players[2]["id"], "status": "absent", "absence_reason": "School"},\n            ],\n            "coach_status": "present",\n        },\n    )\n    assert response.status_code == 422\n'''
    marker = "\n\ndef test_cam14_rejects_unknown_development_skill():"
    text = must_replace(text, marker, insert + marker, "CAM14 retired excused test")
    save(path, text)

    path = "tests/test_cam_attendance_api.py"
    text = load(path)
    text = text.replace("    # Sessions 2-4 exercise all four player statuses and repeated absence alerting.\n", "    # Sessions 2-4 exercise the three supported player statuses and repeated absence alerting.\n")
    text = text.replace('{"player_id": player1["id"], "status": "excused", "absence_reason": "Family commitment"}', '{"player_id": player1["id"], "status": "absent", "absence_reason": "Family commitment"}')
    text = text.replace('    assert summary_data["absent"] == 1\n    assert summary_data["excused"] == 1\n    assert summary_data["attendance_denominator"] == 3\n    assert summary_data["attendance_percentage"] == 66.7\n    assert summary_data["make_up_eligible_count"] == 2\n    assert "excused is excluded" in summary_data["calculation_rule"]\n', '    assert summary_data["absent"] == 2\n    assert "excused" not in summary_data\n    assert summary_data["attendance_denominator"] == 4\n    assert summary_data["attendance_percentage"] == 50.0\n    assert summary_data["make_up_eligible_count"] == 2\n    assert summary_data["calculation_rule"] == "present + late count as attended; absent counts against percentage"\n')
    save(path, text)

    path = "tests/test_cam_attendance_ui.py"
    text = load(path)
    text = text.replace(
        "                # Session 4: excused defaults to make-up eligible and is outside percentage denominator.\n",
        "                # Session 4: Absent remains make-up eligible and counts against attendance percentage.\n",
    )
    text = text.replace('row1.locator(\'[name="attendance_status"]\').select_option("excused")', 'row1.locator(\'[name="attendance_status"]\').select_option("absent")')
    text = text.replace('expect(row1).to_contain_text("66.7% attendance", timeout=10000)', 'expect(row1).to_contain_text("50% attendance", timeout=10000)')
    # Assert the retired status is not present in the browser selector.
    marker = '                expect(page.get_by_text("Alert threshold", exact=True)).to_be_visible()\n'
    addition = marker + '                status_values = page.locator(\'.cam-attendance-player [name="attendance_status"] option\').evaluate_all("els => [...new Set(els.map(e => e.value))]") if page.locator(\'.cam-attendance-player [name="attendance_status"] option\').count() else []\n'
    # The roster is not rendered until a session is selected, so assert after the first session selection instead.
    if addition in text:
        text = text.replace(addition, marker)
    first_session_marker = '                _select_session(page, session_ids[0])\n'
    first_session_add = first_session_marker + '                values = _player_row(page, p1["name"]).locator(\'[name="attendance_status"] option\').evaluate_all("els => els.map(e => e.value)")\n                assert values == ["present", "late", "absent"]\n'
    text = must_replace(text, first_session_marker, first_session_add, "attendance UI three status assertion")
    save(path, text)

    # Naming guard must not flag the literal forbidden strings contained in its own rule definitions.
    path = "tests/test_cam15_naming_guard.py"
    text = load(path)
    old = "        for file in paths:\n            text = file.read_text(encoding=\"utf-8\", errors=\"ignore\")\n"
    new = "        for file in paths:\n            if file.resolve() == Path(__file__).resolve():\n                continue\n            text = file.read_text(encoding=\"utf-8\", errors=\"ignore\")\n"
    text = must_replace(text, old, new, "naming guard self exclusion")
    save(path, text)

    # Add a lightweight guard for the Dashboard -> Attendance deep link.
    dashboard_test = ROOT / "tests" / "test_cam16_dashboard_attendance_entry.py"
    dashboard_test.write_text('''from pathlib import Path\n\nROOT = Path(__file__).resolve().parents[1]\n\n\ndef test_dashboard_sessions_expose_take_attendance_deep_link():\n    dashboard = (ROOT / "app" / "static" / "cam_dashboard_v4.js").read_text(encoding="utf-8")\n    attendance = (ROOT / "app" / "static" / "cam_attendance_v1.js").read_text(encoding="utf-8")\n    assert "Take Attendance" in dashboard\n    assert "cam?tab=attendance&session_id=" in dashboard\n    assert "sessionIdFromHash" in attendance\n    assert "['present','late','absent']" in attendance\n    assert "['present','absent','late','excused']" not in attendance\n''', encoding="utf-8")


def main() -> None:
    patch_dashboard()
    patch_attendance_ui()
    patch_attendance_api()
    patch_player_development()
    patch_tests()
    print("CAM-16 Dashboard attendance entry and three-state attendance patch applied.")


if __name__ == "__main__":
    main()
