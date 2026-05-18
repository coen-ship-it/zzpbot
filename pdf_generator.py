"""
pdf_generator.py — ZZPbot PDF Rapport Generator
Professionele A4 PDF met ReportLab: cover, readiness score,
tijdsverdeling, automatiseringskansen, ROI samenvatting en NextEnabler pagina.
"""

import io
import os
import qrcode
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, KeepTogether, HRFlowable,
)
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Circle
from reportlab.graphics import renderPDF
from reportlab.graphics.charts.barcharts import HorizontalBarChart

# ---------------------------------------------------------------------------
# Kleurenpalet
# ---------------------------------------------------------------------------

C_NAVY     = colors.HexColor("#0f172a")   # Donker navy — headers
C_BLUE     = colors.HexColor("#2563eb")   # Primair blauw
C_BLUE_LT  = colors.HexColor("#dbeafe")   # Licht blauw — achtergronden
C_ORANGE   = colors.HexColor("#ea580c")   # Accent oranje
C_ORANGE_LT= colors.HexColor("#fff7ed")   # Licht oranje
C_GREEN    = colors.HexColor("#15803d")   # Groen — positief
C_GREEN_LT = colors.HexColor("#dcfce7")   # Licht groen
C_AMBER    = colors.HexColor("#d97706")   # Amber — waarschuwing
C_AMBER_LT = colors.HexColor("#fef3c7")   # Licht amber
C_GRAY     = colors.HexColor("#64748b")   # Grijs tekst
C_GRAY_LT  = colors.HexColor("#f1f5f9")   # Licht grijs achtergrond
C_WHITE    = colors.white
C_BLACK    = colors.HexColor("#1e293b")

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm

# ---------------------------------------------------------------------------
# Stijlen
# ---------------------------------------------------------------------------

def get_styles():
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "H1", fontSize=22, fontName="Helvetica-Bold",
            textColor=C_NAVY, spaceAfter=6, spaceBefore=16,
        ),
        "h2": ParagraphStyle(
            "H2", fontSize=15, fontName="Helvetica-Bold",
            textColor=C_NAVY, spaceAfter=4, spaceBefore=12,
        ),
        "h3": ParagraphStyle(
            "H3", fontSize=11, fontName="Helvetica-Bold",
            textColor=C_NAVY, spaceAfter=3, spaceBefore=8,
        ),
        "body": ParagraphStyle(
            "Body", fontSize=10, fontName="Helvetica",
            textColor=C_BLACK, spaceAfter=4, leading=15,
        ),
        "small": ParagraphStyle(
            "Small", fontSize=8, fontName="Helvetica",
            textColor=C_GRAY, spaceAfter=2,
        ),
        "label": ParagraphStyle(
            "Label", fontSize=8, fontName="Helvetica-Bold",
            textColor=C_GRAY, spaceAfter=2, leading=10,
        ),
        "center": ParagraphStyle(
            "Center", fontSize=10, fontName="Helvetica",
            textColor=C_BLACK, alignment=TA_CENTER,
        ),
        "tag_laag": ParagraphStyle(
            "TagLaag", fontSize=8, fontName="Helvetica-Bold",
            textColor=C_GREEN, backColor=C_GREEN_LT,
            borderPadding=3, alignment=TA_CENTER,
        ),
        "quote": ParagraphStyle(
            "Quote", fontSize=10, fontName="Helvetica-Oblique",
            textColor=C_GRAY, leftIndent=12, spaceAfter=6,
        ),
        "cover_title": ParagraphStyle(
            "CoverTitle", fontSize=32, fontName="Helvetica-Bold",
            textColor=C_WHITE, alignment=TA_CENTER, leading=38,
        ),
        "cover_sub": ParagraphStyle(
            "CoverSub", fontSize=14, fontName="Helvetica",
            textColor=colors.HexColor("#93c5fd"), alignment=TA_CENTER,
        ),
    }


# ---------------------------------------------------------------------------
# Paginanummering
# ---------------------------------------------------------------------------

def add_page_number(canvas, doc):
    """Footer met paginanummer op elke pagina (behalve cover)."""
    if doc.page == 1:
        return
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(C_GRAY)
    canvas.drawString(MARGIN, 12 * mm, "ZZPbot — AI Automatisering Scan Rapport")
    canvas.drawRightString(PAGE_W - MARGIN, 12 * mm, f"Pagina {doc.page}")
    # Horizontale lijn
    canvas.setStrokeColor(C_GRAY_LT)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, 15 * mm, PAGE_W - MARGIN, 15 * mm)
    canvas.restoreState()


