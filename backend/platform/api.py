"""
Handwerker-KI Platform API Server
Flask-based API with JWT auth for the SaaS platform.

Endpoints:
  POST   /api/register          - Create account
  POST   /api/login             - Login
  GET    /api/me                - Current user info
  POST   /api/onboarding        - Submit business data (creates customer)
  GET    /api/customers         - List user's customers
  GET    /api/customer/<id>     - Single customer details
  GET    /api/instance/<cid>    - Agent instance status
  POST   /api/payment-webhook   - Payment notification (Stripe/etc)

  GET    /register              - Registration page
  GET    /onboarding            - Onboarding wizard
  GET    /dashboard             - Customer dashboard
  GET    /                      - Redirects to landing page
"""

import os
import json
import sys
import logging
from pathlib import Path

from flask import Flask, request, jsonify, render_template_string, redirect, send_from_directory

from . import database as db
from . import provisioner
from . import whatsapp_gateway as wa

log = logging.getLogger("hk-api")

# Flask app
app = Flask(__name__)

# JWT secret - in production, use a proper secret from env
JWT_SECRET = os.environ.get("SKP_JWT_SECRET", "stuttgart-ki-profis-dev-secret-change-in-production")

# Paths
AGENT_DIR = Path(__file__).parent.parent
LANDING_DIR = Path("/root/projects/stuttgart-ki-profis/landing")
TEMPLATES_DIR = Path(__file__).parent / "templates"


# ── Auth helpers ─────────────────────────────────────────────────────

def _require_auth():
    """Check Authorization header for valid JWT. Returns user dict or None."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.split(" ", 1)[1]
    payload = db.verify_jwt_token(token, JWT_SECRET)
    if not payload:
        return None
    return db.get_user_by_id(payload.get("user_id"))


def _json_error(msg: str, status: int = 400):
    return jsonify({"error": msg}), status


def _json_ok(data: dict, status: int = 200):
    return jsonify({"ok": True, **data}), status


# ── API Endpoints ────────────────────────────────────────────────────


@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({"status": "ok", "version": "1.0.0"})


@app.route("/api/register", methods=["POST"])
def api_register():
    """Register a new user account."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""

    if not email or "@" not in email:
        return _json_error("Bitte gib eine gultige E-Mail-Adresse ein.")
    if len(password) < 8:
        return _json_error("Das Passwort muss mindestens 8 Zeichen lang sein.")

    user = db.create_user(email, password)
    if not user:
        return _json_error("Diese E-Mail-Adresse ist bereits registriert.", 409)

    token = db.generate_jwt_token(user["id"], JWT_SECRET)
    return _json_ok({
        "token": token,
        "user": {"id": user["id"], "email": user["email"]},
    }, 201)


