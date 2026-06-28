"""
WhatsApp Gateway integration for Stuttgart KI Profis platform.
Supports: Twilio (production-ready), Evolution API (self-hosted), Baileys (lightweight).

The gateway handles:
- Inbound message routing to the correct customer agent
- Outbound message delivery (PDFs, text)
- Connection status tracking
- QR code generation for device pairing

Currently configured for Twilio. Extend to Evolution API by setting
WHATSAPP_GATEWAY=evolution and EVOLUTION_API_URL + EVOLUTION_API_KEY.
"""

import os
import json
import logging
import requests
from pathlib import Path
from urllib.parse import urlencode

from agent.platform import database as db

log = logging.getLogger("hk-whatsapp-gateway")

# Gateway configuration from environment
GATEWAY_TYPE = os.environ.get("WHATSAPP_GATEWAY", "twilio")  # twilio, evolution, baileys
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER", "")  # e.g. +14155238886
EVOLUTION_API_URL = os.environ.get("EVOLUTION_API_URL", "")
EVOLUTION_API_KEY = os.environ.get("EVOLUTION_API_KEY", "")

# Path for local WhatsApp gateway state
GATEWAY_STATE_DIR = Path(__file__).parent / "data" / "gateway"
QR_CODE_PATH = GATEWAY_STATE_DIR / "qr_codes"


def _ensure_dirs():
    GATEWAY_STATE_DIR.mkdir(parents=True, exist_ok=True)
    QR_CODE_PATH.mkdir(parents=True, exist_ok=True)


def get_gateway_type() -> str:
    """Return the configured gateway type."""
    return GATEWAY_TYPE


def is_configured() -> bool:
    """Check if the WhatsApp gateway is configured."""
    if GATEWAY_TYPE == "twilio":
        return bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN)
    elif GATEWAY_TYPE == "evolution":
        return bool(EVOLUTION_API_URL and EVOLUTION_API_KEY)
    elif GATEWAY_TYPE == "baileys":
        return False  # Not yet implemented
    return False


def send_message(to_number: str, body: str, media_url: str | None = None) -> bool:
    """
    Send a WhatsApp message via the configured gateway.
    Returns True on success, False on failure.
    """
    if GATEWAY_TYPE == "twilio":
        return _send_twilio(to_number, body, media_url)
    elif GATEWAY_TYPE == "evolution":
        return _send_evolution(to_number, body, media_url)
    else:
        log.error(f"No gateway configured to send message to {to_number}")
        return False


def _send_twilio(to_number: str, body: str, media_url: str | None = None) -> bool:
    """Send via Twilio WhatsApp API."""
    from twilio.rest import Client
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        kwargs = {
            "from_": f"whatsapp:{TWILIO_WHATSAPP_NUMBER}",
            "to": f"whatsapp:{to_number}",
            "body": body,
        }
        if media_url:
            kwargs["media_url"] = [media_url]
        client.messages.create(**kwargs)
        log.info(f"Twilio message sent to {to_number}")
        return True
    except Exception as e:
        log.error(f"Twilio send failed: {e}")
        return False