# ---------------------------------------------------------------------------
# Helper: Score kleur
# ---------------------------------------------------------------------------

def score_color(score: int) -> colors.Color:
    if score >= 75:
        return C_GREEN
    elif score >= 50:
        return C_AMBER
    return colors.HexColor("#dc2626")


def effort_color(effort: str) -> colors.Color:
    return {"Laag": C_GREEN, "Middel": C_AMBER, "Hoog": colors.HexColor("#dc2626")}.get(effort, C_GRAY)


def effort_bg(effort: str) -> colors.Color:
    return {"Laag": C_GREEN_LT, "Middel": C_AMBER_LT, "Hoog": colors.HexColor("#fee2e2")}.get(effort, C_GRAY_LT)


# ---------------------------------------------------------------------------
# QR Code genereren
# ---------------------------------------------------------------------------

def make_qr_image(url: str, size_mm: float = 50) -> Image:
    """Genereer een QR-code als ReportLab Image object."""
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    size = size_mm * mm
    return Image(buf, width=size, height=size)


# ---------------------------------------------------------------------------
# Cover pagina
# ---------------------------------------------------------------------------

def build_cover(styles: dict, profile: dict) -> list:
    """Bouw de coverpagina op."""
    naam = profile.get("naam", "Onbekend")
    bedrijf = profile.get("bedrijfstype", "")
    datum = datetime.now().strftime("%-d %B %Y")

    # Blauwe achtergrondrechthoek via tabel
    cover_table = Table(
        [[Paragraph("ZZPbot", ParagraphStyle(
            "Brand", fontSize=14, fontName="Helvetica-Bold",
            textColor=colors.HexColor("#93c5fd"), alignment=TA_CENTER,
        ))]],
        colWidths=[PAGE_W - 2 * MARGIN],
        rowHeights=[10 * mm],
    )
    cover_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_BLUE),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))

    elements = [
        Spacer(1, 30 * mm),
        cover_table,
        Spacer(1, 25 * mm),
    ]

    # Grote titel in donkere box
    title_block = Table(
        [[
            Paragraph("AI Automatisering<br/>Scan Rapport", ParagraphStyle(
                "CT", fontSize=28, fontName="Helvetica-Bold",
                textColor=C_WHITE, alignment=TA_CENTER, leading=36,
            ))
        ]],
        colWidths=[PAGE_W - 2 * MARGIN],
        rowHeights=[60 * mm],
    )
    title_block.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 15),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 15),
        ("ROUNDEDCORNERS", [6]),
    ]))
    elements.append(title_block)
    elements.append(Spacer(1, 20 * mm))

    # Klantinfo
    client_block = Table(
        [
            [Paragraph(naam, ParagraphStyle(
                "CN", fontSize=20, fontName="Helvetica-Bold",
                textColor=C_NAVY, alignment=TA_CENTER,
            ))],
            [Paragraph(bedrijf, ParagraphStyle(
                "CB", fontSize=12, fontName="Helvetica",
                textColor=C_GRAY, alignment=TA_CENTER,
            ))],
            [Spacer(1, 4 * mm)],
            [Paragraph(datum, ParagraphStyle(
                "CD", fontSize=10, fontName="Helvetica",
                textColor=C_GRAY, alignment=TA_CENTER,
            ))],
        ],
        colWidths=[PAGE_W - 2 * MARGIN],
    )
    client_block.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_GRAY_LT),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("ROUNDEDCORNERS", [6]),
    ]))
    elements.append(client_block)
    elements.append(Spacer(1, 40 * mm))

    elements.append(Paragraph(
        "Dit rapport is vertrouwelijk en uitsluitend bestemd voor de genoemde ondernemer.",
        ParagraphStyle("Conf", fontSize=8, fontName="Helvetica-Oblique",
                       textColor=C_GRAY, alignment=TA_CENTER),
    ))
    elements.append(PageBreak())
    return elements


# ---------------------------------------------------------------------------
# Readiness Score pagina
# ---------------------------------------------------------------------------

