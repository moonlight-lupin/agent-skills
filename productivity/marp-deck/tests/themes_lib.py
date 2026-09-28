import re
EXPECTED = ["Dark starter", "Light starter", "Bold Signal", "Electric Studio", "Creative Voltage",
            "Dark Botanical", "Notebook Tabs", "Pastel Geometry", "Split Pastel", "Vintage Editorial",
            "Neon Cyber", "Terminal Green", "Swiss Modern", "Paper & Ink"]
def section_css(md, name):
    for sec in re.split(r"(?m)^(?=#{2,4} )", md):
        head = sec.splitlines()[0] if sec else ""
        if name in head:
            m = re.search(r"```css\n(.*?)```", sec, re.S)
            return m.group(1) if m else None
    return None