@app.route("/api/login", methods=["POST"])
def api_login():
    """Login with email and password."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""

    user = db.get_user_by_email(email)
    if not user or not db.check_password(password, user["password_hash"]):
        return _json_error("E-Mail oder Passwort falsch.", 401)

    token = db.generate_jwt_token(user["id"], JWT_SECRET)
    return _json_ok({
        "token": token,
        "user": {"id": user["id"], "email": user["email"]},
    })


@app.route("/api/me", methods=["GET"])
def api_me():
    """Get current user info and their customers."""
    user = _require_auth()
    if not user:
        return _json_error("Nicht eingeloggt.", 401)
    customers = db.get_customers_by_user(user["id"])
    return _json_ok({
        "user": {"id": user["id"], "email": user["email"]},
        "customers": customers,
    })


@app.route("/api/onboarding", methods=["POST"])
def api_onboarding():
    """Submit business data to create a new customer/agent."""
    user = _require_auth()
    if not user:
        return _json_error("Nicht eingeloggt.", 401)

    data = request.get_json(silent=True) or {}

    required = ["company_name", "whatsapp_number"]
    for field in required:
        if not data.get(field):
            return _json_error(f"Feld '{field}' wird benotigt.")

    plan = data.get("plan", "basis")
    if plan not in ("basis", "pro", "enterprise"):
        plan = "basis"

    customer = db.create_customer(
        user_id=user["id"],
        company_name=data["company_name"],
        trade=data.get("trade", ""),
        street=data.get("street", ""),
        zip_city=data.get("zip_city", ""),
        phone=data.get("phone", ""),
        email=data.get("email", ""),
        whatsapp_number=data["whatsapp_number"],
        hourly_rate=float(data.get("hourly_rate", 55)),
        employees=int(data.get("employees", 1)),
        vat_id=data.get("vat_id", ""),
        plan=plan,
    )

    if not customer:
        return _json_error("Fehler beim Anlegen des Kunden.", 500)

    # Start provisioning asynchronously
    # For now, run it inline (in production, use a task queue)
    try:
        result = provisioner.provision_customer(customer["customer_id"])
        customer["provisioning"] = result
    except Exception as e:
        log.error(f"Provisioning error: {e}")
        customer["provisioning"] = {"status": "pending", "message": str(e)}

    return _json_ok({"customer": customer}, 201)


@app.route("/api/customers", methods=["GET"])
def api_customers():
    """List all customers for the authenticated user."""
    user = _require_auth()
    if not user:
        return _json_error("Nicht eingeloggt.", 401)

    customers = db.get_customers_by_user(user["id"])
    # Enrich with instance data
    enriched = []
    for c in customers:
        inst = db.get_instance_by_customer(c["id"])
        enriched.append({
            **c,
            "instance": inst,
        })
    return _json_ok({"customers": enriched})


@app.route("/api/customer/<cid>", methods=["GET"])
def api_customer(cid):
    """Get single customer details."""
    user = _require_auth()
    if not user:
        return _json_error("Nicht eingeloggt.", 401)

    customer = db.get_customer_by_customer_id(cid)
    if not customer or customer["user_id"] != user["id"]:
        return _json_error("Kunde nicht gefunden.", 404)

    inst = db.get_instance_by_customer(customer["id"])
    return _json_ok({
        "customer": customer,
        "instance": inst,
    })


@app.route("/api/instance/<cid>", methods=["GET"])
def api_instance(cid):
    """Get agent instance status for a customer."""
    user = _require_auth()
    if not user:
        return _json_error("Nicht eingeloggt.", 401)

    customer = db.get_customer_by_customer_id(cid)
    if not customer or customer["user_id"] != user["id"]:
        return _json_error("Kunde nicht gefunden.", 404)

    inst = db.get_instance_by_customer(customer["id"])
    if not inst:
        return _json_ok({"instance": {"status": "not_provisioned"}})

    return _json_ok({"instance": inst})


@app.route("/api/customer/<cid>", methods=["PATCH"])
def api_update_customer(cid):
    """Update customer profile data."""
    user = _require_auth()
    if not user:
        return _json_error("Nicht eingeloggt.", 401)

    customer = db.get_customer_by_customer_id(cid)
    if not customer or customer["user_id"] != user["id"]:
        return _json_error("Kunde nicht gefunden.", 404)

    data = request.get_json(silent=True) or {}
    db.update_customer(customer["id"], **data)

    updated = db.get_customer_by_id(customer["id"])
    return _json_ok({"customer": updated})


@app.route("/api/payment-webhook", methods=["POST"])
def api_payment_webhook():
    """Stripe/PayPal payment webhook endpoint."""
    data = request.get_json(silent=True) or {}
    customer_id = data.get("customer_id") or data.get("client_reference_id", "")
    amount = data.get("amount", 0)
    provider = data.get("provider", "stripe")
    event_id = data.get("id", "")

    if not customer_id:
        return _json_error("Missing customer_id")

    customer = db.get_customer_by_customer_id(customer_id)
    if not customer:
        return _json_error("Customer not found", 404)

    db.record_payment(customer["id"], amount, provider, event_id)
    db.update_customer(customer["id"], status="active")

    # Trigger provisioning if not already done
    if customer["status"] == "pending":
        provisioner.provision_customer(customer_id)

    return _json_ok({"status": "ok"})


@app.route("/api/admin/instances", methods=["GET"])
def api_admin_instances():
    """Admin: list all instances with user info. Simple token guard."""
    admin_key = os.environ.get("SKP_ADMIN_KEY", "")
    auth = request.headers.get("X-Admin-Key", "")
    if not admin_key or auth != admin_key:
        return _json_error("Unauthorized", 401)
    instances = db.admin_list_all()
    return _json_ok({"instances": instances})


@app.route("/api/admin/stats", methods=["GET"])
def api_admin_stats():
    """Admin: aggregate platform statistics."""
    admin_key = os.environ.get("SKP_ADMIN_KEY", "")
    auth = request.headers.get("X-Admin-Key", "")
    if not admin_key or auth != admin_key:
        return _json_error("Unauthorized", 401)
    stats = db.admin_stats()
    return _json_ok({"stats": stats})


# ── Stripe Checkout ──────────────────────────────────────────────────


PRICING = {
    "basis": {"id": "basis", "name": "Basis", "price": 1900, "currency": "eur", "interval": "month",
               "description": "Ein-Mann-Betrieb, 20 Angebote/Monat"},
    "pro": {"id": "pro", "name": "Pro", "price": 3900, "currency": "eur", "interval": "month",
             "description": "Kleinbetrieb (2-5 MA), unbegrenzt Angebote"},
    "enterprise": {"id": "enterprise", "name": "Enterprise", "price": 7900, "currency": "eur", "interval": "month",
                    "description": "Wachsender Betrieb, alles inklusive"},
}


@app.route("/api/pricing", methods=["GET"])
def api_pricing():
    """Return pricing configuration."""
    return _json_ok({"plans": PRICING})


@app.route("/api/create-checkout-session", methods=["POST"])
def api_create_checkout_session():
    """
    Create a Stripe Checkout Session for a customer.
    After successful payment, the customer's agent is activated.
    """
    user = _require_auth()
    if not user:
        return _json_error("Nicht eingeloggt.", 401)

    data = request.get_json(silent=True) or {}
    customer_id = data.get("customer_id", "")
    success_url = data.get("success_url", "http://localhost:5000/dashboard")
    cancel_url = data.get("cancel_url", "http://localhost:5000/dashboard")

    if not customer_id:
        return _json_error("customer_id erforderlich")

    customer = db.get_customer_by_customer_id(customer_id)
    if not customer or customer["user_id"] != user["id"]:
        return _json_error("Kunde nicht gefunden.", 404)

    plan = customer.get("plan", "basis")
    plan_config = PRICING.get(plan, PRICING["basis"])

    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe_key:
        # Dev mode: simulate successful payment
        log.info(f"DEV MODE: Simulating Stripe checkout for {customer_id} ({plan} - {plan_config['price']}ct)")
        db.update_customer(customer["id"], status="active")
        if customer["status"] == "pending":
            provisioner.provision_customer(customer_id)
        return _json_ok({
            "checkout_url": None,
            "dev_mode": True,
            "message": "Payment simulated (dev mode). Agent wird eingerichtet.",
        })

    try:
        import stripe
        stripe.api_key = stripe_key

        checkout_session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": plan_config["currency"],
                    "product_data": {
                        "name": f"Stuttgart KI Profis - {plan_config['name']}",
                        "description": plan_config["description"],
                    },
                    "unit_amount": plan_config["price"],
                    "recurring": {"interval": plan_config["interval"]},
                },
                "quantity": 1,
            }],
            client_reference_id=customer_id,
            customer_email=user["email"],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"customer_id": customer_id, "user_id": str(user["id"])},
        )

        return _json_ok({
            "checkout_url": checkout_session.url,
            "session_id": checkout_session.id,
        })

    except Exception as e:
        log.error(f"Stripe checkout error: {e}")
        return _json_error(f"Stripe-Fehler: {str(e)}")


@app.route("/api/stripe-webhook", methods=["POST"])
def api_stripe_webhook():
    """
    Stripe webhook endpoint.
    Handles checkout.session.completed and invoice.paid events.
    """
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    if not stripe_key:
        log.info("Stripe not configured - skipping webhook")
        return _json_ok({"status": "ignored"})

    import stripe
    stripe.api_key = stripe_key

    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")

    try:
        if webhook_secret:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        else:
            event = json.loads(payload)
    except ValueError:
        return _json_error("Invalid payload", 400)
    except stripe.error.SignatureVerificationError:
        return _json_error("Invalid signature", 400)

    event_type = event.get("type") if isinstance(event, dict) else event.type
    log.info(f"Stripe webhook: {event_type}")

    if event_type in ("checkout.session.completed", "invoice.paid"):
        session = event["data"]["object"] if isinstance(event, dict) else event.data.object
        customer_id = session.get("client_reference_id") or session.get("metadata", {}).get("customer_id", "")
        amount = session.get("amount_total", 0) / 100.0
        payment_intent = session.get("payment_intent", "")

        if customer_id:
            customer = db.get_customer_by_customer_id(customer_id)
            if customer:
                db.record_payment(customer["id"], amount, "stripe", payment_intent)
                db.update_customer(customer["id"], status="active")
                if customer["status"] == "pending":
                    provisioner.provision_customer(customer_id)
                log.info(f"Payment completed for {customer_id}: {amount} EUR")

    return _json_ok({"status": "received"})


# ── WhatsApp Connection ──────────────────────────────────────────────


@app.route("/api/whatsapp/connection-token", methods=["POST"])
def api_whatsapp_connection_token():
    """Generate or return the WhatsApp connection pairing info for a customer."""
    user = _require_auth()
    if not user:
        return _json_error("Nicht eingeloggt.", 401)

    data = request.get_json(silent=True) or {}
    customer_id = data.get("customer_id", "")
    if not customer_id:
        return _json_error("customer_id erforderlich")

    customer = db.get_customer_by_customer_id(customer_id)
    if not customer or customer["user_id"] != user["id"]:
        return _json_error("Kunde nicht gefunden.", 404)

    result = wa.generate_connection_qr(customer_id)
    if "error" in result:
        return _json_error(result["error"], 404)

    return _json_ok(result)


@app.route("/api/whatsapp/status", methods=["POST"])
def api_whatsapp_status():
    """Check WhatsApp connection status for a customer."""
    user = _require_auth()
    if not user:
        return _json_error("Nicht eingeloggt.", 401)

    data = request.get_json(silent=True) or {}
    customer_id = data.get("customer_id", "")
    if not customer_id:
        return _json_error("customer_id erforderlich")

    customer = db.get_customer_by_customer_id(customer_id)
    if not customer or customer["user_id"] != user["id"]:
        return _json_error("Kunde nicht gefunden.", 404)

    result = wa.get_status(customer_id)
    return _json_ok(result)


@app.route("/api/whatsapp/connect", methods=["POST"])
def api_whatsapp_connect():
    """Mark a customer's WhatsApp as connected (after pairing)."""
    user = _require_auth()
    if not user:
        return _json_error("Nicht eingeloggt.", 401)

    data = request.get_json(silent=True) or {}
    customer_id = data.get("customer_id", "")
    if not customer_id:
        return _json_error("customer_id erforderlich")

    customer = db.get_customer_by_customer_id(customer_id)
    if not customer or customer["user_id"] != user["id"]:
        return _json_error("Kunde nicht gefunden.", 404)

    success = wa.mark_connected(customer_id)
    if not success:
        return _json_error("Konnte Verbindungsstatus nicht aktualisieren.", 500)

    return _json_ok({"connected": True})


