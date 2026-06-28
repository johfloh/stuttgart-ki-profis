"""
Twilio WhatsApp webhook server.
Receives incoming WhatsApp messages (voice + text), routes them through
the Stuttgart KI Profis Agent, and sends the generated PDF back.

Usage:
  export TWILIO_ACCOUNT_SID=...
  export TWILIO_AUTH_TOKEN=...
  export AGENT_CUSTOMER=malermeister-schmidt  # default customer
  
  python -m agent.server [--port 8080]
"""

import os
import sys
import argparse
import tempfile
import logging

from flask import Flask, request, Response

from . import agent as hk_agent
from . import config_loader
from . import transcriber

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("hk-agent")

app = Flask(__name__)

# Twilio (lazy-imported to not crash if unavailable)
_twilio_client = None


def get_twilio():
    global _twilio_client
    if _twilio_client is None:
        from twilio.rest import Client
        sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        if not sid or not token:
            log.warning("TWILIO_ACCOUNT_SID/AUTH_TOKEN not set - cannot send replies")
            return None
        _twilio_client = Client(sid, token)
    return _twilio_client


@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    """Twilio incoming webhook for WhatsApp messages."""
    from_number = request.form.get("From", "")
    to_number = request.form.get("To", "")
    num_media = int(request.form.get("NumMedia", 0))
    body = request.form.get("Body", "")

    log.info(f"Message from {from_number}: {num_media} media, body={body[:80]}")

    # Determine which customer this number belongs to
    customer = resolve_customer(from_number, to_number)
    if not customer:
        log.warning(f"No customer configured for {from_number}")
        return twiml_response(f"Willkommen beim Handwerker-KI Angebotsassistenten. "
                              f"Leider ist Ihr Account noch nicht aktiviert. "
                              f"Bitte kontaktieren Sie Ihren Ansprechpartner.")

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
    log.info(f"Processing request for customer '{customer}': {user_input[:100]}")
    try:
        result = hk_agent.process_request(user_input, customer)
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

    # Send message with PDF via Twilio
    twilio = get_twilio()
    if twilio:
        try:
            # Send summary text
            twilio.messages.create(
                from_=to_number,
                to=from_number,
                body=summary,
            )
            # Send PDF as media
            twilio.messages.create(
                from_=to_number,
                to=from_number,
                body=f"Angebot {result['quote_number']}",
                media_url=[f"file://{pdf_path}"],  # Twilio needs public URL
            )
        except Exception as e:
            log.error(f"Failed to send Twilio message: {e}")
            # Twilio needs publicly-accessible URLs for media - so this won't work
            # with local files. We need a file server too.
            return twiml_response(
                f"{summary}\n\nPDF: {pdf_path}\n\n"
                f"(PDF konnte nicht direkt gesendet werden, liegt aber auf dem Server.)"
            )

    return twiml_response(summary)


def resolve_customer(from_number: str, to_number: str) -> str | None:
    """
    Resolve which customer/handyman this message belongs to.
    Uses mapping: from_number identifies the handyman.
    """
    # Check environment override
    override = os.environ.get("AGENT_CUSTOMER")
    if override:
        return override

    # Load customer configs and match by WhatsApp number
    for c in config_loader.list_customers():
        cfg = config_loader.load_config(c)
        wa = cfg.get("whatsapp", {}).get("number", "")
        if wa and (wa in from_number or from_number.endswith(wa)):
            return c

    return None


def twiml_response(message: str) -> str:
    """Generate TwiML response."""
    from twilio.twiml.messaging_response import MessagingResponse
    resp = MessagingResponse()
    resp.message(message)
    return str(resp)


@app.route("/health", methods=["GET"])
def health():
    return "OK", 200


def main():
    parser = argparse.ArgumentParser(description="Handwerker-KI WhatsApp Webhook")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    args = parser.parse_args()

    # Check config
    customers = config_loader.list_customers()
    if not customers:
        log.warning("No customers configured! Run: python -m agent.setup_customer")
    else:
        log.info(f"Configured customers: {', '.join(customers)}")

    # Verify API key
    if not hk_agent.API_KEY:
        log.error("OPENROUTER_API_KEY not set!")
        sys.exit(1)

    # Pre-load Whisper model
    log.info("Pre-loading Whisper model...")
    transcriber.get_model()
    log.info("Whisper model loaded.")

    log.info(f"Starting webhook server on {args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()