def draw_score_badge(score: int) -> Drawing:
    """Teken een grote scorebadge als SVG-achtige Drawing."""
    d = Drawing(80 * mm, 80 * mm)
    cx, cy, r = 40 * mm, 40 * mm, 35 * mm
    color = score_color(score)

    # Achtergrondcirkel
    d.add(Circle(cx, cy, r, fillColor=C_GRAY_LT, strokeColor=colors.HexColor("#e2e8f0"), strokeWidth=1))
    # Gekleurde rand (gesimuleerd als dikke rand)
    d.add(Circle(cx, cy, r, fillColor=None, strokeColor=color, strokeWidth=8))
    # Score getal
    d.add(String(cx, cy + 5 * mm, str(score),
                 fontName="Helvetica-Bold", fontSize=36,
                 fillColor=C_NAVY, textAnchor="middle"))
    d.add(String(cx, cy - 10 * mm, "/ 100",
                 fontName="Helvetica", fontSize=12,
                 fillColor=C_GRAY, textAnchor="middle"))
    return d


def draw_score_bar(label: str, score: int, bar_width: float = 100 * mm) -> Drawing:
    """Teken een horizontale scorebalk met label."""
    h = 22
    d = Drawing(bar_width + 80 * mm, h)
    color = score_color(score)

    # Label
    d.add(String(0, 6, label, fontName="Helvetica", fontSize=9, fillColor=C_BLACK))
    # Achtergrond balk
    x_start = 75 * mm
    d.add(Rect(x_start, 4, bar_width, 12, fillColor=C_GRAY_LT, strokeColor=None))
    # Gekleurde balk
    filled = bar_width * (score / 100)
    d.add(Rect(x_start, 4, filled, 12, fillColor=color, strokeColor=None))
    # Score tekst
    d.add(String(x_start + bar_width + 5, 6, str(score),
                 fontName="Helvetica-Bold", fontSize=9, fillColor=color))
    return d


def build_readiness_page(styles: dict, analysis: dict) -> list:
    """Bouw de AI Readiness Score pagina."""
    rs = analysis.get("readiness_score", {})
    totaal = rs.get("totaal", 0)
    elements = [
        Paragraph("AI Readiness Score", styles["h1"]),
        HRFlowable(width="100%", thickness=2, color=C_BLUE, spaceAfter=12),
        Spacer(1, 4 * mm),
    ]

    # Score badge + dimensies naast elkaar
    badge = draw_score_badge(totaal)
    bar_w = 95 * mm
    dim_drawing = Drawing(bar_w + 90 * mm, 120)
    dimensies = [
        ("Tijdsbesparing potentieel", rs.get("tijdsbesparing_potentieel", 0)),
        ("Procesherhaalbaarheid",    rs.get("procesherhaalbaarheid", 0)),
        ("Toolkoppeling",            rs.get("toolkoppeling", 0)),
        ("Datakwaliteit",            rs.get("datakwaliteit", 0)),
    ]
    for i, (lbl, val) in enumerate(dimensies):
        bar = draw_score_bar(lbl, val, bar_w)
        for item in bar.contents:
            item.y += (3 - i) * 28
            dim_drawing.add(item)

    score_table = Table(
        [[badge, dim_drawing]],
        colWidths=[85 * mm, PAGE_W - 2 * MARGIN - 85 * mm],
    )
    score_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    elements.append(score_table)
    elements.append(Spacer(1, 6 * mm))

    # Toelichting
    toelichting = rs.get("toelichting", "")
    if toelichting:
        toel_block = Table(
            [[Paragraph(toelichting, styles["body"])]],
            colWidths=[PAGE_W - 2 * MARGIN],
        )
        toel_block.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), C_BLUE_LT),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("ROUNDEDCORNERS", [6]),
        ]))
        elements.append(toel_block)

    elements.append(PageBreak())
    return elements


# ---------------------------------------------------------------------------
# Tijdsverdeling pagina
# ---------------------------------------------------------------------------

