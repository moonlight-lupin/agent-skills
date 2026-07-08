#!/usr/bin/env python3
"""falvid.py — fal.ai video helper for Clips Studio.

Supports text-to-video (`generate`), image-to-video (`animate`), camera moves over a
still (`camera`), cost summaries, and `--dry-run` preflight. Dry-run prints the
model, arguments and estimated cost without requiring FAL_KEY, uploading images,
calling fal.ai, writing logs, or spending credits.
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
DEFAULT_COST_LOG = "_falvid-costs.jsonl"

DEFAULT_MODELS = {
    "generate": "fal-ai/wan/v2.2-a14b/text-to-video",
    "animate": "fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
    "camera": "fal-ai/bytedance/seedance/v1.5/pro/image-to-video",
}

VIDEO_PRICING = {
    "fal-ai/kling-video/v2.5-turbo/pro/image-to-video": {"kind": "per_second", "rate": 0.07},
    "fal-ai/kling-video/v3/pro/image-to-video": {"kind": "per_second", "rate": 0.15},
    "fal-ai/kling-video/v3/4k/image-to-video": {"kind": "per_second", "rate": 0.42},
    "fal-ai/veo3.1/image-to-video": {"kind": "per_second", "rate": 0.20, "audio_rate": 0.40, "k4_mult": 2.0},
    "fal-ai/veo3.1/fast/image-to-video": {"kind": "per_second", "rate": 0.10, "audio_rate": 0.20, "k4_mult": 2.0},
    "fal-ai/bytedance/seedance/v1.5/pro/image-to-video": {"kind": "per_clip", "rate": 0.26, "base_secs": 5, "note": "~720p; scales roughly with tokens"},
    "fal-ai/minimax/hailuo-2.3/pro/image-to-video": {"kind": "per_clip", "rate": 0.49, "base_secs": 5},
    "fal-ai/wan/v2.2-a14b/text-to-video": {"kind": "per_second", "rate": 0.10},
    "fal-ai/veo3.1": {"kind": "per_second", "rate": 0.20, "audio_rate": 0.40, "k4_mult": 2.0},
    "fal-ai/kling-video/v2.5-turbo/pro/text-to-video": {"kind": "per_second", "rate": 0.224, "audio_rate": 0.28},
    "fal-ai/kling-video/v3/pro/text-to-video": {"kind": "per_second", "rate": 0.224, "audio_rate": 0.336},
    "fal-ai/bytedance/seedance/v1.5/pro/text-to-video": {"kind": "per_clip", "rate": 0.26, "base_secs": 5},
    "fal-ai/minimax/hailuo-2.3/pro/text-to-video": {"kind": "per_clip", "rate": 0.49, "base_secs": 5},
    "fal-ai/wan-pro": {"kind": "per_second", "rate": 0.10},
    # Corrected: LTX-2 is estimated on output-frame megapixels, not one still frame.
    # 5s at 1080p and 24fps ≈ 248.8 MP; at $0.0018/MP this is ≈ $0.448.
    "fal-ai/ltx-2-19b/text-to-video": {"kind": "per_megapixel", "rate": 0.0018, "note": "~$0.0018/output-frame MP; 5s 1080p@24fps ≈ 248.8 MP → ~$0.448"},
}

START_IMAGE_MODELS = ("kling-video/v3",)
AUDIO_MODELS = ("veo3.1", "kling-video/v3", "seedance/v1.5")
CAMERA_FIXED_MODELS = ("seedance",)
DEFAULT_RESOLUTION = {"fal-ai/bytedance/seedance/v1.5/pro/image-to-video": "720p"}
MAX_DURATION = {
    "kling-video/v2.5-turbo": 10,
    "kling-video/v3": 15,
    "seedance/v1.5": 12,
    "veo3.1": 8,
    "hailuo-2.3": 5,
    "wan/v2.2": 5,
    "ltx-2": 10,
}
URL_ARGUMENT_KEYS = {"image_url", "start_image_url", "end_image_url", "tail_image_url"}
CAMERA_MOVES = {
    "push-in": "slow, gentle dolly push-in toward the subject; smooth and steady",
    "pull-out": "slow dolly pull-out revealing a little more of the existing space; smooth and steady",
    "pan-left": "slow pan to the left across the scene; smooth and steady",
    "pan-right": "slow pan to the right across the scene; smooth and steady",
    "tilt-up": "slow tilt upward; smooth and steady",
    "tilt-down": "slow tilt downward; smooth and steady",
    "orbit": "slow, shallow orbit around the subject; subtle, smooth and steady",
    "crane-up": "slow crane/pedestal up; smooth and steady",
}


def _money(x, currency="USD"):
    return f"${x:,.4f}" if currency == "USD" else f"{x:,.4f} {currency}"


def _model_has(model, needles):
    return any(n in model for n in needles)


def _check_duration(model, duration):
    for needle, max_s in MAX_DURATION.items():
        if needle in model and duration > max_s:
            sys.exit(f"ERROR: --duration {duration}s exceeds the {max_s}s maximum for {model}.")


def _video_cost(model, duration, arguments):
    arguments = arguments or {}
    spec = VIDEO_PRICING.get(model)
    if not spec:
        return None, f"no rate on file for {model} — see references/fal-video-models.md / fal dashboard", False
    if spec["kind"] == "per_second":
        rate = spec["rate"]
        notes = []
        if arguments.get("generate_audio") and spec.get("audio_rate"):
            rate = spec["audio_rate"]
            notes.append("audio")
        if str(arguments.get("resolution", "")).upper() == "4K" and spec.get("k4_mult"):
            rate *= spec["k4_mult"]
            notes.append("4K")
        secs = int(duration) if duration else 5
        tag = f" ({', '.join(notes)})" if notes else ""
        return rate * secs, f"{secs}s x ${rate}/s{tag}", False
    if spec["kind"] == "per_megapixel":
        secs = int(duration) if duration else 5
        mp_per_frame = 1920 * 1080 / 1_000_000
        fps = 24
        total_mp = mp_per_frame * fps * secs
        extra = f" — {spec['note']}" if spec.get("note") else ""
        return spec["rate"] * total_mp, f"{secs}s @ ~${spec['rate']}/MP, ~{total_mp:.1f} output-frame MP (1080p×{fps}fps){extra}", False
    base = spec.get("base_secs", 5)
    secs = int(duration) if duration else base
    extra = f" — {spec['note']}" if spec.get("note") else ""
    return spec["rate"] * (secs / base), f"${spec['rate']} base clip × {secs}/{base}s{extra}", False


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
            sys.exit('ERROR: --arg-json must parse to a JSON object, e.g. --arg-json \'{"negative_prompt":"blurry"}\'')
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
        lines.append(f"- **Output:** `{o.get('path')}`")
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
            "FAL_KEY=your-key or the raw id:secret key. No video was generated (no data left this machine)."
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


def _resolve_image(ref, fal_client):
    if ref.startswith(("http://", "https://", "data:")):
        return ref
    p = Path(ref).expanduser()
    if not p.is_file():
        sys.exit(f"ERROR: --image not found locally and not a URL: {ref}")
    print(f"  uploading {p.name} to fal storage…", file=sys.stderr)
    return fal_client.upload_file(str(p))


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


def _download(videos, out_dir, name, requests):
    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    saved = []
    multiple = len(videos) > 1
    for i, vid in enumerate(videos, 1):
        url = vid.get("url") if isinstance(vid, dict) else None
        if not url:
            continue
        ext = ".webm" if "webm" in (vid.get("content_type", "") if isinstance(vid, dict) else "") else ".mp4"
        dest = out / (f"{name}_{i}{ext}" if multiple else f"{name}{ext}")
        resp = requests.get(url, timeout=600)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        saved.append({"path": dest, "bytes": dest.stat().st_size})
    return saved


def _run(model, arguments, duration, out_dir, name, cost_log=None, run_log=None, verbose=False, metadata=None):
    fal_client, requests = _import_deps()
    _require_fal_key()
    try:
        result = fal_client.subscribe(model, arguments=arguments, with_logs=verbose)
    except Exception as e:
        sys.exit(f"ERROR: the fal.ai call failed:\n  {e}\n\nNo video was generated.")
    videos = []
    if isinstance(result, dict):
        videos = result.get("videos") or ([result["video"]] if result.get("video") else [])
    if not videos:
        sys.exit("ERROR: no video returned.")
    saved = _download(videos, out_dir, name, requests)
    for o in saved:
        print(f"Saved: {o['path']}")
    cost, basis, exact = _video_cost(model, duration, arguments)
    logp = _cost_log_path(cost_log)
    entry = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "command": (metadata or {}).get("command"),
        "model": model,
        "arguments": _redact_url_arguments(arguments),
        "input_images": (metadata or {}).get("input_images", []),
        "outputs": [{"path": str(o["path"]), "bytes": o.get("bytes")} for o in saved],
        "duration": duration,
        "cost": round(cost, 4) if cost is not None else None,
        "currency": "USD",
        "basis": basis,
        "exact": exact,
    }
    _log_cost(logp, entry)
    if run_log:
        _append_run_log(run_log, entry)
    if cost is None:
        print(f"Est. cost this clip: not on file — {basis}")
    else:
        print(f"Est. cost this clip: ~{_money(cost)} [{basis}] (estimate — dashboard is authoritative)")
    total, tcur, _, n_priced = _session_total(logp)
    print(f"Session total ({n_priced} estimated call(s)): ~{_money(total, tcur)} · log: {logp}")
    bal, why = _balance(requests)
    if bal is not None:
        print(f"Account balance: {_money(bal[0], bal[1])}")
    elif why:
        print(f"(balance not shown — {why})")
    return saved


def _extra_args(a):
    return _parse_extra_args(a.arg, getattr(a, "arg_json", None))


def _dry_run(command, model, arguments, duration, *, input_images=None, out_dir="_workings", name="vid"):
    cost, basis, _ = _video_cost(model, duration, arguments)
    print("DRY RUN — no fal.ai call, no upload, no download, no charge, no log write.")
    print(f"Command:  {command}")
    print(f"Model:    {model}")
    print(f"Duration: {duration}s")
    if input_images:
        print("Input image(s):")
        for img in input_images:
            print(f"  - {img}")
    print("Arguments:")
    print(json.dumps(_redact_url_arguments(arguments), ensure_ascii=False, indent=2))
    if cost is None:
        print(f"Estimated cost: unknown [{basis}]")
    else:
        print(f"Estimated cost: ~{_money(cost)} [{basis}] (estimate; dashboard is authoritative)")
    print("Planned output base:", str(Path(out_dir) / name))


def _build_video_args(a, model, prompt, fal_client=None, dry_run=False):
    img_key = "start_image_url" if _model_has(model, START_IMAGE_MODELS) else "image_url"
    url = "[uploaded image URL]" if dry_run else _resolve_image(a.image, fal_client)
    args = {"prompt": prompt, img_key: url, "duration": str(a.duration) if "kling-video" in model else a.duration}
    res = a.resolution or DEFAULT_RESOLUTION.get(model)
    if res:
        args["resolution"] = res
    if a.aspect:
        args["aspect_ratio"] = a.aspect
    if _model_has(model, AUDIO_MODELS):
        args["generate_audio"] = bool(a.audio)
    if a.seed is not None:
        args["seed"] = a.seed
    args.update(_extra_args(a))
    return url, args, a.duration


def cmd_generate(a):
    if a.duration < 1:
        sys.exit("ERROR: --duration must be at least 1 second")
    model = a.model or DEFAULT_MODELS["generate"]
    _check_duration(model, a.duration)
    args = {"prompt": a.prompt, "duration": str(a.duration) if "kling-video" in model else a.duration, "aspect_ratio": a.aspect or "16:9"}
    res = a.resolution or DEFAULT_RESOLUTION.get(model)
    if res:
        args["resolution"] = res
    if _model_has(model, AUDIO_MODELS):
        args["generate_audio"] = bool(a.audio)
    if a.seed is not None:
        args["seed"] = a.seed
    args.update(_extra_args(a))
    if a.dry_run:
        _dry_run("generate", model, args, a.duration, out_dir=a.out_dir, name=a.name)
        return
    _run(model, args, a.duration, a.out_dir, a.name, a.cost_log, a.run_log, a.verbose, {"command": "generate"})


def cmd_animate(a):
    if a.duration < 1:
        sys.exit("ERROR: --duration must be at least 1 second")
    model = a.model or DEFAULT_MODELS["animate"]
    _check_duration(model, a.duration)
    if a.dry_run:
        _, args, dur = _build_video_args(a, model, a.prompt, dry_run=True)
        _dry_run("animate", model, args, dur, input_images=[a.image], out_dir=a.out_dir, name=a.name)
        return
    fal_client, _ = _import_deps()
    _require_fal_key()
    _, args, dur = _build_video_args(a, model, a.prompt, fal_client=fal_client)
    _run(model, args, dur, a.out_dir, a.name, a.cost_log, a.run_log, a.verbose, {"command": "animate", "input_images": [a.image]})


def cmd_camera(a):
    if a.duration < 1:
        sys.exit("ERROR: --duration must be at least 1 second")
    model = a.model or DEFAULT_MODELS["camera"]
    _check_duration(model, a.duration)
    parts = []
    if a.move:
        if a.move not in CAMERA_MOVES:
            sys.exit(f"ERROR: --move must be one of: {', '.join(CAMERA_MOVES)}")
        parts.append(CAMERA_MOVES[a.move])
    if a.prompt:
        parts.append(a.prompt)
    if not parts:
        sys.exit("ERROR: give a --move and/or a --prompt describing the camera motion.")
    prompt = ". ".join(parts)
    if a.dry_run:
        _, args, dur = _build_video_args(a, model, prompt, dry_run=True)
    else:
        fal_client, _ = _import_deps()
        _require_fal_key()
        _, args, dur = _build_video_args(a, model, prompt, fal_client=fal_client)
    if a.static:
        if _model_has(model, CAMERA_FIXED_MODELS):
            args["camera_fixed"] = True
        else:
            args["prompt"] += ". Static shot, locked-off camera, no camera movement."
    if a.dry_run:
        _dry_run("camera", model, args, dur, input_images=[a.image], out_dir=a.out_dir, name=a.name)
        return
    _run(model, args, dur, a.out_dir, a.name, a.cost_log, a.run_log, a.verbose, {"command": "camera", "input_images": [a.image]})


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
        print(f"  {e.get('time', ''):20}  {e.get('command', ''):8}  {e.get('model', ''):48}  {cstr:>12}  [{e.get('basis', '')}]")
    print(f"\n  TOTAL: ~{_money(total, currency)} (estimates — dashboard authoritative)")


def build_parser():
    p = argparse.ArgumentParser(description="fal.ai VIDEO helper — generate / animate / camera.")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp, default_name, image=True):
        if image:
            sp.add_argument("--image", required=True)
        sp.add_argument("--duration", type=int, default=5)
        sp.add_argument("--resolution")
        sp.add_argument("--aspect")
        sp.add_argument("--audio", action="store_true")
        sp.add_argument("--seed", type=int)
        sp.add_argument("--model")
        sp.add_argument("--out-dir", default="_workings")
        sp.add_argument("--name", default=default_name)
        sp.add_argument("--arg", action="append")
        sp.add_argument("--arg-json", action="append")
        sp.add_argument("--cost-log")
        sp.add_argument("--run-log")
        sp.add_argument("--verbose", action="store_true")
        sp.add_argument("--dry-run", action="store_true", help="Print arguments/cost estimate without calling fal.ai or requiring FAL_KEY.")

    gen = sub.add_parser("generate")
    gen.add_argument("--prompt", required=True)
    common(gen, "vid", image=False)
    gen.set_defaults(func=cmd_generate)

    an = sub.add_parser("animate")
    an.add_argument("--prompt", required=True)
    common(an, "vid")
    an.set_defaults(func=cmd_animate)

    cam = sub.add_parser("camera")
    cam.add_argument("--prompt")
    cam.add_argument("--move")
    cam.add_argument("--static", action="store_true")
    common(cam, "vid_camera")
    cam.set_defaults(func=cmd_camera)

    c = sub.add_parser("costs")
    c.add_argument("--cost-log")
    c.add_argument("--reset", action="store_true")
    c.set_defaults(func=cmd_costs)

    s = sub.add_parser("search", help="Search the live fal model catalogue by keyword (with pricing).")
    s.add_argument("query", help="Search term, e.g. 'video upscale', 'image to video', 'kling'.")
    s.add_argument("--category", help="Filter by category substring, e.g. text-to-video, image-to-video.")
    s.add_argument("--limit", type=int, default=15, help="Max results (default 15).")
    s.set_defaults(func=cmd_search)

    rec = sub.add_parser("recommend", help="Show the recommended default model per mode, with live pricing.")
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
    print("Recommended default per mode for this skill (live pricing):\n")
    for mode, mid in DEFAULT_MODELS.items():
        print(f"  {mode:9} → {mid}   [{_price_str(prices.get(mid))}]")
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
