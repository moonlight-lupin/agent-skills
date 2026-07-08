#!/usr/bin/env python3
"""falgen.py — fal.ai image helper for Image Studio.

Supports image generation, instruction editing, upscaling, background removal,
cost summaries, and `--dry-run` preflight. Dry-run prints the model, arguments
and estimated cost without requiring FAL_KEY, uploading images, calling fal.ai,
downloading outputs, writing logs, or spending credits.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

FAL_API = "https://api.fal.ai/v1"
DEFAULT_COST_LOG = "_falgen-costs.jsonl"

DEFAULT_MODELS = {
    "generate": "fal-ai/flux/schnell",
    "edit": "fal-ai/flux-kontext/dev",
    "upscale": "fal-ai/recraft/upscale/crisp",
    "removebg": "fal-ai/bria/background/remove",
}
APPROX_COST_USD = {
    "fal-ai/flux/schnell": 0.003,
    "fal-ai/flux/dev": 0.025,
    "fal-ai/flux-kontext/dev": 0.005,
    "fal-ai/flux-pro/kontext": 0.04,
    "fal-ai/flux-pro/v1.1": 0.04,
    "fal-ai/nano-banana": 0.039,
    "fal-ai/nano-banana/edit": 0.0398,
    "fal-ai/nano-banana-pro": 0.15,
    "fal-ai/nano-banana-pro/edit": 0.15,
    "openai/gpt-image-2": 0.133,
    "openai/gpt-image-2/edit": 0.133,
    "fal-ai/recraft/v3/text-to-image": 0.04,
    "fal-ai/recraft/v3/image-to-image": 0.04,
    "fal-ai/bria/background/remove": 0.018,
    "fal-ai/recraft/upscale/crisp": 0.004,
    "fal-ai/clarity-upscaler": 0.03,
}
FLUX_SIZE_FROM_ASPECT = {"1:1": "square_hd", "16:9": "landscape_16_9", "9:16": "portrait_16_9", "4:3": "landscape_4_3", "3:4": "portrait_4_3"}
SINGLE_IMAGE_ARG_MODELS = {"fal-ai/flux-kontext/dev", "fal-ai/flux-pro/kontext"}
URL_ARGUMENT_KEYS = {"image_url", "image_urls", "mask_url"}


def _money(x, currency="USD"):
    return f"${x:,.4f}" if currency == "USD" else f"{x:,.4f} {currency}"


FAL_KEY_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}:[0-9a-fA-F]{16,}"
)
# Assignment must start its line (optionally `export`ed) so commented examples
# like `# FAL_KEY=your-key` in notes files are never picked up.
FAL_KEY_ASSIGN_RE = re.compile(r"^\s*(?:export\s+)?FAL_KEY\s*[=:]\s*[\"']?([^\s\"']+)", re.M)
FAL_ADMIN_ASSIGN_RE = re.compile(r"^\s*(?:export\s+)?FAL_ADMIN_KEY\s*[=:]\s*[\"']?([^\s\"']+)", re.M)


def _extract_fal_key(text, name_hinted=False, labeled_only=False):
    """Pull a fal key out of file text. An explicit `FAL_KEY=`/`FAL_KEY:` line always counts.
    Unless `labeled_only`, also accept an UNLABELED token — a fal-shaped `uuid:hex` match
    anywhere, or (for a file whose NAME hints fal/key) the whole file being one such token.
    Unlabeled tokens must fully match the fal key shape so a credential for some OTHER
    service (`user:password`, `sid:token`, …) is never adopted and sent to fal.ai."""
    m = FAL_KEY_ASSIGN_RE.search(text)
    if m:
        return m.group(1)
    if labeled_only:
        return None
    m = FAL_KEY_RE.search(text)
    if m:
        return m.group(0)
    if name_hinted and FAL_KEY_RE.fullmatch(text.strip()):
        return text.strip()
    return None


def _autoload_fal_keys():
    """If FAL_KEY isn't in the environment, find it in a local text file the user saved — WORKING
    FOLDER first, then the home dir — so a non-technical user isn't asked for a key they've already
    dropped in a file. In the working folder the filename does NOT matter (users rarely use `.env`):
    the key is detected by CONTENT — a `FAL_KEY=…` line, or a bare token matching fal's key shape.
    In the HOME dir only name-hinted files (fal/key/api/env) are read, and only an explicit
    `FAL_KEY=…` line is accepted — never a bare token, so other services' credentials that live in
    $HOME can't be mistaken for a fal key. Local-only; nothing fetched or sent; env vars always win."""
    if os.environ.get("FAL_KEY"):
        return
    exts = {".txt", ".env", ".cfg", ".ini", ".text", ""}
    for d in (Path.cwd(), Path.home()):
        try:
            files = [p for p in sorted(d.iterdir()) if p.is_file()]
        except OSError:
            continue
        hinted = [p for p in files if re.search(r"fal|key|api|\.env", p.name, re.I)]
        pool = hinted if d == Path.home() else hinted + [p for p in files if p not in hinted and p.suffix.lower() in exts]
        for p in pool:
            try:
                if p.stat().st_size > 100_000:
                    continue
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            key = _extract_fal_key(text, name_hinted=(p in hinted), labeled_only=(d == Path.home()))
            if key:
                os.environ["FAL_KEY"] = key
                am = FAL_ADMIN_ASSIGN_RE.search(text)
                if am and not os.environ.get("FAL_ADMIN_KEY"):
                    os.environ["FAL_ADMIN_KEY"] = am.group(1)
                print(f"  using FAL_KEY found in {p}", file=sys.stderr)
                return


