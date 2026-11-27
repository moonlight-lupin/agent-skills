#!/usr/bin/env python3
"""dev-pipeline lanes: which model does which job on THIS machine.

The single home for lane resolution. Skills name roles (architect,
test-writer, coder, reviewer); this script turns them into lanes that exist
here, using the plugin's default config merged with machine and project
overrides (see config/lanes.default.toml).

Commands:
  detect   list every lane and whether it can run here
  resolve  pick the architect, test-writer, coder (escalation ladder) and the
           review panel for a tier; record coder switches in a ledger
  command  print the exact dispatch for one lane and role (secrets redacted)
  run      run that dispatch and write a result file
  doctor   check the configuration on this machine

Exit codes: 0 ok; 2 no lane can take a required role; 3 user decision needed
(ASK-USER); 4 refused (an env-routed provider's key is empty); 5 usage or
config error.

Stdlib only (Python 3.11+, tomllib).
"""
from __future__ import annotations

import argparse
import copy
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path

SCHEMA = "dev-pipeline-lanes.v1"
HERE = Path(__file__).resolve()
PLUGIN_ROOT = HERE.parents[3]
DEFAULT_CONFIG = HERE.parents[1] / "config" / "lanes.default.toml"
MACHINE_CANDIDATES = (
    "~/.hermes/dev-pipeline/lanes.toml",
    "~/.config/dev-pipeline/lanes.toml",
)
ROLES = ("architect", "test_writer", "coder")
OPTIONAL_ROLES = ("goldfish",)   # spec-review delegates; never block a round
REVIEW_ROLE = "reviewer"
READ_ONLY_ROLES = (REVIEW_ROLE, "goldfish")
ALL_ROLES = (*ROLES, *OPTIONAL_ROLES, REVIEW_ROLE)
RATE_LIMIT_RE = re.compile(r"\b(429|rate.?limit|too many requests|overloaded|529|402|quota)\b", re.I)


class ConfigError(Exception):
    pass


class Refused(Exception):
    pass


# --------------------------------------------------------------------------- config

def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def config_sources(explicit: list[str] | None, repo: str | None) -> list[tuple[Path, bool]]:
    """Returns (path, trusted) pairs. Only the bundled default, operator env,
    machine config and explicitly named files are trusted; the repo-local
    .dev-pipeline/lanes.toml is untrusted (see strip_untrusted)."""
    srcs: list[tuple[Path, bool]] = [(Path(DEFAULT_CONFIG), True)]
    env = os.environ.get("DEV_PIPELINE_LANES")
    if env:
        srcs.append((Path(env).expanduser(), True))
    else:
        for cand in MACHINE_CANDIDATES:
            p = Path(cand).expanduser()
            if p.is_file():
                srcs.append((p, True))
                break
    if repo:
        p = Path(repo) / ".dev-pipeline" / "lanes.toml"
        if p.is_file():
            srcs.append((p, False))
    for e in explicit or []:
        srcs.append((Path(e).expanduser(), True))
    return srcs


# A repository-provided .dev-pipeline/lanes.toml is UNTRUSTED input: any repo
# the pipeline runs in could otherwise launch an arbitrary executable as a
# reviewer (gate finding r2-C2). Untrusted sources may not define providers
# or new lanes and may only add advisory overrides (model, family, ...) to
# lanes already defined by trusted sources; execution vectors
# (binary/argv templates) are stripped even from trusted lane overrides.
EXEC_KEYS = {"binary", "review_argv", "code_argv"}
TRUSTED_ONLY_KEYS = {"providers"}


def strip_untrusted(data: dict, base_cfg: dict) -> dict:
    out = copy.deepcopy(data)
    for key in TRUSTED_ONLY_KEYS:
        out.pop(key, None)
    lanes = out.get("lanes")
    if isinstance(lanes, dict):
        known = (base_cfg.get("lanes") or {}).keys()
        for lid in list(lanes):
            lane = lanes[lid]
            if lid not in known:
                del lanes[lid]  # untrusted sources cannot define new lanes
            elif isinstance(lane, dict):
                for key in EXEC_KEYS:
                    lane.pop(key, None)
    return out


