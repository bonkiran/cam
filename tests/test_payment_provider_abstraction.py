from __future__ import annotations

from dataclasses import dataclass

from app.payment_providers import MockPaymentProvider, SquarePaymentProvider, StripePaymentProvider


@dataclass
class FakeResponse:
    status_code: int
    payload: dict

    @property
    def content(self) -> bytes:
        return b"{}"

    def json(self):
        return self.payload


class StripeFakeHttp:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if method == "GET" and url.endswith("/v1/account"):
            return FakeResponse(200, {"id": "acct_cam_test"})
        if method == "POST" and url.endswith("/v1/customers"):
            return FakeResponse(200, {"id": "cus_cam_test"})
        if method == "POST" and url.endswith("/v1/setup_intents"):
            return FakeResponse(
                200,
                {
                    "id": "seti_cam_test",
                    "client_secret": "seti_cam_test_secret_123",
                    "status": "requires_payment_method",
                    "customer": "cus_cam_test",
                },
            )
        if method == "GET" and url.endswith("/v1/setup_intents/seti_cam_test"):
            return FakeResponse(
                200,
                {
                    "id": "seti_cam_test",
                    "status": "succeeded",
                    "customer": "cus_cam_test",
                    "payment_method": "pm_cam_test",
                },
            )
        if method == "GET" and url.endswith("/v1/payment_methods/pm_cam_test"):
            return FakeResponse(
                200,
                {
                    "id": "pm_cam_test",
                    "card": {"brand": "visa", "last4": "4242", "exp_month": 12, "exp_year": 2034},
                },
            )
        if method == "POST" and url.endswith("/v1/payment_intents"):
            return FakeResponse(
                200,
                {"id": "pi_cam_test", "status": "succeeded", "amount": 20000, "currency": "usd"},
            )
        if method == "GET" and url.endswith("/v1/payment_intents/pi_cam_test"):
            return FakeResponse(
                200,
                {"id": "pi_cam_test", "status": "succeeded", "amount": 20000, "currency": "usd"},
            )
        if method == "POST" and url.endswith("/v1/refunds"):
            return FakeResponse(200, {"id": "re_cam_test", "status": "succeeded", "amount": 5000})
        raise AssertionError(f"Unexpected Stripe request: {method} {url}")


class SquareFakeHttp:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if method == "GET" and url.endswith("/v2/locations"):
            return FakeResponse(200, {"locations": [{"id": "LOC_CAM_TEST"}]})
        if method == "POST" and url.endswith("/v2/customers"):
            return FakeResponse(200, {"customer": {"id": "SQ_CUS_CAM_TEST"}})
        if method == "POST" and url.endswith("/v2/cards"):
            return FakeResponse(
                200,
                {
                    "card": {
                        "id": "ccof:cam-test",
                        "card_brand": "VISA",
                        "last_4": "1111",
                        "exp_month": 12,
                        "exp_year": 2034,
                    }
                },
            )
        if method == "POST" and url.endswith("/v2/payments"):
            return FakeResponse(
                200,
                {
                    "payment": {
                        "id": "SQ_PAY_CAM_TEST",
                        "status": "COMPLETED",
                        "amount_money": {"amount": 20000, "currency": "USD"},
                    }
                },
            )
        if method == "GET" and url.endswith("/v2/payments/SQ_PAY_CAM_TEST"):
            return FakeResponse(
                200,
                {
                    "payment": {
                        "id": "SQ_PAY_CAM_TEST",
                        "status": "COMPLETED",
                        "amount_money": {"amount": 20000, "currency": "USD"},
                    }
                },
            )
        if method == "POST" and url.endswith("/v2/refunds"):
            return FakeResponse(
                200,
                {
                    "refund": {
                        "id": "SQ_REF_CAM_TEST",
                        "status": "COMPLETED",
                        "amount_money": {"amount": 5000, "currency": "USD"},
                    }
                },
            )
        raise AssertionError(f"Unexpected Square request: {method} {url}")