def build_time_distribution_page(styles: dict, analysis: dict, profile: dict) -> list:
    """Bouw de tijdsverdeling pagina met barchart."""
    by_cat = analysis.get("app_categorieen", {})
    total_hours = analysis.get("total_hours_tracked", 0)
    dc = analysis.get("data_completeness", {})

    elements = [
        Paragraph("Tijdsverdeling — afgelopen week", styles["h1"]),
        HRFlowable(width="100%", thickness=2, color=C_BLUE, spaceAfter=12),
        Paragraph(f"Totaal getrackt: <b>{total_hours} uur</b>", styles["body"]),
        Spacer(1, 4 * mm),
    ]

    if not by_cat:
        elements.append(Paragraph("Geen categoriedata beschikbaar.", styles["body"]))
        elements.append(PageBreak())
        return elements

    # Horizontale barChart
    items = [(cat, info["uren_per_week"]) for cat, info in list(by_cat.items())[:10]]
    cats, vals = zip(*items) if items else ([], [])
    max_val = max(vals) if vals else 1

    chart_h = max(len(cats) * 22, 100)
    d = Drawing(PAGE_W - 2 * MARGIN, chart_h + 20)

    bc = HorizontalBarChart()
    bc.x = 90 * mm
    bc.y = 10
    bc.width = PAGE_W - 2 * MARGIN - 100 * mm
    bc.height = chart_h
    bc.data = [list(vals)]
    bc.categoryAxis.categoryNames = list(cats)
    bc.categoryAxis.labels.fontName = "Helvetica"
    bc.categoryAxis.labels.fontSize = 9
    bc.categoryAxis.labels.dx = -5
    bc.categoryAxis.labels.textAnchor = "end"
    bc.valueAxis.valueMin = 0
    bc.valueAxis.valueMax = max_val * 1.1
    bc.valueAxis.labels.fontName = "Helvetica"
    bc.valueAxis.labels.fontSize = 8
    bc.bars[0].fillColor = C_BLUE
    bc.bars[0].strokeColor = None
    bc.barSpacing = 4
    bc.groupSpacing = 0
    d.add(bc)
    elements.append(d)
    elements.append(Spacer(1, 6 * mm))

    # Tabel
    table_data = [
        [
            Paragraph("<b>Categorie</b>", styles["label"]),
            Paragraph("<b>Uren/week</b>", styles["label"]),
            Paragraph("<b>%</b>", styles["label"]),
        ]
    ]
    row_colors = []
    for i, (cat, info) in enumerate(by_cat.items()):
        row_colors.append(("BACKGROUND", (0, i + 1), (-1, i + 1),
                           C_GRAY_LT if i % 2 == 0 else C_WHITE))
        table_data.append([
            Paragraph(cat, styles["body"]),
            Paragraph(str(info["uren_per_week"]), styles["body"]),
            Paragraph(f"{info['percentage']}%", styles["body"]),
        ])

    cat_table = Table(table_data, colWidths=[90 * mm, 40 * mm, 30 * mm])
    cat_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        *row_colors,
    ]))
    elements.append(cat_table)

    # Waarschuwingsblok
    pct_onbekend = dc.get("percentage_onbekend", 0)
    if dc.get("waarschuwing") or pct_onbekend > 10:
        elements.append(Spacer(1, 6 * mm))
        warn_block = Table(
            [[Paragraph(
                f"⚠️  <b>Let op:</b> {pct_onbekend}% van de activiteitstijd is ongeregistreerd "
                f"(apps buiten de bekende lijst). De resultaten zijn hierdoor mogelijk incompleet.",
                styles["body"],
            )]],
            colWidths=[PAGE_W - 2 * MARGIN],
        )
        warn_block.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), C_AMBER_LT),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ]))
        elements.append(warn_block)

    elements.append(PageBreak())
    return elements


# ---------------------------------------------------------------------------
# Automatiseringskansen
# ---------------------------------------------------------------------------