# ── Dedicated Instance Deployment ────────────────────────────────────


@app.route("/api/deploy/dedicated", methods=["POST"])
def api_deploy_dedicated():
    """
    Deploy a dedicated systemd service for an Enterprise customer.
    This creates an isolated agent instance on its own port.
    """
    user = _require_auth()
    if not user:
        return _json_error("Nicht eingeloggt.", 401)

    data = request.get_json(silent=True) or {}
    customer_id = data.get("customer_id", "")
    if not customer_id:
        return _json_error("customer_id erforderlich")

    customer = db.get_customer_by_customer_id(customer_id)
    if not customer or customer["user_id"] != user["id"]:
        return _json_error("Kunde nicht gefunden.", 404)

    if customer["plan"] not in ("enterprise",):
        return _json_error("Dedizierte Instanzen nur fur Enterprise-Tarif")

    result = provisioner.deploy_dedicated_instance(customer_id)
    if result.get("status") == "error":
        return _json_error(result["message"], 500)

    return _json_ok(result)


# ── Frontend Pages ────────────────────────────────────────────────────


def _render_template(name: str, **context):
    """Render an HTML template from the templates directory."""
    path = TEMPLATES_DIR / name
    if not path.exists():
        return f"<h1>Template {name} not found</h1>", 404
    content = path.read_text(encoding="utf-8")
    # Simple string-based template replacement (no Jinja2 dependency)
    for key, val in context.items():
        content = content.replace(f"{{{{{key}}}}}", str(val))
    return content


