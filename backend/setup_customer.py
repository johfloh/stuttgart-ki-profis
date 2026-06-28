#!/usr/bin/env python3
"""
Customer onboarding tool for Stuttgart KI Profis.
Sets up a new handyman customer with config and price table.

Usage:
  python -m agent.setup_customer malermeister-schmidt \
    --name "Malermeister Schmidt" \
    --strasse "Hauptstr 45" \
    --plz_ort "70199 Stuttgart" \
    --tel "+49 711 123456" \
    --mail "info@malermeister-schmidt.de" \
    --steuer "DE123456789" \
    --whatsapp "+49151123456789" \
    --stundensatz 55
"""

import sys
import os
import argparse
import yaml
from pathlib import Path
from shutil import copy2
from . import config_loader

AGENT_DIR = Path(__file__).parent


def setup_customer():
    parser = argparse.ArgumentParser(description="Neuen Handwerker-Kunden anlegen")
    parser.add_argument("name_id", help="Kurzname (z.B. malermeister-schmidt)")
    parser.add_argument("--display-name", help="Firmenname", default="")
    parser.add_argument("--strasse", default="")
    parser.add_argument("--plz_ort", default="")
    parser.add_argument("--tel", default="")
    parser.add_argument("--mail", default="")
    parser.add_argument("--steuer", default="")
    parser.add_argument("--geschaeftsfuehrer", default="")
    parser.add_argument("--whatsapp", default="", help="WhatsApp Business Nummer")
    parser.add_argument("--stundensatz", type=float, default=55.0)
    parser.add_argument("--logo", default="", help="Pfad zum Logo")
    parser.add_argument("--from-template", action="store_true",
                        help="Kopiere Template-Preisliste und configure")

    args = parser.parse_args()

    customer_dir = config_loader.CUSTOMERS_DIR / args.name_id
    if customer_dir.exists():
        print(f"Fehler: Kunde '{args.name_id}' existiert bereits in {customer_dir}")
        sys.exit(1)

    customer_dir.mkdir(parents=True)

    # Copy template price table if requested
    if args.from_template:
        template_path = AGENT_DIR / "templates" / "price_table.yaml"
        if template_path.exists():
            with open(template_path) as f:
                pt_data = yaml.safe_load(f)
            pt_data["hourly_rate"] = args.stundensatz
            with open(customer_dir / "price_table.yaml", "w") as f:
                yaml.dump(pt_data, f, default_flow_style=False, allow_unicode=True)
            print(f"  Preisliste aus Template kopiert (Stundensatz: {args.stundensatz:.2f} EUR/h)")
        else:
            # Write minimal price table
            pt_data = {
                "hourly_rate": args.stundensatz,
                "materials_markup": 1.15,
                "standard_services": [
                    {"description": "Arbeitsstunde", "price": args.stundensatz, "unit": "h"},
                    {"description": "Anfahrt pauschal (Stadtgebiet)", "price": 35.00, "unit": "pauschal"},
                    {"description": "Kleinmaterialpauschale", "price": 25.00, "unit": "pauschal"},
                ]
            }
            with open(customer_dir / "price_table.yaml", "w") as f:
                yaml.dump(pt_data, f, default_flow_style=False, allow_unicode=True)
            print(f"  Minimale Preisliste erstellt (Stundensatz: {args.stundensatz:.2f} EUR/h)")
    else:
        # Minimal price table
        pt_data = {
            "hourly_rate": args.stundensatz,
            "materials_markup": 1.15,
            "standard_services": [],
        }
        with open(customer_dir / "price_table.yaml", "w") as f:
            yaml.dump(pt_data, f, default_flow_style=False, allow_unicode=True)
        print(f"  Leere Preisliste erstellt (Stundensatz: {args.stundensatz:.2f} EUR/h)")
        print(f"  -> Bearbeite {customer_dir / 'price_table.yaml'} um Services hinzuzufuegen")

    # Write company config
    display = args.display_name or args.name_id.replace("-", " ").title()
    config = {
        "company": {
            "name": display,
            "strasse": args.strasse,
            "plz_ort": args.plz_ort,
            "tel": args.tel,
            "mail": args.mail,
            "steuer": args.steuer,
            "geschaeftsfuehrer": args.geschaeftsfuehrer,
        },
        "whatsapp": {
            "number": args.whatsapp,
        },
        "colors": {
            "primary": [25, 60, 120],
            "secondary": [100, 100, 100],
        },
        "logo_path": args.logo or "",
        "defaults": {
            "zahlungsziel_tage": 14,
            "gueltig_bis_tage": 30,
        },
    }

    with open(customer_dir / "config.yaml", "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

    print(f"\n  Kunde '{args.name_id}' angelegt!")
    print(f"    Verzeichnis: {customer_dir}")
    print(f"    Firmenname:  {display}")
    print(f"    WhatsApp:    {args.whatsapp or '(nicht gesetzt)'}")
    print(f"    Stundensatz: {args.stundensatz:.2f} EUR/h")
    print(f"\n  Bearbeite die Config: {customer_dir / 'config.yaml'}")
    print(f"  Bearbeite Preise:    {customer_dir / 'price_table.yaml'}")
    print(f"\n  Test: python -m agent.agent {args.name_id} \"Kunde Mueller, neue Steckdosen im Wohnzimmer\"")


if __name__ == "__main__":
    setup_customer()