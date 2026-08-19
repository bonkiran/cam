import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8774"


def wait_for_server(timeout: float = 25.0):
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"test server did not become ready: {last_error}")


def request(method: str, path: str, payload=None, token=None, expected=(200, 201)):
    headers={"Authorization": f"Bearer {token}"} if token else {}
    response=httpx.request(method,f"{BASE_URL}{path}",json=payload,headers=headers,timeout=20.0)
    assert response.status_code in expected,response.text
    return response.json() if response.content else None


def seed():
    request("PUT","/api/academy/profile",{
        "name":"Manual UX Academy","email":"owner@manual.test","city":"Johns Creek","state":"GA",
        "postal_code":"30097","country":"United States","timezone":"America/New_York"
    })
    bootstrap=httpx.post(
        f"{BASE_URL}/api/auth/bootstrap",
        json={"display_name":"Manual UX Owner","email":"owner@manual.test","password":"OwnerPassword123!"},
        headers={"X-CAM-Bootstrap":"manual-fixes-bootstrap"},timeout=20.0,
    )
    assert bootstrap.status_code==201,bootstrap.text
    owner=bootstrap.json()["token"]
    player=request("POST","/api/academy/players",{
        "name":"Manual UX Player","status":"active","guardians":[{
            "first_name":"Manual","last_name":"Parent","relationship":"Parent","email":"parent@manual.test",
            "phone":"4045550199","is_primary":True,"billing_contact":True,"pickup_authorized":True
        }]
    },owner)
    guardian_id=player["guardians"][0]["id"]
    program=request("POST","/api/academy/programs",{"name":"Manual UX Program","program_type":"group","status":"active"},owner)
    enrollment=request("POST","/api/academy/enrollments",{
        "player_id":player["id"],"program_id":program["id"],"enrollment_type":"regular","start_date":date.today().isoformat()
    },owner)
    batch=request("POST","/api/academy/batches",{
        "name":"Manual UX Batch","program_id":program["id"],"capacity":12,"status":"active"
    },owner)
    request("POST",f"/api/academy/batches/{batch['id']}/players",{
        "player_id":player["id"],"waitlist_if_full":False,"joined_on":date.today().isoformat()
    },owner)
    fee=request("POST","/api/academy/fee-plans",{
        "name":"Manual UX Monthly","amount_cents":12000,"currency":"USD","billing_frequency":"monthly",
        "due_day_of_month":1,"program_id":program["id"],"status":"active"
    },owner)
    account=request("POST","/api/academy/billing-accounts",{
        "account_name":"Manual UX Family","player_ids":[player["id"]],"primary_guardian_id":guardian_id,
        "overpayment_allowed":True,"status":"active"
    },owner)
    request("PUT",f"/api/academy/enrollments/{enrollment['id']}/billing",{
        "fee_plan_id":fee["id"],"discount_type":"none","discount_value":0
    },owner)
    invoice=request("POST","/api/academy/invoices/from-enrollment",{
        "account_id":account["id"],"enrollment_id":enrollment["id"],"issue_date":date.today().isoformat(),
        "due_date":(date.today()+timedelta(days=7)).isoformat(),"description":"Manual UX invoice"
    },owner)
    request("POST","/api/academy/access/users",{
        "display_name":"Manual UX Parent","email":"parent.login@manual.test","password":"ParentPassword123!",
        "role":"parent","guardian_id":guardian_id,"status":"active"
    },owner)
    parent_login=request("POST","/api/auth/login",{"email":"parent.login@manual.test","password":"ParentPassword123!"})
    parent=parent_login["token"]
    request("POST","/api/academy/parent/payment-methods/sandbox",{
        "card_number":"4242424242424242","exp_month":12,"exp_year":2034,"cvc":"123","make_default":True
    },parent)
    return owner,parent,invoice,batch


