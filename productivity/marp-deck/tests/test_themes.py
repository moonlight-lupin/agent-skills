"""themes.md: a Base rules block + complete palette blocks on the variable contract,
every text colour clearing its contrast floor.

Runs standalone (prints PASS/FAIL lines, exit code = failures) and under pytest
(the `test_themes_contract` function collects normally).
"""
import re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from themes_lib import EXPECTED, section_css
SK = pathlib.Path(__file__).parent.parent
if __name__ == "__main__" and len(sys.argv) > 1:
    SK = pathlib.Path(sys.argv[1])
HEX = ["--accent", "--accent-hover", "--dark", "--card", "--border", "--body", "--label",
       "--muted", "--light", "--green", "--red", "--yellow"]
TYPE = ["--font-head", "--font-body", "--head-weight", "--body-weight"]
FLOORS = [("--body", "--dark", 4.5), ("--light", "--dark", 4.5), ("--body", "--card", 4.5),
          ("--label", "--dark", 3.0), ("--muted", "--dark", 3.0), ("--accent", "--dark", 3.0)]
def lum(h):
    h = h.lstrip("#"); h = "".join(c*2 for c in h) if len(h) == 3 else h[:6]
    c = [int(h[i:i+2], 16)/255 for i in (0, 2, 4)]
    c = [x/12.92 if x <= 0.03928 else ((x+0.055)/1.055)**2.4 for x in c]
    return 0.2126*c[0] + 0.7152*c[1] + 0.0722*c[2]
def ratio(a, b):
    la, lb = sorted([lum(a), lum(b)], reverse=True); return (la+0.05)/(lb+0.05)

def run(report):
    fails = 0
    def check(cond, msg):
        nonlocal fails
        report(cond, msg); fails += (not cond)
    md = (SK / "references/themes.md").read_text()
    base = section_css(md, "Base rules")
    check(base is not None and "section.lead" in base and "table" in base and ".card" in base, "Base rules block: lead, table, card")
    for name in EXPECTED:
        css = section_css(md, name)
        check(css is not None, f"{name}: has a ```css block")
        if css is None: continue
        vars_ = dict(re.findall(r"(--[a-z-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;", css))
        missing = [v for v in HEX if v not in vars_] + [v for v in TYPE if v + ":" not in css.replace(" ", "")]
        check(not missing, f"{name}: defines contract vars" + (f" (missing {missing})" if missing else ""))
        check("@import" in css, f"{name}: imports its fonts")
        for fg, bg, floor in FLOORS:
            if fg in vars_ and bg in vars_:
                r = ratio(vars_[fg], vars_[bg]); check(r >= floor, f"{name}: {fg} on {bg} = {r:.2f} (>= {floor})")
    return fails

def test_themes_contract():
    fails = run(lambda cond, msg: None)
    assert fails == 0, f"{fails} theme-contract checks failed"

if __name__ == "__main__":
    fails = run(lambda cond, msg: print(("PASS  " if cond else "FAIL  ") + msg))
    print(f"---- {fails} failures")
    sys.exit(1 if fails else 0)