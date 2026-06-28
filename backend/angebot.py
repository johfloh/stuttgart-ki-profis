#!/usr/bin/env python3
"""
KI-Angebots-Assistent fuer Handwerker
MVP: Generiert professionelle PDF-Angebote aus Freitext-Eingabe
"""

import os, json, sys, textwrap
from datetime import datetime, date
from fpdf import FPDF

# ── Config ───────────────────────────────────────────────────────────
# API-Key: zuerst env, dann .env Datei
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
MODEL = "google/gemini-2.0-flash-001"
FIRMA = {
    "name": "[IHR FIRMENNAME]",
    "strasse": "[STRASSE]",
    "plz_ort": "[PLZ ORT]",
    "tel": "[TELEFON]",
    "mail": "[EMAIL]",
    "steuer": "DE[STEUERNUMMER]",
    "geschaeftsfuehrer": "[GESCHAEFTSFUEHRER]",
}
# ──────────────────────────────────────────────────────────────────────


def llm_parse(eingabe_text: str) -> dict:
    """Freitext -> strukturierte Angebotsdaten per LLM"""
    prompt = f"""
Du bist ein Angebots-Assistent fuer deutsche Handwerksbetriebe.
Extrahiere aus dem folgenden Freitext ein strukturiertes Angebot.
Falls Informationen fehlen, setze leere Strings oder None.

Gib NUR JSON zurueck, genau dieses Schema:
{{
    "kunde": {{
        "name": "",
        "strasse": "",
        "plz_ort": ""
    }},
    "positionen": [
        {{
            "beschreibung": "",
            "menge": 1,
            "einheit": "Stk",
            "einzelpreis_netto": 0.0
        }}
    ],
    "rabatt_prozent": 0.0,
    "zahlungsziel_tage": 14,
    "liefertermin": "",
    "gueltig_bis_tage": 30,
    "zusatztext": ""
}}

Freitext des Kunden:
---
{eingabe_text}
---
"""
    import urllib.request
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}]
    }).encode()
    req = urllib.request.Request(
        API_URL, data=payload,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://stuttgart-ki-profis.de"
        }
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]
        # JSON aus Markdown extrahieren falls noetig
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(content)
    except Exception as e:
        print(f"Fehler bei KI-Anfrage: {e}")
        return None


def angebot_nummer() -> str:
    return f"A-{date.today().strftime('%Y%m%d')}-{datetime.now().strftime('%H%M')}"