def build_opportunity_page(styles: dict, kans: dict, index: int, total: int) -> list:
    """Bouw één automatiseringskans pagina op."""
    elements = []

    titel = kans.get("titel", f"Kans {index}")
    effort = kans.get("implementatie_inspanning", "Middel")
    uren = kans.get("tijdsbesparing_uren_per_week", 0)
    euros = kans.get("euros_bespaard_per_maand", 0)
    terugverdien = kans.get("terugverdientijd", "")

    # Header met nummer
    header_text = f"Kans {index} van {total} — {titel}"
    header_block = Table(
        [[Paragraph(header_text, ParagraphStyle(
            "KansH", fontSize=14, fontName="Helvetica-Bold",
            textColor=C_WHITE,
        ))]],
        colWidths=[PAGE_W - 2 * MARGIN],
    )
    header_block.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("ROUNDEDCORNERS", [6]),
    ]))
    elements.append(header_block)
    elements.append(Spacer(1, 4 * mm))

    # Tags rij
    def make_tag(text: str, fg: colors.Color, bg: colors.Color) -> Table:
        t = Table([[Paragraph(text, ParagraphStyle(
            "Tag", fontSize=8, fontName="Helvetica-Bold",
            textColor=fg, alignment=TA_CENTER,
        ))]], colWidths=[45 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ROUNDEDCORNERS", [4]),
        ]))
        return t

    tags = Table(
        [[
            make_tag(f"💪 Inspanning: {effort}", effort_color(effort), effort_bg(effort)),
            make_tag(f"⏱ {uren} uur/week bespaard", C_BLUE, C_BLUE_LT),
            make_tag(f"💶 €{int(euros):,}/maand".replace(",", "."), C_GREEN, C_GREEN_LT),
            make_tag(f"⏰ Terugverdien: {terugverdien}", C_AMBER, C_AMBER_LT),
        ]],
        colWidths=[47 * mm, 47 * mm, 47 * mm, 47 * mm],
        hAlign="LEFT",
    )
    tags.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(tags)
    elements.append(Spacer(1, 5 * mm))

    # Beschrijving
    beschrijving = kans.get("beschrijving", "")
    if beschrijving:
        elements.append(Paragraph("Wat speelt er?", styles["h3"]))
        elements.append(Paragraph(beschrijving, styles["body"]))
        elements.append(Spacer(1, 3 * mm))

    # Bewijs
    bewijs = kans.get("bewijs", "")
    if bewijs:
        bewijs_block = Table(
            [[Paragraph(f"<i>📊 {bewijs}</i>", styles["quote"])]],
            colWidths=[PAGE_W - 2 * MARGIN],
        )
        bewijs_block.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), C_BLUE_LT),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ]))
        elements.append(Paragraph("Bewijs uit jouw data", styles["h3"]))
        elements.append(bewijs_block)
        elements.append(Spacer(1, 3 * mm))

    # Agent briefing
    briefing = kans.get("agent_briefing", {})
    if briefing:
        elements.append(Paragraph("Hoe werkt de AI-agent?", styles["h3"]))
        briefing_rows = [
            [Paragraph("<b>Input</b>", styles["label"]),
             Paragraph(briefing.get("input", ""), styles["body"])],
            [Paragraph("<b>Logica</b>", styles["label"]),
             Paragraph(briefing.get("logica", ""), styles["body"])],
            [Paragraph("<b>Output</b>", styles["label"]),
             Paragraph(briefing.get("output", ""), styles["body"])],
        ]
        briefing_table = Table(briefing_rows, colWidths=[30 * mm, PAGE_W - 2 * MARGIN - 30 * mm])
        briefing_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), C_GRAY_LT),
            ("BACKGROUND", (1, 0), (1, -1), C_WHITE),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        elements.append(briefing_table)
        elements.append(Spacer(1, 3 * mm))

    # ROI detail
    pct = kans.get("tijdsbesparing_percentage", 0)
    roi_rows = [
        [Paragraph("<b>Tijdsbesparing</b>", styles["label"]),
         Paragraph(f"{pct}% minder handmatig werk = {uren} uur/week", styles["body"])],
        [Paragraph("<b>Besparing/maand</b>", styles["label"]),
         Paragraph(f"€{int(euros):,}".replace(",", "."), ParagraphStyle(
             "ROIVal", fontSize=12, fontName="Helvetica-Bold", textColor=C_GREEN,
         ))],
        [Paragraph("<b>Terugverdientijd</b>", styles["label"]),
         Paragraph(terugverdien, styles["body"])],
    ]
    roi_table = Table(roi_rows, colWidths=[50 * mm, PAGE_W - 2 * MARGIN - 50 * mm])
    roi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_GREEN_LT),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bbf7d0")),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(Paragraph("ROI Overzicht", styles["h3"]))
    elements.append(roi_table)
    elements.append(PageBreak())
    return elements


# ---------------------------------------------------------------------------
# ROI Samenvatting
# ---------------------------------------------------------------------------