def _run_provider_contract(provider, setup_payload):
    connection = provider.test_connection()
    assert connection["ok"] is True

    customer = provider.create_customer(
        idempotency_key="cam-provider-customer-0001",
        name="Ravi Kumar",
        email="ravi@example.com",
        cam_parent_reference="parent-100",
    )
    assert customer["provider"] == provider.provider
    assert customer["customer_id"]

    setup = provider.begin_payment_method_setup(
        customer_id=customer["customer_id"],
        idempotency_key="cam-provider-setup-0001",
    )
    assert setup["provider"] == provider.provider
    assert setup["customer_id"] == customer["customer_id"]
    assert setup["mode"]

    saved = provider.complete_payment_method_setup(
        customer_id=customer["customer_id"],
        setup_payload={**setup_payload, "setup_session_id": setup.get("setup_session_id")},
        idempotency_key="cam-provider-complete-0001",
    )
    assert saved["provider"] == provider.provider
    assert saved["payment_method_id"]
    assert saved["card_last4"]
    assert saved["setup_status"] == "succeeded"

    payment = provider.charge_saved_method(
        customer_id=customer["customer_id"],
        payment_method_id=saved["payment_method_id"],
        amount_cents=20000,
        currency="USD",
        idempotency_key="cam-provider-charge-0001",
        description="CAM monthly academy tuition",
        reference_id="invoice-200",
    )
    assert payment["provider"] == provider.provider
    assert payment["payment_id"]
    assert payment["amount_cents"] == 20000
    assert payment["currency"] == "USD"

    status = provider.get_payment_status(payment_id=payment["payment_id"])
    assert status["payment_id"] == payment["payment_id"]
    assert status["amount_cents"] == 20000

    refund = provider.refund_payment(
        payment_id=payment["payment_id"],
        amount_cents=5000,
        currency="USD",
        idempotency_key="cam-provider-refund-0001",
    )
    assert refund["provider"] == provider.provider
    assert refund["payment_id"] == payment["payment_id"]
    assert refund["amount_cents"] == 5000


def test_stripe_and_square_publish_same_cam_capabilities():
    stripe = StripePaymentProvider(secret_key="sk_test_cam", publishable_key="pk_test_cam", http_request=StripeFakeHttp())
    square = SquarePaymentProvider(
        access_token="square-test-token",
        application_id="sandbox-sq0idb-cam",
        location_id="LOC_CAM_TEST",
        environment="sandbox",
        http_request=SquareFakeHttp(),
    )

    for provider in (stripe, square):
        descriptor = provider.descriptor().as_dict()
        assert descriptor["configured"] is True
        assert descriptor["environment"] == "sandbox"
        assert "save_payment_method_without_charge" in descriptor["capabilities"]
        assert "off_session_charge" in descriptor["capabilities"]
        assert "refund" in descriptor["capabilities"]
        assert "multi_tenant_saas" in descriptor["capabilities"]


def test_stripe_adapter_satisfies_cam_payment_contract():
    provider = StripePaymentProvider(
        secret_key="sk_test_cam",
        publishable_key="pk_test_cam",
        http_request=StripeFakeHttp(),
    )
    _run_provider_contract(provider, {})


def test_square_adapter_satisfies_cam_payment_contract():
    provider = SquarePaymentProvider(
        access_token="square-test-token",
        application_id="sandbox-sq0idb-cam",
        location_id="LOC_CAM_TEST",
        environment="sandbox",
        http_request=SquareFakeHttp(),
    )
    _run_provider_contract(
        provider,
        {
            "source_token": "cnon:card-nonce-ok",
            "verification_token": "verification-token-test",
            "cardholder_name": "Ravi Kumar",
            "billing_address": {
                "address_line_1": "500 Electric Ave",
                "locality": "New York",
                "administrative_district_level_1": "NY",
                "postal_code": "10003",
                "country": "US",
            },
        },
    )


def test_mock_provider_gives_ci_a_provider_independent_contract_fixture():
    provider = MockPaymentProvider()
    _run_provider_contract(provider, {"source_token": "mock_visa"})
