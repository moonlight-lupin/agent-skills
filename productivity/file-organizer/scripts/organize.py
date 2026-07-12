#!/usr/bin/env python3
"""Scan directories, propose plans, and execute file organization plans."""

from __future__ import annotations

import argparse
import json
import math
import mimetypes
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


MAX_SNIPPET_FILE_SIZE = 50 * 1024 * 1024
DEFAULT_SNIPPET_CHARS = 500
DEFAULT_TOTAL_SNIPPET_BUDGET = 20_000
DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 4096

SYSTEM_PROMPT = (
    "You are a file organization assistant. Given file metadata and content snippets, "
    "propose a clean folder structure with descriptive filenames. Return ONLY a valid "
    'JSON object with "moves" and "folders_to_create" arrays. Every destination path '
    "must start with the source_dir. Do not include markdown formatting or explanations."
)

PROVIDER_DEFAULTS = {
    "deepseek": {
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1/chat/completions",
        "api_key_env": "DEEPSEEK_API_KEY",
    },
    "openai": {
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1/chat/completions",
        "api_key_env": "OPENAI_API_KEY",
    },
    "openrouter": {
        "model": "deepseek/deepseek-chat",
        "base_url": "https://openrouter.ai/api/v1/chat/completions",
        "api_key_env": "OPENROUTER_API_KEY",
    },
    "ollama": {
        "model": "llama3.2:3b",
        "base_url": "http://localhost:11434/api/chat",
        "api_key_env": None,
    },
}

TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".py",
    ".js",
    ".ts",
    ".json",
    ".csv",
    ".yaml",
    ".yml",
    ".xml",
    ".html",
    ".htm",
    ".css",
    ".log",
    ".ini",
    ".toml",
}
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}
OFFICE_EXTENSIONS = {".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt", ".odt", ".ods", ".odp"}
ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".tgz", ".rar", ".7z"}


def detect_type(path: Path) -> str:
    """Return a coarse type label based on file extension."""

    ext = path.suffix.lower()
    if ext in TEXT_EXTENSIONS:
        return "text"
    if ext in PDF_EXTENSIONS:
        return "pdf"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in OFFICE_EXTENSIONS:
        return "office"
    if ext in ARCHIVE_EXTENSIONS or "".join(path.suffixes[-2:]).lower() == ".tar.gz":
        return "archive"
    return "other"


def is_hidden(path: Path, root: Path) -> bool:
    """Return True when a path below root contains a hidden component."""

    try:
        relative_parts = path.relative_to(root).parts
    except ValueError:
        relative_parts = path.parts
    return any(part.startswith(".") for part in relative_parts)


def iter_files(root: Path, depth: int | None, include_hidden: bool) -> Iterable[Path]:
    """Yield files under root up to the requested depth."""

    root = root.resolve()
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        rel_parts = current_path.relative_to(root).parts
        current_depth = 0 if rel_parts == (".",) else len(rel_parts)

        if not include_hidden:
            dirs[:] = [name for name in dirs if not name.startswith(".")]
            files = [name for name in files if not name.startswith(".")]

        if depth is not None and current_depth >= depth:
            dirs[:] = []

        for name in sorted(files):
            file_path = current_path / name
            if include_hidden or not is_hidden(file_path, root):
                yield file_path


def read_text_snippet(path: Path, max_chars: int) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return handle.read(max_chars)


def read_pdf_snippet(path: Path, max_chars: int) -> str:
    try:
        import fitz  # type: ignore
    except ImportError:
        return "PDF document"

    try:
        document = fitz.open(str(path))
        try:
            if len(document) == 0:
                return "PDF document with no pages"
            return document[0].get_text()[:max_chars] or "PDF document"
        finally:
            document.close()
    except Exception as exc:  # pragma: no cover - depends on optional parser internals
        return f"PDF document (text extraction failed: {exc})"