def _require_fal_key():
    _autoload_fal_keys()
    if not os.environ.get("FAL_KEY"):
        sys.exit(
            "ERROR: FAL_KEY is not set, and no key file was found in this folder or your home dir.\n"
            "Set the env var, or save it in a text file in this folder (any name) containing a line\n"
            "FAL_KEY=your-key or the raw id:secret key. No image was generated (no data left this machine)."
        )


def _import_deps():
    try:
        import fal_client  # noqa: F401
        import requests  # noqa: F401
    except ImportError as e:
        sys.exit(f"ERROR: missing dependency ({e.name}). Install with: pip install fal-client requests")
    import fal_client
    import requests
    return fal_client, requests


def _unit_price(model, requests):
    key = os.environ.get("FAL_KEY", "")
    try:
        r = requests.get(f"{FAL_API}/models/pricing", params={"endpoint_id": model}, headers={"Authorization": f"Key {key}"}, timeout=20)
        if r.status_code != 200:
            return None
        prices = r.json().get("prices") or []
        match = next((p for p in prices if p.get("endpoint_id") == model), prices[0] if prices else None)
        if not match:
            return None
        return float(match["unit_price"]), str(match.get("unit", "")).lower(), match.get("currency", "USD")
    except Exception:
        return None


def _read_dims(path):
    try:
        with open(path, "rb") as f:
            head = f.read(26)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
            if head[:2] != b"\xff\xd8":
                return None
            f.seek(2)
            b = f.read()
        i = 0
        sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
        while i < len(b) - 9:
            if b[i] != 0xFF:
                i += 1
                continue
            marker = b[i + 1]
            if marker in sof:
                return int.from_bytes(b[i + 7:i + 9], "big"), int.from_bytes(b[i + 5:i + 7], "big")
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            i += 2 + int.from_bytes(b[i + 2:i + 4], "big")
    except Exception:
        return None
    return None