def load_config(explicit=None, repo=None) -> tuple[dict, list[str]]:
    cfg: dict = {}
    used = []
    for src, trusted in config_sources(explicit, repo):
        if not src.is_file():
            raise ConfigError(f"config file not found: {src}")
        try:
            data = tomllib.loads(src.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"{src}: {e}") from e
        if not trusted:
            data = strip_untrusted(data, cfg)
        cfg = deep_merge(cfg, data)
        used.append(str(src))
    validate(cfg)
    return cfg, used


def validate(cfg: dict) -> None:
    lanes = cfg.get("lanes", {})
    providers = cfg.get("providers", {})
    for lid, lane in lanes.items():
        via = lane.get("via")
        if via not in ("claude-code", "cli", "controller"):
            raise ConfigError(f"lane {lid}: via must be claude-code | cli | controller, got {via!r}")
        if via == "claude-code":
            prov = lane.get("provider", "anthropic")
            if prov not in providers:
                raise ConfigError(f"lane {lid}: unknown provider {prov!r}")
            pk = providers[prov].get("kind")
            if pk == "anthropic-compatible":
                for key in ("base_url", "auth_env"):
                    if not providers[prov].get(key):
                        raise ConfigError(f"provider {prov}: {key} is required")
                if not lane.get("model"):
                    raise ConfigError(
                        f"lane {lid}: an anthropic-compatible provider needs a model, "
                        "or the CLI would request Claude model names from it")
            elif pk != "anthropic-login":
                raise ConfigError(f"provider {prov}: kind must be anthropic-login | anthropic-compatible")
        if via == "cli":
            for key in ("binary", "review_argv", "code_argv"):
                if not lane.get(key):
                    raise ConfigError(f"lane {lid}: {key} is required for a cli lane")
    roles = cfg.get("roles", {})
    for role in (*ROLES, *OPTIONAL_ROLES, "reviewers"):
        for lid in roles.get(role, []):
            if lid not in lanes:
                raise ConfigError(f"roles.{role} names unknown lane {lid!r}")
    for lid in cfg.get("ladder", {}).get("approval_lanes", []):
        if lid not in lanes:
            raise ConfigError(f"ladder.approval_lanes names unknown lane {lid!r}")
    for lid, who in cfg.get("review", {}).get("dispatch", {}).items():
        if lid not in lanes or who not in ("runner", "controller"):
            raise ConfigError(f"review.dispatch.{lid} = {who!r} is invalid")
    if cfg.get("review", {}).get("same_family_seats", "ask") not in ("ask", "allow", "never"):
        raise ConfigError("review.same_family_seats must be ask | allow | never")
    checks = [("claude_code.blinding", cfg.get("claude_code", {}).get("blinding", "no-memory"))]
    checks += [(f"lanes.{k}.blinding", v["blinding"]) for k, v in lanes.items() if "blinding" in v]
    for where, val in checks:
        if val not in ("config-dir", "no-memory"):
            raise ConfigError(f"{where} must be config-dir | no-memory")


# --------------------------------------------------------------------------- detect

def which(names) -> str | None:
    if isinstance(names, str):
        names = [names]
    for n in names:
        if os.path.isabs(n) and os.path.exists(n):
            return n
        found = shutil.which(n)
        if found:
            return found
    return None


def lane_status(cfg: dict, lid: str) -> dict:
    lane = cfg["lanes"][lid]
    via = lane["via"]
    st = {"lane": lid, "via": via, "family": lane.get("family", lid),
          "model": lane.get("model", "") or "(cli default)", "available": True, "why": "ok"}
    if via == "controller":
        st["model"] = "(controller)"
        return st
    if via == "claude-code":
        cc = cfg.get("claude_code", {})
        path = which(cc.get("binary", "claude"))
        st["provider"] = lane.get("provider", "anthropic")
        if not path:
            st.update(available=False, why=f"claude binary not found ({cc.get('binary', 'claude')})")
            return st
        st["binary"] = path
        prov = cfg["providers"][st["provider"]]
        if prov.get("kind") == "anthropic-compatible":
            env = prov["auth_env"]
            if not os.environ.get(env):
                st.update(available=False, why=f"${env} is empty or unset")
        return st
    path = which(lane["binary"])
    if not path:
        st.update(available=False, why=f"binary not found ({', '.join(_as_list(lane['binary']))})")
    else:
        st["binary"] = path
    return st