@app.route("/register")
def page_register():
    return _render_template("register.html", page_title="Registrieren - Stuttgart KI Profis")


@app.route("/onboarding")
def page_onboarding():
    return _render_template("onboarding.html", page_title="Onboarding - Stuttgart KI Profis")


@app.route("/dashboard")
def page_dashboard():
    return _render_template("dashboard.html", page_title="Dashboard - Stuttgart KI Profis")


@app.route("/admin")
def page_admin():
    return _render_template("admin.html", page_title="Agency Dashboard - Stuttgart KI Profis")


@app.route("/login")
def page_login():
    return _render_template("login.html", page_title="Login - Stuttgart KI Profis")


@app.route("/")
def page_root():
    """Serve landing page directly from the platform API server.
    Falls back to GitHub Pages redirect if available."""
    landing_index = LANDING_DIR / "index.html"
    if landing_index.exists():
        return open(landing_index).read()
    return redirect("https://stuttgart-ki-profis.de")


@app.route("/photo.jpg")
def page_photo():
    return send_from_directory(str(LANDING_DIR), "photo.jpg")


@app.route("/business-card.html")
def page_business_card():
    return send_from_directory(str(LANDING_DIR), "business-card.html")


@app.route("/qr-code.svg")
def page_qr_code():
    return send_from_directory(str(LANDING_DIR), "qr-code.svg")


@app.route("/qr-code-card.svg")
def page_qr_code_card():
    return send_from_directory(str(LANDING_DIR), "qr-code-card.svg")


@app.route("/card")
def page_card_redirect():
    """URL forwarding for the business card QR code.
    Change the target by updating SAP_CARD_REDIRECT env var and restarting.
    """
    target = os.environ.get(
        "SAP_CARD_REDIRECT",
        "http://85.215.163.241:5000/#kontakt",
    )
    return redirect(target)


# ── Main ──────────────────────────────────────────────────────────────


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Initialize database
    db.init_db()
    log.info("Database initialized.")

    # Ensure templates exist
    templates_dir = TEMPLATES_DIR
    templates_dir.mkdir(parents=True, exist_ok=True)

    port = int(os.environ.get("SAP_API_PORT", 5000))
    host = os.environ.get("SAP_API_HOST", "0.0.0.0")
    debug = os.environ.get("SAP_DEBUG", "").lower() in ("1", "true", "yes")

    log.info(f"Stuttgart KI Profis Platform API starting on {host}:{port}")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()