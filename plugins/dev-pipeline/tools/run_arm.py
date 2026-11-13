#!/usr/bin/env python3
"""Bounded CLI arm dispatch runner for the dev-pipeline plugin.

Wraps exactly ONE CLI arm dispatch (``claude`` / ``codex`` / ``muse``), writes
the combined stdout+stderr to an absolute log path, and writes a
machine-readable run-record JSON to an absolute record path. The outcome maps
onto a small exit-code contract:

    0  success (reviewer runs must end in a parsable VERDICT line)
    2  bad arguments/paths, or a refused ``--dangerously-skip-permissions``
    3  reviewer run produced no final ``VERDICT: (APPROVE|REJECT|SHIP)``
    4  underlying CLI failed (non-zero exit / could not start)
    5  meter/quota abort before any burn (muse usage gate)

Stdlib only, Python 3.10+. No secrets, PII, or org names in this file:
credentials are only ever copied between paths the caller already owns.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

EXIT_OK = 0
EXIT_ARGS = 2
EXIT_NO_VERDICT = 3
EXIT_CLI_FAILED = 4
EXIT_QUOTA = 5

ARMS = ("claude", "codex", "muse")
ROLES = ("coder", "reviewer")

DEFAULT_MODEL = {
    "claude": "glm-5.3",
    "codex": "gpt-6-sol",
    "muse": "muse-spark-1.3",
}

# NEVER passed to a bounded arm dispatch; refused with a clear error.
FORBIDDEN_FLAG = "--dangerously-skip-permissions"

CLAUDE_CODER_ALLOWED_TOOLS = " ".join(
    [
        "Read",
        "Edit",
        "Write",
        "Glob",
        "Grep",
        "Bash(git add:*)",
        "Bash(git commit:*)",
        "Bash(git status:*)",
        "Bash(git log:*)",
        "Bash(git diff:*)",
        "/usr/bin/python3:*",
    ]
)

CREDENTIALS_NAME = ".credentials.json"
SETTINGS_NAME = "settings.json"


class UsageError(Exception):
    """Bad arguments/paths — maps to exit code 2."""


class QuotaAbortError(Exception):
    """Meter/quota abort before dispatch — maps to exit code 5."""


VERDICT_RE = re.compile(r"VERDICT:\s*(APPROVE|REJECT|SHIP)\b", re.IGNORECASE)
CODEX_TOKENS_RE = re.compile(r"tokens\s+used\s*:?\s*([0-9][0-9,]*)", re.IGNORECASE)
MUSE_RESET_RE = re.compile(
    r"reset(?:s|ting)?(?:\s+date)?(?:\s+(?:on|at|by))?\s*[:\-]?\s*"
    r"(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

# Text that means the muse meter is exhausted: abort, zero burn.
MUSE_BLOCK_RES = (
    re.compile(r"quota\s+exhausted", re.IGNORECASE),
    re.compile(r"quota\s+exceeded", re.IGNORECASE),
    re.compile(r"rate[- ]limit(?:ed|ing)?", re.IGNORECASE),
    re.compile(r"usage\s+limit", re.IGNORECASE),
)
# server_sent_no_usage is benign: can happen before the first use in a
# new window — proceed, do not abort.
MUSE_NO_DATA_RES = (
    re.compile(r"server_sent_no_usage", re.IGNORECASE),
    re.compile(r"no\s+usage\s+data", re.IGNORECASE),
)

# The usage/meter query run before every muse dispatch (monkeypatch point).
MUSE_USAGE_CMD = ("muse", "usage")


def default_gate_config_dir() -> Path:
    """Clean config dir used for route-isolated gate claude reviews."""
    return Path.home() / ".cache" / "dev-pipeline" / "claude-gate-config"


def extract_verdict(log_text):
    """Return the last ``VERDICT: (APPROVE|REJECT|SHIP)`` in the FINAL 200 chars.

    None when the tail carries no verdict line (or the log is empty).
    """
    if not log_text:
        return None
    tail = log_text[-200:]
    matches = VERDICT_RE.findall(tail)
    if not matches:
        return None
    return matches[-1].upper()


def extract_last_json_object(text):
    """Return the last complete top-level JSON object embedded in ``text``.

    The claude blob may sit among warning lines; nested objects inside a
    bigger blob do NOT count (only top-level spans compete, last start wins).
    """
    if not text:
        return None
    decoder = json.JSONDecoder()
    spans = []
    for match in re.finditer(r"\{", text):
        try:
            obj, end = decoder.raw_decode(text, match.start())
        except ValueError:
            continue
        if isinstance(obj, dict):
            spans.append((match.start(), end, obj))
    if not spans:
        return None
    top_level = [
        span
        for span in spans
        if not any(
            other[0] < span[0] and span[1] <= other[1] for other in spans
        )
    ]
    pool = top_level or spans
    return max(pool, key=lambda span: span[0])[2]


def parse_codex_tokens_used(log_text):
    """Parse the integer from the codex log's ``tokens used`` line (or None)."""
    if not log_text:
        return None
    matches = CODEX_TOKENS_RE.findall(log_text)
    if not matches:
        return None
    return int(matches[-1].replace(",", ""))


