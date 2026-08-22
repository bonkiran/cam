import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8791"


def _reset_shared_postgres_state() -> None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return
    import psycopg

    candidates = [
        "academy_billing_security_audit",
        "academy_saved_payment_methods",
        "academy_review_actions",
        "academy_player_reviews",
        "academy_refunds",
        "academy_payment_allocations",
        "academy_payments",
        "academy_invoice_items",
        "academy_invoices",
        "academy_enrollment_billing",
        "academy_billing_account_players",
        "academy_billing_accounts",
        "academy_fee_plans",
        "academy_auth_sessions",
        "academy_access_audit",
        "academy_users",
        "session_attendance",
        "session_players",
        "academy_sessions",
        "batch_coach_assignments",
        "batch_players",
        "batches",
        "coach_player_assignments",
        "coaches",
        "enrollments",
        "programs",
        "player_guardians",
        "guardians",
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
    raise RuntimeError(f"Track A roster UI server did not become ready: {last_error}")


def _request(method: str, path: str, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    request = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            body = json.loads(raw) if raw else None
        except Exception:
            body = raw
        return exc.code, body


def _post(path: str, payload: dict):
    status, body = _request("POST", path, payload)
    assert status in (200, 201), body
    return body


def test_batch_roster_remove_and_waitlist_promote_in_browser():
    _reset_shared_postgres_state()

    data_dir = tempfile.mkdtemp(prefix="cam-track-a-roster-ui-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["PYTHONPATH"] = str(REPO_ROOT)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--host", "127.0.0.1", "--port", "8791"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_for_server(f"{BASE_URL}/api/health")

        status, _ = _request("PUT", "/api/cam/profile", {"name": "Track A Browser Academy"})
        assert status == 200
        program = _post("/api/cam/programs", {"name": "Track A Browser U13", "program_type": "group", "status": "active"})
        player1 = _post("/api/cam/players", {"name": "Browser Active Player", "status": "active"})
        player2 = _post("/api/cam/players", {"name": "Browser Waitlist Player", "status": "active"})
        batch = _post(
            "/api/cam/batches",
            {"name": "Track A Browser Batch", "program_id": program["id"], "capacity": 1, "status": "active"},
        )
        _post(f"/api/cam/batches/{batch['id']}/players", {"player_id": player1["id"]})
        _post(
            f"/api/cam/batches/{batch['id']}/players",
            {"player_id": player2["id"], "waitlist_if_full": True},
        )

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            try:
                page.goto(f"{BASE_URL}/#cam?tab=batches", wait_until="domcontentloaded")
                expect(page.get_by_role("heading", name="Batches & Sessions")).to_be_visible(timeout=15000)

                active_row = page.locator(".cam-batch-membership-row", has_text="Browser Active Player")
                waitlist_row = page.locator(".cam-batch-membership-row", has_text="Browser Waitlist Player")
                expect(active_row).to_be_visible(timeout=10000)
                expect(waitlist_row).to_be_visible(timeout=10000)
                expect(active_row.get_by_role("button", name="Remove")).to_be_visible(timeout=10000)
                expect(waitlist_row.get_by_role("button", name="Promote")).to_be_visible(timeout=10000)
                expect(waitlist_row.get_by_role("button", name="Remove")).to_be_visible(timeout=10000)

                # Promotion must fail while capacity is still full and leave the
                # waitlist membership unchanged.
                waitlist_row.get_by_role("button", name="Promote").click()
                expect(page.locator("#toast")).to_contain_text("Batch is still at capacity", timeout=10000)

                # Remove the active roster player. The lifecycle control performs
                # a full rare-action refresh so all batch/session counts reload.
                active_row.get_by_role("button", name="Remove").click()
                expect(page.get_by_role("heading", name="Batches & Sessions")).to_be_visible(timeout=15000)
                expect(page.locator(".cam-batch-membership-row", has_text="Browser Active Player")).to_contain_text("inactive")

                waitlist_row = page.locator(".cam-batch-membership-row", has_text="Browser Waitlist Player")
                expect(waitlist_row.get_by_role("button", name="Promote")).to_be_visible(timeout=10000)
                waitlist_row.get_by_role("button", name="Promote").click()

                expect(page.get_by_role("heading", name="Batches & Sessions")).to_be_visible(timeout=15000)
                promoted_row = page.locator(".cam-batch-membership-row", has_text="Browser Waitlist Player")
                expect(promoted_row).to_contain_text("active", timeout=10000)
                expect(promoted_row.get_by_role("button", name="Remove")).to_be_visible(timeout=10000)
                expect(promoted_row.get_by_role("button", name="Promote")).to_have_count(0)

                status, memberships = _request("GET", f"/api/cam/batches/{batch['id']}/players")
                assert status == 200
                states = {row["player_name"]: row["status"] for row in memberships}
                assert states["Browser Active Player"] == "inactive"
                assert states["Browser Waitlist Player"] == "active"

                status, batch_after = _request("GET", f"/api/cam/batches/{batch['id']}")
                assert status == 200
                assert int(batch_after["active_player_count"]) == 1
                assert int(batch_after["waitlist_count"]) == 0
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
