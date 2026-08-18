import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="cam-reviews-api-test-")
os.environ["CAM_BOOTSTRAP_TOKEN"] = "reviews-bootstrap-key"

from fastapi.testclient import TestClient
from run import app

client = TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _post(path: str, payload: dict, token: str | None = None, expected=(200, 201)):
    response = client.post(path, json=payload, headers=_auth(token) if token else {})
    assert response.status_code in expected, response.text
    return response.json() if response.content else None


def _login(email: str, password: str) -> str:
    return _post("/api/auth/login", {"email": email, "password": password})["token"]


def _create_access(owner_token: str, **payload):
    return _post("/api/academy/access/users", payload, owner_token)


def _review_payload(player_id: int, session_id: int | None = None, coach_id: int | None = None, label="August Skill Review"):
    payload = {
        "player_id": player_id,
        "review_date": "2026-08-18",
        "review_type": "session",
        "period_label": label,
        "batting_score": 4,
        "bowling_score": 3,
        "fielding_score": 4,
        "fitness_score": 5,
        "batting_notes": "Balanced base and improved contact consistency.",
        "bowling_notes": "Keep developing control under fatigue.",
        "fielding_notes": "Quick release and good anticipation.",
        "fitness_notes": "Strong repeat-effort work.",
        "strengths": "Balance, intent and coachability.",
        "focus_areas": "Earlier decision making against fuller length.",
        "coach_summary": "Strong session with a clear improvement trend.",
        "next_steps": "Repeat the front-foot decision drill and review next week.",
        "actions": [
            {
                "category": "batting",
                "title": "Front-foot decision drill",
                "detail": "Three sets of 18 balls with a stable head at contact.",
                "target_date": "2026-08-25",
            }
        ],
    }
    if session_id is not None:
        payload["session_id"] = session_id
    if coach_id is not None:
        payload["coach_id"] = coach_id
    return payload


