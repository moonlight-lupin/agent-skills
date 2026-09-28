#!/usr/bin/env python3
"""md2pptx-officecli.py — build an editable PPTX from a Marp Markdown deck.

Fallback path for machines without a full LibreOffice install (LibreOffice 24.2+
removed the Impress HTML import filter, which breaks `marp --pptx-editable`).
Parses the deck's Markdown structurally — headings, bullets, numbered lists,
tables, blockquotes — and emits native PowerPoint text boxes, tables and shapes
via the `officecli` CLI. Styling: reads the deck's own theme colours when the
frontmatter defines `--dark`, `--light` and `--accent` CSS variables in a
`:root` block; otherwise uses PowerPoint defaults.

This is a fidelity-lost conversion by design: complex HTML components, SVG
charts and background images are skipped (a placeholder line names them). The
pixel-faithful render stays with `marp deck.md --pdf`. Keep both.

Usage:
    python3 md2pptx-officecli.py deck.md output.pptx
Requires:
    officecli on PATH — https://github.com/iOfficeAI/OfficeCLI
      curl -fsSL https://raw.githubusercontent.com/iOfficeAI/OfficeCLI/main/install.sh | bash
"""
import json
import re
import subprocess
import sys

CANVAS_W, CANVAS_H = 33.87, 19.05   # cm — officecli default 960x540pt
MX = 1.4
CW = CANVAS_W - 2 * MX

# Fallback palette (near-neutral, readable on white)
C_BG, C_INK, C_SOFT, C_FAINT = "FFFFFF", "1A1A1A", "444444", "8A8A8A"
C_ACCENT, C_LINE, C_ONACC = "1F4E79", "D9D9D9", "FFFFFF"

ops = []
slide_n = 0


def add(parent, type_, **props):
    parent = parent.replace("/slide[1]", f"/slide[{slide_n}]")
    ops.append({"command": "add", "parent": parent, "type": type_,
                "props": {k: str(v) for k, v in props.items()}})


def st(path, **props):
    path = path.replace("/slide[1]", f"/slide[{slide_n}]")
    ops.append({"command": "set", "path": path,
                "props": {k: str(v) for k, v in props.items()}})


def strip_md(text):
    text = re.sub(r"<[^>]+>", "", text)              # inline HTML/strong tags
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)     # bold
    text = re.sub(r"\*(.+?)\*", r"\1", text)         # italic
    text = re.sub(r"`(.+?)`", r"\1", text)           # code
    text = re.sub(r"!\[.*?\]\(.*?\)", "[image]", text)
    text = re.sub(r"\[(.+?)\]\(.*?\)", r"\1", text)  # links
    return text.strip()


def parse_theme(md_text):
    """Pull --dark/--light/--accent from a :root block in the frontmatter style."""
    global C_BG, C_INK, C_SOFT, C_FAINT, C_ACCENT, C_LINE, C_ONACC
    root = re.search(r":root\s*\{(.*?)\}", md_text, re.S)
    if not root:
        return
    block = root.group(1)

    def var(name, default):
        m = re.search(rf"--{name}\s*:\s*#([0-9a-fA-F]{{6}})", block)
        return m.group(1).upper() if m else default

    dark = var("dark", "")          # dark = background colour in Marp themes
    light = var("light", "")
    accent = var("accent", "")
    if light and dark:
        # Convention: --light is body/foreground, --dark is background
        C_BG = dark
        C_INK = light
        C_ONACC = dark if _luma(dark) > 0.5 else "FFFFFF"
        C_ONACC = "FFFFFF" if _luma(dark) < 0.5 else dark
    if accent:
        C_ACCENT = accent
        C_ONACC = "FFFFFF" if _luma(accent) < 0.5 else dark or "1A1A1A"
    m = re.search(r"--body\s*:\s*#([0-9a-fA-F]{6})", block)
    if m:
        C_SOFT = m.group(1).upper()


