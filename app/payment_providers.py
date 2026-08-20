from __future__ import annotations

import os
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

import requests


STRIPE_API_BASE = "https://api.stripe.com"
SQUARE_API_BASE = "https://connect.squareup.com"
SQUARE_SANDBOX_API_BASE = "https://connect.squareupsandbox.com"
SQUARE_API_VERSION = "2026-07-15"

SUPPORTED_PAYMENT_PROVIDERS = ("stripe", "square")


class PaymentProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        provider: str,
        code: str | None = None,
        retryable: bool = False,
        http_status: int = 502,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.code = code
        self.retryable = retryable
        self.http_status = http_status


class PaymentProviderNotConfigured(PaymentProviderError):
    def __init__(self, provider: str, message: str) -> None:
        super().__init__(
            message,
            provider=provider,
            code="not_configured",
            retryable=False,
            http_status=409,
        )


@dataclass(frozen=True)
class ProviderDescriptor:
    provider: str
    display_name: str
    configured: bool
    environment: str
    capabilities: tuple[str, ...]
    client_config: dict[str, Any]
    configuration_notes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "display_name": self.display_name,
            "configured": self.configured,
            "environment": self.environment,
            "capabilities": list(self.capabilities),
            "client_config": dict(self.client_config),
            "configuration_notes": list(self.configuration_notes),
        }