def _as_list(v):
    return [v] if isinstance(v, str) else list(v)


def detect(cfg: dict) -> list[dict]:
    rows = [lane_status(cfg, lid) for lid in cfg.get("lanes", {})]
    for row in rows:
        # Existing lane selection remains unchanged. Binary/key presence
        # is a prerequisite, not proof of a valid login or model entitlement.
        row["readiness"] = ("controller" if row["via"] == "controller" else
                            "prerequisites_present" if row["available"] else "unavailable")
        row["authentication"] = "not_verified"
    return rows


# --------------------------------------------------------------------------- resolve

def load_usage(path: str | None) -> dict:
    if not path:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = {}
    for k, v in data.items():
        if isinstance(v, dict):
            v = v.get("used_pct")
        if isinstance(v, (int, float)):
            out[k] = float(v)
    return out


def read_ledger(path: str | None) -> list[dict]:
    if not path or not Path(path).is_file():
        return []
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def pick(cfg, candidates, status, *, usage, failed, rate_limits, approved, use_ladder_rules, trace):
    ladder = cfg.get("ladder", {})
    thr = float(ladder.get("threshold_pct", 80))
    max_rl = int(ladder.get("max_rate_limits", 2))
    approval = set(ladder.get("approval_lanes", [])) if use_ladder_rules else set()
    needs_approval = []
    for lid in candidates:
        st = status[lid]
        lane = cfg["lanes"][lid]
        if not st["available"]:
            trace.append({"lane": lid, "skip": "unavailable", "why": st["why"]})
            continue
        if lid in failed:
            trace.append({"lane": lid, "skip": "reactive", "why": f"failed this round ({failed[lid]})"})
            continue
        if rate_limits.get(lid, 0) >= max_rl:
            trace.append({"lane": lid, "skip": "reactive",
                          "why": f"{rate_limits[lid]} rate-limit errors (limit {max_rl})"})
            continue
        used = max([usage.get(lid, -1.0), usage.get(lane.get("provider", ""), -1.0)])
        if used >= thr:
            trace.append({"lane": lid, "skip": "threshold", "why": f"{used:g}% used >= {thr:g}%"})
            continue
        if lid in approval and not approved:
            trace.append({"lane": lid, "skip": "approval", "why": "approval-only lane; round not marked --approved"})
            needs_approval.append(lid)
            continue
        return lid, needs_approval
    return None, needs_approval


def build_panel(cfg, status, tier_key, coder_lane, exclude_families):
    seats = int(cfg.get("review", {}).get("seats", {}).get(tier_key, 0))
    policy = cfg.get("review", {}).get("same_family_seats", "ask")
    dispatch = cfg.get("review", {}).get("dispatch", {})
    panel, notes = [], []
    taken_fam = set()
    order = cfg.get("roles", {}).get("reviewers", [])
    # The coder's own lane never reviews its round. The one exception is the
    # controller lane: each of its dispatches is a fresh subagent, so it may take
    # a flagged same-family seat as a last resort.
    avail = [lid for lid in order if status[lid]["available"]
             and (lid != coder_lane or status[lid]["via"] == "controller")]

    def seat(lid, flag):
        fam = status[lid]["family"]
        panel.append({"lane": lid, "family": fam, "model": status[lid]["model"],
                      "dispatched_by": dispatch.get(lid, "runner"), "same_family": flag})
        taken_fam.add(fam)

    for lid in avail:
        if len(panel) >= seats:
            break
        fam = status[lid]["family"]
        if fam == "controller" or fam in exclude_families or fam in taken_fam:
            continue
        seat(lid, False)
    if len(panel) < seats and policy != "never":
        for lid in avail:
            if len(panel) >= seats:
                break
            if any(p["lane"] == lid for p in panel):
                continue
            seat(lid, True)
            notes.append(f"seat filled by {lid}: shares a family with the coder or another seat, "
                          "or has an unknown family (controller)")
    shortfall = max(0, seats - len(panel))
    return seats, panel, shortfall, notes