def _compute_cost(model, unit_info, outputs, arguments=None):
    n = max(1, len(outputs))
    arguments = arguments or {}
    if unit_info:
        unit_price, unit, currency = unit_info
        if "megapixel" in unit or unit in ("mp", "megapixels"):
            mp, known = 0.0, True
            for out in outputs:
                if out.get("w") and out.get("h"):
                    mp += (out["w"] * out["h"]) / 1_000_000
                else:
                    known = False
            if known and mp > 0:
                return unit_price * mp, currency, f"{mp:.2f} MP x ${unit_price}/MP", False
            return unit_price * n, currency, f"~{n} MP (dims unknown) x ${unit_price}/MP", False
        if unit in ("image", "images", "generation", "generations", "request", "requests"):
            resolution = str(arguments.get("resolution", "")).upper()
            multiplier = 2.0 if "nano-banana" in model and resolution == "4K" else 1.0
            cost = unit_price * n * multiplier
            surcharge = f" (×{multiplier:.0f} for {resolution})" if multiplier != 1.0 else ""
            return cost, currency, f"{n} x ${unit_price}/{unit.rstrip('s')}{surcharge}", multiplier == 1.0
        if "second" in unit or "compute" in unit:
            return None, currency, f"billed per compute-second (~${unit_price}/s); run time not in API response", False
        return unit_price * n, currency, f"{n} x ${unit_price}/{unit or 'call'}", False
    approx = APPROX_COST_USD.get(model)
    if approx is not None:
        multiplier = 2.0 if "nano-banana" in model and str(arguments.get("resolution", "")).upper() == "4K" else 1.0
        return approx * n * multiplier, "USD", f"{n} x ~${approx} (offline estimate)" + (" ×2 for 4K" if multiplier != 1 else ""), False
    return None, "USD", "unknown", False


def _balance(requests):
    admin = os.environ.get("FAL_ADMIN_KEY")
    if not admin:
        return None, "set FAL_ADMIN_KEY (a fal Admin key) to show balance"
    try:
        r = requests.get(f"{FAL_API}/account/billing", params={"expand": "credits"}, headers={"Authorization": f"Key {admin}"}, timeout=20)
        if r.status_code == 403:
            return None, "FAL_ADMIN_KEY is not an Admin key (billing returned 403)"
        if r.status_code != 200:
            return None, f"billing HTTP {r.status_code}"
        credits = r.json().get("credits") or {}
        bal = credits.get("current_balance")
        if bal is None:
            return None, "no balance in billing response"
        return (float(bal), credits.get("currency", "USD")), None
    except Exception as e:
        return None, f"balance check failed: {e}"


def _cost_log_path(explicit):
    return Path(explicit).expanduser() if explicit else Path.cwd() / DEFAULT_COST_LOG


def _read_cost_log(path):
    entries = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                entries.append(json.loads(line))
            except Exception:
                pass
    return entries


def _log_cost(path, entry):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _append_run_log(run_log, entry):
    """Append a human-readable markdown audit block for one call."""
    path = Path(run_log).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    args = entry.get("arguments") or {}
    lines = [f"## {entry.get('time')} — {entry.get('command') or 'run'}", ""]
    lines.append(f"- **Model:** `{entry.get('model')}`")
    inputs = entry.get("input_images") or []
    if inputs:
        lines.append("- **Input image(s):** " + ", ".join(f"`{p}`" for p in inputs))
    for o in entry.get("outputs") or []:
        dims = f" ({o.get('w')}x{o.get('h')})" if o.get("w") and o.get("h") else ""
        lines.append(f"- **Output:** `{o.get('path')}`{dims}")
    if "prompt" in args:
        lines.append(f"- **Prompt:** {args.get('prompt')}")
    if args.get("seed") is not None:
        lines.append(f"- **Seed:** {args.get('seed')}")
    other = {k: v for k, v in args.items() if k not in ("prompt", "seed")}
    if other:
        lines.append(f"- **Arguments:** `{json.dumps(other, ensure_ascii=False)}`")
    if entry.get("duration") is not None:
        lines.append(f"- **Duration:** {entry.get('duration')}s")
    cost = entry.get("cost")
    cost_str = ("~" + _money(cost, entry.get("currency", "USD"))) if cost is not None else (entry.get("basis") or "unknown")
    lines.append(f"- **Cost:** {cost_str} ({entry.get('basis')})")
    lines.append("")
    with path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _session_total(path):
    entries = _read_cost_log(path)
    total, currency, priced = 0.0, "USD", 0
    for e in entries:
        if e.get("cost") is not None:
            total += float(e["cost"])
            currency = e.get("currency", currency)
            priced += 1
    return total, currency, len(entries), priced