def read_image_snippet(path: Path) -> str:
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return "Image file"

    try:
        with Image.open(path) as image:
            parts = [f"Image dimensions: {image.width}x{image.height}"]
            try:
                exif = image.getexif()
                exif_date = exif.get(36867) or exif.get(306) if exif else None
                if exif_date:
                    parts.append(f"EXIF date: {exif_date}")
            except Exception:
                pass
            return "; ".join(parts)
    except Exception as exc:  # pragma: no cover - depends on optional parser internals
        return f"Image file (metadata read failed: {exc})"


def read_audio_snippet(path: Path) -> str:
    try:
        from mutagen import File as MutagenFile  # type: ignore
    except ImportError:
        return "Audio file"

    try:
        audio = MutagenFile(path)
        if audio is None:
            return "Audio file"
        parts = ["Audio file"]
        info = getattr(audio, "info", None)
        length = getattr(info, "length", None)
        if length is not None:
            parts.append(f"duration: {length:.1f}s")
        tags = getattr(audio, "tags", None)
        if tags:
            tag_parts: list[str] = []
            for key in ("title", "artist", "album", "TIT2", "TPE1", "TALB"):
                if key in tags:
                    tag_parts.append(f"{key}: {tags[key]}")
                if len(tag_parts) >= 3:
                    break
            if tag_parts:
                parts.append("tags: " + ", ".join(tag_parts))
        return "; ".join(parts)
    except Exception as exc:  # pragma: no cover - depends on optional parser internals
        return f"Audio file (metadata read failed: {exc})"


def read_archive_snippet(path: Path) -> str:
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                return f"Archive, {len(archive.infolist())} files"
        if tarfile.is_tarfile(path):
            with tarfile.open(path) as archive:
                return f"Archive, {len(archive.getmembers())} files"
    except Exception as exc:
        return f"Archive (metadata read failed: {exc})"
    return "Archive"


def build_snippet(path: Path, file_type: str, max_chars: int, size: int) -> str | None:
    """Build a snippet or lightweight metadata string for a file."""

    if size > MAX_SNIPPET_FILE_SIZE and file_type in {"text", "pdf"}:
        return None
    if file_type == "text":
        return read_text_snippet(path, max_chars)
    if file_type == "pdf":
        return read_pdf_snippet(path, max_chars)
    if file_type == "image":
        return read_image_snippet(path)
    if file_type == "audio":
        return read_audio_snippet(path)
    if file_type == "office":
        return "Office document"
    if file_type == "archive":
        return read_archive_snippet(path)
    mime_type, _ = mimetypes.guess_type(path.name)
    return mime_type or f"{path.suffix.lower().lstrip('.') or 'Unknown'} file"


def file_entry(path: Path, root: Path, max_chars: int, remaining_budget: int) -> tuple[dict[str, Any], int]:
    """Return a scan entry and the updated remaining snippet budget."""

    stat = path.stat()
    file_type = detect_type(path)
    entry: dict[str, Any] = {
        "path": str(path.resolve()),
        "relative_path": str(path.resolve().relative_to(root.resolve())),
        "name": path.name,
        "size": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "type": file_type,
        "mime": mimetypes.guess_type(path.name)[0],
        "snippet": None,
    }

    if remaining_budget <= 0:
        entry["snippet_omitted"] = "total snippet budget exhausted"
        return entry, remaining_budget

    try:
        snippet = build_snippet(path, file_type, min(max_chars, remaining_budget), stat.st_size)
    except Exception as exc:
        entry["error"] = str(exc)
        return entry, remaining_budget

    if snippet:
        snippet = snippet[:remaining_budget]
        entry["snippet"] = snippet
        remaining_budget -= len(snippet)
    elif stat.st_size > MAX_SNIPPET_FILE_SIZE and file_type in {"text", "pdf"}:
        entry["snippet_omitted"] = "file exceeds 50MB snippet limit"
    return entry, remaining_budget