def resolve(cfg, args) -> tuple[int, dict]:
    status = {s["lane"]: s for s in detect(cfg)}
    usage = load_usage(args.usage)
    failed = {}
    for item in args.failed or []:
        lid, _, why = item.partition(":")
        failed[lid] = why or "error"
    rate_limits: dict[str, int] = {}
    for lid in args.rate_limited or []:
        rate_limits[lid] = rate_limits.get(lid, 0) + 1
    for lid in [*failed, *rate_limits]:
        if lid not in cfg["lanes"]:
            raise ConfigError(f"unknown lane {lid!r}")
    roles_cfg = cfg.get("roles", {})
    harness = cfg.get("harness", {})
    coding = harness.get("coding", "auto")
    if coding == "auto":
        coding = "claude-code" if which(cfg.get("claude_code", {}).get("binary", "claude")) else "controller"

    result = {"schema": SCHEMA, "tier": args.tier, "gate": bool(args.gate),
              "controller": harness.get("controller", "auto"), "coding": coding,
              "roles": {}, "trace": {}, "panel": [], "notes": [], "verdict": "OK"}
    exit_code = 0

    ledger_rows = read_ledger(args.ledger)
    last_coder = next((r["to"] for r in reversed(ledger_rows) if r.get("event") == "coder"), None)

    for role in (*ROLES, *OPTIONAL_ROLES):
        cands = list(roles_cfg.get(role, []))
        if coding == "controller":
            cands = [c for c in cands if cfg["lanes"][c]["via"] != "claude-code"]
        trace: list = []
        chosen = None
        approval_wait: list = []
        if role == "coder" and args.reuse_last and last_coder in cands \
                and status[last_coder]["available"] and last_coder not in failed:
            chosen = last_coder
            trace.append({"lane": last_coder, "pick": "reuse-last",
                          "why": "re-dispatch of an interrupted round reuses the last confirmed lane"})
        if chosen is None:
            chosen, approval_wait = pick(
                cfg, cands, status, usage=usage, failed=failed, rate_limits=rate_limits,
                approved=args.approved, use_ladder_rules=(role == "coder"), trace=trace)
        result["trace"][role] = trace
        if chosen is None and role in OPTIONAL_ROLES:
            result["roles"][role] = None
            if cands:
                result["notes"].append(f"{role}: no listed lane can run here (optional role)")
            continue
        if chosen is None:
            if approval_wait:
                result["verdict"] = "ASK-USER"
                result["notes"].append(
                    f"{role}: only approval-only lanes remain ({', '.join(approval_wait)}); "
                    "the user approves the round, then re-run with --approved")
                exit_code = max(exit_code, 3)
            else:
                result["verdict"] = "NO-LANE"
                result["notes"].append(f"{role}: no lane in roles.{role} can run here")
                exit_code = 2
            result["roles"][role] = None
            continue
        result["roles"][role] = {"lane": chosen, "family": status[chosen]["family"],
                                 "model": status[chosen]["model"], "via": status[chosen]["via"]}

    coder = result["roles"].get("coder")
    tier_key = "gate" if args.gate else args.tier
    if coder:
        excl = {coder["family"]}
        seats, panel, shortfall, notes = build_panel(cfg, status, tier_key, coder["lane"], excl)
        result["seats"] = seats
        result["panel"] = panel
        result["shortfall"] = shortfall
        result["notes"].extend(notes)
        policy = cfg.get("review", {}).get("same_family_seats", "ask")
        flagged = [p for p in panel if p["same_family"]]
        if shortfall:
            result["notes"].append(
                f"review panel short by {shortfall} of {seats} seat(s)"
                + ("; a gate holds the deploy until the user decides" if args.gate else ""))
        if (shortfall or (flagged and policy == "ask")) and result["verdict"] == "OK":
            result["verdict"] = "ASK-USER"
            exit_code = max(exit_code, 3)

        # coder-switch ledger
        if args.ledger and coder["lane"] != last_coder:
            prev_skip = next((t for t in result["trace"]["coder"] if t.get("lane") == last_coder), None)
            reason = ("first-round" if last_coder is None else
                      (prev_skip or {}).get("skip", "config"))
            row = {"event": "coder", "at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                   "round": args.round, "from": last_coder, "to": coder["lane"], "reason": reason,
                   "detail": (prev_skip or {}).get("why", ""),
                   "panel": [p["lane"] for p in panel]}
            Path(args.ledger).parent.mkdir(parents=True, exist_ok=True)
            with open(args.ledger, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
            result["switch"] = row
    return exit_code, result


# --------------------------------------------------------------------------- command

def _fill(argv, values):
    out = []
    for tok in argv:
        if tok in ("{model_args}", "{effort_args}"):
            out.extend(values[tok])
            continue
        for k, v in values.items():
            if isinstance(v, str):
                tok = tok.replace(k, v)
        out.append(tok)
    return out


def build_command(cfg, lane_id, role, prompt_file, cwd, add_dirs=(), redact=True) -> dict:
    if lane_id not in cfg["lanes"]:
        raise ConfigError(f"unknown lane {lane_id!r}")
    if role not in ALL_ROLES:
        raise ConfigError(f"role must be one of {', '.join(ALL_ROLES)}")
    lane = cfg["lanes"][lane_id]
    st = lane_status(cfg, lane_id)
    prompt_path = str(Path(prompt_file).resolve())
    spec = {"lane": lane_id, "role": role, "via": lane["via"], "cwd": str(Path(cwd).resolve()),
            "env": {}, "stdin_file": None}
    if lane["via"] == "controller":
        spec["argv"] = None
        spec["instruction"] = ("dispatch through the controller's own subagent tool "
                               "(Hermes delegate_task / Claude Code Task) with the prompt file as the brief")
        return spec
    if not st["available"]:
        raise Refused(f"lane {lane_id} is unavailable here: {st['why']}")

    if lane["via"] == "cli":
        model, effort = lane.get("model", ""), lane.get("effort", "")
        values = {
            "{binary}": st["binary"],
            "{prompt_file}": prompt_path,
            "{prompt_pointer}": f"Read the brief at {prompt_path} and follow it exactly.",
            "{model}": model, "{effort}": effort,
        }
        values["{model_args}"] = _fill(lane.get("model_args", []), values) if model else []
        values["{effort_args}"] = _fill(lane.get("effort_args", []), values) if effort else []
        template = lane["review_argv"] if role in READ_ONLY_ROLES else lane["code_argv"]
        spec["argv"] = _fill(template, values)
        return spec

    # claude-code
    cc = cfg.get("claude_code", {})
    disallowed = list(cc.get("disallowed_tools", []))
    if role in READ_ONLY_ROLES:
        disallowed += list(cc.get("reviewer_disallowed_tools", []))
    argv = [st["binary"], *cc.get("binary_args", []), "-p",
            "--output-format", "json",
            "--max-turns", str(cc.get("max_turns", 80)),
            "--no-session-persistence",
            "--permission-mode", "default" if role in READ_ONLY_ROLES else cc.get("permission_mode", "acceptEdits")]
    allowed = [t for t in cc.get("allowed_tools", []) if t not in disallowed]
    if allowed:
        argv += ["--allowedTools", ",".join(allowed)]
    if disallowed:
        argv += ["--disallowedTools", ",".join(disallowed)]
    if lane.get("model"):
        argv += ["--model", lane["model"]]
    for d in add_dirs:
        argv += ["--add-dir", str(Path(d).resolve())]
    argv += list(cc.get("extra_args", []))
    env = {"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
    if cc.get("version_pin"):
        env["DISABLE_AUTOUPDATER"] = "1"
    blinding = lane.get("blinding", cc.get("blinding", "no-memory"))
    spec["blinding"] = blinding
    if blinding == "config-dir":
        root = Path(cc.get("role_root", "~/.config/dev-pipeline/roles")).expanduser()
        env["CLAUDE_CONFIG_DIR"] = str(root / role)
    else:
        env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
        argv += ["--settings", json.dumps({"autoMemoryEnabled": False})]
    prov = cfg["providers"][lane.get("provider", "anthropic")]
    if prov["kind"] == "anthropic-compatible":
        key_env = prov["auth_env"]
        secret = os.environ.get(key_env, "")
        if not secret:
            raise Refused(f"${key_env} is empty: refusing to dispatch, so the CLI can't fall back "
                          "to the logged-in Anthropic account")
        m = lane["model"]
        env.update({
            "ANTHROPIC_BASE_URL": prov["base_url"],
            "ANTHROPIC_AUTH_TOKEN": f"${key_env}" if redact else secret,
            "ANTHROPIC_API_KEY": "",
            "ANTHROPIC_MODEL": m,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": m,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": m,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": m,
            "CLAUDE_CODE_SUBAGENT_MODEL": m,
        })
    spec["argv"] = argv
    spec["env"] = env
    spec["stdin_file"] = prompt_path
    return spec


def run_spec(spec, out_dir, timeout) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{spec['role']}-{spec['lane']}"
    env = dict(os.environ)
    env.update(spec["env"])
    stdin = open(spec["stdin_file"], "rb") if spec["stdin_file"] else subprocess.DEVNULL
    t0 = time.monotonic()
    try:
        proc = subprocess.run(spec["argv"], cwd=spec["cwd"], env=env, stdin=stdin,
                              capture_output=True, timeout=timeout)
        code, so, se = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        code, so, se = 124, e.stdout or b"", e.stderr or b""
    except FileNotFoundError as e:
        code, so, se = 127, b"", str(e).encode()
    finally:
        if stdin is not subprocess.DEVNULL:
            stdin.close()
    (out / f"{stem}.out").write_bytes(so)
    (out / f"{stem}.err").write_bytes(se)
    tail = (se[-4000:] + so[-4000:]).decode("utf-8", "replace")
    res = {"schema": "lane-run.v1", "lane": spec["lane"], "role": spec["role"],
           "exit_code": code, "seconds": round(time.monotonic() - t0, 1),
           "rate_limited": bool(code != 0 and RATE_LIMIT_RE.search(tail)),
           "stdout": str(out / f"{stem}.out"), "stderr": str(out / f"{stem}.err")}
    (out / f"{stem}.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    return res


# --------------------------------------------------------------------------- doctor

def plugin_version(root: Path) -> str | None:
    p = root / "plugin.yaml"
    if not p.is_file():
        return None
    m = re.search(r"(?m)^version:\s*([^\s#]+)", p.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def doctor(cfg, used) -> tuple[int, dict]:
    problems, warnings = [], []
    status = detect(cfg)
    by = {s["lane"]: s for s in status}
    cc = cfg.get("claude_code", {})
    roles = cfg.get("roles", {})
    for role in (*ROLES, "reviewers"):
        lanes_ok = [l for l in roles.get(role, []) if by[l]["available"]]
        if not lanes_ok:
            problems.append(f"roles.{role}: no listed lane is available here")
    claude_path = which(cc.get("binary", "claude"))
    if cc.get("version_pin") and claude_path:
        try:
            v = subprocess.run([claude_path, *cc.get("binary_args", []), "--version"],
                               capture_output=True, text=True, timeout=60).stdout
            have = (re.search(r"\d+\.\d+\.\d+", v) or [None])[0]
        except (OSError, subprocess.TimeoutExpired):
            have = None
        if have != cc["version_pin"]:
            problems.append(f"Claude Code is {have or 'unknown'}, pinned {cc['version_pin']}")
    for lid, lane in cfg["lanes"].items():
        if lane["via"] == "claude-code" and lane.get("blinding", cc.get("blinding")) == "config-dir" and \
                cfg["providers"][lane.get("provider", "anthropic")]["kind"] == "anthropic-login":
            if any(lid in roles.get(r, []) for r in (*ROLES, *OPTIONAL_ROLES, "reviewers")):
                    warnings.append(
                        f"lane {lid} uses the Anthropic login with config-dir blinding: log in once "
                        "per role dir (CLAUDE_CONFIG_DIR=<role_root>/<role> claude), or set blinding = no-memory")
    for p in cfg.get("review", {}).get("dispatch", {}):
        if p not in roles.get("reviewers", []):
            warnings.append(f"review.dispatch names {p}, which is not in roles.reviewers")
    for lid in cfg.get("lanes", {}):
        if cfg["lanes"][lid]["via"] == "cli" and lid in roles.get("coder", []) \
                and lid in roles.get("reviewers", []) and lid not in cfg.get("ladder", {}).get("approval_lanes", []):
            warnings.append(f"lane {lid} both codes and reviews; consider ladder.approval_lanes "
                            "so coding never spends the review quota by default")
    have_v = plugin_version(PLUGIN_ROOT)
    pin = cfg.get("pin", {})
    if pin.get("plugin_version") and pin["plugin_version"] != have_v:
        problems.append(f"plugin is {have_v}, config pins {pin['plugin_version']}")
    if pin.get("master_path"):
        mv = plugin_version(Path(pin["master_path"]).expanduser())
        if mv is None:
            warnings.append(f"master plugin not readable at {pin['master_path']}")
        elif mv != have_v:
            problems.append(f"plugin is {have_v}, master at {pin['master_path']} is {mv}")
    rep = {"schema": SCHEMA, "config": used, "plugin_version": have_v, "lanes": status,
           "problems": problems, "warnings": warnings,
           "ok": not problems}
    return (0 if not problems else 3), rep


# --------------------------------------------------------------------------- cli

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", action="append", help="extra config file (applied last; repeatable)")
    ap.add_argument("--repo", help="project root, for <repo>/.dev-pipeline/lanes.toml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("detect")
    r = sub.add_parser("resolve")
    r.add_argument("--tier", required=True, choices=["T0", "T1", "T2", "T3"])
    r.add_argument("--gate", action="store_true", help="size the panel for the deploy gate")
    r.add_argument("--usage", help='JSON {"<lane|provider>": percent_used}, written by the controller')
    r.add_argument("--failed", action="append", metavar="LANE[:why]",
                   help="lane hit a hard error this round (429/402/overload); skip it")
    r.add_argument("--rate-limited", action="append", metavar="LANE",
                   help="one rate-limit error from LANE this round (repeat per error)")
    r.add_argument("--approved", action="store_true", help="round is approval-worthy: approval-only lanes may code")
    r.add_argument("--reuse-last", action="store_true", help="re-dispatch: reuse the ledger's last coder lane")
    r.add_argument("--ledger", help="JSONL file recording coder switches")
    r.add_argument("--round", default="", help="round label for the ledger, e.g. R2")

    for name in ("command", "run"):
        c = sub.add_parser(name)
        c.add_argument("--lane", required=True)
        c.add_argument("--role", required=True, choices=list(ALL_ROLES))
        c.add_argument("--prompt-file", required=True)
        c.add_argument("--cwd", default=".")
        c.add_argument("--add-dir", action="append", default=[])
        if name == "run":
            c.add_argument("--out", required=True, help="directory for .out/.err/.json")
            c.add_argument("--timeout", type=int, default=3600)
    sub.add_parser("doctor")

    a = ap.parse_args(argv)
    try:
        cfg, used = load_config(a.config, a.repo)
        if a.cmd == "detect":
            print(json.dumps({"schema": SCHEMA, "config": used, "lanes": detect(cfg)}, indent=2))
            return 0
        if a.cmd == "resolve":
            code, res = resolve(cfg, a)
            print(json.dumps(res, indent=2))
            return code
        if a.cmd == "command":
            print(json.dumps(build_command(cfg, a.lane, a.role, a.prompt_file, a.cwd, a.add_dir), indent=2))
            return 0
        if a.cmd == "run":
            spec = build_command(cfg, a.lane, a.role, a.prompt_file, a.cwd, a.add_dir, redact=False)
            if spec["argv"] is None:
                print(json.dumps(spec, indent=2))
                return 5
            res = run_spec(spec, a.out, a.timeout)
            print(json.dumps(res, indent=2))
            return 0 if res["exit_code"] == 0 else 1
        if a.cmd == "doctor":
            code, rep = doctor(cfg, used)
            print(json.dumps(rep, indent=2))
            return code
    except Refused as e:
        print(json.dumps({"refused": str(e)}), file=sys.stderr)
        return 4
    except (ConfigError, json.JSONDecodeError, OSError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 5
    return 5


if __name__ == "__main__":
    sys.exit(main())
