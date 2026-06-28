"""
Platform-aware webhook server. Extension of agent/server.py that
auto-discovers all customers from the platform database.

Instead of AGENT_CUSTOMER env var, this loads ALL active customers
from the database and routes messages accordingly.
"""

import os
import sys
import logging
from pathlib import Path

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, request
from agent import agent as hk_agent
from agent import config_loader
from agent import transcriber
from agent.server import twiml_response, get_twilio

# Import platform database
from agent.platform import database as db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("hk-platform-server")

app = Flask(__name__)


@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    """Twilio incoming webhook - platform aware multi-tenant routing."""
    from_number = request.form.get("From", "")
    to_number = request.form.get("To", "")
    num_media = int(request.form.get("NumMedia", 0))
    body = request.form.get("Body", "")

    log.info(f"Message from {from_number}: {num_media} media, body={body[:80]}")

    # Resolve customer - check DB first, then filesystem
    customer = resolve_platform_customer(from_number)
    if not customer:
        log.warning(f"No customer configured for {from_number}")
        return twiml_response(
            "Willkommen beim Handwerker-KI Angebotsassistenten. "
            "Leider ist Ihr Account noch nicht aktiviert. "
            "Bitte registrieren Sie sich unter: stuttgart-ki-profis.de"
        )

    customer_id = customer["customer_id"] if isinstance(customer, dict) else customer

    # Process voice message
    if num_media > 0:
        media_url = request.form.get("MediaUrl0", "")
        media_type = request.form.get("MediaContentType0", "")

        if "audio" in media_type or "video" in media_type or "voice" in media_type:
            log.info(f"Downloading and transcribing audio from {media_url}")
            try:
                user_input = transcriber.download_and_transcribe(media_url)
                log.info(f"Transcribed: {user_input[:100]}")
            except Exception as e:
                log.error(f"Transcription failed: {e}")
                return twiml_response(
                    "Entschuldigung, ich konnte die Sprachnachricht nicht verstehen. "
                    "Bitte versuchen Sie es noch einmal oder schreiben Sie mir eine Textnachricht."
                )
        else:
            user_input = body.strip()
    else:
        user_input = body.strip()

    if not user_input:
        return twiml_response(
            "Ich habe keine Nachricht erhalten. "
            "Bitte senden Sie mir eine Sprachnachricht oder schreiben Sie, "
            "welche Arbeit Sie anbieten moechten."
        )

    # Generate quote
    log.info(f"Processing request for customer '{customer_id}': {user_input[:100]}")
    try:
        result = hk_agent.process_request(user_input, customer_id)
    except Exception as e:
        log.error(f"Agent processing failed: {e}")
        return twiml_response(
            "Entschuldigung, bei der Angebotserstellung ist ein Fehler aufgetreten. "
            "Bitte versuchen Sie es spaeter noch einmal."
        )

    if "error" in result:
        return twiml_response(
            f"Entschuldigung, ich konnte Ihre Anfrage nicht verarbeiten: {result['error']}"
        )

    # Send result back via WhatsApp
    pdf_path = result["pdf_path"]
    summary = (
        f"Angebot {result['quote_number']} erstellt!\n"
        f"Kunde: {result['data']['kunde']['name']}\n"
        f"Betrag: {result['brutto']:.2f} EUR brutto\n"
        f"Aus Preisliste: {result['matched_items']} Positionen\n"
        f"PDF wird per Anhang gesendet..."
    )

    twilio = get_twilio()
    if twilio:
        try:
            twilio.messages.create(from_=to_number, to=from_number, body=summary)
            twilio.messages.create(
                from_=to_number, to=from_number,
                body=f"Angebot {result['quote_number']}",
                media_url=[f"file://{pdf_path}"],
            )
        except Exception as e:
            log.error(f"Failed to send Twilio message: {e}")
            return twiml_response(
                f"{summary}\n\nPDF: {pdf_path}\n\n"
                f"(PDF konnte nicht direkt gesendet werden, liegt aber auf dem Server.)"
            )

    return twiml_response(summary)


def resolve_platform_customer(from_number: str) -> str | dict | None:
    """
    Resolve customer by WhatsApp number.
    Checks: 1) Platform DB, 2) Filesystem customers, 3) AGENT_CUSTOMER env
    """
    # 1. Check platform database for active customers
    try:
        conn = db.get_conn()
        rows = conn.execute(
            "SELECT customer_id, company_name, whatsapp_number, status FROM customers WHERE status='active'"
        ).fetchall()
        conn.close()

        for row in rows:
            wa = row.get("whatsapp_number", "")
            if wa and (wa in from_number or from_number.endswith(wa)):
                log.info(f"Matched DB customer '{row['customer_id']}' for {from_number}")
                return row
    except Exception as e:
        log.warning(f"DB lookup failed: {e}")

    # 2. Fallback: filesystem customers
    override = os.environ.get("AGENT_CUSTOMER")
    if override:
        return override

    for c in config_loader.list_customers():
        cfg = config_loader.load_config(c)
        wa = cfg.get("whatsapp", {}).get("number", "")
        if wa and (wa in from_number or from_number.endswith(wa)):
            return c

    return None


@app.route("/health", methods=["GET"])
def health():
    return "OK", 200


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Stuttgart KI Profis Platform Webhook")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    # Check config
    try:
        db.init_db()
        conn = db.get_conn()
        count = conn.execute("SELECT COUNT(*) as c FROM customers WHERE status='active'").fetchone()["c"]
        conn.close()
        log.info(f"Platform DB: {count} active customers")
    except Exception as e:
        log.warning(f"Could not init DB: {e}")

    filesystem_customers = config_loader.list_customers()
    if filesystem_customers:
        log.info(f"Filesystem customers: {', '.join(filesystem_customers)}")

    if not hk_agent.API_KEY:
        log.error("OPENROUTER_API_KEY not set!")
        sys.exit(1)

    log.info("Pre-loading Whisper model...")
    transcriber.get_model()
    log.info("Whisper model loaded.")

    log.info(f"Starting platform webhook server on {args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()