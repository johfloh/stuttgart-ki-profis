"""
Handwerker-KI Agent Core
The main subagent that orchestrates the quote generation pipeline:

1. Receive input (text from voice transcription or direct text)
2. Parse with Gemini to extract work items
3. Match items against the handyman's price table
4. Generate professional PDF
5. Return the result
"""

import os
import json
import sys
import urllib.request
from pathlib import Path

from . import config_loader
from . import price_table as pt
from . import pdf_generator

# ── Config ───────────────────────────────────────────────────────────
API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
if not API_KEY:
    env_paths = [
        os.path.expanduser("~/.hermes/.env"),
        os.path.expanduser("~/.env"),
        ".env",
    ]
    for ep in env_paths:
        if os.path.exists(ep):
            with open(ep) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("OPENROUTER_API_KEY=") and not line.startswith("#"):
                        API_KEY = line.split("=", 1)[1].strip().strip("\"'")
                        break
            if API_KEY:
                break

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "google/gemini-3.1-flash-lite"  # cost-optimized for quotes
# ──────────────────────────────────────────────────────────────────────


def process_request(
    user_input: str,
    customer_name: str,
    output_dir: str | None = None,
) -> dict:
    """
    Process a handyman's request and generate a quote.

    Args:
        user_input: Free text or transcribed voice note from the handyman
        customer_name: The customer (handyman) identifier
        output_dir: Override output directory

    Returns:
        dict with keys: pdf_path, quote_number, data (the structured quote data)
    """
    # 1. Load customer config
    config = config_loader.load_config(customer_name)
    price_table = config_loader.load_price_table(customer_name)

    # 2. Parse input with Gemini
    extracted = _llm_parse(user_input, config, price_table)
    if not extracted:
        return {"error": "Konnte Eingabe nicht verarbeiten.", "data": None}

    # 3. Match against price table
    matched_items = pt.match_items(extracted.get("positionen", []), price_table)

    # 4. Build quote data
    quote_data = {
        "kunde": extracted.get("kunde", {"name": "Kunde", "strasse": "", "plz_ort": ""}),
        "positionen": matched_items,
        "rabatt_prozent": extracted.get("rabatt_prozent", 0.0),
        "zahlungsziel_tage": extracted.get("zahlungsziel_tage", 14),
        "gueltig_bis_tage": extracted.get("gueltig_bis_tage", 30),
        "betreff": extracted.get("betreff", "Angebot ueber Handwerksleistungen"),
        "zusatztext": extracted.get("zusatztext", ""),
    }

    # 5. Generate PDF
    nummer = pdf_generator.quote_number(customer_name)
    pdf_path = pdf_generator.generate_pdf(quote_data, nummer, config, output_dir)

    # 6. Calculate summary
    netto = sum(
        p["menge"] * p["einzelpreis_netto"]
        for p in quote_data["positionen"]
    )
    rabatt_betrag = round(netto * quote_data["rabatt_prozent"] / 100, 2)
    brutto = round((netto - rabatt_betrag) * 1.19, 2)

    # Count matched vs unmatched items
    matched_count = sum(1 for p in matched_items if p.get("match_source") == "price_table")
    estimated_count = sum(1 for p in matched_items if p.get("match_source") != "price_table")

    return {
        "pdf_path": pdf_path,
        "quote_number": nummer,
        "netto": netto,
        "brutto": brutto,
        "matched_items": matched_count,
        "estimated_items": estimated_count,
        "data": quote_data,
    }


def _llm_parse(
    user_input: str,
    config: dict,
    price_table: dict,
) -> dict | None:
    """
    Use Gemini to parse the handyman's free-text into structured quote data.
    The prompt includes the price table so Gemini can fill in accurate prices.
    """
    # Build a compact price table summary for the prompt
    services = price_table.get("standard_services", [])
    price_list_str = "\n".join(
        f"  - {s['description']}: {s['price']:.2f} EUR/{s['unit']}"
        for s in services
    ) if services else "  (Keine Preisliste konfiguriert)"

    prompt = f"""Du bist ein Angebots-Assistent fuer einen deutschen Handwerksbetrieb.

FIRMENNAME: {config.get('company', {}).get('name', 'Unbekannt')}

PREISLISTE des Handwerkers (VERWENDE DIESE PREISE):
{price_list_str}
Stundensatz: {price_table.get('hourly_rate', 0):.2f} EUR/h

Extrahiere aus dem folgenden Kunden-Input ein strukturiertes Angebot.
WICHTIG: Verwende die Preise aus der Preisliste. Wenn etwas nicht in der Preisliste steht,
schaetze einen marktueblichen Preis und kennzeichne die Position nicht als "lt. Preisliste".

Bei Stundenarbeiten: nimm den Stundensatz aus der Preisliste * Anzahl Stunden.

Gib NUR JSON zurueck, genau dieses Schema:
{{
    "kunde": {{
        "name": "",
        "strasse": "",
        "plz_ort": ""
    }},
    "betreff": "Angebot ueber ...",
    "positionen": [
        {{
            "beschreibung": "",
            "menge": 1,
            "einheit": "h",
            "einzelpreis_netto": 0.0
        }}
    ],
    "rabatt_prozent": 0.0,
    "zahlungsziel_tage": 14,
    "gueltig_bis_tage": 30,
    "zusatztext": ""
}}

Kunden-Input:
---
{user_input}
---"""

    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}]
    }).encode()

    req = urllib.request.Request(
        API_URL, data=payload,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://stuttgart-ki-profis.de",
        }
    )

    try:
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"].strip()
        # Strip markdown code blocks
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(content)
    except Exception as e:
        print(f"LLM parse error: {e}", file=sys.stderr)
        return None


# ── CLI entry point ─────────────────────────────────────────────────
def main():
    """Direct CLI usage: python -m agent.agent <customer> <input text>"""
    if len(sys.argv) < 3:
        customers = config_loader.list_customers()
        print("Usage: python -m agent.agent <customer_name> <input text>")
        print(f"Available customers: {', '.join(customers) if customers else '(none configured)'}")
        sys.exit(1)

    customer = sys.argv[1]
    text = " ".join(sys.argv[2:])

    # Verify customer exists
    if customer not in config_loader.list_customers():
        print(f"Fehler: Kunde '{customer}' nicht gefunden.")
        print(f"Verfuegbar: {', '.join(config_loader.list_customers())}")
        sys.exit(1)

    result = process_request(text, customer)

    if "error" in result:
        print(f"Fehler: {result['error']}")
        sys.exit(1)

    print(f"\n  Angebot erstellt!")
    print(f"  Nummer:      {result['quote_number']}")
    print(f"  Kunde:       {result['data']['kunde']['name']}")
    print(f"  Netto:       {result['netto']:.2f} EUR")
    print(f"  Brutto:      {result['brutto']:.2f} EUR")
    print(f"  Aus Preisliste: {result['matched_items']} Positionen")
    print(f"  Aus Schaetzung: {result['estimated_items']} Positionen")
    print(f"  PDF:         {result['pdf_path']}")


if __name__ == "__main__":
    main()