def _resolve_image(ref, fal_client):
    if ref.startswith(("http://", "https://", "data:")):
        return ref
    p = Path(ref).expanduser()
    if not p.is_file():
        sys.exit(f"ERROR: --image not found locally and not a URL: {ref}")
    print(f"  uploading {p.name} to fal storage…", file=sys.stderr)
    return fal_client.upload_file(str(p))


def _aspect_args(model, aspect):
    if not aspect:
        return {}
    if "kontext" in model:
        print(f"  note: {model} keeps the input image's aspect; --aspect {aspect} ignored", file=sys.stderr)
        return {}
    if "flux" in model or "gpt-image" in model or "recraft" in model:
        preset = FLUX_SIZE_FROM_ASPECT.get(aspect)
        if preset:
            return {"image_size": preset}
        print(f"  note: aspect {aspect} has no size preset; leaving model default", file=sys.stderr)
        return {}
    return {"aspect_ratio": aspect}


def _parse_scalar(v):
    stripped = v.strip()
    if stripped[:1] in ("{", "[", '"') or stripped in ("true", "false", "null"):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as e:
            sys.exit(f"ERROR: invalid JSON value for --arg: {v}\n  {e}")
    lv = stripped.lower()
    if lv in ("true", "false"):
        return lv == "true"
    try:
        return int(stripped)
    except ValueError:
        try:
            return float(stripped)
        except ValueError:
            return v


def _parse_extra_args(pairs, json_blobs=None):
    out = {}
    for blob in json_blobs or []:
        try:
            parsed = json.loads(blob)
        except json.JSONDecodeError as e:
            sys.exit(f"ERROR: --arg-json must be a JSON object, got invalid JSON:\n  {e}")
        if not isinstance(parsed, dict):
            sys.exit('ERROR: --arg-json must parse to a JSON object')
        out.update(parsed)
    for pair in pairs or []:
        if "=" not in pair:
            sys.exit(f"ERROR: --arg must be key=value, got: {pair}")
        k, v = pair.split("=", 1)
        k = k.strip()
        if not k:
            sys.exit(f"ERROR: --arg key is empty in: {pair}")
        out[k] = _parse_scalar(v)
    return out


def _redact_url_arguments(arguments):
    return {k: ("[omitted from log; see input_images]" if k in URL_ARGUMENT_KEYS else v) for k, v in arguments.items()}


def _collect_image_objs(result):
    if isinstance(result, dict):
        if result.get("images"):
            return result["images"]
        if result.get("image"):
            return [result["image"]]
    return []


def _download(images, out_dir, name, requests):
    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    saved = []
    multiple = len(images) > 1
    for i, img in enumerate(images, 1):
        url = img.get("url") if isinstance(img, dict) else None
        if not url:
            continue
        ct = img.get("content_type", "") if isinstance(img, dict) else ""
        ext = ".jpg" if "jpeg" in ct or "jpg" in ct else ".webp" if "webp" in ct else ".png"
        dest = out / (f"{name}_{i}{ext}" if multiple else f"{name}{ext}")
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        w, h = img.get("width"), img.get("height")
        if not (w and h):
            dims = _read_dims(dest)
            if dims:
                w, h = dims
        saved.append({"path": dest, "w": w, "h": h})
    return saved


