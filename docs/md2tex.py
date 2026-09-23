"""Convert docs/report.md to docs/report.tex (one-off; edit the .tex afterwards).

    uv run python docs/md2tex.py && cd docs && pdflatex report.tex
"""

from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).parent
SRC, OUT = HERE / "report.md", HERE / "report.tex"

PREAMBLE = r"""\documentclass[11pt]{article}
\usepackage[letterpaper,margin=1in]{geometry}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{textcomp}
\usepackage{lmodern}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{amsmath}
\usepackage{microtype}
\usepackage[hidelinks]{hyperref}
\usepackage{caption}
\captionsetup{font=small,labelfont=bf}
\setlength{\parskip}{4pt}
\graphicspath{{./}}

\title{%(title)s}
\author{Daniel Kuo \\ ELEC 549}
\date{%(date)s}

\begin{document}
\maketitle
"""

# Equations in the Markdown are written informally; give each its proper LaTeX form.
EQUATIONS = {
    "b = D · f · |1/z − 1/z~0~|  pixels.": r"b = D \, f \, \left| \frac{1}{z} - \frac{1}{z_0} \right| \quad \text{pixels.}",
    "H = K (R + t n^T^ / d) K^-1^": r"H = K \left( R + \frac{t\, n^{\mathsf T}}{d} \right) K^{-1}",
}


def esc(t: str) -> str:
    return "".join(p if i % 2 else _esc(p) for i, p in enumerate(re.split(r"(\x01.*?\x01)", t)))


def _esc(t: str) -> str:
    t = t.replace("\\", r"\textbackslash{}")
    for a, b in [("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"), ("_", r"\_"), ("~", r"\~{}"), ("^", r"\^{}")]:
        t = t.replace(a, b)
    return t


MATH = {  # informal expressions in the prose → proper inline math
    "f·t·|1/z − 1/z~0~|": r"$f\,t\,|1/z - 1/z_0|$",
    "D·f·|1/z − 1/z~0~|": r"$D\,f\,|1/z - 1/z_0|$",
    "D f |1/z − 1/z~0~|": r"$D\,f\,|1/z - 1/z_0|$",
    "f·t/z": r"$f\,t/z$",
    "t n^T^/d": r"$t\,n^{\mathsf T}/d$",
    "K^-1^": r"$K^{-1}$",
    "z~0~": r"$z_0$",
    "3×3": r"$3\times 3$",
}


def inline(t: str) -> str:
    for k, v in MATH.items():
        t = t.replace(k, "\x01" + v.replace("\\", "\x02") + "\x01")
    # protect markup before escaping
    t = re.sub(r"(\w)~(\w+)~", lambda m: f"{m.group(1)}\x00sub{m.group(2)}\x00", t)
    t = re.sub(r"(\w)\^(\S+?)\^", lambda m: f"{m.group(1)}\x00sup{m.group(2)}\x00", t)
    parts = re.split(r"(\*\*.+?\*\*|(?<!\*)\*(?!\*).+?\*|`.+?`|https?://\S+)", t)
    out = []
    for p in parts:
        if p.startswith("**"):
            out.append(r"\textbf{" + esc(p[2:-2]) + "}")
        elif p.startswith("*"):
            out.append(r"\emph{" + esc(p[1:-1]) + "}")
        elif p.startswith("`"):
            out.append(r"\texttt{" + esc(p[1:-1]) + "}")
        elif p.startswith("http"):
            url = p.rstrip(".,;)")
            out.append(r"\url{" + url + "}" + p[len(url):])
        else:
            out.append(esc(p))
    t = "".join(out)
    t = re.sub(r"\x00sub(\w+)\x00", lambda m: "$_{" + m.group(1) + "}$", t)
    t = re.sub(r"\x00sup(\S+?)\x00", lambda m: "$^{" + m.group(1) + "}$", t)
    t = t.replace("·", r"$\cdot$").replace("−", r"$-$").replace("×", r"$\times$").replace("°", r"$^\circ$")
    t = t.replace("→", r"$\rightarrow$").replace("–", "--").replace("—", "---")
    t = re.sub(r"\x01(.*?)\x01", lambda m: m.group(1).replace("\x02", "\\"), t)
    return t


def convert(md: str) -> str:
    lines = md.splitlines()
    title = lines[0][2:]
    date = re.search(r"· (\d+ \w+ \d{4})", lines[2]).group(1)
    body, para, rows, fig = [], [], [], 0

    def flush():
        nonlocal para, rows
        if para:
            body.append(inline(" ".join(para)) + "\n\n")
            para = []
        if rows:
            ncol = len(rows[0])
            spec = "p{0.28\\linewidth}p{0.66\\linewidth}" if ncol == 2 else "l" * ncol
            body.append("\\begin{center}\\small\n\\begin{tabular}{" + spec + "}\n\\toprule\n")
            body.append(" & ".join(r"\textbf{" + inline(c) + "}" for c in rows[0]) + " \\\\\n\\midrule\n")
            for r in rows[1:]:
                body.append(" & ".join(inline(c) for c in r) + " \\\\\n")
            body.append("\\bottomrule\n\\end{tabular}\n\\end{center}\n")
            rows = []

    for line in lines[3:]:
        if line.startswith("## "):
            flush()
            body.append("\n\\section{" + inline(re.sub(r"^\d+\. ", "", line[3:])) + "}\n")
        elif m := re.match(r"!\[(.*)\]\((.*)\)", line):
            flush()
            fig += 1
            cap = re.sub(r"^Figure \d+\. ", "", m.group(1))
            body.append("\\begin{figure}[htbp]\n\\centering\n\\includegraphics[width=\\linewidth]{" + m.group(2) + "}\n"
                        "\\caption{" + inline(cap) + "}\n\\label{fig:" + str(fig) + "}\n\\end{figure}\n")
        elif line.startswith("|"):
            if para:
                flush()
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not all(re.fullmatch(r"-+", c) for c in cells):
                rows.append(cells)
        elif line.startswith("    "):
            flush()
            eq = line.strip()
            body.append("\\begin{equation*}\n" + EQUATIONS.get(eq, esc(eq)) + "\n\\end{equation*}\n")
        elif not line.strip():
            flush()
        else:
            para.append(line.strip())
    flush()
    text = "".join(body)
    text = re.sub(r"\(?Figure (\d+)([,)])", lambda m: ("(" if m.group(0).startswith("(") else "") + "Figure~\\ref{fig:" + m.group(1) + "}" + m.group(2), text)
    text = re.sub(r"Figure (\d+)", r"Figure~\\ref{fig:\1}", text)
    return PREAMBLE % {"title": esc(title), "date": date} + text + "\n\\end{document}\n"


OUT.write_text(convert(SRC.read_text()))
print(f"→ {OUT}")