def test_dashboard_setup_batch_invoice_and_parent_payment_ui():
    data_dir=tempfile.mkdtemp(prefix="cam-post-track-a-ui-")
    env=os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"]=data_dir
    env["PYTHONPATH"]=str(REPO_ROOT)
    env["CAM_BOOTSTRAP_TOKEN"]="manual-fixes-bootstrap"
    env["CAM_PAYMENT_MODE"]="sandbox"
    env.pop("WEATHER_COM_API_KEY",None)
    server=subprocess.Popen(
        [sys.executable,"-m","uvicorn","run:app","--host","127.0.0.1","--port","8774"],
        cwd=REPO_ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,
    )
    try:
        wait_for_server()
        owner_token,parent_token,invoice,batch=seed()
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True)
            page=browser.new_page(viewport={"width":1440,"height":1100})
            try:
                page.add_init_script(f"sessionStorage.setItem('cam-academy-session-v1', {json.dumps(owner_token)});")
                page.goto(f"{BASE_URL}/#academy",wait_until="domcontentloaded")
                expect(page.get_by_role("button",name="Dashboard")).to_be_visible(timeout=15000)
                expect(page.get_by_role("heading",name="Welcome, Manual UX Owner")).to_be_visible(timeout=15000)
                expect(page.get_by_text("Fee received",exact=True)).to_be_visible()
                expect(page.get_by_text("Fee Pending / Late",exact=True)).to_be_visible()
                expect(page.get_by_role("heading",name="Upcoming Events for Manual UX Academy")).to_be_visible()
                expect(page.get_by_role("heading",name="Today's Sessions")).to_be_visible()
                expect(page.get_by_role("heading",name="Yesterday's Attendance")).to_be_visible()
                assert page.get_by_text("Guardian contacts",exact=True).count()==0
                assert page.get_by_text("Players with analysis",exact=True).count()==0

                page.get_by_role("button",name="Academy Setup").click()
                expect(page.get_by_role("heading",name="Academy Setup")).to_be_visible(timeout=10000)
                timezone=page.locator('#academyProfileForm [name="timezone"]')
                expect(timezone).to_be_hidden()
                expect(timezone).to_have_value("America/New_York")

                page.goto(f"{BASE_URL}/#academy?tab=batches",wait_until="domcontentloaded")
                row=page.locator('.academy-batch-membership-row',has_text='Manual UX Player')
                expect(row).to_be_visible(timeout=15000)
                expect(row.get_by_role("button",name="Remove")).to_be_visible(timeout=10000)
                status_box=row.locator(':scope > .academy-program-status').bounding_box()
                actions_box=row.locator(':scope > .academy-roster-lifecycle-actions').bounding_box()
                assert status_box and actions_box
                assert abs(status_box["y"]-actions_box["y"])<16

                page.goto(f"{BASE_URL}/#academy?tab=fees",wait_until="domcontentloaded")
                invoice_row=page.locator('.academy-invoice-row',has_text=invoice['invoice_number'])
                expect(invoice_row).to_be_visible(timeout=15000)
                open_button=invoice_row.get_by_role("button",name="Open")
                expect(open_button).to_be_visible(timeout=10000)
                open_button.click()
                expect(page.locator('.academy-invoice-detail').get_by_role("heading",name=invoice['invoice_number'])).to_be_visible(timeout=10000)
                expect(page.locator('.academy-invoice-detail')).to_contain_text("Balance")

                page.evaluate("(token) => sessionStorage.setItem('cam-academy-session-v1', token)",parent_token)
                page.goto(f"{BASE_URL}/#academy?tab=parent",wait_until="domcontentloaded")
                expect(page.get_by_role("heading",name="Parent Portal")).to_be_visible(timeout=15000)
                pay=page.locator(f'[data-pay-invoice="{invoice["id"]}"]')
                expect(pay).to_be_visible(timeout=10000)
                pay.click()
                amount=page.locator('#academyParentPayForm [name="amount"]')
                expect(amount).to_be_visible(timeout=10000)
                assert amount.evaluate("el => el.readOnly") is True
                expect(amount).to_have_value("120.00")
            except Exception:
                Path("test-results").mkdir(exist_ok=True)
                page.screenshot(path="test-results/post-track-a-manual-fixes-ui.png",full_page=True)
                raise
            finally:
                browser.close()
    finally:
        server.terminate()
        try:server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill();server.wait(timeout=5)