def _iso_local(moment):
    if moment.tzinfo is None:
        moment = moment.astimezone()
    return moment.isoformat()


def build_run_record(
    *,
    arm,
    role,
    model,
    workdir,
    prompt_file,
    log_path,
    started,
    ended,
    exit_code,
    log_text,
):
    """Build the run-record dict from the dispatch log and timestamps."""
    record = {
        "arm": arm,
        "role": role,
        "model": model,
        "workdir": str(workdir),
        "prompt_file": str(prompt_file),
        "log_path": str(log_path),
        "started_local": _iso_local(started),
        "ended_local": _iso_local(ended),
        "elapsed_s": round((ended - started).total_seconds(), 3),
        "exit_code": exit_code,
        "turns": None,
        "cost_usd": None,
        "tokens_out": None,
        "tokens_used": None,
        "verdict": None,
    }
    if arm == "claude":
        blob = extract_last_json_object(log_text)
        if isinstance(blob, dict):
            record["turns"] = blob.get("num_turns")
            record["cost_usd"] = blob.get("total_cost_usd")
            usage = blob.get("usage")
            if isinstance(usage, dict):
                record["tokens_out"] = usage.get("output_tokens")
    elif arm == "codex":
        record["tokens_used"] = parse_codex_tokens_used(log_text)
    if role == "reviewer":
        record["verdict"] = extract_verdict(log_text)
    return record


