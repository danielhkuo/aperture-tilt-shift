"""Build docs/ELEC549_report.pdf from docs/report.md.

    uv run python docs/build_report.py

Markdown subset: '#'/'##' headings, paragraphs, pipe tables, '![caption](path)'
figures, indented lines as centred equations, **bold**, *italic*, `code`,
x~sub~ and x^super^.
"""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = Path(__file__).parent
SRC, OUT = HERE / "report.md", HERE / "ELEC549_report.pdf"

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=14, spaceBefore=12, spaceAfter=5)
BODY = ParagraphStyle("B", parent=styles["Normal"], fontSize=10.5, leading=14, spaceAfter=6)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=9, leading=11.5, spaceAfter=0)
CELLB = ParagraphStyle("cellb", parent=CELL, fontName="Helvetica-Bold")
CAP = ParagraphStyle("cap", parent=BODY, fontSize=9, leading=11.5, textColor=colors.HexColor("#444444"), spaceBefore=3, spaceAfter=10)
TITLE = ParagraphStyle("T", parent=styles["Title"], fontSize=19, spaceAfter=4)
SUB = ParagraphStyle("S", parent=BODY, fontSize=11, textColor=colors.HexColor("#555555"), spaceAfter=12)
EQ = ParagraphStyle("eq", parent=BODY, alignment=1, fontName="Helvetica-Oblique")
WIDTH = letter[0] - 1.8 * inch


def inline(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*", r"<i>\1</i>", text)
    text = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", text)
    text = re.sub(r"~(.+?)~", r"<sub>\1</sub>", text)
    text = re.sub(r"\^(.+?)\^", r"<super>\1</super>", text)
    return text


def figure(caption: str, path: str):
    img = HERE / path
    w, h = PILImage.open(img).size
    width = WIDTH * (0.78 if h / w > 0.6 else 1.0)  # tall figures narrower, so they share a page with text
    return KeepTogether([Image(str(img), width=width, height=width * h / w, hAlign="CENTER"), Paragraph(inline(caption), CAP)])


def table(rows: list[list[str]]):
    ncol = len(rows[0])
    widths = [WIDTH / ncol] * ncol
    if ncol == 2:
        widths = [2.2 * inch, WIDTH - 2.2 * inch]
    elif ncol == 3:
        widths = [0.8 * inch, 1.6 * inch, WIDTH - 2.4 * inch]
    elif ncol == 4:
        widths = [0.6 * inch, 2.7 * inch, 1.0 * inch, WIDTH - 4.3 * inch]
    data = [[Paragraph(inline(c), CELLB) for c in rows[0]]] + [[Paragraph(inline(c), CELL) for c in r] for r in rows[1:]]
    t = Table(data, colWidths=widths, hAlign="LEFT")
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black), ("LINEBELOW", (0, -1), (-1, -1), 0.4, colors.grey),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return [t, Spacer(1, 8)]


def parse(md: str):
    story, para, rows, first_heading = [], [], [], True

    def flush():
        nonlocal para, rows
        if para:
            story.append(Paragraph(inline(" ".join(para)), BODY))
            para = []
        if rows:
            story.extend(table(rows))
            rows = []

    for line in md.splitlines():
        if line.startswith("# "):
            flush()
            story.append(Paragraph(inline(line[2:]), TITLE))
        elif line.startswith("## "):
            flush()
            story.append(Paragraph(inline(line[3:]), H1))
        elif m := re.match(r"!\[(.*)\]\((.*)\)", line):
            flush()
            story.append(figure(m.group(1), m.group(2)))
        elif line.startswith("|"):
            if para:
                flush()
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not all(re.fullmatch(r"-+", c) for c in cells):
                rows.append(cells)
        elif re.match(r"\d+\. ", line):
            flush()
            story.append(Paragraph(inline(line), ParagraphStyle("li", parent=BODY, leftIndent=18, firstLineIndent=-18)))
        elif line.startswith("    "):
            flush()
            story.append(Paragraph(inline(line.strip()), EQ))
        elif not line.strip():
            flush()
        else:
            if first_heading and story and isinstance(story[-1], Paragraph) and story[-1].style is TITLE:
                story.append(Paragraph(inline(line), SUB))
                first_heading = False
            else:
                para.append(line.strip())
    flush()
    return story


def main():
    md = SRC.read_text()
    title = re.search(r"^# (.*)$", md, re.M).group(1)
    doc = SimpleDocTemplate(str(OUT), pagesize=letter, leftMargin=0.9 * inch, rightMargin=0.9 * inch,
                            topMargin=0.8 * inch, bottomMargin=0.8 * inch, title=title, author="Daniel Kuo")
    doc.build(parse(md))
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
