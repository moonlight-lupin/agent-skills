import re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from themes_lib import EXPECTED, section_css
SK, OUT = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
md = (SK / "references/themes.md").read_text()
SAMPLE = """
<!-- _class: lead -->
<!-- _paginate: false -->

### Quarterly review

# Q3 Portfolio Review

## UK student accommodation · September 2026

---

### 01 · Performance

# Occupancy ahead of target

## Rent growth and occupancy both beat plan

Body copy with a **highlighted figure**, an `inline code` span and a [link](#).

<div style="display:flex;gap:16px;margin:12px 0;">
<div class="card" style="flex:1;"><span style="color:var(--label);font-size:0.6em;letter-spacing:.1em;">OCCUPANCY</span><br><span style="color:var(--light);font-size:1.5em;font-family:var(--font-head);">97.2%</span> <span class="tag" style="color:var(--green);border:1px solid var(--green);">+1.2 pts</span></div>
<div class="card" style="flex:1;"><span style="color:var(--label);font-size:0.6em;letter-spacing:.1em;">NOI</span><br><span style="color:var(--light);font-size:1.5em;font-family:var(--font-head);">£14.2m</span> <span class="tag" style="color:var(--accent);border:1px solid var(--accent);">vs £13.6m</span></div>
</div>

| Asset | Beds | Occupancy |
|---|---|---|
| Canongate | 312 | 98.1% |
| Kelvin | 240 | 96.4% |

---

### 02 · Risk

# Booking pace

> 2027/28 bookings are running 4 pts behind last year at the same date.

- Pricing held; conversion is the gap
- Agent channel reactivated in August
- Weekly pace review until parity
"""
base = section_css(md, "Base rules") or ""
for name in EXPECTED:
    css = section_css(md, name)
    if css is None: print("no css for", name); continue
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    style = "\n".join("  " + l for l in (base + css).splitlines())
    (OUT / f"{slug}.md").write_text(f"---\nmarp: true\npaginate: true\nstyle: |\n{style}\n---\n{SAMPLE}")