def _send_evolution(to_number: str, body: str, media_url: str | None = None) -> bool:
    """Send via Evolution API."""
    try:
        payload = {
            "number": to_number,
            "text": body,
            "delay": 1200,
        }
        if media_url:
            payload["media"] = media_url

        resp = requests.post(
            f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_API_KEY}",
            json=payload,
            timeout=15,
        )
        if resp.ok:
            log.info(f"Evolution message sent to {to_number}")
            return True
        else:
            log.error(f"Evolution send failed: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        log.error(f"Evolution send error: {e}")
        return False


def generate_connection_qr(customer_id: str) -> dict:
    """
    Generate a WhatsApp connection QR code for a customer.
    For Twilio: returns instructions to configure the webhook.
    For Evolution API: triggers QR code generation on the gateway.
    For Dev: returns a placeholder QR code URL.

    Returns:
        dict with: qr_code_url, instructions, gateway_type, connected
    """
    _ensure_dirs()
    customer = db.get_customer_by_customer_id(customer_id)
    if not customer:
        return {"error": "Customer not found"}

    wa_number = customer.get("whatsapp_number", "")
    setup_token = customer.get("setup_token", "")

    if GATEWAY_TYPE == "evolution" and EVOLUTION_API_URL:
        # Trigger QR code generation on Evolution API
        try:
            instance = customer.get("customer_id", customer_id)
            resp = requests.get(
                f"{EVOLUTION_API_URL}/instance/connect/{instance}",
                params={"apiKey": EVOLUTION_API_KEY},
                timeout=10,
            )
            if resp.ok:
                data = resp.json()
                qr_url = data.get("qrcode", {}).get("code", "")
                return {
                    "qr_code_url": f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={qr_url}",
                    "whatsapp_number": wa_number,
                    "gateway_type": "evolution",
                    "connected": False,
                    "instructions": "Scanne den QR-Code mit WhatsApp (Einstellungen > Gekoppelte Gerate).",
                }
        except Exception as e:
            log.warning(f"Evolution QR failed: {e}")

    # Default: Twilio / Dev mode instructions
    twilio_number = TWILIO_WHATSAPP_NUMBER or "+14155238886"
    instructions = (
        f"Dein KI-Agent ist bereit unter der Nummer {wa_number or twilio_number}.\n\n"
        f"So konfigurierst du Twilio WhatsApp:\n"
        f"1. Gehe zu console.twilio.com\n"
        f"2. Sandbox: Sende 'join {setup_token[:8]}' an {twilio_number}\n"
        f"3. Oder konfiguriere die Webhook-URL:\n"
        f"   POST https://dein-server.com/webhook/whatsapp\n\n"
        f"Falls du WhatsApp Business nutzt:\n"
        f"1. Scanne den QR-Code unten in WhatsApp\n"
        f"2. Oder sende eine Nachricht an deine Agent-Nummer"
    )

    return {
        "qr_code_url": f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={setup_token}",
        "whatsapp_number": wa_number or twilio_number,
        "gateway_type": GATEWAY_TYPE,
        "connected": False,
        "instructions": instructions,
        "twilio_webhook_url": f"/webhook/whatsapp",
        "setup_token": setup_token,
    }


def get_status(customer_id: str) -> dict:
    """Get WhatsApp connection status for a customer."""
    customer = db.get_customer_by_customer_id(customer_id)
    if not customer:
        return {"error": "Customer not found"}

    inst = db.get_instance_by_customer(customer["id"])
    connected = bool(inst and inst.get("whatsapp_connected"))

    return {
        "customer_id": customer_id,
        "whatsapp_number": customer.get("whatsapp_number", ""),
        "connected": connected,
        "gateway_type": GATEWAY_TYPE,
        "gateway_configured": is_configured(),
        "instance_status": inst["status"] if inst else "not_provisioned",
    }


def mark_connected(customer_id: str) -> bool:
    """Mark a customer's WhatsApp as connected."""
    customer = db.get_customer_by_customer_id(customer_id)
    if not customer:
        return False
    inst = db.get_instance_by_customer(customer["id"])
    if inst:
        import datetime
        db.update_instance(
            inst["id"],
            whatsapp_connected=1,
            last_seen=datetime.datetime.now().isoformat(),
        )
        log.info(f"WhatsApp connection marked for {customer_id}")
        return True
    return False


def get_twilio_webhook_url(base_url: str) -> str:
    """Get the webhook URL for Twilio configuration."""
    return f"{base_url.rstrip('/')}/webhook/whatsapp"


# ── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Usage: python -m agent.platform.whatsapp_gateway <command> [args]")
        print("Commands:")
        print("  status <customer_id>          - Check connection status")
        print("  qr <customer_id>              - Generate connection QR")
        print("  connect <customer_id>         - Mark customer as connected")
        print("  send <to> <message>            - Send a test message")
        print("  info                          - Show gateway info")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "info":
        print(f"Gateway type: {GATEWAY_TYPE}")
        print(f"Configured: {is_configured()}")
        print(f"Twilio SID: {TWILIO_ACCOUNT_SID[:10] if TWILIO_ACCOUNT_SID else '(not set)'}...")
        print(f"Evolution URL: {EVOLUTION_API_URL or '(not set)'}")

    elif cmd == "status" and len(sys.argv) > 2:
        result = get_status(sys.argv[2])
        print(json.dumps(result, indent=2, default=str))

    elif cmd == "qr" and len(sys.argv) > 2:
        result = generate_connection_qr(sys.argv[2])
        print(json.dumps(result, indent=2, default=str))

    elif cmd == "connect" and len(sys.argv) > 2:
        result = mark_connected(sys.argv[2])
        print(f"Connected: {result}")

    elif cmd == "send" and len(sys.argv) > 3:
        result = send_message(sys.argv[2], sys.argv[3])
        print(f"Sent: {result}")

    else:
        print(f"Unknown command: {cmd}")