def build_roi_summary_page(styles: dict, analysis: dict, profile: dict) -> list:
    """Bouw de ROI samenvattingspagina."""
    roi = analysis.get("roi_samenvatting", {})
    kansen = analysis.get("kansen", [])

    uren_week = roi.get("totale_uren_bespaard_per_week", 0)
    euros_maand = roi.get("totale_euros_bespaard_per_maand", 0)
    euros_jaar = roi.get("totale_euros_bespaard_per_jaar", 0)
    eerste_stap = roi.get("aanbevolen_eerste_stap", "")

    elements = [
        Paragraph("Totale ROI Samenvatting", styles["h1"]),
        HRFlowable(width="100%", thickness=2, color=C_GREEN, spaceAfter=12),
        Spacer(1, 4 * mm),
    ]

    # Grote getallen
    kpi_data = [
        [
            Table([[
                Paragraph(f"{uren_week}", ParagraphStyle("KPI", fontSize=36, fontName="Helvetica-Bold",
                          textColor=C_BLUE, alignment=TA_CENTER)),
                Paragraph("uur/week<br/>bespaard", ParagraphStyle("KPIL", fontSize=10,
                          fontName="Helvetica", textColor=C_GRAY, alignment=TA_CENTER)),
            ]], colWidths=[75 * mm]),
            Table([[
                Paragraph(f"€{int(euros_maand):,}".replace(",", "."), ParagraphStyle("KPI2", fontSize=36, fontName="Helvetica-Bold",
                          textColor=C_GREEN, alignment=TA_CENTER)),
                Paragraph("per maand<br/>bespaard", ParagraphStyle("KPIL2", fontSize=10,
                          fontName="Helvetica", textColor=C_GRAY, alignment=TA_CENTER)),
            ]], colWidths=[75 * mm]),
            Table([[
                Paragraph(f"€{int(euros_jaar):,}".replace(",", "."), ParagraphStyle("KPI3", fontSize=28, fontName="Helvetica-Bold",
                          textColor=C_ORANGE, alignment=TA_CENTER)),
                Paragraph("per jaar<br/>bespaard", ParagraphStyle("KPIL3", fontSize=10,
                          fontName="Helvetica", textColor=C_GRAY, alignment=TA_CENTER)),
            ]], colWidths=[PAGE_W - 2 * MARGIN - 150 * mm]),
        ]
    ]
    kpi_table = Table(kpi_data, colWidths=[75 * mm, 75 * mm, PAGE_W - 2 * MARGIN - 150 * mm])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_GRAY_LT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 16),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
        ("LINEAFTER", (0, 0), (1, 0), 1, colors.HexColor("#e2e8f0")),
        ("ROUNDEDCORNERS", [8]),
    ]))
    elements.append(kpi_table)
    elements.append(Spacer(1, 8 * mm))

    # Overzichtstabel van kansen
    if kansen:
        elements.append(Paragraph("Overzicht automatiseringskansen", styles["h2"]))
        table_data = [[
            Paragraph("<b>Kans</b>", styles["label"]),
            Paragraph("<b>Tijdsbesparing</b>", styles["label"]),
            Paragraph("<b>€/maand</b>", styles["label"]),
            Paragraph("<b>Inspanning</b>", styles["label"]),
        ]]
        for i, kans in enumerate(kansen):
            table_data.append([
                Paragraph(kans.get("titel", f"Kans {i+1}"), styles["body"]),
                Paragraph(f"{kans.get('tijdsbesparing_uren_per_week', 0)} u/w", styles["body"]),
                Paragraph(f"€{int(kans.get('euros_bespaard_per_maand', 0)):,}".replace(",", "."), styles["body"]),
                Paragraph(kans.get("implementatie_inspanning", ""), styles["body"]),
            ])
        ov_table = Table(table_data, colWidths=[90 * mm, 40 * mm, 35 * mm, 30 * mm])
        ov_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_GRAY_LT]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        elements.append(ov_table)
        elements.append(Spacer(1, 8 * mm))

    # Eerste stap
    if eerste_stap:
        stap_block = Table(
            [[Paragraph(f"<b>🎯 Aanbevolen eerste stap:</b><br/>{eerste_stap}", styles["body"])]],
            colWidths=[PAGE_W - 2 * MARGIN],
        )
        stap_block.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), C_ORANGE_LT),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ("LEFTPADDING", (0, 0), (-1, -1), 16),
            ("RIGHTPADDING", (0, 0), (-1, -1), 16),
            ("ROUNDEDCORNERS", [6]),
        ]))
        elements.append(stap_block)

    elements.append(PageBreak())
    return elements


# ---------------------------------------------------------------------------
# NextEnabler pagina
# ---------------------------------------------------------------------------