def _run(model, arguments, out_dir, name, cost_log=None, run_log=None, verbose=False, metadata=None):
    fal_client, requests = _import_deps()
    _require_fal_key()
    try:
        result = fal_client.subscribe(model, arguments=arguments, with_logs=verbose)
    except Exception as e:
        sys.exit(f"ERROR: the fal.ai call failed:\n  {e}\n\nNo image was generated.")
    saved = _download(_collect_image_objs(result), out_dir, name, requests)
    if not saved:
        sys.exit("ERROR: no image returned.")
    for o in saved:
        dims = f" ({o['w']}x{o['h']})" if o.get("w") and o.get("h") else ""
        print(f"Saved: {o['path']}{dims}")
    cost, currency, basis, exact = _compute_cost(model, _unit_price(model, requests), saved, arguments)
    logp = _cost_log_path(cost_log)
    entry = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "command": (metadata or {}).get("command"),
        "model": model,
        "arguments": _redact_url_arguments(arguments),
        "input_images": (metadata or {}).get("input_images", []),
        "outputs": [{"path": str(o["path"]), "w": o.get("w"), "h": o.get("h")} for o in saved],
        "cost": round(cost, 4) if cost is not None else None,
        "currency": currency,
        "basis": basis,
        "exact": exact,
    }
    _log_cost(logp, entry)
    if run_log:
        _append_run_log(run_log, entry)
    print(f"Cost this step: {'~' + _money(cost, currency) if cost is not None else basis}")
    total, tcur, _, n_priced = _session_total(logp)
    print(f"Session total ({n_priced} priced call(s)): ~{_money(total, tcur)} · log: {logp}")
    bal, why = _balance(requests)
    if bal is not None:
        print(f"Account balance: {_money(bal[0], bal[1])}")
    elif why:
        print(f"(balance not shown — {why})")
    return saved


def _extra_args(a):
    return _parse_extra_args(a.arg, getattr(a, "arg_json", None))


def _dry_run(command, model, arguments, *, input_images=None, num_outputs=1, out_dir="_workings", name="image"):
    dummy = [{"path": f"{out_dir}/{name}_{i}.png" if num_outputs > 1 else f"{out_dir}/{name}.png"} for i in range(1, max(1, num_outputs) + 1)]
    cost, currency, basis, _ = _compute_cost(model, None, dummy, arguments)
    print("DRY RUN — no fal.ai call, no upload, no download, no charge, no log write.")
    print(f"Command: {command}")
    print(f"Model:   {model}")
    if input_images:
        print("Input image(s):")
        for img in input_images:
            print(f"  - {img}")
    print("Arguments:")
    print(json.dumps(_redact_url_arguments(arguments), ensure_ascii=False, indent=2))
    if cost is None:
        print(f"Estimated cost: unknown [{basis}]")
    else:
        print(f"Estimated cost: ~{_money(cost, currency)} [{basis}] (offline estimate; dashboard is authoritative)")
    print("Planned output base:", str(Path(out_dir) / name))


def cmd_generate(a):
    if a.num < 1:
        sys.exit("ERROR: --num must be at least 1")
    model = a.model or DEFAULT_MODELS["generate"]
    args = {"prompt": a.prompt, "num_images": a.num}
    args.update(_aspect_args(model, a.aspect))
    if a.seed is not None:
        args["seed"] = a.seed
    args.update(_extra_args(a))
    if a.dry_run:
        _dry_run("generate", model, args, num_outputs=a.num, out_dir=a.out_dir, name=a.name)
        return
    _run(model, args, a.out_dir, a.name, a.cost_log, a.run_log, a.verbose, {"command": "generate"})


def cmd_edit(a):
    if a.num < 1:
        sys.exit("ERROR: --num must be at least 1")
    model = a.model or DEFAULT_MODELS["edit"]
    if model in SINGLE_IMAGE_ARG_MODELS and len(a.image) != 1:
        sys.exit(f"ERROR: {model} accepts exactly one --image.")
    if model in SINGLE_IMAGE_ARG_MODELS and a.num > 1:
        sys.exit(f"ERROR: {model} does not accept --num/num_images.")
    args = {"prompt": a.prompt}
    if a.num > 1:
        args["num_images"] = a.num
    if model in SINGLE_IMAGE_ARG_MODELS:
        args["image_url"] = "[uploaded image URL]" if a.dry_run else None
    else:
        args["image_urls"] = ["[uploaded image URL]" for _ in a.image] if a.dry_run else None
    args.update(_aspect_args(model, a.aspect))
    if a.seed is not None:
        args["seed"] = a.seed
    args.update(_extra_args(a))
    if a.dry_run:
        _dry_run("edit", model, args, input_images=a.image, num_outputs=a.num, out_dir=a.out_dir, name=a.name)
        return
    fal_client, _ = _import_deps()
    _require_fal_key()
    urls = [_resolve_image(ref, fal_client) for ref in a.image]
    if model in SINGLE_IMAGE_ARG_MODELS:
        args["image_url"] = urls[0]
    else:
        args["image_urls"] = urls
    _run(model, args, a.out_dir, a.name, a.cost_log, a.run_log, a.verbose, {"command": "edit", "input_images": a.image})


