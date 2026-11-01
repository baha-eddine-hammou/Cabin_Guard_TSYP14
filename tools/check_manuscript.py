#!/usr/bin/env python3
"""Mechanical checks for the house manuscript rules in CLAUDE.md.

Usage: python tools/check_manuscript.py paper.tex [--max-pages 5]

Each finding is printed as ``rule N  line L: message``. The exit status is the
number of findings (capped at 255), so a clean manuscript exits with 0. Rules
that need a human (semantics, rendered figures) are not checked here.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

FLOAT_ENVS = ("figure", "figure*", "table", "table*", "algorithm", "tikzpicture")
MATH_ENVS = ("equation", "equation*", "align", "align*", "gather", "multline")


def strip_comments(text: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", text)


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def env_spans(text: str, names) -> list[tuple[int, int, str]]:
    spans = []
    for name in names:
        esc = re.escape(name)
        for m in re.finditer(r"\\begin\{" + esc + r"\}", text):
            end = text.find("\\end{" + name + "}", m.end())
            if end != -1:
                spans.append((m.start(), end + len(name) + 6, name))
    return spans


def inside(pos: int, spans) -> bool:
    return any(a <= pos < b for a, b, _ in spans)


def check(tex_path: Path, max_pages: int) -> list[tuple[str, int, str]]:
    raw = tex_path.read_text(encoding="utf-8")
    text = strip_comments(raw)
    out: list[tuple[str, int, str]] = []

    doc_start = max(text.find("\\begin{document}"), text.find("\\maketitle"))
    bib_start = text.find("\\begin{thebibliography}")
    if bib_start == -1:
        bib_start = len(text)
    body = (doc_start, bib_start)
    float_spans = env_spans(text, FLOAT_ENVS)
    math_spans = env_spans(text, MATH_ENVS)

    def in_body(pos: int) -> bool:
        return body[0] <= pos < body[1]

    # Rule 1: em dashes
    for m in re.finditer(r"---|\u2014", text):
        if in_body(m.start()):
            out.append(("1", line_of(text, m.start()), "em dash"))

    # Rule 2: emphasis in running text
    for m in re.finditer(r"\\(emph|textbf|textit)\{", text):
        if in_body(m.start()) and not inside(m.start(), float_spans):
            out.append(("2", line_of(text, m.start()), f"\\{m.group(1)} in running text"))

    # Labels and their positions
    labels = {m.group(1): m.start() for m in re.finditer(r"\\label\{([^}]*)\}", text)}
    refs = [(m.group(2), m.start(), m.group(1))
            for m in re.finditer(r"\\(eqref|ref)\{([^}]*)\}", text)]

    # Rule 4: forward references to sections and equations
    for name, pos, _kind in refs:
        if name in labels and labels[name] > pos and not inside(pos, float_spans):
            if name.startswith(("sec:", "eq:")):
                out.append(("4", line_of(text, pos), f"forward reference to {name}"))
        if name not in labels:
            out.append(("8", line_of(text, pos), f"reference to undefined label {name}"))

    # Equations never named again
    referenced = {name for name, _, _ in refs}
    for name, pos in labels.items():
        if inside(pos, math_spans) and name not in referenced:
            out.append(("eq", line_of(text, pos), f"equation {name} is never named by \\eqref"))
        if not inside(pos, math_spans) and name not in referenced:
            out.append(("8", line_of(text, pos), f"label {name} is never referenced"))

    # Rule 6: punctuation inside displayed maths
    for a, b, _ in math_spans:
        block = text[a:b]
        for m in re.finditer(r"[.,;]\s*(\\\\|\\qquad|\\quad|\\end\{)", block):
            out.append(("6", line_of(text, a + m.start()), "punctuation in displayed equation"))

    # Rule 8: typed cross-reference numbers
    for m in re.finditer(r"\b(Eq\.|Equation|Fig\.|Figure|Table|Algorithm|Section)\s*~?\s*\(?\d", text):
        if in_body(m.start()):
            out.append(("8", line_of(text, m.start()), f"typed number after '{m.group(1)}'"))
    for m in re.finditer(r"(^|[.!?]\s+)Fig\.~\\ref", text):
        out.append(("8", line_of(text, m.start()), "'Fig.' at the start of a sentence"))

    # Rule 21: citation order and unused entries
    order: list[str] = []
    for m in re.finditer(r"\\cite\{([^}]*)\}", text[:bib_start]):
        for key in (k.strip() for k in m.group(1).split(",")):
            if key not in order:
                order.append(key)
    bibitems = re.findall(r"\\bibitem\{([^}]*)\}", text)
    for key in order:
        if key not in bibitems:
            out.append(("21", 0, f"cited key {key} has no bibitem"))
    for key in bibitems:
        if key not in order:
            out.append(("21", 0, f"bibitem {key} is never cited"))
    listed = [k for k in bibitems if k in order]
    if listed != [k for k in order if k in bibitems]:
        out.append(("21", 0, "bibitems are not in order of first citation"))

    # Rule 22: captions
    for m in re.finditer(r"\\caption\{", text):
        depth, i = 1, m.end()
        while i < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        cap = re.sub(r"\s+", " ", text[m.end():i - 1]).strip()
        plain = re.sub(r"\$[^$]*\$|\\[a-zA-Z]+\{?|[{}~]", "", cap)
        if len(plain) > 160:
            out.append(("22", line_of(text, m.start()), f"caption is {len(plain)} characters"))
        if re.search(r"[.!?]\s+[A-Z]", plain):
            out.append(("22", line_of(text, m.start()), "caption has more than one sentence"))

    # Rule 24: full stop before closing parenthesis
    for m in re.finditer(r"\.\)", text):
        if in_body(m.start()) and not re.search(r"(e\.g|i\.e|et al|etc|vs)\.\)$", text[max(0, m.start() - 6):m.end()]):
            out.append(("24", line_of(text, m.start()), "full stop before ')'"))

    # Rule 25: prose forward pointers
    for m in re.finditer(r"\b(below|later in this|remainder of the paper|following section)\b(?!\s*[$\d])", text, re.I):
        if in_body(m.start()) and not inside(m.start(), float_spans):
            out.append(("25", line_of(text, m.start()), f"prose pointer '{m.group(1)}'"))

    # Rule 26: table pattern
    for a, b, name in env_spans(text, ("table", "table*")):
        block = text[a:b]
        if re.search(r"\\(resizebox|scalebox)", block):
            out.append(("26", line_of(text, a), "table scaled with resizebox/scalebox"))
        cap, tab = block.find("\\caption"), block.find("\\begin{tabular")
        if cap == -1 or (tab != -1 and cap > tab):
            out.append(("26", line_of(text, a), "table caption must come above the tabular"))
    for a, b, name in env_spans(text, ("figure", "figure*", "table", "table*")):
        m = re.match(r"\\begin\{" + re.escape(name) + r"\}(\[[^\]]*\])?", text[a:b])
        if m and m.group(1) and re.search(r"[hbp]", m.group(1)):
            out.append(("18", line_of(text, a), f"float placement {m.group(1)} is not top-of-column"))

    # Rule 28 / 35: claims
    for m in re.finditer(r"\b(guarantee[sd]?|compliant|certified|compliance with)\b", text, re.I):
        if in_body(m.start()):
            ctx = text[max(0, m.start() - 40):m.end() + 10]
            if not re.search(r"\b(not|no|without|never)\b", ctx, re.I):
                out.append(("35", line_of(text, m.start()), f"claim word '{m.group(1)}'"))

    # Rule 32: abstract
    am = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", text, re.S)
    if am:
        words = len(re.sub(r"\$[^$]*\$", "x", am.group(1)).split())
        if words > 250:
            out.append(("32", line_of(text, am.start()), f"abstract has {words} words"))
        if "\\cite" in am.group(1):
            out.append(("32", line_of(text, am.start()), "citation in abstract"))

    # Page limit from the LaTeX log, if a build exists
    log = tex_path.with_suffix(".log")
    if log.exists():
        lm = re.search(r"Output written on .*?\((\d+) pages?", log.read_text(errors="ignore"), re.S)
        if lm and int(lm.group(1)) > max_pages:
            out.append(("pages", 0, f"{lm.group(1)} pages, limit {max_pages}"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tex", type=Path)
    ap.add_argument("--max-pages", type=int, default=5)
    args = ap.parse_args()
    findings = check(args.tex, args.max_pages)
    for rule, line, msg in findings:
        print(f"rule {rule:>5}  line {line:>4}: {msg}")
    print(f"{len(findings)} finding(s)")
    return min(len(findings), 255)


if __name__ == "__main__":
    sys.exit(main())
