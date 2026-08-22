import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="cam-track-a-tournament-type-")

from fastapi.testclient import TestClient
from run import app

client = TestClient(app)


def _reset_shared_postgres_state() -> None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return
    import psycopg

    candidates = [
        "academy_tournament_entries",
        "academy_tournaments",
        "academy_match_player_stats",
        "academy_match_squad",
        "academy_matches",
        "academy_team_roster",
        "academy_teams",
        "academy_auth_sessions",
        "academy_access_audit",
        "academy_users",
        "players",
        "academies",
    ]
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cursor:
            existing = []
            for table in candidates:
                cursor.execute("SELECT to_regclass(%s)", (f"public.{table}",))
                if cursor.fetchone()[0] is not None:
                    existing.append(table)
            if existing:
                cursor.execute(f"TRUNCATE TABLE {', '.join(existing)} RESTART IDENTITY CASCADE")
        conn.commit()


def _create(payload: dict):
    response = client.post("/api/cam/tournaments", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_internal_and_external_tournament_classification_is_persisted():
    _reset_shared_postgres_state()

    profile = client.put("/api/cam/profile", json={"name": "Track A Competition Academy"})
    assert profile.status_code == 200, profile.text

    internal = _create(
        {
            "name": "Track A Internal Academy Cup",
            "tournament_type": "internal",
            "organizer": "Track A Competition Academy",
            "start_date": "2026-09-12",
            "end_date": "2026-09-13",
            "location": "Academy Ground",
            "status": "planned",
        }
    )
    assert internal["tournament_type"] == "internal"

    external = _create(
        {
            "name": "Track A External Invitational",
            "tournament_type": "external",
            "organizer": "Regional Cricket Association",
            "start_date": "2026-10-10",
            "end_date": "2026-10-12",
            "location": "Regional Cricket Complex",
            "status": "open",
        }
    )
    assert external["tournament_type"] == "external"

    # Backward compatibility: old clients that omit the new field remain valid
    # and default to external instead of breaking existing integrations/tests.
    legacy = _create(
        {
            "name": "Track A Legacy Tournament Payload",
            "start_date": "2026-11-01",
            "end_date": "2026-11-02",
            "status": "planned",
        }
    )
    assert legacy["tournament_type"] == "external"

    invalid = client.post(
        "/api/cam/tournaments",
        json={
            "name": "Invalid Tournament Type",
            "tournament_type": "partner",
            "start_date": "2026-12-01",
            "end_date": "2026-12-02",
        },
    )
    assert invalid.status_code == 422, invalid.text

    rows = client.get("/api/cam/tournaments")
    assert rows.status_code == 200, rows.text
    by_name = {row["name"]: row for row in rows.json()}
    assert by_name["Track A Internal Academy Cup"]["tournament_type"] == "internal"
    assert by_name["Track A External Invitational"]["tournament_type"] == "external"

    # Classification remains editable while retaining the same tournament row.
    changed = client.put(
        f"/api/cam/tournaments/{internal['id']}",
        json={
            "name": internal["name"],
            "tournament_type": "external",
            "organizer": internal["organizer"],
            "start_date": internal["start_date"],
            "end_date": internal["end_date"],
            "location": internal["location"],
            "status": internal["status"],
        },
    )
    assert changed.status_code == 200, changed.text
    assert int(changed.json()["id"]) == int(internal["id"])
    assert changed.json()["tournament_type"] == "external"
