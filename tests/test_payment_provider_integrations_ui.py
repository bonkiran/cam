from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_payment_provider_integrations_ui_is_loaded_and_provider_neutral():
    index = (REPO_ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    js = (REPO_ROOT / "app" / "static" / "academy_payment_provider_integrations_v2.js").read_text(encoding="utf-8")
    css = (REPO_ROOT / "app" / "static" / "academy_payment_provider_integrations_v1.css").read_text(encoding="utf-8")

    assert "academy_payment_provider_integrations_v1.css?v=1" in index
    assert "academy_payment_provider_integrations_v2.js?v=3" in index
    assert "academy_payment_provider_integrations_v1.js?v=1" not in index

    assert "/api/academy/payment-providers" in js
    assert "/api/academy/payment-providers/${provider}/test-connection" in js
    assert "/api/academy/payment-providers/select" in js
    assert "Stripe + Square compatibility" in js
    assert "CAM_STRIPE_SECRET_KEY" in js
    assert "CAM_SQUARE_ACCESS_TOKEN" in js
    assert "CAM never stores full card numbers or CVC/CVV" in js

    assert ".cam-provider-grid" in css
    assert ".cam-provider-status.selected" in css


def test_integrations_v2_mount_is_non_destructive_and_does_not_replace_app_shell():
    js = (REPO_ROOT / "app" / "static" / "academy_payment_provider_integrations_v2.js").read_text(encoding="utf-8")

    # Regression for production flicker: v1 replaced #app.innerHTML while the legacy
    # integrations renderer also owned the route. V2 only injects the payment-provider
    # section into the existing page and therefore cannot fight the route renderer.
    assert "app.innerHTML" not in js
    assert "shell(pageMarkup" not in js
    assert "document.createElement('section')" in js
    assert "insertAdjacentElement('afterend', host)" in js
    assert "document.querySelector(ROOT_SELECTOR)" in js


def test_provider_feedback_survives_provider_grid_refresh():
    js = (REPO_ROOT / "app" / "static" / "academy_payment_provider_integrations_v2.js").read_text(encoding="utf-8")

    # Test Connection and provider selection refresh the provider grid so connection/
    # selection status changes immediately. Feedback must be stored outside that grid
    # and re-rendered into the replacement card rather than disappearing after ~1 sec.
    assert "const feedbackByProvider = new Map();" in js
    assert "feedbackByProvider.set(provider, {message, state});" in js
    assert "feedbackByProvider.get(provider)" in js
    assert "data-state=\"${esc(feedback.state || '')}\"" in js
    assert "${esc(feedback.message || '')}</p>" in js
    assert "sandbox connection successful." in js


def test_payment_provider_ui_does_not_embed_secret_keys():
    js = (REPO_ROOT / "app" / "static" / "academy_payment_provider_integrations_v2.js").read_text(encoding="utf-8")
    index = (REPO_ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")

    combined = f"{js}\n{index}"
    assert "sk_test_" not in combined
    assert "sk_live_" not in combined
    assert "CAM_STRIPE_PUBLISHABLE_KEY =" not in combined
    assert "CAM_STRIPE_SECRET_KEY =" not in combined
