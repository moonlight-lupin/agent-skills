#!/usr/bin/env python3
"""Self-test for receipt_pack — synthetic fixtures, no network, no external files.

Builds synthetic "receipt photos" (tilted rectangles with printed text), runs
scan -> review -> pack end-to-end, and asserts the confirmation gate variants,
digest binding, scale (30+), single receipt, mixed currencies, unreadable
images, and the removal of any bypass flag.
Run: python3 receipt_pack_selftest.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "receipt_compiler.py"


def _font(size):
    for name in ("DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            from PIL import ImageFont
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def make_receipt_photo(path: Path, w=900, h=1300, angle=6.0, lines=None,
                       total="10.30") -> None:
    """A white receipt with black text, rotated `angle` degrees on a gray desk."""
    lines = lines or [
        "COLD STORAGE SINGAPORE", "1 Bukit Timah Rd", "2026-09-05",
        "MILK 2L            6.50", "BREAD WHOLEMEAL    3.80", f"TOTAL         {total}",
    ]
    img = Image.new("L", (w, h), 250)
    d = ImageDraw.Draw(img)
    f = _font(36)
    y = 80
    for ln in lines:
        d.text((60, y), ln, fill=10, font=f)
        y += 60
    d.rectangle([2, 2, w - 3, h - 3], outline=5, width=3)

    bg = Image.new("L", (w + 400, h + 400), 120)
    bg.paste(img, (200, 200))
    bg = bg.rotate(angle, expand=True, fillcolor=120, resample=Image.BICUBIC)
    bg.convert("RGB").save(path, "JPEG", quality=90)


def run(*args):
    p = subprocess.run([sys.executable, str(SCRIPT), *args],
                       capture_output=True, text=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def confirm(work: Path):
    """Approve via the real confirm subcommand (binds digest to current state)."""
    rc, out, err = run("confirm", str(work))
    assert rc == 0, f"confirm failed: {out} {err}"
    return json.loads((work / "manifest.json").read_text())


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="receipt_selftest_"))
    src = tmp / "photos"
    src.mkdir()
    n = 5
    for i in range(n):
        make_receipt_photo(src / f"r{i+1}.jpg", angle=(-8 + i * 4.0))
    work = tmp / "work"

    # 1. scan
    rc, out, err = run("scan", str(src), "-o", str(work))
    assert rc == 0, f"scan failed rc={rc} err={err}"
    data = json.loads(out)
    assert data["receipts"] == n, f"expected {n} receipts, got {data['receipts']}"
    m = json.loads((work / "manifest.json").read_text())
    assert len(m["receipts"]) == n
    # 19. processed PNGs: exactly one per receipt
    pngs = sorted((work / "processed").glob("*.png"))
    assert len(pngs) == n, f"expected {n} processed pngs, got {len(pngs)}"
    assert all(p.exists() for p in pngs)

    # 2. review prints table
    rc, out, err = run("review", str(work))
    assert rc == 0 and "Total" in out, f"review failed: {out} {err}"

    # 3. pack must FAIL while unconfirmed (gate)
    rc, out, err = run("pack", str(work), "-o", str(tmp / "out.pdf"))
    assert rc == 1 and "not confirmed" in (out + err), \
        f"gate missing: rc={rc} out={out} err={err}"

    # 3b. string "confirmed": "false"/1 must also fail (no truthy bypass)
    m2 = dict(m)
    for bad in ("false", 1, "yes"):
        m2["confirmed"] = bad
        (work / "manifest.json").write_text(json.dumps(m2))
        rc, out, err = run("pack", str(work), "-o", str(tmp / "out.pdf"))
        assert rc == 1, f"gate passed for confirmed={bad!r}: {out}"

    # 3c. --force flag removed: argparse must reject it
    rc, out, err = run("pack", "--force", str(work), "-o", str(tmp / "x.pdf"))
    assert rc != 0, "--force still accepted"

    # 3d. hand-stamped confirmation without confirm subcommand must fail
    # (no review_digest in manifest)
    m3 = json.loads((work / "manifest.json").read_text())
    m3["confirmed"] = True
    (work / "manifest.json").write_text(json.dumps(m3))
    rc, out, err = run("pack", str(work), "-o", str(tmp / "out.pdf"))
    assert rc == 1 and "review_digest" in (out + err), \
        f"digest-less confirm bypassed: rc={rc} {out} {err}"
    # 3e. digest deletion after confirm also fails
    m = confirm(work)
    mm = json.loads((work / "manifest.json").read_text())
    mm.pop("review_digest")
    (work / "manifest.json").write_text(json.dumps(mm))
    rc, out, err = run("pack", str(work), "-o", str(tmp / "out.pdf"))
    assert rc == 1 and "review_digest" in (out + err), \
        f"digest-removal bypassed: rc={rc} {out} {err}"

    # 4. confirm (subcommand) and pack with cover
    m = confirm(work)
    pdf = tmp / "out.pdf"
    rc, out, err = run("pack", str(work), "-o", str(pdf),
                       "--cover", "--number", "--captions")
    assert rc == 0, f"pack failed: {err}"
    data = json.loads(out)
    assert Path(data["out"]).exists() and data["out"].endswith(".pdf")
    assert data["receipts"] == n
    assert data["pages"] >= 2, f"cover+content expected, pages={data['pages']}"

    # 4b. digest: post-confirmation edit must be rejected
    m["receipts"][0]["amount"] = 99.99
    (work / "manifest.json").write_text(json.dumps(m))
    rc, out, err = run("pack", str(work), "-o", str(tmp / "tampered.pdf"))
    assert rc == 1 and "digest" in (out + err).lower(), \
        f"digest check missing: rc={rc} {out} {err}"
    # 4c. but re-confirm after legitimate edits works (fresh approval)
    m = confirm(work)
    rc, out, err = run("pack", str(work), "-o", str(tmp / "reconfirm.pdf"))
    assert rc == 0, f"re-confirm flow broken: {out} {err}"

    # 5. pdf sanity
    import fitz
    doc = fitz.open(pdf)
    assert doc.page_count == data["pages"]
    doc.close()

    # 6. exclusion flow: exclude one receipt, re-confirm, repack
    m["receipts"][0]["include"] = False
    (work / "manifest.json").write_text(json.dumps(m))
    m = confirm(work)
    pdf2 = tmp / "out2.pdf"
    rc, out, err = run("pack", str(work), "-o", str(pdf2))
    assert rc == 0 and json.loads(out)["receipts"] == n - 1

    # 7. scale: 30+ receipts flow across pages
    src30 = tmp / "photos30"
    src30.mkdir()
    for i in range(32):
        make_receipt_photo(src30 / f"p{i+1:02d}.jpg", angle=(i % 10) - 5.0)
    work30 = tmp / "work30"
    rc, out, err = run("scan", str(src30), "-o", str(work30))
    assert rc == 0 and json.loads(out)["receipts"] == 32
    m30 = json.loads((work30 / "manifest.json").read_text())
    confirm(work30)
    pdf30 = tmp / "out30.pdf"
    rc, out, err = run("pack", str(work30), "-o", str(pdf30),
                       "--cover", "--number", "--captions")
    assert rc == 0, f"pack30 failed: {err}"
    d30 = json.loads(out)
    assert d30["receipts"] == 32 and d30["pages"] >= 3, \
        f"32 receipts should span 3+ pages: {d30}"
    doc = fitz.open(pdf30)
    assert doc.page_count == d30["pages"]
    doc.close()

    # 7b. multi-page cover: 50 receipts force the cover index to paginate
    src120 = tmp / "photos120"
    src120.mkdir()
    for i in range(50):
        make_receipt_photo(src120 / f"q{i+1:03d}.jpg", angle=(i % 8) - 4.0)
    work120 = tmp / "work120"
    rc, out, err = run("scan", str(src120), "-o", str(work120))
    assert rc == 0 and json.loads(out)["receipts"] == 50
    confirm(work120)
    pdf120 = tmp / "out120.pdf"
    rc, out, err = run("pack", str(work120), "-o", str(pdf120), "--cover")
    assert rc == 0, f"pack120 failed: {err}"
    d120 = json.loads(out)
    import fitz
    doc = fitz.open(pdf120)
    assert doc.page_count == d120["pages"]
    # every cover page must stay inside margins: last row + totals above footer
    import re as _re
    cover_done = 0
    for i in range(doc.page_count):
        txt = doc[i].get_text()
        if "Amount" in txt and "Description" in txt:
            cover_done += 1
            a4_h = doc[i].rect.height
            footer_y = a4_h - 28.35  # 10mm footer zone top
            # every non-footer text block must end above the footer zone
            offenders = [b[4].strip()[:40] for b in doc[i].get_text("blocks")
                         if b[4].strip() and not b[4].strip().startswith("Page ")
                         and b[3] >= footer_y]
            assert not offenders, \
                f"cover page {i+1} content overflows into footer zone: {offenders}"
    assert cover_done >= 2, f"expected multi-page cover, got {cover_done} pages"
    doc.close()

    # 8. single receipt
    src1 = tmp / "photos1"
    src1.mkdir()
    make_receipt_photo(src1 / "only.jpg")
    work1 = tmp / "work1"
    rc, out, err = run("scan", str(src1), "-o", str(work1))
    assert rc == 0 and json.loads(out)["receipts"] == 1
    m1 = json.loads((work1 / "manifest.json").read_text())
    confirm(work1)
    rc, out, err = run("pack", str(work1), "-o", str(tmp / "out1.pdf"),
                       "--cover", "--number", "--captions")
    assert rc == 0 and json.loads(out)["pages"] >= 2

    # 9. mixed currencies: review + cover print per-currency totals
    m1["receipts"][0]["currency"] = "SGD"
    m1["receipts"].append(dict(m1["receipts"][0], n=2, currency="MYR", amount=25.00))
    (work1 / "manifest.json").write_text(json.dumps(m1))
    m1 = confirm(work1)
    rc, out, err = run("review", str(work1))
    assert rc == 0 and "SGD" in out and "MYR" in out and "mixed" in out.lower()
    rc, out, err = run("pack", str(work1), "-o", str(tmp / "mixed.pdf"), "--cover")
    assert rc == 0, f"mixed pack failed: {err}"

    # 10. unreadable image: scan fails loudly, does not write empty manifest
    bad = tmp / "photos_bad"
    bad.mkdir()
    make_receipt_photo(bad / "good.jpg")
    (bad / "corrupt.jpg").write_bytes(b"\x00\x01\x02notanimage")
    rc, out, err = run("scan", str(bad), "-o", str(tmp / "workbad"))
    assert rc == 0 and json.loads(out)["receipts"] == 1  # good one survives
    allbad = tmp / "photos_allbad"
    allbad.mkdir()
    (allbad / "corrupt.jpg").write_bytes(b"\x00\x01\x02notanimage")
    rc, out, err = run("scan", str(allbad), "-o", str(tmp / "work_allbad"))
    assert rc == 1 and "could be decoded" in (out + err), \
        f"all-unreadable must fail: rc={rc} {out} {err}"

    # 11. missing input dir
    rc, out, err = run("scan", str(tmp / "no_such_dir"), "-o", str(tmp / "w"))
    assert rc == 1 and "not found" in (out + err).lower()

    # 12. OCR-parser unit tests (regressions from the Muse review round)
    import importlib.util
    spec = importlib.util.spec_from_file_location("rp", SCRIPT)
    rp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rp)

    # 11a. month-name dates must not crash and must parse
    assert rp._extract_date("12 Jan 2026") == "2026-01-12"
    assert rp._extract_date("3 September 2026") == "2026-09-03"
    assert rp._parse_ocr(["COLD STORAGE", "12 January 2026", "TOTAL 9.90"])["date"] \
        == "2026-01-12"

    # 11b. tendered/change must not beat the real total
    r = rp._parse_ocr(["SHOP", "TOTAL 12.30", "AMOUNT TENDERED 50.00",
                       "CHANGE 37.70"])
    assert r["amount"] == 12.30, f"tendered beat total: {r}"
    # 11c. multi-line total: lone TOTAL keyword then amount on next line
    r = rp._parse_ocr(["SHOP XYZ", "TOTAL", "12.30", "CASH 50.00"])
    assert r["amount"] == 12.30, f"multi-line total failed: {r}"
    # 11d. subtotal must not beat grand total
    r = rp._parse_ocr(["SHOP", "SUBTOTAL 8.00", "GST 0.56", "GRAND TOTAL 8.56"])
    assert r["amount"] == 8.56, f"subtotal beat grand total: {r}"
    # 11d2 (Claude M1 regression): next-line fallback must not pick a tender row
    r = rp._parse_ocr(["SUBTOTAL 9.00", "TOTAL", "CASH 50.00", "CHANGE 41.00"])
    assert r["amount"] == 9.00, f"tender beat total via fallback: {r}"
    # 11d3 (Claude M2 regression): TOTAL QTY must not become the total
    r = rp._parse_ocr(["SUBTOTAL 8.00", "TOTAL QTY 25", "TOTAL 8.56"])
    assert r["amount"] == 8.56, f"qty line became total: {r}"
    # 11d4 (Claude m2): 3-decimal petrol prices must not inflate 1000x
    assert rp._to_float("1.899") is None
    assert rp._to_float("2.150") is None
    # 11e. whole-dollar and 1-decimal totals must match
    assert rp._parse_ocr(["SHOP", "TOTAL 100"])["amount"] == 100.0
    assert rp._parse_ocr(["SHOP", "TOTAL 10.5"])["amount"] == 10.5
    # 11f. bare integers outside total context (years/qtys) are ignored
    assert rp._parse_ocr(["SHOP 2026", "MILK 2", "TOTAL 7.20"])["amount"] == 7.20
    # 11f2 (Claude B1 regression): guard must fire even when the total keyword
    # is OCR-mangled and the fallback max() path runs
    r = rp._parse_ocr(["SHOP 2026", "MILK 2", "TDTAL 7.20"])
    assert r["amount"] == 7.20, f"dead bare-integer guard regressed: {r}"
    # 11f3: phone/yr fragments never win via the fallback either
    r = rp._parse_ocr(["TEL: 6221 1234", "GST NO 2018", "MILK 2L 6.50"])
    assert r["amount"] == 6.50, f"phone fragment became total: {r}"
    # 11g. merchant: noise words don't discard the whole line
    r = rp._parse_ocr(["TAX INVOICE COLD STORAGE", "1 Bukit Timah Rd", "TOTAL 5.00"])
    assert "COLD STORAGE" in r["merchant"], f"merchant lost to noise: {r}"

    # 11h. string amount in manifest: review errors cleanly, and confirm
    # fails closed too (Claude M6: the review-bypass path must not stamp a
    # digest over a bad amount)
    src1b = tmp / "photos1b"
    src1b.mkdir()
    make_receipt_photo(src1b / "only.jpg")
    work1b = tmp / "work1b"
    rc, out, err = run("scan", str(src1b), "-o", str(work1b))
    mb = json.loads((work1b / "manifest.json").read_text())
    mb["receipts"][0]["amount"] = "abc"
    (work1b / "manifest.json").write_text(json.dumps(mb))
    rc, out, err = run("review", str(work1b))
    assert rc == 1 and "not a number" in (out + err), \
        f"string amount not caught: rc={rc} {out} {err}"
    rc, out, err = run("confirm", str(work1b))
    assert rc == 1 and "not a number" in (out + err), \
        f"confirm stamped bad amount: rc={rc} {out} {err}"

    # 11i. image-swap after confirm must break the digest
    src2 = tmp / "photos_swap"
    src2 = tmp / "work_swap"
    make_receipt_photo(src1b / "swap.jpg", total="10.30")
    rc, out, err = run("scan", str(src1b), "-o", str(src2))
    confirm(src2)
    png = sorted((src2 / "processed").glob("*.png"))[0]
    make_receipt_photo(png, total="99.99", angle=0.0)  # overwrite in place
    rc, out, err = run("pack", str(src2), "-o", str(tmp / "swap.pdf"))
    assert rc == 1 and "digest" in (out + err).lower(), \
        f"image swap not caught: rc={rc} {out} {err}"

    # 11j. missing processed file after confirm: clean error, no traceback
    png.unlink()
    m = json.loads((src2 / "manifest.json").read_text())
    m.pop("review_digest", None)
    (src2 / "manifest.json").write_text(json.dumps(m))
    confirm(src2)
    rc, out, err = run("pack", str(src2), "-o", str(tmp / "missing.pdf"))
    assert rc == 1 and "missing" in (out + err).lower() and "Traceback" not in err, \
        f"missing image not handled: rc={rc} {out} {err}"

    # 11k (Claude M7): non-Latin merchant must not crash pack AND must render
    # as real glyphs (not tofu) when a CJK-capable font exists
    src3 = tmp / "work_cjk"
    make_receipt_photo(src1b / "cjk.jpg")
    rc, out, err = run("scan", str(src1b), "-o", str(src3))
    mc = json.loads((src3 / "manifest.json").read_text())
    mc["receipts"][0]["merchant"] = "大众书局"
    (src3 / "manifest.json").write_text(json.dumps(mc))
    confirm(src3)
    rc, out, err = run("pack", str(src3), "-o", str(tmp / "cjk.pdf"),
                       "--cover", "--captions", "--claimant", "MH 先生")
    assert rc == 0, f"CJK pack crashed: {err}"
    import fitz as _fz
    _doc = _fz.open(tmp / "cjk.pdf")
    assert _doc.page_count >= 1
    # if a CJK-capable font is installed, the merchant text must be extractable
    # (not tofu-substituted); otherwise the sanitize fallback must have warned
    all_text = "".join(_doc[i].get_text() for i in range(_doc.page_count))
    has_cjk_face = any(Path(p).is_file() for p in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"))
    if has_cjk_face:
        assert "大众书局" in all_text, \
            f"CJK merchant not rendered despite CJK font: {all_text[:200]!r}"
    _doc.close()

    # 11l (Claude M3): receipt numbers must be sequential, no gaps
    bad2 = tmp / "photos_gap"
    bad2.mkdir()
    (bad2 / "a_corrupt.jpg").write_bytes(b"\x00\x01\x02notanimage")
    make_receipt_photo(bad2 / "b_good.jpg")
    rc, out, err = run("scan", str(bad2), "-o", str(tmp / "work_gap"))
    assert rc == 0
    mg = json.loads(out)
    assert mg["receipts"] == 1 and mg["unreadable"] == ["a_corrupt.jpg"], \
        f"unreadable not surfaced: {mg}"
    wg = json.loads((tmp / "work_gap" / "manifest.json").read_text())
    assert wg["receipts"][0]["n"] == 1, f"n gap: {wg['receipts'][0]['n']}"
    rc, out, err = run("review", str(tmp / "work_gap"))
    assert "NOT in this claim" in out, f"review hides unreadable: {out}"

    print(f"SELFTEST OK — gate variants, digest, image-swap binding, OCR parser "
          f"(month dates, tender, subtotal, whole-dollar), 32-pack, single, "
          f"mixed ccy, unreadable inputs all verified ({tmp})")
    return 0


if __name__ == "__main__":
    sys.exit(main())