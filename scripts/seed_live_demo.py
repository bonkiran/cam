from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://crickanalysis.onrender.com"


def request(method: str, path: str, payload=None, *, retries: int = 4):
    url = BASE_URL + path
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"User-Agent": "CrickAnalysis-Demo-Seeder/1.0"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last = RuntimeError(f"{method} {path} -> HTTP {exc.code}: {body}")
            if exc.code < 500:
                raise last
        except Exception as exc:
            last = exc
        if attempt < retries:
            time.sleep(3 * attempt)
    raise RuntimeError(f"{method} {path} failed after {retries} attempts: {last}")


def get(path: str):
    return request("GET", path)


def post(path: str, payload):
    return request("POST", path, payload)


def wait_for_postgres():
    for attempt in range(1, 61):
        try:
            state = get("/api/system/storage")
            print(f"storage attempt {attempt}: {state}")
            if state and state.get("database") == "postgresql":
                return
        except Exception as exc:
            print(f"storage attempt {attempt}: {exc}")
        time.sleep(10)
    raise RuntimeError("Live Render service did not report PostgreSQL within 10 minutes")


def find_by(items, key, value):
    wanted = str(value).casefold()
    for item in items:
        if str(item.get(key, "")).casefold() == wanted:
            return item
    return None


def ensure_player(payload):
    players = get("/api/academy/players")
    found = find_by(players, "name", payload["name"])
    if found:
        print("reuse player", found["name"], found["id"])
        return found
    created = post("/api/academy/players", payload)
    print("created player", created["name"], created["id"])
    return created


def ensure_program(payload):
    programs = get("/api/academy/programs")
    found = find_by(programs, "name", payload["name"])
    if found:
        print("reuse program", found["name"], found["id"])
        return found
    created = post("/api/academy/programs", payload)
    print("created program", created["name"], created["id"])
    return created


def ensure_enrollment(player_id: int, program_id: int, enrollment_type="regular", start_date="2026-08-17", notes=None):
    rows = get(f"/api/academy/enrollments?player_id={player_id}&program_id={program_id}")
    for row in rows:
        if row.get("status") in {"active", "frozen"}:
            print("reuse enrollment", row["id"], row.get("player_name"), "->", row.get("program_name"))
            return row
    created = post("/api/academy/enrollments", {
        "player_id": player_id,
        "program_id": program_id,
        "enrollment_type": enrollment_type,
        "start_date": start_date,
        "notes": notes,
    })
    print("created enrollment", created["id"], created.get("player_name"), "->", created.get("program_name"))
    return created


def ensure_coach(payload):
    coaches = get("/api/academy/coaches")
    for coach in coaches:
        if str(coach.get("first_name", "")).casefold() == payload["first_name"].casefold() and str(coach.get("last_name", "")).casefold() == payload["last_name"].casefold():
            print("reuse coach", coach["first_name"], coach["last_name"], coach["id"])
            return coach
    created = post("/api/academy/coaches", payload)
    print("created coach", created["first_name"], created["last_name"], created["id"])
    return created


def ensure_coach_player(coach_id: int, player_id: int, role="primary"):
    rows = get(f"/api/academy/coach-player-assignments?coach_id={coach_id}&player_id={player_id}")
    for row in rows:
        if row.get("status") == "active":
            print("reuse coach-player assignment", row["id"])
            return row
    created = post("/api/academy/coach-player-assignments", {
        "coach_id": coach_id,
        "player_id": player_id,
        "assignment_role": role,
        "start_date": "2026-08-17",
        "notes": "DEMO persistent coaching relationship",
    })
    print("created coach-player assignment", created["id"])
    return created


def ensure_batch(payload):
    batches = get("/api/academy/batches")
    found = find_by(batches, "name", payload["name"])
    if found:
        print("reuse batch", found["name"], found["id"])
        return found
    created = post("/api/academy/batches", payload)
    print("created batch", created["name"], created["id"])
    return created


def ensure_batch_player(batch_id: int, player_id: int, *, waitlist_if_full=False):
    rows = get(f"/api/academy/batches/{batch_id}/players")
    for row in rows:
        if int(row.get("player_id", 0)) == player_id and row.get("status") in {"active", "waitlisted"}:
            print("reuse batch player", row["id"], row.get("player_name"), row.get("status"))
            return row
    created = post(f"/api/academy/batches/{batch_id}/players", {
        "player_id": player_id,
        "waitlist_if_full": waitlist_if_full,
        "joined_on": "2026-08-17",
    })
    print("created batch player", created["id"], created.get("player_name"), created.get("status"))
    return created