def _luma(hex6):
    r, g, b = (int(hex6[i:i + 2], 16) for i in (0, 2, 4))
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def parse_deck(path):
    """Return list of slides; each = dict(kind, title, blocks[]).
    block = (btype, payload) with btype in h1/h2/h3/bullets/table/quote/par/peg/html."""
    md = open(path, encoding="utf-8").read()
    parse_theme(md)

    # Drop frontmatter (allow leading blank lines)
    md = re.sub(r"\A\s*---\n.*?\n---\n", "", md, count=1, flags=re.S)
    # Drop Marp directives
    md = re.sub(r"<!--_class:.*?-->", "", md)
    md = re.sub(r"<!--\s*_?class:.*?-->", "", md)
    md = re.sub(r"<!--.*?-->", "", md)

    slides = []
    for chunk in re.split(r"\n---+\n", md):
        lines = chunk.strip().splitlines()
        if not lines or all(not ln.strip() for ln in lines):
            continue
        slide = {"title": None, "subtitle": None, "blocks": []}
        i, buf = 0, lines
        while i < len(buf):
            ln = buf[i].rstrip()
            if not ln.strip():
                i += 1
                continue
            if ln.startswith("# ") and slide["title"] is None:
                slide["title"] = strip_md(ln[2:])
            elif ln.startswith("## "):
                t = strip_md(ln[3:])
                if slide["title"] is None:
                    slide["title"] = t
                else:
                    slide["blocks"].append(("h3", t))
            elif ln.startswith("### "):
                slide["blocks"].append(("h3", strip_md(ln[4:])))
            elif re.match(r"^- |\* ", ln):
                items = []
                while i < len(buf) and re.match(r"^\s*[-*] ", buf[i]):
                    indent = len(buf[i]) - len(buf[i].lstrip())
                    items.append(("  " * (indent // 2)) + strip_md(re.sub(r"^\s*[-*] ", "", buf[i])))
                    i += 1
                slide["blocks"].append(("bullets", items))
                continue
            elif re.match(r"^\d+\. ", ln):
                items = []
                while i < len(buf) and re.match(r"^\s*\d+\. ", buf[i]):
                    items.append(strip_md(re.sub(r"^\s*\d+\. ", "", buf[i])))
                    i += 1
                slide["blocks"].append(("numbers", items))
                continue
            elif ln.startswith("|"):
                rows = []
                while i < len(buf) and buf[i].strip().startswith("|"):
                    cells = [strip_md(c.strip()) for c in buf[i].strip().strip("|").split("|")]
                    if not re.match(r"^\s*\|[\s:|-]+\|?\s*$", buf[i]):
                        rows.append(cells)
                    i += 1
                if rows:
                    slide["blocks"].append(("table", rows))
                continue
            elif ln.startswith(">"):
                quote = strip_md(ln.lstrip("> "))
                slide["blocks"].append(("quote", quote))
            elif ln.startswith("<"):  # HTML block (peg-row, cols, rule divs…)
                html = []
                while i < len(buf) and buf[i].strip().startswith("<"):
                    html.append(buf[i].strip())
                    i += 1
                joined = " ".join(html)
                peg = re.search(r'class="peg"[^>]*>(\d+)<', joined)  # header-tag rows (any theme)
                label = re.search(r'class="peg-label"[^>]*>([^<]+)<', joined)
                if peg and label:
                    slide["blocks"].append(("peg", (peg.group(1), label.group(1))))
                elif "<strong>" in joined or "<div" in joined:
                    txt = strip_md(re.sub(r"<br\s*/?>", "\n", joined))
                    if txt:
                        slide["blocks"].append(("box", txt))
                continue
            else:
                txt = strip_md(ln)
                if txt and not slide["subtitle"] and slide["title"] and not slide["blocks"]:
                    slide["subtitle"] = txt
                elif txt:
                    slide["blocks"].append(("par", txt))
            i += 1
        slides.append(slide)
    return slides


def emit(slides):
    for s in slides:
        globals()["slide_n"] += 1
        y = 1.2
        # Background: light theme only (officecli renders text themes simply)
        add(f"/slide[{slide_n}]", "shape", x="0cm", y="0cm",
            width=f"{CANVAS_W}cm", height=f"{CANVAS_H}cm", fill=C_BG,
            line="none")
        title_y = 1.6
        if s["title"]:
            add(f"/slide[{slide_n}]", "shape", text=s["title"],
                x=f"{MX}cm", y=f"{title_y}cm", width=f"{CW}cm", height="1.5cm",
                font="Arial", size=28, bold="true", color=C_INK)
            y = title_y + 2.0
        if s["subtitle"]:
            add(f"/slide[{slide_n}]", "shape", text=s["subtitle"],
                x=f"{MX}cm", y=f"{y}cm", width=f"{CW}cm", height="1.0cm",
                font="Arial", size=15, color=C_SOFT)
            y += 1.5

        for btype, payload in s["blocks"]:
            if btype == "peg":
                num, label = payload
                add(f"/slide[{slide_n}]", "shape", text=num,
                    x=f"{MX}cm", y=f"{y}cm", width="1.2cm", height="1.2cm",
                    fill=C_BG, font="Consolas", size=13, bold="true",
                    color=C_ACCENT, geometry="roundRect", line=C_LINE)
                add(f"/slide[{slide_n}]", "shape", text=label.upper(),
                    x=f"{MX + 1.8}cm", y=f"{y + 0.25}cm", width="12cm",
                    height="0.8cm", font="Consolas", size=10, bold="true",
                    color=C_ACCENT)
                y += 1.8
            elif btype == "h3":
                add(f"/slide[{slide_n}]", "shape", text=payload.upper(),
                    x=f"{MX}cm", y=f"{y}cm", width=f"{CW}cm", height="0.8cm",
                    font="Consolas", size=11, bold="true", color=C_ACCENT)
                y += 1.2
            elif btype == "bullets":
                txt = "\n".join("· " + item for item in payload)
                h = max(1.2, 0.75 * len(payload) + 0.6)
                add(f"/slide[{slide_n}]", "shape", text=txt,
                    x=f"{MX}cm", y=f"{y}cm", width=f"{CW}cm", height=f"{h}cm",
                    font="Arial", size=14, color=C_SOFT, valign="top")
                y += h + 0.4
            elif btype == "numbers":
                txt = "\n".join(f"{i}. {item}" for i, item in enumerate(payload, 1))
                h = max(1.2, 0.75 * len(payload) + 0.6)
                add(f"/slide[{slide_n}]", "shape", text=txt,
                    x=f"{MX}cm", y=f"{y}cm", width=f"{CW}cm", height=f"{h}cm",
                    font="Arial", size=14, color=C_SOFT, valign="top")
                y += h + 0.4
            elif btype == "table":
                rows = payload
                n, c = len(rows), len(rows[0])
                colw = (CW - 0.4 * (c - 1)) / c
                add(f"/slide[{slide_n}]", "table", rows=n, cols=c,
                    x=f"{MX}cm", y=f"{y}cm",
                    colWidths=",".join(f"{colw:.2f}cm" for _ in range(c)),
                    bandedRows="false")
                t = f"/slide[{slide_n}]/table[1]"
                for r, row in enumerate(rows, 1):
                    st(f"{t}/tr[{r}]", height="0.85cm" if r == 1 else "1.1cm")
                    for cix, val in enumerate(row, 1):
                        if r == 1:
                            st(f"{t}/tr[1]/tc[{cix}]", text=val, fill=C_BG,
                               color=C_ACCENT, bold="true", font="Consolas",
                               size=10)
                        else:
                            st(f"{t}/tr[{r}]/tc[{cix}]", text=val,
                               fill="FFFFFF", color=C_SOFT, font="Arial",
                               size=11, valign="middle")
                y += (0.85 if n else 0) + 1.1 * (n - 1) + 0.6
            elif btype == "quote":
                add(f"/slide[{slide_n}]", "shape", text=payload,
                    x=f"{MX}cm", y=f"{y}cm", width=f"{CW}cm", height="1.6cm",
                    font="Arial", size=12.5, color=C_INK, fill=C_BG,
                    geometry="rect")
                add(f"/slide[{slide_n}]", "shape", x=f"{MX}cm", y=f"{y}cm",
                    width="0.13cm", height="1.6cm", fill=C_ACCENT, line="none")
                y += 2.0
            elif btype == "par":
                h = 1.2 + 0.5 * (len(payload) // 110)
                add(f"/slide[{slide_n}]", "shape", text=payload,
                    x=f"{MX}cm", y=f"{y}cm", width=f"{CW}cm", height=f"{h}cm",
                    font="Arial", size=13, color=C_SOFT, valign="top")
                y += h + 0.3
            elif btype == "box":
                add(f"/slide[{slide_n}]", "shape", text=payload,
                    x=f"{MX}cm", y=f"{y}cm", width=f"{CW}cm", height="2.0cm",
                    font="Arial", size=12.5, color=C_SOFT, fill=C_BG,
                    geometry="rect", line=C_LINE, margin="12pt,10pt,12pt,10pt")
                y += 2.4
            if y > 17.2:
                break  # keep content on-canvas; overflow goes to next slide in a full rebuild


def flush(out_path):
    payload = json.dumps(ops)
    r = subprocess.run(["officecli", "batch", out_path, "--commands", payload,
                        "--json"], capture_output=True, text=True)
    try:
        data = json.loads(r.stdout)
        fails = [x for x in data.get("data", {}).get("results", [])
                 if not x.get("success")]
    except Exception:
        fails = ["(unparseable output)"]
    if r.returncode != 0 or fails:
        print(f"officecli batch failed: {len(fails)} item(s)", file=sys.stderr)
        for f in fails[:4]:
            print(f, file=sys.stderr)
        sys.exit(1)
    print(f"officecli batch ok: {data.get('data', {}).get('summary', '')}")


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    src, out = sys.argv[1], sys.argv[2]
    subprocess.run(["officecli", "create", out], capture_output=True)
    # Pre-create slides one at a time (mixed slide-adds in one batch are unreliable)
    slides = parse_deck(src)
    for _ in slides:
        subprocess.run(["officecli", "add", out, "/", "--type", "slide"],
                       capture_output=True)
    emit(slides)
    flush(out)
    subprocess.run(["officecli", "close", out], capture_output=True)
    print(f"Written {out} ({len(slides)} slides) — editable text boxes + tables.")


if __name__ == "__main__":
    main()