def scan_directory(
    path: str | Path,
    depth: int | None = None,
    max_snippet_chars: int = DEFAULT_SNIPPET_CHARS,
    include_hidden: bool = False,
    total_snippet_budget: int = DEFAULT_TOTAL_SNIPPET_BUDGET,
) -> list[dict[str, Any]]:
    """Scan a directory and return JSON-serializable file metadata."""

    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"scan path is not a directory: {root}")

    entries: list[dict[str, Any]] = []
    remaining_budget = max(0, total_snippet_budget)
    for file_path in iter_files(root, depth, include_hidden):
        try:
            entry, remaining_budget = file_entry(file_path, root, max_snippet_chars, remaining_budget)
        except Exception as exc:
            entry = {
                "path": str(file_path.resolve()),
                "relative_path": str(file_path.resolve().relative_to(root)),
                "name": file_path.name,
                "type": detect_type(file_path),
                "snippet": None,
                "error": str(exc),
            }
        entries.append(entry)
    return entries


def compress_scan(scan_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only fields needed by the proposal prompt."""

    keep_fields = ("path", "name", "type", "snippet", "size", "mtime")
    compressed: list[dict[str, Any]] = []
    for entry in scan_entries:
        item = {}
        for key in keep_fields:
            if key == "snippet" and entry.get(key) is None:
                continue
            if key in entry:
                item[key] = entry[key]
        compressed.append(item)
    return compressed


def build_propose_prompts(source_dir: str | Path, scan_entries: list[dict[str, Any]]) -> tuple[str, str]:
    """Build the system and user prompts for the proposal LLM."""

    compressed_json = json.dumps(compress_scan(scan_entries), indent=2, ensure_ascii=False)
    user_prompt = (
        f"Source directory: {source_dir}. Organize these files. Return JSON only.\n\n"
        f"Compressed scan JSON:\n{compressed_json}"
    )
    return SYSTEM_PROMPT, user_prompt


def load_env_file(path: str | Path) -> dict[str, str]:
    """Parse a simple KEY=VALUE env file."""

    env_path = Path(path).expanduser()
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    with env_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                values[key] = value
    return values


def hermes_env_values() -> dict[str, str]:
    return load_env_file(Path.home() / ".hermes" / ".env")


def resolve_provider(provider: str | None, env: dict[str, str] | None = None) -> str:
    """Resolve provider from CLI flag, environment, Hermes env file, then fail."""

    if provider:
        return provider

    current_env = env if env is not None else os.environ
    file_env = hermes_env_values()
    merged = {**file_env, **current_env}
    if merged.get("DEEPSEEK_API_KEY"):
        return "deepseek"
    if merged.get("OPENAI_API_KEY"):
        return "openai"
    if merged.get("OPENROUTER_API_KEY"):
        return "openrouter"
    if merged.get("OLLAMA_HOST"):
        return "ollama"
    raise ValueError("no LLM provider available; set --provider or an API/provider environment variable")


def resolve_api_key(provider: str, api_key: str | None, env: dict[str, str] | None = None) -> str | None:
    """Resolve API key from CLI flag, environment, then ~/.hermes/.env."""

    if api_key:
        return api_key

    env_name = PROVIDER_DEFAULTS[provider]["api_key_env"]
    if env_name is None:
        return None

    current_env = env if env is not None else os.environ
    if current_env.get(env_name):
        return current_env[env_name]
    return hermes_env_values().get(env_name)


def strip_markdown_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def extract_json_response(text: str) -> dict[str, Any]:
    """Extract a JSON object from a plain or markdown-wrapped LLM response."""

    candidate = strip_markdown_code_fence(text)
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("LLM response did not contain a JSON object") from None
        payload = json.loads(candidate[start : end + 1])

    if not isinstance(payload, dict):
        raise ValueError("LLM response JSON must be an object")
    return payload


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Validate the proposal plan schema."""

    if not isinstance(plan.get("moves"), list):
        raise ValueError("plan must include a moves array")
    if not isinstance(plan.get("folders_to_create"), list):
        raise ValueError("plan must include a folders_to_create array")
    for index, move in enumerate(plan["moves"]):
        if not isinstance(move, dict):
            raise ValueError(f"move {index} must be an object")
        if not isinstance(move.get("source"), str) or not isinstance(move.get("destination"), str):
            raise ValueError(f"move {index} must include source and destination strings")
    return plan


def llm_response_content(provider: str, response_payload: dict[str, Any]) -> str:
    if provider == "ollama":
        content = response_payload.get("message", {}).get("content")
    else:
        choices = response_payload.get("choices")
        content = choices[0].get("message", {}).get("content") if choices else None
    if not isinstance(content, str):
        raise ValueError("LLM API response did not include message content")
    return content


def call_llm_api(
    provider: str,
    model: str,
    base_url: str,
    system_prompt: str,
    user_prompt: str,
    api_key: str | None,
    temperature: float,
    max_tokens: int,
) -> str:
    """Call the selected LLM API using urllib only."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    if provider == "ollama":
        body: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
    else:
        if not api_key:
            raise ValueError(f"{provider} requires an API key")
        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(
        base_url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM API request failed: {exc.reason}") from exc

    return llm_response_content(provider, json.loads(raw))


def propose_plan(
    scan_path: str | Path,
    source_dir: str | Path,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> dict[str, Any]:
    with Path(scan_path).expanduser().open("r", encoding="utf-8") as handle:
        scan_entries = json.load(handle)
    if not isinstance(scan_entries, list):
        raise ValueError("scan JSON must be an array")

    resolved_provider = resolve_provider(provider)
    if resolved_provider not in PROVIDER_DEFAULTS:
        raise ValueError(f"unsupported provider: {resolved_provider}")
    defaults = PROVIDER_DEFAULTS[resolved_provider]
    resolved_model = model or str(defaults["model"])
    resolved_base_url = base_url or str(defaults["base_url"])
    resolved_api_key = resolve_api_key(resolved_provider, api_key)

    system_prompt, user_prompt = build_propose_prompts(source_dir, scan_entries)
    content = call_llm_api(
        resolved_provider,
        resolved_model,
        resolved_base_url,
        system_prompt,
        user_prompt,
        resolved_api_key,
        temperature,
        max_tokens,
    )
    return validate_plan(extract_json_response(content))


def load_plan(plan_path: str | Path) -> dict[str, Any]:
    with Path(plan_path).expanduser().open("r", encoding="utf-8") as handle:
        plan = json.load(handle)
    if not isinstance(plan, dict):
        raise ValueError("plan must be a JSON object")
    if not isinstance(plan.get("moves", []), list):
        raise ValueError("plan moves must be a list")
    if not isinstance(plan.get("folders_to_create", []), list):
        raise ValueError("plan folders_to_create must be a list")
    return plan


def error_record(source: Path | None, destination: Path | None, message: str) -> dict[str, str]:
    record: dict[str, str] = {"error": message}
    if source is not None:
        record["source"] = str(source)
    if destination is not None:
        record["destination"] = str(destination)
    return record


def execute_plan(plan_path: str | Path, chunk_size: int = 10, dry_run: bool = False) -> dict[str, Any]:
    """Execute a move plan, returning a summary dictionary."""

    if chunk_size < 1:
        raise ValueError("chunk-size must be at least 1")

    plan = load_plan(plan_path)
    summary: dict[str, Any] = {
        "moved": 0,
        "failed": 0,
        "skipped": 0,
        "dry_run": dry_run,
        "errors": [],
    }

    for folder in plan.get("folders_to_create", []):
        folder_path = Path(folder).expanduser()
        try:
            if dry_run:
                print(f"[dry-run] create folder {folder_path}", file=sys.stderr)
            else:
                folder_path.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            summary["failed"] += 1
            summary["errors"].append(error_record(None, folder_path, f"create folder failed: {exc}"))

    moves = plan.get("moves", [])
    total_chunks = math.ceil(len(moves) / chunk_size) if moves else 0
    for chunk_index, start in enumerate(range(0, len(moves), chunk_size), start=1):
        chunk = moves[start : start + chunk_size]
        before_moved = summary["moved"]
        before_failed = summary["failed"]
        before_skipped = summary["skipped"]

        for move in chunk:
            source = Path(str(move.get("source", ""))).expanduser()
            destination = Path(str(move.get("destination", ""))).expanduser()
            try:
                if not source.exists():
                    summary["failed"] += 1
                    summary["errors"].append(error_record(source, destination, "source does not exist"))
                    continue
                if destination.exists():
                    summary["skipped"] += 1
                    summary["errors"].append(error_record(source, destination, "destination already exists"))
                    continue
                if dry_run:
                    print(f"[dry-run] move {source} -> {destination}", file=sys.stderr)
                    summary["skipped"] += 1
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(destination))
                summary["moved"] += 1
            except Exception as exc:
                summary["failed"] += 1
                summary["errors"].append(error_record(source, destination, str(exc)))

        moved_delta = summary["moved"] - before_moved
        failed_delta = summary["failed"] - before_failed
        skipped_delta = summary["skipped"] - before_skipped
        print(
            f"[chunk {chunk_index}/{total_chunks}] moved {moved_delta}, "
            f"failed {failed_delta}, skipped {skipped_delta}",
            file=sys.stderr,
        )

    return summary


def run_self_test() -> int:
    """Run the local unittest suite for this script."""

    test_path = Path(__file__).with_name("test_organize.py")
    command = [sys.executable, "-m", "unittest", test_path.stem]
    return subprocess.run(command, cwd=test_path.parent).returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan directories and execute organization plans.")
    parser.add_argument("--self-test", action="store_true", help="run the bundled test suite and exit")
    subparsers = parser.add_subparsers(dest="command")

    scan = subparsers.add_parser("scan", help="scan a directory and output JSON metadata")
    scan.add_argument("--path", required=True, help="directory to scan")
    scan.add_argument("--depth", type=int, default=None, help="maximum directory depth to scan")
    scan.add_argument("--max-snippet-chars", type=int, default=DEFAULT_SNIPPET_CHARS)
    scan.add_argument("--include-hidden", action="store_true", help="include hidden files and folders")
    scan.add_argument("--snippet-budget", type=int, default=DEFAULT_TOTAL_SNIPPET_BUDGET)

    execute = subparsers.add_parser("execute", help="execute a confirmed move plan")
    execute.add_argument("--plan", required=True, help="path to plan JSON")
    execute.add_argument("--chunk-size", type=int, default=10)
    execute.add_argument("--dry-run", action="store_true", help="preview without filesystem changes")

    propose = subparsers.add_parser("propose", help="call an LLM to propose an organization plan")
    propose.add_argument("--scan", required=True, help="path to scan JSON")
    propose.add_argument("--source-dir", required=True, help="source directory all destinations must stay under")
    propose.add_argument("--provider", choices=sorted(PROVIDER_DEFAULTS), default=None)
    propose.add_argument("--model", default=None, help="model id")
    propose.add_argument("--api-key", default=None)
    propose.add_argument("--base-url", default=None)
    propose.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    propose.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    if args.command == "scan":
        entries = scan_directory(
            args.path,
            depth=args.depth,
            max_snippet_chars=args.max_snippet_chars,
            include_hidden=args.include_hidden,
            total_snippet_budget=args.snippet_budget,
        )
        json.dump(entries, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    if args.command == "execute":
        summary = execute_plan(args.plan, chunk_size=args.chunk_size, dry_run=args.dry_run)
        json.dump(summary, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    if args.command == "propose":
        try:
            plan = propose_plan(
                args.scan,
                args.source_dir,
                provider=args.provider,
                model=args.model,
                api_key=args.api_key,
                base_url=args.base_url,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )
        except Exception as exc:
            print(f"propose failed: {exc}", file=sys.stderr)
            return 1
        json.dump(plan, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