class PaymentProvider(ABC):
    """CAM-facing payment contract. Provider-specific details stay behind this interface."""

    provider: str
    display_name: str

    @abstractmethod
    def descriptor(self) -> ProviderDescriptor:
        raise NotImplementedError

    @abstractmethod
    def test_connection(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def create_customer(
        self,
        *,
        idempotency_key: str,
        name: str,
        email: str | None,
        cam_parent_reference: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def begin_payment_method_setup(
        self,
        *,
        customer_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def complete_payment_method_setup(
        self,
        *,
        customer_id: str,
        setup_payload: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def charge_saved_method(
        self,
        *,
        customer_id: str,
        payment_method_id: str,
        amount_cents: int,
        currency: str,
        idempotency_key: str,
        description: str | None = None,
        reference_id: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def refund_payment(
        self,
        *,
        payment_id: str,
        amount_cents: int,
        currency: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_payment_status(self, *, payment_id: str) -> dict[str, Any]:
        raise NotImplementedError


class StripePaymentProvider(PaymentProvider):
    provider = "stripe"
    display_name = "Stripe"

    def __init__(
        self,
        *,
        secret_key: str | None = None,
        publishable_key: str | None = None,
        http_request: Callable[..., Any] = requests.request,
    ) -> None:
        self.secret_key = (secret_key if secret_key is not None else os.environ.get("CAM_STRIPE_SECRET_KEY", "")).strip()
        self.publishable_key = (
            publishable_key if publishable_key is not None else os.environ.get("CAM_STRIPE_PUBLISHABLE_KEY", "")
        ).strip()
        self.http_request = http_request

    @property
    def environment(self) -> str:
        if self.secret_key.startswith("sk_live_") or self.publishable_key.startswith("pk_live_"):
            return "live"
        return "sandbox"

    @property
    def configured(self) -> bool:
        return bool(self.secret_key and self.publishable_key)

    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider=self.provider,
            display_name=self.display_name,
            configured=self.configured,
            environment=self.environment,
            capabilities=(
                "sandbox",
                "save_payment_method_without_charge",
                "off_session_charge",
                "refund",
                "webhooks",
                "multi_tenant_saas",
            ),
            client_config={
                "integration_mode": "stripe_elements_setup_intent",
                "publishable_key": self.publishable_key if self.configured else None,
            },
            configuration_notes=(
                "Set CAM_STRIPE_SECRET_KEY and CAM_STRIPE_PUBLISHABLE_KEY in server environment variables.",
                "Use Stripe sandbox/test keys until CAM is ready for production payments.",
            ),
        )

    def _require_configured(self) -> None:
        if not self.configured:
            raise PaymentProviderNotConfigured(
                self.provider,
                "Stripe is supported but not configured. Add CAM_STRIPE_SECRET_KEY and CAM_STRIPE_PUBLISHABLE_KEY.",
            )

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        self._require_configured()
        headers = {"Authorization": f"Bearer {self.secret_key}"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            response = self.http_request(
                method,
                f"{STRIPE_API_BASE}{path}",
                headers=headers,
                data=data,
                timeout=15,
            )
        except requests.RequestException as exc:
            raise PaymentProviderError(
                "Stripe could not be reached. Please retry.",
                provider=self.provider,
                code="network_error",
                retryable=True,
                http_status=503,
            ) from exc
        body = response.json() if getattr(response, "content", b"") else {}
        if int(response.status_code) >= 400:
            error = body.get("error") if isinstance(body, dict) else None
            error = error if isinstance(error, dict) else {}
            raise PaymentProviderError(
                str(error.get("message") or "Stripe rejected the request."),
                provider=self.provider,
                code=str(error.get("code") or error.get("type") or "provider_error"),
                retryable=int(response.status_code) >= 500,
                http_status=422 if int(response.status_code) < 500 else 503,
            )
        return body

    def test_connection(self) -> dict[str, Any]:
        account = self._request("GET", "/v1/account")
        return {
            "ok": True,
            "provider": self.provider,
            "environment": self.environment,
            "provider_merchant_id": account.get("id"),
            "provider_location_id": None,
        }

    def create_customer(
        self,
        *,
        idempotency_key: str,
        name: str,
        email: str | None,
        cam_parent_reference: str,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": name,
            "metadata[cam_parent_reference]": cam_parent_reference,
        }
        if email:
            data["email"] = email
        customer = self._request("POST", "/v1/customers", data=data, idempotency_key=idempotency_key)
        return {"provider": self.provider, "customer_id": str(customer["id"])}

    def begin_payment_method_setup(
        self,
        *,
        customer_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        setup_intent = self._request(
            "POST",
            "/v1/setup_intents",
            data={
                "customer": customer_id,
                "usage": "off_session",
                "payment_method_types[]": "card",
            },
            idempotency_key=idempotency_key,
        )
        return {
            "provider": self.provider,
            "mode": "stripe_elements_setup_intent",
            "customer_id": customer_id,
            "setup_session_id": str(setup_intent["id"]),
            "client_secret": setup_intent.get("client_secret"),
            "client_config": {"publishable_key": self.publishable_key},
        }

    def complete_payment_method_setup(
        self,
        *,
        customer_id: str,
        setup_payload: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        del idempotency_key  # Retrieval is idempotent; retained in the CAM contract for provider parity.
        setup_intent_id = str(setup_payload.get("setup_session_id") or "").strip()
        if not setup_intent_id:
            raise PaymentProviderError(
                "Stripe setup_session_id is required.",
                provider=self.provider,
                code="invalid_setup_payload",
                http_status=422,
            )
        setup_intent = self._request("GET", f"/v1/setup_intents/{setup_intent_id}")
        if str(setup_intent.get("status")) != "succeeded":
            raise PaymentProviderError(
                "Stripe payment-method setup is not complete.",
                provider=self.provider,
                code=str(setup_intent.get("status") or "setup_incomplete"),
                http_status=409,
            )
        if str(setup_intent.get("customer") or "") != customer_id:
            raise PaymentProviderError(
                "Stripe setup session does not belong to this CAM customer.",
                provider=self.provider,
                code="customer_mismatch",
                http_status=409,
            )
        payment_method = setup_intent.get("payment_method")
        payment_method_id = str(payment_method.get("id")) if isinstance(payment_method, dict) else str(payment_method or "")
        if not payment_method_id:
            raise PaymentProviderError(
                "Stripe did not return a saved payment method.",
                provider=self.provider,
                code="missing_payment_method",
                http_status=409,
            )
        details = payment_method if isinstance(payment_method, dict) else self._request("GET", f"/v1/payment_methods/{payment_method_id}")
        card = details.get("card") if isinstance(details, dict) else None
        card = card if isinstance(card, dict) else {}
        return {
            "provider": self.provider,
            "customer_id": customer_id,
            "payment_method_id": payment_method_id,
            "card_brand": card.get("brand"),
            "card_last4": card.get("last4"),
            "card_exp_month": card.get("exp_month"),
            "card_exp_year": card.get("exp_year"),
            "setup_status": "succeeded",
        }

    def charge_saved_method(
        self,
        *,
        customer_id: str,
        payment_method_id: str,
        amount_cents: int,
        currency: str,
        idempotency_key: str,
        description: str | None = None,
        reference_id: str | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "amount": amount_cents,
            "currency": currency.lower(),
            "customer": customer_id,
            "payment_method": payment_method_id,
            "off_session": "true",
            "confirm": "true",
        }
        if description:
            data["description"] = description
        if reference_id:
            data["metadata[cam_reference_id]"] = reference_id
        payment = self._request("POST", "/v1/payment_intents", data=data, idempotency_key=idempotency_key)
        return {
            "provider": self.provider,
            "payment_id": str(payment["id"]),
            "status": str(payment.get("status") or "unknown"),
            "amount_cents": int(payment.get("amount") or amount_cents),
            "currency": str(payment.get("currency") or currency).upper(),
        }

    def refund_payment(
        self,
        *,
        payment_id: str,
        amount_cents: int,
        currency: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        del currency  # Stripe identifies currency from the original PaymentIntent.
        refund = self._request(
            "POST",
            "/v1/refunds",
            data={"payment_intent": payment_id, "amount": amount_cents},
            idempotency_key=idempotency_key,
        )
        return {
            "provider": self.provider,
            "refund_id": str(refund["id"]),
            "payment_id": payment_id,
            "status": str(refund.get("status") or "unknown"),
            "amount_cents": int(refund.get("amount") or amount_cents),
        }

    def get_payment_status(self, *, payment_id: str) -> dict[str, Any]:
        payment = self._request("GET", f"/v1/payment_intents/{payment_id}")
        return {
            "provider": self.provider,
            "payment_id": payment_id,
            "status": str(payment.get("status") or "unknown"),
            "amount_cents": int(payment.get("amount") or 0),
            "currency": str(payment.get("currency") or "").upper(),
        }


class SquarePaymentProvider(PaymentProvider):
    provider = "square"
    display_name = "Square"

    def __init__(
        self,
        *,
        access_token: str | None = None,
        application_id: str | None = None,
        location_id: str | None = None,
        environment: str | None = None,
        http_request: Callable[..., Any] = requests.request,
    ) -> None:
        self.access_token = (access_token if access_token is not None else os.environ.get("CAM_SQUARE_ACCESS_TOKEN", "")).strip()
        self.application_id = (
            application_id if application_id is not None else os.environ.get("CAM_SQUARE_APPLICATION_ID", "")
        ).strip()
        self.location_id = (location_id if location_id is not None else os.environ.get("CAM_SQUARE_LOCATION_ID", "")).strip()
        requested_environment = (environment if environment is not None else os.environ.get("CAM_SQUARE_ENVIRONMENT", "sandbox")).strip().lower()
        self.environment = "live" if requested_environment == "live" else "sandbox"
        self.http_request = http_request

    @property
    def configured(self) -> bool:
        return bool(self.access_token and self.application_id and self.location_id)

    @property
    def api_base(self) -> str:
        return SQUARE_API_BASE if self.environment == "live" else SQUARE_SANDBOX_API_BASE

    @property
    def script_url(self) -> str:
        return "https://web.squarecdn.com/v1/square.js" if self.environment == "live" else "https://sandbox.web.squarecdn.com/v1/square.js"

    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider=self.provider,
            display_name=self.display_name,
            configured=self.configured,
            environment=self.environment,
            capabilities=(
                "sandbox",
                "save_payment_method_without_charge",
                "off_session_charge",
                "refund",
                "webhooks",
                "multi_tenant_saas",
            ),
            client_config={
                "integration_mode": "square_web_payments_card_on_file",
                "application_id": self.application_id if self.configured else None,
                "location_id": self.location_id if self.configured else None,
                "script_url": self.script_url,
            },
            configuration_notes=(
                "Set CAM_SQUARE_ACCESS_TOKEN, CAM_SQUARE_APPLICATION_ID, CAM_SQUARE_LOCATION_ID and CAM_SQUARE_ENVIRONMENT.",
                "Use CAM_SQUARE_ENVIRONMENT=sandbox until CAM is ready for production payments.",
            ),
        )

    def _require_configured(self) -> None:
        if not self.configured:
            raise PaymentProviderNotConfigured(
                self.provider,
                "Square is supported but not configured. Add CAM_SQUARE_ACCESS_TOKEN, CAM_SQUARE_APPLICATION_ID and CAM_SQUARE_LOCATION_ID.",
            )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_configured()
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Square-Version": SQUARE_API_VERSION,
            "Content-Type": "application/json",
        }
        try:
            response = self.http_request(
                method,
                f"{self.api_base}{path}",
                headers=headers,
                json=json_body,
                timeout=15,
            )
        except requests.RequestException as exc:
            raise PaymentProviderError(
                "Square could not be reached. Please retry.",
                provider=self.provider,
                code="network_error",
                retryable=True,
                http_status=503,
            ) from exc
        body = response.json() if getattr(response, "content", b"") else {}
        if int(response.status_code) >= 400:
            errors = body.get("errors") if isinstance(body, dict) else None
            first = errors[0] if isinstance(errors, list) and errors else {}
            first = first if isinstance(first, dict) else {}
            raise PaymentProviderError(
                str(first.get("detail") or first.get("code") or "Square rejected the request."),
                provider=self.provider,
                code=str(first.get("code") or "provider_error"),
                retryable=int(response.status_code) >= 500,
                http_status=422 if int(response.status_code) < 500 else 503,
            )
        return body

    def test_connection(self) -> dict[str, Any]:
        body = self._request("GET", "/v2/locations")
        locations = body.get("locations") if isinstance(body, dict) else None
        location_ids = {str(item.get("id")) for item in locations or [] if isinstance(item, dict)}
        if self.location_id not in location_ids:
            raise PaymentProviderError(
                "Configured Square location was not returned by the connected account.",
                provider=self.provider,
                code="location_not_found",
                http_status=409,
            )
        return {
            "ok": True,
            "provider": self.provider,
            "environment": self.environment,
            "provider_merchant_id": None,
            "provider_location_id": self.location_id,
        }

    def create_customer(
        self,
        *,
        idempotency_key: str,
        name: str,
        email: str | None,
        cam_parent_reference: str,
    ) -> dict[str, Any]:
        parts = name.strip().split(maxsplit=1)
        body: dict[str, Any] = {
            "idempotency_key": idempotency_key,
            "given_name": parts[0] if parts else name,
            "family_name": parts[1] if len(parts) > 1 else None,
            "reference_id": cam_parent_reference,
        }
        if email:
            body["email_address"] = email
        customer = self._request("POST", "/v2/customers", json_body=body).get("customer") or {}
        return {"provider": self.provider, "customer_id": str(customer["id"])}

    def begin_payment_method_setup(
        self,
        *,
        customer_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        del idempotency_key  # Square Web Payments setup begins client-side; CreateCard is idempotent in completion.
        self._require_configured()
        return {
            "provider": self.provider,
            "mode": "square_web_payments_card_on_file",
            "customer_id": customer_id,
            "setup_session_id": f"sqsetup_{secrets.token_urlsafe(12)}",
            "client_config": {
                "application_id": self.application_id,
                "location_id": self.location_id,
                "script_url": self.script_url,
            },
        }

    def complete_payment_method_setup(
        self,
        *,
        customer_id: str,
        setup_payload: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        source_token = str(setup_payload.get("source_token") or "").strip()
        if not source_token:
            raise PaymentProviderError(
                "Square source_token is required.",
                provider=self.provider,
                code="invalid_setup_payload",
                http_status=422,
            )
        card: dict[str, Any] = {"customer_id": customer_id}
        cardholder_name = str(setup_payload.get("cardholder_name") or "").strip()
        if cardholder_name:
            card["cardholder_name"] = cardholder_name
        billing_address = setup_payload.get("billing_address")
        if isinstance(billing_address, dict) and billing_address:
            card["billing_address"] = billing_address
        request_body: dict[str, Any] = {
            "idempotency_key": idempotency_key,
            "source_id": source_token,
            "card": card,
        }
        verification_token = str(setup_payload.get("verification_token") or "").strip()
        if verification_token:
            request_body["verification_token"] = verification_token
        response = self._request("POST", "/v2/cards", json_body=request_body)
        saved_card = response.get("card") or {}
        return {
            "provider": self.provider,
            "customer_id": customer_id,
            "payment_method_id": str(saved_card["id"]),
            "card_brand": saved_card.get("card_brand"),
            "card_last4": saved_card.get("last_4"),
            "card_exp_month": saved_card.get("exp_month"),
            "card_exp_year": saved_card.get("exp_year"),
            "setup_status": "succeeded",
        }

    def charge_saved_method(
        self,
        *,
        customer_id: str,
        payment_method_id: str,
        amount_cents: int,
        currency: str,
        idempotency_key: str,
        description: str | None = None,
        reference_id: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "idempotency_key": idempotency_key,
            "amount_money": {"amount": amount_cents, "currency": currency.upper()},
            "source_id": payment_method_id,
            "autocomplete": True,
            "customer_id": customer_id,
            "location_id": self.location_id,
        }
        if reference_id:
            body["reference_id"] = reference_id
        if description:
            body["note"] = description[:500]
        response = self._request("POST", "/v2/payments", json_body=body)
        payment = response.get("payment") or {}
        amount_money = payment.get("amount_money") if isinstance(payment, dict) else {}
        amount_money = amount_money if isinstance(amount_money, dict) else {}
        return {
            "provider": self.provider,
            "payment_id": str(payment["id"]),
            "status": str(payment.get("status") or "unknown").lower(),
            "amount_cents": int(amount_money.get("amount") or amount_cents),
            "currency": str(amount_money.get("currency") or currency).upper(),
        }

    def refund_payment(
        self,
        *,
        payment_id: str,
        amount_cents: int,
        currency: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        response = self._request(
            "POST",
            "/v2/refunds",
            json_body={
                "idempotency_key": idempotency_key,
                "payment_id": payment_id,
                "amount_money": {"amount": amount_cents, "currency": currency.upper()},
            },
        )
        refund = response.get("refund") or {}
        amount_money = refund.get("amount_money") if isinstance(refund, dict) else {}
        amount_money = amount_money if isinstance(amount_money, dict) else {}
        return {
            "provider": self.provider,
            "refund_id": str(refund["id"]),
            "payment_id": payment_id,
            "status": str(refund.get("status") or "unknown").lower(),
            "amount_cents": int(amount_money.get("amount") or amount_cents),
        }

    def get_payment_status(self, *, payment_id: str) -> dict[str, Any]:
        response = self._request("GET", f"/v2/payments/{payment_id}")
        payment = response.get("payment") or {}
        amount_money = payment.get("amount_money") if isinstance(payment, dict) else {}
        amount_money = amount_money if isinstance(amount_money, dict) else {}
        return {
            "provider": self.provider,
            "payment_id": payment_id,
            "status": str(payment.get("status") or "unknown").lower(),
            "amount_cents": int(amount_money.get("amount") or 0),
            "currency": str(amount_money.get("currency") or "").upper(),
        }


class MockPaymentProvider(PaymentProvider):
    """Deterministic provider used by CAM automated tests only."""

    provider = "mock"
    display_name = "CAM Mock Payments"

    def __init__(self) -> None:
        self.customers: dict[str, dict[str, Any]] = {}
        self.payment_methods: dict[str, dict[str, Any]] = {}
        self.payments: dict[str, dict[str, Any]] = {}
        self.refunds: dict[str, dict[str, Any]] = {}

    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider=self.provider,
            display_name=self.display_name,
            configured=True,
            environment="test",
            capabilities=("save_payment_method_without_charge", "off_session_charge", "refund"),
            client_config={"integration_mode": "mock"},
            configuration_notes=("Automated tests only; never expose as a production payment option.",),
        )

    def test_connection(self) -> dict[str, Any]:
        return {"ok": True, "provider": self.provider, "environment": "test", "provider_merchant_id": "mock_merchant", "provider_location_id": None}

    def create_customer(self, *, idempotency_key: str, name: str, email: str | None, cam_parent_reference: str) -> dict[str, Any]:
        customer_id = f"mock_cus_{idempotency_key[-10:]}"
        self.customers.setdefault(customer_id, {"name": name, "email": email, "reference": cam_parent_reference})
        return {"provider": self.provider, "customer_id": customer_id}

    def begin_payment_method_setup(self, *, customer_id: str, idempotency_key: str) -> dict[str, Any]:
        if customer_id not in self.customers:
            raise PaymentProviderError("Mock customer not found.", provider=self.provider, code="customer_not_found", http_status=404)
        return {
            "provider": self.provider,
            "mode": "mock",
            "customer_id": customer_id,
            "setup_session_id": f"mock_setup_{idempotency_key[-8:]}",
            "client_config": {},
        }

    def complete_payment_method_setup(self, *, customer_id: str, setup_payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        token = str(setup_payload.get("source_token") or "mock_visa").strip()
        if token == "mock_decline":
            raise PaymentProviderError("Mock card was declined.", provider=self.provider, code="card_declined", http_status=422)
        payment_method_id = f"mock_pm_{idempotency_key[-10:]}"
        self.payment_methods[payment_method_id] = {"customer_id": customer_id, "token": token}
        return {
            "provider": self.provider,
            "customer_id": customer_id,
            "payment_method_id": payment_method_id,
            "card_brand": "visa",
            "card_last4": "4242",
            "card_exp_month": 12,
            "card_exp_year": 2034,
            "setup_status": "succeeded",
        }

    def charge_saved_method(self, *, customer_id: str, payment_method_id: str, amount_cents: int, currency: str, idempotency_key: str, description: str | None = None, reference_id: str | None = None) -> dict[str, Any]:
        method = self.payment_methods.get(payment_method_id)
        if not method or method.get("customer_id") != customer_id:
            raise PaymentProviderError("Mock payment method not found.", provider=self.provider, code="payment_method_not_found", http_status=404)
        if method.get("token") == "mock_charge_decline":
            raise PaymentProviderError("Mock charge declined.", provider=self.provider, code="card_declined", http_status=422)
        payment_id = f"mock_pay_{idempotency_key[-10:]}"
        payment = {"provider": self.provider, "payment_id": payment_id, "status": "succeeded", "amount_cents": amount_cents, "currency": currency.upper(), "description": description, "reference_id": reference_id}
        self.payments[payment_id] = payment
        return dict(payment)

    def refund_payment(self, *, payment_id: str, amount_cents: int, currency: str, idempotency_key: str) -> dict[str, Any]:
        if payment_id not in self.payments:
            raise PaymentProviderError("Mock payment not found.", provider=self.provider, code="payment_not_found", http_status=404)
        refund_id = f"mock_ref_{idempotency_key[-10:]}"
        refund = {"provider": self.provider, "refund_id": refund_id, "payment_id": payment_id, "status": "succeeded", "amount_cents": amount_cents, "currency": currency.upper()}
        self.refunds[refund_id] = refund
        return dict(refund)

    def get_payment_status(self, *, payment_id: str) -> dict[str, Any]:
        payment = self.payments.get(payment_id)
        if not payment:
            raise PaymentProviderError("Mock payment not found.", provider=self.provider, code="payment_not_found", http_status=404)
        return dict(payment)


def get_payment_provider(provider: str) -> PaymentProvider:
    provider_name = provider.strip().lower()
    if provider_name == "stripe":
        return StripePaymentProvider()
    if provider_name == "square":
        return SquarePaymentProvider()
    if provider_name == "mock" and os.environ.get("CAM_PAYMENT_PROVIDER_ENABLE_MOCK", "").strip().lower() in {"1", "true", "yes", "on"}:
        return MockPaymentProvider()
    raise PaymentProviderError(
        "Unsupported payment provider.",
        provider=provider_name or "unknown",
        code="unsupported_provider",
        http_status=404,
    )


def payment_provider_catalog() -> list[dict[str, Any]]:
    return [StripePaymentProvider().descriptor().as_dict(), SquarePaymentProvider().descriptor().as_dict()]
