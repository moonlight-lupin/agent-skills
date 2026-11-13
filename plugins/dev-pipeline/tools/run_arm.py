#!/usr/bin/env python3
"""Bounded CLI arm dispatch runner for the dev-pipeline plugin.

Wraps exactly ONE CLI arm dispatch (``claude`` / ``codex`` / ``muse``), writes
the combined stdout+stderr to an absolute log path (which must NOT already
exist — it is opened exclusively, so two concurrent dispatches can never
share one log), and writes a machine-readable run-record JSON to an
absolute record path (must be absolute; may be created later, after the
dispatch). The outcome maps onto a small exit-code contract:

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

# Provider-routing / model-selection env keys stripped from reviewer (gate)
# claude children. Without this the child inherits routing vars from
# os.environ / --env-file and the clean gate config dir does not isolate
# the route. Unrelated vars are left in place.
ANTHROPIC_PROVIDER_ENV_KEYS = (
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL",
    "ANTHROPIC_MODEL_ERROR_HINT",
)

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


# A verdict must be a line of its own: this anchored pattern must match the
# WHOLE line, so an inline or quoted match inside a longer line never counts.
VERDICT_LINE_RE = re.compile(
    r"^VERDICT:\s*(APPROVE|REJECT|SHIP)\s*$", re.IGNORECASE
)
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
    re.compile(r"\b429\b"),
)
# server_sent_no_usage can happen before the first use in a new window —
# proceed, do not abort.
# Only these keep a dispatch going; a FAILED query may only be excused by
# MUSE_BENIGN_ON_FAILURE_RES (a strict subset of this tuple).
MUSE_NO_DATA_RES = (
    re.compile(r"server_sent_no_usage", re.IGNORECASE),
    re.compile(r"no\s+usage\s+data", re.IGNORECASE),
)
# Failed meter queries are excused ONLY by this marker; the looser
# no-usage-data phrasing does not prove the meter is healthy.
MUSE_BENIGN_ON_FAILURE_RES = (MUSE_NO_DATA_RES[0],)

# The usage/meter query run before every muse dispatch (monkeypatch point).
MUSE_USAGE_CMD = ("muse", "usage")


def default_gate_config_dir() -> Path:
    """Clean config dir used for route-isolated gate claude reviews."""
    return Path.home() / ".cache" / "dev-pipeline" / "claude-gate-config"


def _verdict_from_last_line(text):
    """Anchor-match the LAST non-blank line of ``text`` against the verdict
    pattern. An inline or quoted match inside a longer line never counts.
    """
    if not text:
        return None
    for raw in reversed(text.splitlines()):
        line = raw.strip()
        if line:
            match = VERDICT_LINE_RE.match(line)
            return match.group(1).upper() if match else None
    return None


def extract_verdict(log_text, arm=None):
    """Return the reviewer verdict ("APPROVE"|"REJECT"|"SHIP") or None.

    For claude arms (``--output-format json``) the log ends with the JSON
    result blob, not a bare VERDICT line: the verdict is taken from the
    LAST parsed JSON blob's ``result`` string — its last non-blank line must
    fully match ``^VERDICT: (APPROVE|REJECT|SHIP)$``. Only when no blob
    parses (e.g. a non-json claude run, codex, muse) fall back to the log
    text: the last non-blank line of the WHOLE log, anchor-matched against
    the same pattern. Inline or quoted matches inside longer lines are
    never accepted.
    """
    if not log_text:
        return None
    if arm == "claude":
        blob = extract_last_json_object(log_text)
        if isinstance(blob, dict):
            result = blob.get("result")
            if isinstance(result, str):
                return _verdict_from_last_line(result)
            return None
    return _verdict_from_last_line(log_text)


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
        record["verdict"] = extract_verdict(log_text, arm=arm)
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
    """Parse KEY=VALUE lines (``#`` comments and blanks skipped) into a dict.

    Raises OSError when the file cannot be read (mapped to exit 2 by the
    caller).
    """
    env = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def strip_provider_env(env):
    """Remove ANTHROPIC_PROVIDER_ENV_KEYS from ``env`` (in place).

    Used for reviewer (gate) claude runs: the clean gate config dir must be
    the only thing controlling provider routing and model selection, so
    routing vars inherited from os.environ / --env-file are stripped.
    Unrelated vars are left untouched.
    """
    for key in ANTHROPIC_PROVIDER_ENV_KEYS:
        env.pop(key, None)
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


def validate_extra_args(extra_args):
    """Reject ``--extra-arg`` values that could override the built-in
    safety envelope (maps to exit 2):

    * any ``--allowedTools`` — extra args are appended AFTER the role's own
      ``--allowedTools``, so a second one would override the role's tool
      whitelist;
    * ``--dangerously-skip-permissions`` in any spelling (case, hyphens,
      underscores, camelCase) — never passed to a bounded arm run.
    """
    for arg in extra_args:
        if arg == "--allowedTools" or arg.startswith("--allowedTools"):
            raise UsageError(
                "refusing dispatch: --extra-arg --allowedTools would "
                "override the role's tool whitelist"
            )
        normalized = re.sub(r"[^a-z0-9]", "", arg.lower())
        if "dangerously" in normalized and "permission" in normalized:
            raise UsageError(
                "refusing dispatch: --dangerously-skip-permissions (or a "
                "variant spelling) is never passed to a bounded arm run"
            )


def build_claude_args(model, prompt, role, extra_args):
    """Build the claude CLI args (after the program name)."""
    validate_extra_args(extra_args)
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

    A failed query (cannot run, or exits nonzero) is a METER FAILURE, not a
    clean bill of health: it raises QuotaAbortError (exit 5, zero burn)
    unless the output carries the benign ``server_sent_no_usage`` marker,
    which can happen before the first use in a new window.
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
        text = f"usage query unavailable: {exc}"
        failed = True
    else:
        text = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
        failed = proc.returncode != 0
    benign = any(
        marker.search(text) for marker in MUSE_BENIGN_ON_FAILURE_RES
    )
    if failed and not benign:
        raise QuotaAbortError(
            "muse usage/meter query failed; meter state unknown. Aborting "
            "the dispatch with zero burn."
        )
    return text


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
    """Write the run record; an unwritable/parentless path maps to exit 2."""
    try:
        Path(record_path).write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        raise UsageError(
            f"cannot write --record-path ({record_path}): {exc}"
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
    parser.add_argument(
        "--log-path",
        required=True,
        help="ABSOLUTE path for combined stdout+stderr (must NOT already exist)",
    )
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

    validate_extra_args(args.extra_arg)
    if not log_path.is_absolute() or not record_path.is_absolute():
        raise UsageError("--log-path and --record-path must be absolute paths")
    if not workdir.is_dir():
        raise UsageError(f"--workdir is not an existing directory: {workdir}")
    if not prompt_file.is_file():
        raise UsageError(f"--prompt-file does not exist: {prompt_file}")
    # The log path must not exist at ALL (any size): combined with the
    # exclusive "x" open below, two concurrent dispatches can never both
    # pass the check and share one log (no TOCTOU window).
    if log_path.exists():
        raise UsageError(
            f"--log-path already exists ({log_path}); refusing so two "
            "concurrent dispatches never share one log"
        )

    model = args.model or DEFAULT_MODEL[arm]
    try:
        prompt = prompt_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise UsageError(f"cannot read --prompt-file ({prompt_file}): {exc}")
    env = dict(os.environ)
    if args.env_file:
        try:
            env.update(load_env_file(args.env_file))
        except OSError as exc:
            raise UsageError(
                f"cannot read --env-file ({args.env_file}): {exc}"
            )

    started = datetime.now().astimezone()

    if arm == "muse":
        try:
            muse_quota_gate(env)
        except QuotaAbortError as exc:
            message = str(exc)
            try:
                with open(log_path, "x", encoding="utf-8") as handle:
                    handle.write(message + "\n")
            except OSError as exc2:
                raise UsageError(
                    f"cannot open --log-path ({log_path}): {exc2}"
                )
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
            try:
                gate_dir = prepare_gate_config_dir(
                    default_gate_config_dir(),
                    Path.home() / ".claude" / CREDENTIALS_NAME,
                    Path.home() / ".claude" / SETTINGS_NAME,
                )
            except OSError as exc:
                raise UsageError(f"cannot prepare gate config dir: {exc}")
            env["CLAUDE_CONFIG_DIR"] = str(gate_dir)
            # Route isolation is only real if the child also loses provider
            # routing vars inherited from os.environ / --env-file.
            strip_provider_env(env)
    elif arm == "codex":
        cli = [
            "codex"
        ] + build_codex_args(model, prompt, is_inside_git_repo(workdir), args.extra_arg)
    else:
        cli = ["muse"] + build_muse_args(model, prompt, args.extra_arg)

    exit_code = None
    # Exclusive create: "x" fails if the log appeared since the precondition
    # check above (FileExistsError is an OSError → clean exit 2).
    try:
        log_handle = open(log_path, "x", encoding="utf-8")
    except OSError as exc:
        raise UsageError(f"cannot open --log-path ({log_path}): {exc}")
    try:
        with log_handle:
            proc = subprocess.run(
                cli,
                cwd=str(workdir),
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )
        exit_code = proc.returncode
    except OSError as exc:
        # The CLI itself failed to spawn: map to the CLI-failed exit code so
        # the record never carries a null exit_code for a dispatch that did
        # not run.
        exit_code = EXIT_CLI_FAILED
        try:
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write(f"dispatch error: {exc}\n")
        except OSError:
            pass

    ended = datetime.now().astimezone()
    try:
        log_text = log_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise UsageError(f"cannot read back --log-path ({log_path}): {exc}")
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
    except OSError as exc:
        # Belt-and-braces: any precondition-style OSError still maps to a
        # clean exit 2, never a traceback.
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ARGS


if __name__ == "__main__":
    sys.exit(main())
