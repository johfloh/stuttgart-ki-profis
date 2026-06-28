"""
Professional PDF quote generator with template integration.
Generates A4 PDFs matching the handyman's branding (logo, colors, etc.)
"""

import os
import json
from datetime import date, datetime
from pathlib import Path
from fpdf import FPDF

DEJA_VU = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
DEJA_VU_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def quote_number(customer_name: str = "") -> str:
    """Generate a unique quote number."""
    prefix = customer_name[:3].upper() if customer_name else "A"
    return f"{prefix}-{date.today().strftime('%Y%m%d')}-{datetime.now().strftime('%H%M')}"


def generate_pdf(
    daten: dict,
    nummer: str,
    company_config: dict,
    output_dir: str | None = None,
) -> str:
    """
    Generate a professional PDF quote.

    Args:
        daten: Quote data dict with kunde, positionen, rabatt_prozent, etc.
        nummer: Quote number string
        company_config: Handyman's company configuration
        output_dir: Override output directory (default: ~/angebote/)

    Returns:
        Path to generated PDF
    """
    cfg = company_config
    firma = cfg.get("company", {})

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.add_page()

    # Fonts
    pdf.add_font("DejaVu", "", DEJA_VU)
    pdf.add_font("DejaVu", "B", DEJA_VU_BOLD)

    # Colors from config or defaults
    primary_color = cfg.get("colors", {}).get("primary", [25, 60, 120])
    secondary_color = cfg.get("colors", {}).get("secondary", [100, 100, 100])

    # ── Header ──
    logo_path = cfg.get("logo_path")
    if logo_path and os.path.exists(logo_path):
        pdf.image(logo_path, x=10, y=10, w=35)

    pdf.set_font("DejaVu", "B", 20)
    pdf.set_text_color(*primary_color)
    if logo_path:
        pdf.set_xy(50, 10)

    title_y = 10 if not logo_path else 12
    pdf.set_xy(10, title_y)
    pdf.cell(0, 12, "ANGEBOT", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("DejaVu", "", 8)
    pdf.set_text_color(*secondary_color)
    pdf.cell(0, 4, f"Nr: {nummer}  |  Datum: {date.today().strftime('%d.%m.%Y')}",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    # ── Absender ──
    if logo_path:
        pdf.set_y(max(pdf.get_y(), 30))
    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(60, 60, 60)
    addr = firma
    absender = f"{addr.get('name', '')} | {addr.get('strasse', '')} | {addr.get('plz_ort', '')}"
    pdf.cell(0, 4, absender, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ── Trennlinie ──
    pdf.set_draw_color(*primary_color)
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
    betreff = daten.get("betreff", "Angebot ueber Handwerksleistungen")
    pdf.set_font("DejaVu", "B", 12)
    pdf.set_text_color(*primary_color)
    pdf.cell(0, 8, betreff, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ── Einleitung ──
    pdf.set_font("DejaVu", "", 10)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(0, 5,
        f"Sehr geehrte Damen und Herren,\n"
        f"vielen Dank fuer Ihre Anfrage. Wir bieten Ihnen folgende Leistungen an:")
    pdf.ln(4)

    # ── Positionen Tabelle ──
    pdf.set_font("DejaVu", "B", 9)
    pdf.set_fill_color(*primary_color)
    pdf.set_text_color(255, 255, 255)

    col_w = [80, 14, 18, 38, 40]
    headers = ["Beschreibung", "Menge", "Einheit", "Einzelpreis", "Gesamtpreis"]
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 7, h, border=0, fill=True, align="C" if i > 0 else "L")
    pdf.ln()

    # ── Tabellenzeilen ──
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

        pdf.set_font("DejaVu", "", 9)
        x_start = pdf.get_x()
        y_start = pdf.get_y()
        pdf.multi_cell(col_w[0], 5, beschreibung, border=0, fill=fill)
        y_end = pdf.get_y()
        row_h = max(row_h, y_end - y_start)

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

    right_x = 190
    labels = []
    labels.append(("Nettosumme:", f"{netto_summe:.2f} EUR"))
    if rabatt > 0:
        labels.append((f"Rabatt ({rabatt:.0f}%):", f"-{rabatt_betrag:.2f} EUR"))
        labels.append(("Zwischensumme:", f"{netto_nach_rabatt:.2f} EUR"))
    labels.append(("zzgl. 19% MwSt.:", f"{mwst:.2f} EUR"))

    for label, wert in labels:
        pdf.set_font("DejaVu", "", 10)
        pdf.set_text_color(60, 60, 60)
        pdf.cell(right_x - 50, 6, label, align="R")
        pdf.set_font("DejaVu", "B", 10)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(50, 6, wert, align="R")
        pdf.ln(6)

    # Gesamtbetrag
    pdf.set_font("DejaVu", "B", 13)
    pdf.set_text_color(*primary_color)
    pdf.cell(right_x - 50, 8, "GESAMTBETRAG:", align="R")
    pdf.cell(50, 8, f"{brutto:.2f} EUR", align="R")
    pdf.ln(8)
    pdf.set_font("DejaVu", "", 8)
    pdf.set_text_color(*secondary_color)
    pdf.cell(0, 4,
        "Der Gesamtbetrag versteht sich inklusive gesetzlicher Umsatzsteuer.",
        new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ── Zahlungsbedingungen ──
    ziele = daten.get("zahlungsziel_tage", 14)
    gueltig = daten.get("gueltig_bis_tage", 30)
    pdf.set_font("DejaVu", "B", 10)
    pdf.set_text_color(*primary_color)
    pdf.cell(0, 6, "Zahlungsbedingungen", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(60, 60, 60)
    pdf.multi_cell(0, 5,
        f"- Zahlbar innerhalb von {ziele} Tagen nach Rechnungsdatum ohne Abzug\n"
        f"- Dieses Angebot ist {gueltig} Tage ab Angebotsdatum gueltig\n"
        f"- Es gelten unsere Allgemeinen Geschaeftsbedingungen (AGB)")
    pdf.ln(4)

    # ── Zusatztext ──
    if daten.get("zusatztext"):
        pdf.set_font("DejaVu", "B", 10)
        pdf.set_text_color(*primary_color)
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
    footer = (
        f"{addr.get('name', '')} | {addr.get('strasse', '')} | {addr.get('plz_ort', '')} | "
        f"Tel: {addr.get('tel', '')} | {addr.get('mail', '')}"
    )
    pdf.cell(0, 3, footer, align="C")

    # ── Output ──
    if output_dir is None:
        output_dir = os.path.expanduser("~/angebote")
    os.makedirs(output_dir, exist_ok=True)

    pdf_path = os.path.join(output_dir, f"angebot-{nummer}.pdf")
    pdf.output(pdf_path)

    # Save data JSON alongside
    json_path = os.path.join(output_dir, f"angebot-{nummer}.json")
    with open(json_path, "w") as f:
        json.dump({
            "nummer": nummer,
            "datum": str(date.today()),
            "daten": daten,
        }, f, indent=2, ensure_ascii=False)

    return pdf_path