def ensure_batch_coach(batch_id: int, coach_id: int):
    rows = get(f"/api/academy/batch-coach-assignments?batch_id={batch_id}&coach_id={coach_id}")
    for row in rows:
        if row.get("status") == "active":
            print("reuse batch coach assignment", row["id"])
            return row
    query = urllib.parse.urlencode({"batch_id": batch_id})
    created = post(f"/api/academy/batch-coach-assignments?{query}", {
        "coach_id": coach_id,
        "assignment_role": "primary",
        "start_date": "2026-08-17",
    })
    print("created batch coach assignment", created["id"])
    return created


def ensure_sessions(batch_id: int):
    sessions = get(f"/api/academy/sessions?batch_id={batch_id}")
    if not sessions:
        generated = post(f"/api/academy/batches/{batch_id}/generate-sessions", {
            "start_date": "2026-08-17",
            "end_date": "2026-08-31",
            "weekdays": [0, 2, 5],
            "start_time": "18:30",
            "duration_minutes": 90,
        })
        print("generated sessions", generated)
        sessions = get(f"/api/academy/sessions?batch_id={batch_id}")
    else:
        print("reuse sessions", len(sessions))
    return sessions


def seed_attendance(session, player_ids, coach_present=True):
    current = get(f"/api/academy/sessions/{session['id']}/attendance")
    if current.get("players") and all(row.get("attendance_id") for row in current["players"]):
        print("reuse attendance for session", session["id"])
        return current

    statuses = [
        ("present", None, "Strong session; good intent."),
        ("late", None, "Arrived 10 minutes late."),
        ("absent", "Family travel", "Eligible for a make-up session."),
    ]
    entries = []
    for idx, player_id in enumerate(player_ids):
        status, reason, notes = statuses[idx % len(statuses)]
        entries.append({
            "player_id": player_id,
            "status": status,
            "absence_reason": reason,
            "notes": notes,
            "make_up_eligible": True if status == "absent" else False,
        })
    saved = request("PUT", f"/api/academy/sessions/{session['id']}/attendance", {
        "players": entries,
        "coach_status": "present" if coach_present else None,
        "coach_notes": "DEMO attendance entry",
    })
    print("saved attendance for session", session["id"])
    return saved