def cmd_upscale(a):
    model = a.model or DEFAULT_MODELS["upscale"]
    args = {"image_url": "[uploaded image URL]" if a.dry_run else None}
    if a.factor is not None:
        args["upscale_factor"] = a.factor
    args.update(_extra_args(a))
    if a.dry_run:
        _dry_run("upscale", model, args, input_images=[a.image], out_dir=a.out_dir, name=a.name)
        return
    fal_client, _ = _import_deps()
    _require_fal_key()
    args["image_url"] = _resolve_image(a.image, fal_client)
    _run(model, args, a.out_dir, a.name, a.cost_log, a.run_log, a.verbose, {"command": "upscale", "input_images": [a.image]})


def cmd_removebg(a):
    model = a.model or DEFAULT_MODELS["removebg"]
    args = {"image_url": "[uploaded image URL]" if a.dry_run else None}
    args.update(_extra_args(a))
    if a.dry_run:
        _dry_run("removebg", model, args, input_images=[a.image], out_dir=a.out_dir, name=a.name)
        return
    fal_client, _ = _import_deps()
    _require_fal_key()
    args["image_url"] = _resolve_image(a.image, fal_client)
    _run(model, args, a.out_dir, a.name, a.cost_log, a.run_log, a.verbose, {"command": "removebg", "input_images": [a.image]})


def cmd_costs(a):
    logp = _cost_log_path(a.cost_log)
    if a.reset:
        if logp.is_file():
            logp.unlink()
        print(f"Cost log cleared: {logp}")
        return
    entries = _read_cost_log(logp)
    if not entries:
        print(f"No cost log yet at {logp}")
        return
    total, currency = 0.0, "USD"
    print(f"Cost summary — {logp}\n")
    for e in entries:
        c = e.get("cost")
        if c is not None:
            total += float(c)
            currency = e.get("currency", currency)
            cstr = f"~{_money(float(c), currency)}"
        else:
            cstr = "n/a"
        print(f"  {e.get('time', ''):20}  {e.get('command', ''):9}  {e.get('model', ''):32}  {cstr:>12}  [{e.get('basis', '')}]")
    print(f"\n  TOTAL: ~{_money(total, currency)}")


def build_parser():
    p = argparse.ArgumentParser(description="fal.ai image helper — generate / edit / upscale.")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp, default_name):
        sp.add_argument("--model")
        sp.add_argument("--out-dir", default="_workings")
        sp.add_argument("--name", default=default_name)
        sp.add_argument("--arg", action="append")
        sp.add_argument("--arg-json", action="append")
        sp.add_argument("--cost-log")
        sp.add_argument("--run-log")
        sp.add_argument("--verbose", action="store_true")
        sp.add_argument("--dry-run", action="store_true", help="Print arguments/cost estimate without calling fal.ai or requiring FAL_KEY.")

    g = sub.add_parser("generate")
    g.add_argument("--prompt", required=True)
    g.add_argument("--aspect")
    g.add_argument("--num", type=int, default=1)
    g.add_argument("--seed", type=int)
    common(g, "image")
    g.set_defaults(func=cmd_generate)

    e = sub.add_parser("edit")
    e.add_argument("--prompt", required=True)
    e.add_argument("--image", action="append", required=True)
    e.add_argument("--aspect")
    e.add_argument("--num", type=int, default=1)
    e.add_argument("--seed", type=int)
    common(e, "image_edit")
    e.set_defaults(func=cmd_edit)

    u = sub.add_parser("upscale")
    u.add_argument("--image", required=True)
    u.add_argument("--factor", type=int)
    common(u, "image_upscaled")
    u.set_defaults(func=cmd_upscale)

    rb = sub.add_parser("removebg")
    rb.add_argument("--image", required=True)
    common(rb, "image_nobg")
    rb.set_defaults(func=cmd_removebg)

    c = sub.add_parser("costs")
    c.add_argument("--cost-log")
    c.add_argument("--reset", action="store_true")
    c.set_defaults(func=cmd_costs)

    s = sub.add_parser("search", help="Search the live fal model catalogue by keyword (with pricing).")
    s.add_argument("query", help="Search term, e.g. 'upscale', 'portrait', 'text to image'.")
    s.add_argument("--category", help="Filter by category substring, e.g. image-to-image, text-to-image.")
    s.add_argument("--limit", type=int, default=15, help="Max results (default 15).")
    s.set_defaults(func=cmd_search)

    rec = sub.add_parser("recommend", help="Show the recommended default model per stage, with live pricing.")
    rec.set_defaults(func=cmd_recommend)
    return p