def build_nextenabler_page(styles: dict, profile: dict) -> list:
    """Bouw de NextEnabler referral pagina met QR-code."""
    client_id = profile.get("client_id", "unknown")
    ne_url = os.getenv("NEXTENABLER_URL", "https://nextenabler.com/scan")
    url = f"{ne_url}?ref={client_id}"

    elements = []

    # Header blok
    header = Table(
        [[Paragraph("Klaar om te beginnen?", ParagraphStyle(
            "NEH", fontSize=26, fontName="Helvetica-Bold",
            textColor=C_WHITE, alignment=TA_CENTER,
        ))]],
        colWidths=[PAGE_W - 2 * MARGIN],
    )
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 18),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 18),
        ("ROUNDEDCORNERS", [8]),
    ]))
    elements.append(header)
    elements.append(Spacer(1, 10 * mm))

    # Body tekst
    body = Table(
        [[Paragraph(
            "NextEnabler bouwt de AI-automatiseringen die passen bij jouw werkwijze.<br/>"
            "Op basis van dit rapport weten we precies waar de winst zit.<br/><br/>"
            "<b>Plan een gratis kennismaking — we starten binnen een week.</b>",
            ParagraphStyle("NEB", fontSize=12, fontName="Helvetica",
                           textColor=C_BLACK, alignment=TA_CENTER, leading=18),
        )]],
        colWidths=[PAGE_W - 2 * MARGIN],
    )
    body.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    elements.append(body)
    elements.append(Spacer(1, 10 * mm))

    # QR code
    try:
        qr_img = make_qr_image(url, size_mm=55)
        qr_table = Table([[qr_img]], colWidths=[PAGE_W - 2 * MARGIN])
        qr_table.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        elements.append(qr_table)
    except Exception:
        pass

    elements.append(Spacer(1, 6 * mm))

    # URL
    elements.append(Paragraph(url, ParagraphStyle(
        "NEURL", fontSize=11, fontName="Helvetica-Bold",
        textColor=C_BLUE, alignment=TA_CENTER,
    )))
    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph(
        f"Jouw unieke code: <b>{client_id}</b>",
        ParagraphStyle("NEID", fontSize=9, fontName="Helvetica",
                       textColor=C_GRAY, alignment=TA_CENTER),
    ))
    elements.append(Spacer(1, 12 * mm))

    # Footer
    footer_block = Table(
        [[Paragraph(
            "NextEnabler • AI Automatisering voor Ondernemers • nextenabler.com",
            ParagraphStyle("NEF", fontSize=8, fontName="Helvetica",
                           textColor=C_GRAY, alignment=TA_CENTER),
        )]],
        colWidths=[PAGE_W - 2 * MARGIN],
    )
    footer_block.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_GRAY_LT),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(footer_block)
    return elements


# ---------------------------------------------------------------------------
# Hoofd generator functie
# ---------------------------------------------------------------------------

def generate_report(profile: dict, activity_data: dict, analysis: dict, output_path: str) -> str:
    """
    Genereer het volledige ZZPbot PDF-rapport.

    Args:
        profile:       Klantprofiel dict (uit profiles/{client_id}.json)
        activity_data: Activiteitsdata dict (geüpload door klant)
        analysis:      Analyseresultaat dict (uit analyzer.py)
        output_path:   Pad naar het te genereren PDF-bestand

    Returns:
        Pad naar het gegenereerde PDF-bestand
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=20 * mm,
        title=f"ZZPbot Rapport — {profile.get('naam', 'Klant')}",
        author="ZZPbot",
        subject="AI Automatisering Scan",
    )

    styles = get_styles()
    story = []

    # 1. Cover
    story += build_cover(styles, profile)

    # 2. Readiness Score
    story += build_readiness_page(styles, analysis)

    # 3. Tijdsverdeling
    story += build_time_distribution_page(styles, analysis, profile)

    # 4. Automatiseringskansen
    kansen = analysis.get("kansen", [])
    for i, kans in enumerate(kansen, start=1):
        story += build_opportunity_page(styles, kans, i, len(kansen))

    # 5. ROI Samenvatting
    story += build_roi_summary_page(styles, analysis, profile)

    # 6. NextEnabler
    story += build_nextenabler_page(styles, profile)

    doc.build(story, onLaterPages=add_page_number)
    return output_path