def prepare_gate_config_dir(gate_dir, credentials_src, settings_src):
    """Create or reuse a clean config dir for a route-isolated gate review.

    Copies ``credentials_src`` (if present) verbatim, and writes a copy of
    ``settings_src`` with any top-level ``env`` key REMOVED, so provider
    routing env cannot leak into the gate run through settings.
    """
    gate_dir = Path(gate_dir)
    gate_dir.mkdir(parents=True, exist_ok=True)
    if credentials_src is not None:
        credentials_src = Path(credentials_src)
        if credentials_src.is_file():
            shutil.copy2(credentials_src, gate_dir / CREDENTIALS_NAME)
    settings = {}
    if settings_src is not None:
        settings_src = Path(settings_src)
        if settings_src.is_file():
            try:
                loaded = json.loads(settings_src.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                loaded = {}
            if isinstance(loaded, dict):
                settings = loaded
    settings.pop("env", None)
    (gate_dir / SETTINGS_NAME).write_text(
        json.dumps(settings, indent=2) + "\n", encoding="utf-8"
    )
    return gate_dir


def load_env_file(path):
    """Parse KEY=VALUE lines (``#`` comments and blanks skipped) into a dict."""
    env = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def is_inside_git_repo(start):
    """True when ``start`` or any parent carries a ``.git`` dir/file."""
    current = Path(start).resolve()
    while True:
        if (current / ".git").exists():
            return True
        parent = current.parent
        if parent == current:
            return False
        current = parent


def build_claude_args(model, prompt, role, extra_args):
    """Build the claude CLI args (after the program name)."""
    if FORBIDDEN_FLAG in extra_args:
        raise UsageError(
            f"refusing dispatch: {FORBIDDEN_FLAG} is never passed to a "
            "bounded arm run"
        )
    args = ["-p", prompt, "--model", model, "--output-format", "json"]
    if role == "coder":
        args += ["--allowedTools", CLAUDE_CODER_ALLOWED_TOOLS]
    elif role == "reviewer":
        args += ["--allowedTools", "Read"]
    return args + list(extra_args)


def build_codex_args(model, prompt, in_git_repo, extra_args):
    """Build the codex CLI args (after the program name)."""
    args = ["exec"]
    if not in_git_repo:
        args.append("--skip-git-repo-check")
    args += ["-m", model, "-c", "model_reasoning_effort=high", prompt]
    return args + list(extra_args)


def build_muse_args(model, prompt, extra_args):
    """Build the muse CLI args (after the program name)."""
    args = [
        "exec",
        "--trust-workspace",
        "--model",
        model,
        "--reasoning-effort",
        "high",
        prompt,
    ]
    return args + list(extra_args)


def interpret_muse_usage(text):
    """Classify a muse usage/meter report.

    Returns ``{"status": "ok"|"no_data"|"blocked", "reset_date": str|None}``.
    Only ``blocked`` aborts the dispatch.
    """
    text = text or ""
    if any(block.search(text) for block in MUSE_BLOCK_RES):
        reset_match = MUSE_RESET_RE.search(text)
        reset_date = None
        if reset_match:
            reset_date = reset_match.group(1)
        else:
            fallback = ISO_DATE_RE.search(text)
            reset_date = fallback.group(0) if fallback else None
        return {"status": "blocked", "reset_date": reset_date}
    if any(no_data.search(text) for no_data in MUSE_NO_DATA_RES):
        return {"status": "no_data", "reset_date": None}
    return {"status": "ok", "reset_date": None}


def _muse_usage_output(env):
    """Run the muse usage/meter query and return its combined output.

    A failed/unavailable query is treated like benign no-usage-data: it can
    happen before the first use in a new window and must not burn anything.
    """
    try:
        proc = subprocess.run(
            list(MUSE_USAGE_CMD),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"usage query unavailable: {exc}"
    return "\n".join(part for part in (proc.stdout, proc.stderr) if part)


def muse_quota_gate(env):
    """Abort (QuotaAbortError, exit 5) when the muse meter is exhausted."""
    info = interpret_muse_usage(_muse_usage_output(env))
    if info["status"] == "blocked":
        reset = info["reset_date"] or "an unknown date"
        raise QuotaAbortError(
            "muse meter reports quota exhausted / rate-limited; aborting the "
            f"dispatch with zero burn. Quota resets on {reset}."
        )
    return info


def _write_record(record_path, record):
    Path(record_path).write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="run_arm.py",
        description="Wrap one bounded CLI arm dispatch and write a "
        "machine-readable run record.",
        epilog="exit codes: 0 success, 2 bad args/paths, 3 missing reviewer "
        "verdict, 4 underlying CLI failed, 5 meter/quota abort",
    )
    parser.add_argument("--arm", required=True, choices=ARMS)
    parser.add_argument("--role", required=True, choices=ROLES)
    parser.add_argument("--workdir", required=True, help="directory to run the CLI in")
    parser.add_argument("--prompt-file", required=True, help="file holding the dispatch prompt")
    parser.add_argument("--log-path", required=True, help="ABSOLUTE path for combined stdout+stderr")
    parser.add_argument("--record-path", required=True, help="ABSOLUTE path for the run-record JSON")
    parser.add_argument("--model", help="model override (arm default otherwise)")
    parser.add_argument(
        "--extra-arg",
        action="append",
        default=[],
        metavar="ARG",
        help="extra CLI argument (repeatable; appended after the built args)",
    )
    parser.add_argument("--env-file", help="optional KEY=VALUE lines merged over os.environ")
    return parser.parse_args(argv)


def _run(args):
    arm = args.arm
    role = args.role
    workdir = Path(args.workdir)
    prompt_file = Path(args.prompt_file)
    log_path = Path(args.log_path)
    record_path = Path(args.record_path)

    if FORBIDDEN_FLAG in args.extra_arg:
        raise UsageError(
            f"refusing dispatch: {FORBIDDEN_FLAG} is never passed to a "
            "bounded arm run"
        )
    if not log_path.is_absolute() or not record_path.is_absolute():
        raise UsageError("--log-path and --record-path must be absolute paths")
    if not workdir.is_dir():
        raise UsageError(f"--workdir is not an existing directory: {workdir}")
    if not prompt_file.is_file():
        raise UsageError(f"--prompt-file does not exist: {prompt_file}")
    if log_path.exists() and log_path.stat().st_size > 0:
        raise UsageError(
            f"--log-path already has content ({log_path}); refusing so two "
            "concurrent dispatches never share one log"
        )

    model = args.model or DEFAULT_MODEL[arm]
    prompt = prompt_file.read_text(encoding="utf-8")
    env = dict(os.environ)
    if args.env_file:
        env.update(load_env_file(args.env_file))

    started = datetime.now().astimezone()

    if arm == "muse":
        try:
            muse_quota_gate(env)
        except QuotaAbortError as exc:
            message = str(exc)
            with open(log_path, "w", encoding="utf-8") as handle:
                handle.write(message + "\n")
            record = build_run_record(
                arm=arm,
                role=role,
                model=model,
                workdir=workdir,
                prompt_file=prompt_file,
                log_path=log_path,
                started=started,
                ended=datetime.now().astimezone(),
                exit_code=EXIT_QUOTA,
                log_text=message,
            )
            _write_record(record_path, record)
            print(message, file=sys.stderr)
            return EXIT_QUOTA

    if arm == "claude":
        cli = ["claude"] + build_claude_args(model, prompt, role, args.extra_arg)
        if role == "reviewer":
            gate_dir = prepare_gate_config_dir(
                default_gate_config_dir(),
                Path.home() / ".claude" / CREDENTIALS_NAME,
                Path.home() / ".claude" / SETTINGS_NAME,
            )
            env["CLAUDE_CONFIG_DIR"] = str(gate_dir)
    elif arm == "codex":
        cli = [
            "codex"
        ] + build_codex_args(model, prompt, is_inside_git_repo(workdir), args.extra_arg)
    else:
        cli = ["muse"] + build_muse_args(model, prompt, args.extra_arg)

    exit_code = None
    try:
        with open(log_path, "w", encoding="utf-8") as handle:
            proc = subprocess.run(
                cli,
                cwd=str(workdir),
                env=env,
                stdout=handle,
                stderr=subprocess.STDOUT,
            )
        exit_code = proc.returncode
    except OSError as exc:
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(f"dispatch error: {exc}\n")

    ended = datetime.now().astimezone()
    log_text = log_path.read_text(encoding="utf-8")
    record = build_run_record(
        arm=arm,
        role=role,
        model=model,
        workdir=workdir,
        prompt_file=prompt_file,
        log_path=log_path,
        started=started,
        ended=ended,
        exit_code=exit_code,
        log_text=log_text,
    )
    _write_record(record_path, record)

    if exit_code != 0:
        print(
            f"{arm} CLI failed (exit {exit_code}); log: {log_path}",
            file=sys.stderr,
        )
        return EXIT_CLI_FAILED
    if role == "reviewer" and record["verdict"] is None:
        print(
            "reviewer run has no final VERDICT: (APPROVE|REJECT|SHIP) line; "
            f"log: {log_path}",
            file=sys.stderr,
        )
        return EXIT_NO_VERDICT
    return EXIT_OK


def main(argv=None):
    args = parse_args(argv)
    try:
        return _run(args)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ARGS


if __name__ == "__main__":
    sys.exit(main())