def generate_pdf(daten: dict, nummer: str, out_path: str):
    """Erzeugt professionelles PDF-Angebot"""
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.add_page()

    # Schriftarten
    pdf.add_font("DejaVu", "", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    pdf.add_font("DejaVu", "B", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

    # ── Header ──
    pdf.set_font("DejaVu", "B", 20)
    pdf.set_text_color(25, 60, 120)
    pdf.cell(0, 12, "ANGEBOT", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 8)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 4, f"Nr: {nummer}  |  Datum: {date.today().strftime('%d.%m.%Y')}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    # ── Absender ──
    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(60, 60, 60)
    absender = f"{FIRMA['name']} | {FIRMA['strasse']} | {FIRMA['plz_ort']}"
    pdf.cell(0, 4, absender, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ── Trennlinie ──
    pdf.set_draw_color(25, 60, 120)
    pdf.set_line_width(0.5)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(6)

    # ── Kundenadresse ──
    k = daten["kunde"]
    pdf.set_font("DejaVu", "B", 11)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 6, k["name"], new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 10)
    if k.get("strasse"):
        pdf.cell(0, 5, k["strasse"], new_x="LMARGIN", new_y="NEXT")
    if k.get("plz_ort"):
        pdf.cell(0, 5, k["plz_ort"], new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # ── Betreff ──
    pdf.set_font("DejaVu", "B", 12)
    pdf.set_text_color(25, 60, 120)
    pdf.cell(0, 8, "Angebot ueber Handwerksleistungen", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ── Einleitung ──
    pdf.set_font("DejaVu", "", 10)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(0, 5, f"Sehr geehrte Damen und Herren,\nvielen Dank fuer Ihre Anfrage. Wir bieten Ihnen folgende Leistungen an:")
    pdf.ln(4)

    # ── Positionen Tabelle ──
    pdf.set_font("DejaVu", "B", 9)
    pdf.set_fill_color(25, 60, 120)
    pdf.set_text_color(255, 255, 255)
    col_w = [80, 14, 18, 38, 40]
    headers = ["Beschreibung", "Menge", "Einheit", "Einzelpreis", "Gesamtpreis"]
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 7, h, border=0, fill=True, align="C" if i > 0 else "L")
    pdf.ln()

    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(40, 40, 40)
    fill = False
    netto_summe = 0.0
    for pos in daten["positionen"]:
        menge = pos.get("menge", 1)
        ep = pos.get("einzelpreis_netto", 0.0)
        gp = round(menge * ep, 2)
        netto_summe += gp
        beschreibung = pos.get("beschreibung", "")
        pdf.set_fill_color(240, 244, 250)
        row_h = 6

        # Beschreibung umbrechen falls zu lang
        pdf.set_font("DejaVu", "", 9)
        x_start = pdf.get_x()
        y_start = pdf.get_y()
        pdf.multi_cell(col_w[0], 5, beschreibung, border=0, fill=fill)
        y_end = pdf.get_y()
        row_h = max(row_h, y_end - y_start)

        # Rest der Spalten
        pdf.set_xy(x_start + col_w[0], y_start)
        pdf.cell(col_w[1], row_h, str(menge), border=0, fill=fill, align="C")
        pdf.cell(col_w[2], row_h, pos.get("einheit", "Stk"), border=0, fill=fill, align="C")
        pdf.cell(col_w[3], row_h, f"{ep:.2f} EUR", border=0, fill=fill, align="R")
        pdf.cell(col_w[4], row_h, f"{gp:.2f} EUR", border=0, fill=fill, align="R")
        pdf.set_y(y_start + row_h)
        fill = not fill

    pdf.ln(2)

    # ── Summen ──
    rabatt = daten.get("rabatt_prozent", 0.0)
    rabatt_betrag = round(netto_summe * rabatt / 100, 2)
    netto_nach_rabatt = netto_summe - rabatt_betrag
    mwst = round(netto_nach_rabatt * 0.19, 2)
    brutto = round(netto_nach_rabatt + mwst, 2)

    pdf.set_font("DejaVu", "", 10)
    right_x = 190
    labels = [
        ("Nettosumme:", f"{netto_summe:.2f} EUR"),
    ]
    if rabatt > 0:
        labels.append((f"Rabatt ({rabatt:.0f}%):", f"-{rabatt_betrag:.2f} EUR"))
        labels.append(("Zwischensumme:", f"{netto_nach_rabatt:.2f} EUR"))
    labels += [
        ("zzgl. 19% MwSt.:", f"{mwst:.2f} EUR"),
        ("", ""),
    ]

    for label, wert in labels:
        if label == "":
            pdf.set_font("DejaVu", "B", 13)
            pdf.set_text_color(25, 60, 120)
            pdf.cell(right_x - 50, 8, "GESAMTBETRAG:", align="R")
            pdf.cell(50, 8, f"{brutto:.2f} EUR", align="R")
            pdf.ln(8)
            pdf.set_font("DejaVu", "", 8)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(0, 4, "Der Gesamtbetrag versteht sich inklusive gesetzlicher Umsatzsteuer.", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(4)
            continue
        pdf.set_font("DejaVu", "", 10)
        pdf.set_text_color(60, 60, 60)
        pdf.cell(right_x - 50, 6, label, align="R")
        pdf.set_font("DejaVu", "B", 10)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(50, 6, wert, align="R")
        pdf.ln(6)

    pdf.ln(4)

    # ── Zahlungsbedingungen ──
    ziele = daten.get("zahlungsziel_tage", 14)
    gueltig = daten.get("gueltig_bis_tage", 30)
    pdf.set_font("DejaVu", "B", 10)
    pdf.set_text_color(25, 60, 120)
    pdf.cell(0, 6, "Zahlungsbedingungen", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(60, 60, 60)
    pdf.multi_cell(0, 5, f"- Zahlbar innerhalb von {ziele} Tagen nach Rechnungsdatum ohne Abzug\n- Dieses Angebot ist {gueltig} Tage ab Angebotsdatum gueltig\n- Es gelten unsere Allgemeinen Geschaeftsbedingungen (AGB)")
    pdf.ln(4)

    # ── Zusatztext ──
    if daten.get("zusatztext"):
        pdf.set_font("DejaVu", "B", 10)
        pdf.set_text_color(25, 60, 120)
        pdf.cell(0, 6, "Anmerkungen", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("DejaVu", "", 9)
        pdf.set_text_color(60, 60, 60)
        pdf.multi_cell(0, 5, daten["zusatztext"])
        pdf.ln(4)

    # ── Footer ──
    pdf.set_y(-30)
    pdf.set_draw_color(200, 200, 200)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)
    pdf.set_font("DejaVu", "", 7)
    pdf.set_text_color(130, 130, 130)
    footer = f"{FIRMA['name']} | {FIRMA['strasse']} | {FIRMA['plz_ort']} | Tel: {FIRMA['tel']} | {FIRMA['mail']}"
    pdf.cell(0, 3, footer, align="C")

    pdf.output(out_path)
    return out_path


def interactive_mode():
    print("\n" + "=" * 60)
    print("  KI-Angebots-Assistent fuer Handwerker (MVP)")
    print("=" * 60)
    print("\nDu kannst entweder:")
    print("  1) Freitext eingeben (z.B. 'Kunde Mueller, Heizung einbauen...')")
    print("  2) Schritt fuer Schritt ausfuellen")
    print()
    modus = input("Modus (1 oder 2, Default=1): ").strip() or "1"

    if modus == "1":
        print("\nBeschreibe den Auftrag in Freitext:")
        print("(z.B.: 'Kunde Mueller, Hauptstr. 12, 70173 Stuttgart, neue Gasheizung Vaillant inkl. Montage, 8500 Euro Material, 12 Stunden Arbeit um 85 Euro/h')\n")
        eingabe = input("> ").strip()
        if not eingabe:
            print("Keine Eingabe. Abbruch.")
            return

        print("\n Verarbeite Eingabe mit KI...")
        daten = llm_parse(eingabe)
        if not daten:
            print("Konnte Eingabe nicht verarbeiten. Bitte Schritt-fuer-Schritt-Modus probieren.")
            return
    else:
        daten = {
            "kunde": {
                "name": input("Kundenname: ").strip(),
                "strasse": input("Strasse: ").strip(),
                "plz_ort": input("PLZ Ort: ").strip(),
            },
            "positionen": [],
            "rabatt_prozent": 0.0,
            "zahlungsziel_tage": 14,
            "gueltig_bis_tage": 30,
            "zusatztext": "",
        }
        print("\nPositionen (leere Beschreibung = fertig):")
        while True:
            beschreibung = input(f"  Beschreibung ({len(daten['positionen'])+1}): ").strip()
            if not beschreibung:
                break
            menge = input("  Menge (Default 1): ").strip() or "1"
            einheit = input("  Einheit (Default Stk): ").strip() or "Stk"
            ep = input("  Einzelpreis netto (EUR): ").strip()
            daten["positionen"].append({
                "beschreibung": beschreibung,
                "menge": float(menge) if "." in menge else int(menge),
                "einheit": einheit,
                "einzelpreis_netto": float(ep.replace(",", ".")) if ep else 0.0,
            })
        rabatt = input("\nRabatt in % (Default 0): ").strip()
        if rabatt:
            daten["rabatt_prozent"] = float(rabatt.replace(",", "."))

    # Zusammenfassung anzeigen
    print("\n" + "-" * 60)
    print("  ANGEBOT - ZUSAMMENFASSUNG")
    print("-" * 60)
    k = daten["kunde"]
    print(f"  Kunde:     {k['name']}")
    if k.get("strasse"):
        print(f"  Adresse:   {k['strasse']}, {k.get('plz_ort', '')}")
    print(f"  Positionen: {len(daten['positionen'])}")
    netto = sum(p["menge"] * p["einzelpreis_netto"] for p in daten["positionen"])
    print(f"  Netto:     {netto:.2f} EUR")
    print(f"  Brutto:    {netto * 1.19:.2f} EUR")
    print("-" * 60)

    ok = input("\nPDF erzeugen? (Enter=ja, n=nein): ").strip().lower()
    if ok == "n":
        print("Abgebrochen.")
        return

    nummer = angebot_nummer()
    out_dir = os.path.expanduser("~/angebote")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"angebot-{nummer}.pdf")
    generate_pdf(daten, nummer, out_path)

    print(f"\n PDF erzeugt: {out_path}")
    print(f"  Angebots-Nr: {nummer}")
    print()

    # Angebotsdaten speichern
    json_path = os.path.join(out_dir, f"angebot-{nummer}.json")
    with open(json_path, "w") as f:
        json.dump({"nummer": nummer, "datum": str(date.today()), "daten": daten}, f, indent=2, ensure_ascii=False)
    print(f"  Daten: {json_path}")


if __name__ == "__main__":
    # Quick-Mode mit CLI-Argument
    if len(sys.argv) > 1:
        eingabe = " ".join(sys.argv[1:])
        if API_KEY:
            daten = llm_parse(eingabe)
        else:
            print("Fehler: OPENROUTER_API_KEY nicht gesetzt.")
            sys.exit(1)
        if not daten:
            print("Fehler beim Parsen der Eingabe.")
            sys.exit(1)
        nummer = angebot_nummer()
        out_dir = os.path.expanduser("~/angebote")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"angebot-{nummer}.pdf")
        generate_pdf(daten, nummer, out_path)
        print(f"PDF: {out_path}")
    else:
        interactive_mode()