def _search_models(query, requests, limit=15, category=None):
    """Live keyword search of the fal model catalogue (GET /v1/models?query=). Read-only, no spend."""
    key = os.environ.get("FAL_KEY", "")
    try:
        r = requests.get(f"{FAL_API}/models", params={"query": query},
                         headers={"Authorization": f"Key {key}"}, timeout=20)
        if r.status_code != 200:
            return []
    except Exception:
        return []
    out = []
    for m in (r.json().get("models") or []):
        md = m.get("metadata") or {}
        if md.get("status") and md.get("status") != "active":
            continue
        if category and category.lower() not in str(md.get("category", "")).lower():
            continue
        out.append({
            "endpoint_id": m.get("endpoint_id", ""),
            "name": md.get("display_name", ""),
            "category": md.get("category", ""),
            "license": md.get("license_type", ""),
            "desc": " ".join(str(md.get("description", "")).split()),
        })
        if len(out) >= limit:
            break
    return out


def _prices_batch(endpoint_ids, requests):
    """Live pricing for several endpoints in one call → {endpoint_id: (unit_price, unit)}."""
    key = os.environ.get("FAL_KEY", "")
    ids = [e for e in dict.fromkeys(endpoint_ids) if e]
    out = {}
    if not ids:
        return out
    try:
        params = [("endpoint_id", e) for e in ids]
        r = requests.get(f"{FAL_API}/models/pricing", params=params,
                         headers={"Authorization": f"Key {key}"}, timeout=20)
        if r.status_code == 200:
            for p in (r.json().get("prices") or []):
                out[p.get("endpoint_id")] = (p.get("unit_price"), str(p.get("unit", "")))
    except Exception:
        pass
    return out


def _price_str(pr):
    return f"${pr[0]}/{pr[1]}" if pr and pr[0] is not None else "price n/a"


def cmd_search(a):
    fal_client, requests = _import_deps()
    _require_fal_key()          # discovery needs the key for the Authorization header (read-only, no spend)
    models = _search_models(a.query, requests, a.limit, a.category)
    if not models:
        print(f"No active models matched '{a.query}'. Browse the full catalogue at https://fal.ai/models")
        return
    prices = _prices_batch([m["endpoint_id"] for m in models], requests)
    print(f"fal models matching '{a.query}' (live):\n")
    for m in models:
        print(f"  {m['endpoint_id']}   [{_price_str(prices.get(m['endpoint_id']))}]")
        meta = "  ·  ".join(x for x in (m["name"], m["category"], m["license"]) if x)
        if meta:
            print(f"      {meta}")
        if m["desc"]:
            print(f"      {m['desc'][:130]}")
    print("\nDefault-first: reach for these only if the tuned defaults fall short (see SKILL.md). "
          "Full catalogue: https://fal.ai/models")


def cmd_recommend(a):
    fal_client, requests = _import_deps()
    _require_fal_key()
    prices = _prices_batch(list(DEFAULT_MODELS.values()), requests)
    print("Recommended default per stage for this skill (live pricing):\n")
    for stage, mid in DEFAULT_MODELS.items():
        print(f"  {stage:9} → {mid}   [{_price_str(prices.get(mid))}]")
    print("\nThese are the tuned, cost-balanced defaults — stick with them unless a result is genuinely\n"
          "unsatisfactory. To explore alternatives, search the catalogue with:  search <term>")


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