def main():
    wait_for_postgres()

    profile = get("/api/academy/profile")
    if not profile:
        raise RuntimeError("Academy profile is not configured. Refusing to create/replace the live Academy profile.")
    print("using existing academy profile:", profile.get("name"))

    players_payload = [
        {
            "name": "DEMO Aarav Patel", "first_name": "Aarav", "last_name": "Patel",
            "date_of_birth": "2012-03-14", "gender": "Male", "batting_style": "Right-handed",
            "bowling_style": "Right-arm medium", "handedness": "Right", "skill_level": "Advanced",
            "joined_on": "2026-08-01", "status": "active",
            "emergency_contact_name": "Neha Patel", "emergency_contact_phone": "555-0101",
            "notes": "DEMO DATA — advanced top-order batter.",
            "guardians": [{"first_name": "Neha", "last_name": "Patel", "relationship": "Mother", "email": "demo.neha@example.com", "phone": "555-0101", "is_primary": True, "billing_contact": True, "pickup_authorized": True}],
        },
        {
            "name": "DEMO Maya Rao", "first_name": "Maya", "last_name": "Rao",
            "date_of_birth": "2013-07-08", "gender": "Female", "batting_style": "Left-handed",
            "bowling_style": "Right-arm off spin", "handedness": "Left", "skill_level": "Intermediate",
            "joined_on": "2026-08-03", "status": "active",
            "emergency_contact_name": "Anita Rao", "emergency_contact_phone": "555-0102",
            "notes": "DEMO DATA — developing left-handed batter.",
            "guardians": [{"first_name": "Anita", "last_name": "Rao", "relationship": "Mother", "email": "demo.anita@example.com", "phone": "555-0102", "is_primary": True, "billing_contact": True, "pickup_authorized": True}],
        },
        {
            "name": "DEMO Rohan Singh", "first_name": "Rohan", "last_name": "Singh",
            "date_of_birth": "2012-11-21", "gender": "Male", "batting_style": "Right-handed",
            "bowling_style": "Right-arm leg spin", "handedness": "Right", "skill_level": "Intermediate",
            "joined_on": "2026-08-05", "status": "active",
            "emergency_contact_name": "Kiran Singh", "emergency_contact_phone": "555-0103",
            "notes": "DEMO DATA — batting all-rounder.",
            "guardians": [{"first_name": "Kiran", "last_name": "Singh", "relationship": "Father", "email": "demo.kiran@example.com", "phone": "555-0103", "is_primary": True, "billing_contact": True, "pickup_authorized": True}],
        },
        {
            "name": "DEMO Zoe Carter", "first_name": "Zoe", "last_name": "Carter",
            "date_of_birth": "2013-01-30", "gender": "Female", "batting_style": "Right-handed",
            "bowling_style": "Right-arm fast", "handedness": "Right", "skill_level": "Developing",
            "joined_on": "2026-08-10", "status": "active",
            "emergency_contact_name": "Chris Carter", "emergency_contact_phone": "555-0104",
            "notes": "DEMO DATA — currently waitlisted for the advanced batch.",
            "guardians": [{"first_name": "Chris", "last_name": "Carter", "relationship": "Father", "email": "demo.chris@example.com", "phone": "555-0104", "is_primary": True, "billing_contact": True, "pickup_authorized": True}],
        },
    ]
    players = [ensure_player(payload) for payload in players_payload]

    advanced = ensure_program({
        "name": "DEMO U15 Advanced Batting", "code": "DEMO-U15-AB",
        "description": "DEMO DATA — advanced batting development program.", "program_type": "group",
        "age_group": "U15", "skill_level": "Advanced", "start_date": "2026-08-17", "end_date": "2026-12-15", "status": "active",
    })
    foundation = ensure_program({
        "name": "DEMO Junior Foundations", "code": "DEMO-JR-FND",
        "description": "DEMO DATA — foundational cricket skills and trial pathway.", "program_type": "group",
        "age_group": "U13", "skill_level": "Developing", "start_date": "2026-08-17", "end_date": "2026-11-30", "status": "active",
    })

    for player in players[:3]:
        ensure_enrollment(int(player["id"]), int(advanced["id"]), "regular", notes="DEMO regular enrollment")
    ensure_enrollment(int(players[3]["id"]), int(foundation["id"]), "trial", notes="DEMO trial enrollment")

    coach_priya = ensure_coach({
        "first_name": "DEMO Priya", "last_name": "Shah", "preferred_name": "Coach Priya",
        "email": "demo.priya@example.com", "phone": "555-0201",
        "specialties": ["Batting", "Fielding"], "availability": "Mon/Wed 5:00–9:00 PM; Sat mornings",
        "certifications": "DEMO Level 2 Coaching Certification", "joined_on": "2026-07-15", "status": "active",
        "notes": "DEMO DATA — primary batting coach.",
    })
    ensure_coach({
        "first_name": "DEMO Daniel", "last_name": "Brooks", "preferred_name": "Coach Daniel",
        "email": "demo.daniel@example.com", "phone": "555-0202",
        "specialties": ["Fast Bowling", "Fitness"], "availability": "Tue/Thu evenings; Sunday mornings",
        "certifications": "DEMO Strength & Conditioning Certificate", "joined_on": "2026-07-20", "status": "active",
        "notes": "DEMO DATA — bowling and conditioning coach.",
    })
    ensure_coach_player(int(coach_priya["id"]), int(players[0]["id"]), "primary")

    batch = ensure_batch({
        "name": "DEMO U15 Mon-Wed-Sat", "code": "DEMO-BAT-U15",
        "program_id": int(advanced["id"]), "capacity": 3,
        "location": "DEMO Main Indoor Center", "resource": "DEMO Net 3",
        "start_date": "2026-08-17", "end_date": "2026-12-15", "status": "active",
        "notes": "DEMO DATA — capacity intentionally set to 3 to demonstrate the waitlist.",
    })
    active_members = []
    for player in players[:3]:
        membership = ensure_batch_player(int(batch["id"]), int(player["id"]), waitlist_if_full=False)
        if membership.get("status") == "active":
            active_members.append(int(player["id"]))
    ensure_batch_player(int(batch["id"]), int(players[3]["id"]), waitlist_if_full=True)
    ensure_batch_coach(int(batch["id"]), int(coach_priya["id"]))

    sessions = ensure_sessions(int(batch["id"]))
    target = None
    if sessions:
        target = next((s for s in sessions if s.get("session_date") == "2026-08-17"), sessions[0])
        seed_attendance(target, active_members)

    summary = {
        "academy": profile.get("name"),
        "players": [p["name"] for p in players],
        "programs": [advanced["name"], foundation["name"]],
        "coaches": ["DEMO Priya Shah", "DEMO Daniel Brooks"],
        "batch": batch["name"],
        "session_count": len(sessions),
        "attendance_session": target["id"] if target else None,
    }
    print("DEMO_SEED_COMPLETE")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"DEMO_SEED_FAILED: {exc}", file=sys.stderr)
        raise
