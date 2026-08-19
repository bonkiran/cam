import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8784"
SESSION_KEY = "cam-academy-session-v1"


def _wait_for_server(url: str, timeout: float = 25.0) -> None:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"CAM reviews test server did not become ready: {last_error}")


def _json_request(method: str, path: str, payload: dict | None = None, headers: dict | None = None):
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=request_headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as response:
        body = response.read().decode("utf-8")
        return json.loads(body) if body else None


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _reset_shared_postgres_state() -> None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return
    import psycopg

    candidates = [
        "academy_review_actions",
        "academy_player_reviews",
        "academy_auth_sessions",
        "academy_access_audit",
        "academy_users",
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


def _set_session(page, token: str) -> None:
    # Seed the Academy session before the app loads. This avoids coupling the
    # Reviews regression to whichever landing/dashboard view is configured.
    page.add_init_script(
        f"sessionStorage.setItem({json.dumps(SESSION_KEY)}, {json.dumps(token)});"
    )
    page.goto(f"{BASE_URL}/#academy?tab=reviews", wait_until="domcontentloaded")


def test_player_reviews_staff_to_parent_publish_flow():
    data_dir = tempfile.mkdtemp(prefix="cam-reviews-ui-test-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["CAM_BOOTSTRAP_TOKEN"] = "reviews-ui-bootstrap"
    env["PYTHONPATH"] = str(REPO_ROOT)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--host", "127.0.0.1", "--port", "8784"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_for_server(f"{BASE_URL}/api/health")
        _reset_shared_postgres_state()

        _json_request("PUT", "/api/academy/profile", {"name": "Reviews UI Academy"})
        coach = _json_request(
            "POST",
            "/api/academy/coaches",
            {"first_name": "Leena", "last_name": "Coach", "email": "leena.ui@example.test", "status": "active"},
        )
        player = _json_request(
            "POST",
            "/api/academy/players",
            {
                "name": "Reviews UI Arjun",
                "status": "active",
                "guardians": [
                    {
                        "first_name": "Kavya",
                        "last_name": "Rao",
                        "relationship": "Mother",
                        "email": "kavya.ui@example.test",
                        "is_primary": True,
                    }
                ],
            },
        )
        guardian_id = int(player["guardians"][0]["id"])

        bootstrap = _json_request(
            "POST",
            "/api/auth/bootstrap",
            {"display_name": "Reviews UI Owner", "email": "reviews.ui.owner@example.test", "password": "OwnerReviews!123"},
            {"X-CAM-Bootstrap": "reviews-ui-bootstrap"},
        )
        owner_token = bootstrap["token"]
        _json_request(
            "POST",
            "/api/academy/access/users",
            {
                "display_name": "Kavya Rao",
                "email": "reviews.ui.parent@example.test",
                "password": "ParentReviews!123",
                "role": "parent",
                "guardian_id": guardian_id,
                "status": "active",
            },
            _auth(owner_token),
        )
        parent_login = _json_request(
            "POST",
            "/api/auth/login",
            {"email": "reviews.ui.parent@example.test", "password": "ParentReviews!123"},
        )
        parent_token = parent_login["token"]

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            staff = browser.new_page(viewport={"width": 1600, "height": 1200})
            parent = browser.new_page(viewport={"width": 1400, "height": 1000})
            try:
                _set_session(staff, owner_token)
                expect(staff.get_by_role("heading", name="Player Reviews")).to_be_visible(timeout=15000)
                expect(staff.get_by_text("Reviews UI Owner", exact=True)).to_be_visible()
                expect(staff.locator("#academyNewReview")).to_be_visible()

                staff.locator("#academyNewReview").click()
                form = staff.locator("#academyReviewForm")
                expect(form).to_be_visible()
                form.locator('[name="player_id"]').select_option(str(player["id"]))
                form.locator('[name="coach_id"]').select_option(str(coach["id"]))
                form.locator('[name="period_label"]').fill("August Development Review")
                form.locator('[name="batting_score"]').select_option("4")
                form.locator('[name="bowling_score"]').select_option("3")
                form.locator('[name="fielding_score"]').select_option("4")
                form.locator('[name="fitness_score"]').select_option("5")
                form.locator('[name="strengths"]').fill("Balance, intent and repeatable preparation.")
                form.locator('[name="focus_areas"]').fill("Earlier decision making to fuller length.")
                form.locator('[name="coach_summary"]').fill("Arjun showed better balance and clearer scoring intent throughout the session.")
                form.locator('[name="next_steps"]').fill("Repeat front-foot decision drill before the next assessment.")
                form.locator('[name="action_title"]').fill("Front-foot decision drill")
                form.get_by_role("button", name="Save Draft Review").click()

                card = staff.locator(".academy-review-card", has_text="August Development Review")
                expect(card).to_be_visible(timeout=10000)
                expect(card).to_contain_text("draft")
                expect(card).to_contain_text("4.00")
                expect(card).to_contain_text("Front-foot decision drill")

                # The linked parent should not see the staff-only draft.
                _set_session(parent, parent_token)
                expect(parent.get_by_role("heading", name="Player Reviews")).to_be_visible(timeout=15000)
                expect(parent.get_by_text("No published report cards yet")).to_be_visible()
                expect(parent.locator("#academyNewReview")).to_have_count(0)

                card.get_by_role("button", name="Publish report card").click()
                published_card = staff.locator(".academy-review-card", has_text="August Development Review")
                expect(published_card).to_contain_text("published", timeout=10000)

                parent.reload(wait_until="domcontentloaded")
                parent_card = parent.locator(".academy-review-card", has_text="August Development Review")
                expect(parent_card).to_be_visible(timeout=10000)
                expect(parent_card).to_contain_text("published")
                expect(parent_card).to_contain_text("Arjun showed better balance")
                expect(parent_card).to_contain_text("Front-foot decision drill")
                expect(parent.locator("#academyNewReview")).to_have_count(0)
                expect(parent.get_by_role("button", name="Publish report card")).to_have_count(0)

                # Staff can complete the assigned action without changing the published report content.
                action_button = published_card.get_by_role("button", name="Mark complete")
                expect(action_button).to_be_visible()
                action_button.click()
                updated_card = staff.locator(".academy-review-card", has_text="August Development Review")
                expect(updated_card.locator(".academy-review-action.completed")).to_have_count(1, timeout=10000)
                expect(updated_card).to_contain_text("0 open")
                expect(updated_card.get_by_role("button", name="Reopen")).to_be_visible()
            except Exception:
                Path("test-results").mkdir(exist_ok=True)
                staff.screenshot(path="test-results/academy-reviews-staff-failure.png", full_page=True)
                parent.screenshot(path="test-results/academy-reviews-parent-failure.png", full_page=True)
                raise
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