def test_player_reviews_rbac_publish_history_and_actions():
    profile = client.put("/api/academy/profile", json={"name": "Reviews Test Academy"})
    assert profile.status_code == 200, profile.text

    coach = _post(
        "/api/academy/coaches",
        {"first_name": "Maya", "last_name": "Shah", "email": "maya.reviews@example.test", "status": "active"},
    )
    other_coach = _post(
        "/api/academy/coaches",
        {"first_name": "Ravi", "last_name": "Kumar", "email": "ravi.reviews@example.test", "status": "active"},
    )
    player = _post(
        "/api/academy/players",
        {
            "name": "Review Aarav Patel",
            "status": "active",
            "guardians": [
                {
                    "first_name": "Priya",
                    "last_name": "Patel",
                    "relationship": "Mother",
                    "email": "priya.review@example.test",
                    "is_primary": True,
                    "billing_contact": True,
                }
            ],
        },
    )
    unrelated_player = _post(
        "/api/academy/players",
        {
            "name": "Review Nisha Rao",
            "status": "active",
            "guardians": [
                {
                    "first_name": "Meena",
                    "last_name": "Rao",
                    "relationship": "Mother",
                    "email": "meena.review@example.test",
                    "is_primary": True,
                }
            ],
        },
    )
    guardian_id = int(player["guardians"][0]["id"])
    unrelated_guardian_id = int(unrelated_player["guardians"][0]["id"])

    session = _post(
        "/api/academy/sessions/private",
        {
            "player_id": player["id"],
            "coach_id": coach["id"],
            "session_date": "2026-08-18",
            "start_time": "17:00",
            "duration_minutes": 60,
            "location": "Net 1",
        },
    )

    bootstrap = client.post(
        "/api/auth/bootstrap",
        json={"display_name": "Academy Owner", "email": "owner.reviews@example.test", "password": "OwnerReview!123"},
        headers={"X-CAM-Bootstrap": "reviews-bootstrap-key"},
    )
    assert bootstrap.status_code == 201, bootstrap.text
    owner_token = bootstrap.json()["token"]

    _create_access(
        owner_token,
        display_name="Coach Maya",
        email="coach.reviews@example.test",
        password="CoachReview!123",
        role="coach",
        coach_id=coach["id"],
        status="active",
    )
    _create_access(
        owner_token,
        display_name="Parent Priya",
        email="parent.reviews@example.test",
        password="ParentReview!123",
        role="parent",
        guardian_id=guardian_id,
        status="active",
    )
    _create_access(
        owner_token,
        display_name="Player Aarav",
        email="player.reviews@example.test",
        password="PlayerReview!123",
        role="player",
        player_id=player["id"],
        status="active",
    )
    _create_access(
        owner_token,
        display_name="Parent Meena",
        email="unrelated.reviews@example.test",
        password="Unrelated!123",
        role="parent",
        guardian_id=unrelated_guardian_id,
        status="active",
    )

    coach_token = _login("coach.reviews@example.test", "CoachReview!123")
    parent_token = _login("parent.reviews@example.test", "ParentReview!123")
    player_token = _login("player.reviews@example.test", "PlayerReview!123")
    unrelated_token = _login("unrelated.reviews@example.test", "Unrelated!123")

    reference = client.get("/api/academy/reviews/reference", headers=_auth(coach_token))
    assert reference.status_code == 200, reference.text
    reference_json = reference.json()
    assert len(reference_json["coaches"]) == 1
    assert int(reference_json["coaches"][0]["id"]) == int(coach["id"])
    assert any(int(row["id"]) == int(player["id"]) for row in reference_json["players"])

    review = _post(
        "/api/academy/reviews",
        _review_payload(player["id"], session["id"]),
        coach_token,
    )
    review_id = int(review["id"])
    assert review["status"] == "draft"
    assert int(review["coach_id"]) == int(coach["id"])
    assert review["coach_name"] == "Maya Shah"
    assert review["overall_score"] == 4.0
    assert len(review["actions"]) == 1

    parent_draft_list = client.get("/api/academy/reviews", headers=_auth(parent_token))
    assert parent_draft_list.status_code == 200
    assert parent_draft_list.json() == []
    parent_draft_get = client.get(f"/api/academy/reviews/{review_id}", headers=_auth(parent_token))
    assert parent_draft_get.status_code == 404

    impersonation = client.post(
        "/api/academy/reviews",
        json=_review_payload(player["id"], session["id"], coach_id=other_coach["id"], label="Impersonation Attempt"),
        headers=_auth(coach_token),
    )
    assert impersonation.status_code == 403

    wrong_roster = client.post(
        "/api/academy/reviews",
        json=_review_payload(unrelated_player["id"], session["id"], label="Wrong Roster"),
        headers=_auth(coach_token),
    )
    assert wrong_roster.status_code == 422

    published = _post(f"/api/academy/reviews/{review_id}/publish", {}, coach_token)
    assert published["status"] == "published"
    assert published["published_at"]

    parent_list = client.get("/api/academy/reviews", headers=_auth(parent_token))
    assert parent_list.status_code == 200
    assert [int(row["id"]) for row in parent_list.json()] == [review_id]
    player_list = client.get("/api/academy/reviews", headers=_auth(player_token))
    assert player_list.status_code == 200
    assert [int(row["id"]) for row in player_list.json()] == [review_id]
    unrelated_list = client.get("/api/academy/reviews", headers=_auth(unrelated_token))
    assert unrelated_list.status_code == 200
    assert unrelated_list.json() == []

    forbidden_player = client.get(
        f"/api/academy/reviews?player_id={unrelated_player['id']}",
        headers=_auth(parent_token),
    )
    assert forbidden_player.status_code == 403

    immutable = client.put(
        f"/api/academy/reviews/{review_id}",
        json=_review_payload(player["id"], session["id"], label="Edited Published Review"),
        headers=_auth(coach_token),
    )
    assert immutable.status_code == 409

    action_id = int(published["actions"][0]["id"])
    completed = client.put(
        f"/api/academy/reviews/{review_id}/actions/{action_id}",
        json={"status": "completed"},
        headers=_auth(coach_token),
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["actions"][0]["status"] == "completed"
    assert completed.json()["actions"][0]["completed_at"]

    # A second published review establishes the player-development trend.
    second = _post(
        "/api/academy/reviews",
        {
            **_review_payload(player["id"], coach_id=coach["id"], label="September Skill Review"),
            "review_date": "2026-09-18",
            "batting_score": 5,
            "bowling_score": 4,
            "fielding_score": 5,
            "fitness_score": 5,
        },
        owner_token,
    )
    _post(f"/api/academy/reviews/{second['id']}/publish", {}, owner_token)

    trend = client.get(f"/api/academy/reviews/trend/{player['id']}", headers=_auth(parent_token))
    assert trend.status_code == 200, trend.text
    trend_json = trend.json()
    assert len(trend_json["points"]) == 2
    assert trend_json["points"][0]["overall_score"] == 4.0
    assert trend_json["points"][1]["overall_score"] == 4.75
    assert trend_json["overall_delta"] == 0.75

    audit = client.get("/api/academy/access/audit?limit=100", headers=_auth(owner_token))
    assert audit.status_code == 200
    actions = {row["action"] for row in audit.json()}
    assert {"create_player_review", "publish_player_review", "update_review_action"}.issubset(actions)
